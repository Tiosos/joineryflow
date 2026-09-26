"""SQL queries for the estimating module — sub-project #9a.

Routes own the transaction boundary; queries flush only (audit/edit-log
writes use db.flush() inline). Convert-to-Project flushes at the end so the
route's commit lands the whole transaction atomically.

Workspace isolation: every query joins through `customer.workspace_id` or
`estimate.workspace_id`. Cross-workspace reads return None (route → 404).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..edit_log import write_edit_log


STAGE_KEYS: tuple[str, ...] = (
    "REQ", "SM", "LISTED", "DOWN", "CNC", "EDGED",
    "PAINTED", "MADE", "DEL", "INST",
)


# ============================================================================
# Material catalog snapshot resolvers
# ============================================================================

_PART_CATALOG_BY_TYPE: dict[str, tuple[str, str, str, str, str]] = {
    "BOARD":    ("board_materials",    "material_id", "sku", "default_supplier", "cost_per_sheet"),
    "CUSTOM":   ("custom_made",        "material_id", "sku", "default_supplier", "cost"),
    "BENCHTOP": ("benchtop_materials", "material_id", "sku", "default_supplier", "cost_per_slab"),
}

_HW_CATALOG_BY_TYPE: dict[str, tuple[str, str, str, str, str]] = {
    "HARDWARE":  ("hardware_materials", "material_id", "sku", "default_supplier", "cost_per_unit"),
    "APPLIANCE": ("appliances",         "material_id", "sku", "default_supplier", "cost_per_unit"),
}


def _resolve_part_snapshot(
    db: Session, *, workspace_id: int, material_type: str, material_id: int
) -> dict | None:
    cfg = _PART_CATALOG_BY_TYPE.get(material_type)
    if cfg is None:
        return None
    table, id_col, sku_col, supplier_col, cost_col = cfg
    sql = text(
        f"""
        SELECT {sku_col} AS sku, description, {supplier_col} AS supplier,
               {cost_col} AS cost
          FROM {table}
         WHERE {id_col} = :mid AND workspace_id = :w
           AND archived_at IS NULL
        """
    )
    row = db.execute(sql, {"mid": material_id, "w": workspace_id}).mappings().first()
    return dict(row) if row else None


def _resolve_hardware_snapshot(
    db: Session, *, workspace_id: int, material_type: str, material_id: int
) -> dict | None:
    cfg = _HW_CATALOG_BY_TYPE.get(material_type)
    if cfg is None:
        return None
    table, id_col, sku_col, supplier_col, cost_col = cfg
    sql = text(
        f"""
        SELECT {sku_col} AS sku, description, {supplier_col} AS supplier,
               {cost_col} AS cost
          FROM {table}
         WHERE {id_col} = :mid AND workspace_id = :w
           AND archived_at IS NULL
        """
    )
    row = db.execute(sql, {"mid": material_id, "w": workspace_id}).mappings().first()
    return dict(row) if row else None


# ============================================================================
# Customer CRUD
# ============================================================================

def list_customers(
    db: Session, *, workspace_id: int, q: str | None = None,
    include_archived: bool = False,
) -> list[dict]:
    where = ["workspace_id = :w"]
    params: dict = {"w": workspace_id}
    if not include_archived:
        where.append("archived_at IS NULL")
    if q:
        where.append("(name ILIKE :q OR email ILIKE :q OR phone ILIKE :q)")
        params["q"] = f"%{q}%"
    sql = text(
        f"""
        SELECT customer_id, name, email, phone, billing_address,
               abn, notes, archived_at, created_at
          FROM customer
         WHERE {' AND '.join(where)}
         ORDER BY name
        """
    )
    return [dict(r) for r in db.execute(sql, params).mappings()]


def get_customer(
    db: Session, *, customer_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT customer_id, name, email, phone, billing_address,
                   abn, notes, archived_at, created_at
              FROM customer
             WHERE customer_id = :c AND workspace_id = :w
            """
        ),
        {"c": customer_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def create_customer(
    db: Session, *, workspace_id: int, actor_id: int, payload: dict
) -> int:
    sql = text(
        """
        INSERT INTO customer(
            workspace_id, name, email, phone, billing_address, abn, notes,
            created_by
        )
        VALUES (:w, :name, :email, :phone, :billing, :abn, :notes, :a)
        RETURNING customer_id
        """
    )
    cid = db.execute(
        sql,
        {
            "w": workspace_id,
            "name": payload["name"],
            "email": payload.get("email"),
            "phone": payload.get("phone"),
            "billing": payload.get("billing_address"),
            "abn": payload.get("abn"),
            "notes": payload.get("notes"),
            "a": actor_id,
        },
    ).scalar()
    db.flush()
    return int(cid)


def patch_customer(
    db: Session, *, customer_id: int, workspace_id: int,
    actor_id: int, fields: dict[str, Any],
) -> dict | None:
    if not fields:
        return get_customer(db, customer_id=customer_id, workspace_id=workspace_id)
    columns = {
        "name": "name", "email": "email", "phone": "phone",
        "billing_address": "billing_address", "abn": "abn", "notes": "notes",
    }
    set_clauses = ", ".join(
        f"{columns[k]} = :{k}" for k in fields if k in columns
    )
    if not set_clauses:
        return get_customer(db, customer_id=customer_id, workspace_id=workspace_id)
    set_clauses += ", updated_at = now()"
    sql = text(
        f"""
        UPDATE customer
           SET {set_clauses}
         WHERE customer_id = :cid AND workspace_id = :w
        """
    )
    result = db.execute(sql, {**fields, "cid": customer_id, "w": workspace_id})
    if result.rowcount == 0:
        return None
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="customer.update", target=str(customer_id),
        payload={"fields": list(fields.keys())},
    )
    return get_customer(db, customer_id=customer_id, workspace_id=workspace_id)


def archive_customer(
    db: Session, *, customer_id: int, workspace_id: int, actor_id: int
) -> dict | None:
    cur = get_customer(db, customer_id=customer_id, workspace_id=workspace_id)
    if cur is None:
        return None
    if cur["archived_at"] is not None:
        raise ValueError("ALREADY_ARCHIVED")
    db.execute(
        text(
            """
            UPDATE customer
               SET archived_at = now(), archived_by = :a, updated_at = now()
             WHERE customer_id = :cid AND workspace_id = :w
            """
        ),
        {"a": actor_id, "cid": customer_id, "w": workspace_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="customer.archive", target=str(customer_id),
        payload={},
    )
    return get_customer(db, customer_id=customer_id, workspace_id=workspace_id)


# ============================================================================
# Estimate header CRUD
# ============================================================================

def _next_estimate_no(db: Session, *, workspace_id: int) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"EST-{year}-"
    row = db.execute(
        text(
            """
            SELECT estimate_no
              FROM estimate
             WHERE workspace_id = :w
               AND estimate_no LIKE :pfx
             ORDER BY estimate_no DESC
             LIMIT 1
            """
        ),
        {"w": workspace_id, "pfx": prefix + "%"},
    ).scalar()
    next_n = 1
    if row is not None:
        try:
            next_n = int(str(row).split("-")[-1]) + 1
        except (ValueError, IndexError):
            next_n = 1
    return f"{prefix}{next_n:04d}"


def list_estimates(
    db: Session, *, workspace_id: int, customer_id: int | None = None,
    status: str | None = None, q: str | None = None,
    subtab: str = "active",
) -> list[dict]:
    where = ["e.workspace_id = :w"]
    params: dict = {"w": workspace_id}
    if customer_id is not None:
        where.append("e.customer_id = :cid")
        params["cid"] = customer_id
    if q:
        where.append(
            "(e.title ILIKE :q OR e.estimate_no ILIKE :q OR c.name ILIKE :q)"
        )
        params["q"] = f"%{q}%"
    active_set = "('draft','sent','accepted')"
    archive_set = "('rejected','expired','withdrawn')"
    if status:
        where.append("r.status = :st")
        params["st"] = status
    elif subtab == "archive":
        where.append(f"r.status IN {archive_set}")
    else:
        where.append(f"r.status IN {active_set}")

    sql = text(
        f"""
        SELECT
            e.estimate_id,
            e.estimate_no,
            e.title,
            e.site_address,
            e.customer_id,
            c.name AS customer_name,
            e.current_revision_id,
            r.rev_no    AS current_rev_no,
            r.status    AS current_status,
            r.total_inc_gst AS current_total_inc_gst,
            r.converted_project_id,
            e.created_at,
            e.updated_at
          FROM estimate e
          JOIN customer c ON c.customer_id = e.customer_id
          LEFT JOIN estimate_revision r
            ON r.revision_id = e.current_revision_id
         WHERE {' AND '.join(where)}
         ORDER BY e.estimate_no DESC
        """
    )
    return [dict(r) for r in db.execute(sql, params).mappings()]


def get_estimate_summary(
    db: Session, *, estimate_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT
                e.estimate_id, e.workspace_id, e.estimate_no, e.title,
                e.site_address, e.customer_id, c.name AS customer_name,
                e.current_revision_id, e.created_at, e.updated_at
              FROM estimate e
              JOIN customer c ON c.customer_id = e.customer_id
             WHERE e.estimate_id = :eid AND e.workspace_id = :w
            """
        ),
        {"eid": estimate_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def create_estimate(
    db: Session, *, workspace_id: int, actor_id: int, payload: dict
) -> int:
    cust = get_customer(
        db, customer_id=payload["customer_id"], workspace_id=workspace_id
    )
    if cust is None:
        raise ValueError("CUSTOMER_NOT_FOUND")
    if cust.get("archived_at") is not None:
        raise ValueError("CUSTOMER_ARCHIVED")

    est_no = payload.get("estimate_no") or _next_estimate_no(
        db, workspace_id=workspace_id
    )
    eid = db.execute(
        text(
            """
            INSERT INTO estimate(
                workspace_id, customer_id, estimate_no, title, site_address,
                created_by
            )
            VALUES (:w, :cid, :no, :title, :site, :a)
            RETURNING estimate_id
            """
        ),
        {
            "w": workspace_id,
            "cid": payload["customer_id"],
            "no": est_no,
            "title": payload["title"],
            "site": payload.get("site_address"),
            "a": actor_id,
        },
    ).scalar()
    rid = _insert_blank_revision(
        db, estimate_id=eid, rev_no=1, actor_id=actor_id
    )
    db.execute(
        text(
            """
            UPDATE estimate
               SET current_revision_id = :rid
             WHERE estimate_id = :eid
            """
        ),
        {"rid": rid, "eid": eid},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.create", target=str(eid),
        payload={"estimate_no": est_no, "customer_id": payload["customer_id"]},
    )
    db.flush()
    return int(eid)


def patch_estimate(
    db: Session, *, estimate_id: int, workspace_id: int,
    actor_id: int, fields: dict[str, Any],
) -> dict | None:
    columns = {"customer_id": "customer_id", "title": "title",
               "site_address": "site_address"}
    set_clauses = ", ".join(
        f"{columns[k]} = :{k}" for k in fields if k in columns
    )
    if not set_clauses:
        return get_estimate_summary(
            db, estimate_id=estimate_id, workspace_id=workspace_id
        )
    set_clauses += ", updated_at = now()"
    if "customer_id" in fields:
        cust = get_customer(
            db, customer_id=fields["customer_id"], workspace_id=workspace_id
        )
        if cust is None:
            raise ValueError("CUSTOMER_NOT_FOUND")
        if cust.get("archived_at") is not None:
            raise ValueError("CUSTOMER_ARCHIVED")

    result = db.execute(
        text(
            f"""
            UPDATE estimate
               SET {set_clauses}
             WHERE estimate_id = :eid AND workspace_id = :w
            """
        ),
        {**fields, "eid": estimate_id, "w": workspace_id},
    )
    if result.rowcount == 0:
        return None
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.update", target=str(estimate_id),
        payload={"fields": list(fields.keys())},
    )
    return get_estimate_summary(
        db, estimate_id=estimate_id, workspace_id=workspace_id
    )


# ============================================================================
# Revision CRUD + status transitions
# ============================================================================

def _insert_blank_revision(
    db: Session, *, estimate_id: int, rev_no: int, actor_id: int
) -> int:
    rid = db.execute(
        text(
            """
            INSERT INTO estimate_revision(
                estimate_id, rev_no, status, markup_pct, gst_pct, created_by
            )
            VALUES (:eid, :rn, 'draft', 0, 10.00, :a)
            RETURNING revision_id
            """
        ),
        {"eid": estimate_id, "rn": rev_no, "a": actor_id},
    ).scalar()
    db.flush()
    return int(rid)


def get_revision(
    db: Session, *, revision_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT r.*, e.workspace_id AS _wid, e.estimate_no, e.title,
                   e.customer_id, e.site_address
              FROM estimate_revision r
              JOIN estimate e ON e.estimate_id = r.estimate_id
             WHERE r.revision_id = :rid AND e.workspace_id = :w
            """
        ),
        {"rid": revision_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def lock_revision_for_update(
    db: Session, *, revision_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT r.*, e.workspace_id AS _wid
              FROM estimate_revision r
              JOIN estimate e ON e.estimate_id = r.estimate_id
             WHERE r.revision_id = :rid AND e.workspace_id = :w
             FOR UPDATE OF r
            """
        ),
        {"rid": revision_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def patch_revision(
    db: Session, *, revision_id: int, workspace_id: int,
    actor_id: int, fields: dict[str, Any],
) -> dict | None:
    cur = get_revision(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if cur is None:
        return None
    draft_only_keys = {"markup_pct", "gst_pct", "terms_text"}
    if (set(fields.keys()) & draft_only_keys) and cur["status"] != "draft":
        raise ValueError("REVISION_LOCKED")
    if "expires_at" in fields and cur["status"] != "sent":
        raise ValueError("NOT_SENT")
    columns = {
        "markup_pct": "markup_pct", "gst_pct": "gst_pct",
        "terms_text": "terms_text", "expires_at": "expires_at",
    }
    set_clauses = ", ".join(
        f"{columns[k]} = :{k}" for k in fields if k in columns
    )
    if not set_clauses:
        return cur
    db.execute(
        text(
            f"""
            UPDATE estimate_revision
               SET {set_clauses}
             WHERE revision_id = :rid
            """
        ),
        {**fields, "rid": revision_id},
    )
    if cur["status"] == "draft":
        _recompute_revision_totals(db, revision_id=revision_id)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.update", target=str(revision_id),
        payload={"fields": list(fields.keys())},
    )
    return get_revision(
        db, revision_id=revision_id, workspace_id=workspace_id
    )


def revise_estimate(
    db: Session, *, estimate_id: int, workspace_id: int, actor_id: int
) -> int:
    cur_summary = get_estimate_summary(
        db, estimate_id=estimate_id, workspace_id=workspace_id
    )
    if cur_summary is None:
        raise ValueError("NOT_FOUND")
    existing_draft = db.execute(
        text(
            """
            SELECT revision_id FROM estimate_revision
             WHERE estimate_id = :eid AND status = 'draft'
            """
        ),
        {"eid": estimate_id},
    ).scalar()
    if existing_draft is not None:
        raise ValueError("DRAFT_EXISTS")
    source_rid = cur_summary.get("current_revision_id")
    if source_rid is None:
        raise ValueError("NO_SOURCE_REVISION")
    source = db.execute(
        text(
            """
            SELECT * FROM estimate_revision WHERE revision_id = :rid
            """
        ),
        {"rid": source_rid},
    ).mappings().first()
    if source is None:
        raise ValueError("NO_SOURCE_REVISION")
    max_rev_no = db.execute(
        text(
            """
            SELECT MAX(rev_no) FROM estimate_revision WHERE estimate_id = :eid
            """
        ),
        {"eid": estimate_id},
    ).scalar() or 0
    new_rn = int(max_rev_no) + 1
    new_rid = db.execute(
        text(
            """
            INSERT INTO estimate_revision(
                estimate_id, rev_no, status, markup_pct, gst_pct, terms_text,
                created_by
            )
            VALUES (:eid, :rn, 'draft', :markup, :gst, :terms, :a)
            RETURNING revision_id
            """
        ),
        {
            "eid": estimate_id, "rn": new_rn,
            "markup": source["markup_pct"],
            "gst": source["gst_pct"],
            "terms": source["terms_text"],
            "a": actor_id,
        },
    ).scalar()
    _clone_lines(db, src_revision_id=source_rid, dst_revision_id=new_rid)
    db.execute(
        text(
            """
            UPDATE estimate
               SET current_revision_id = :rid, updated_at = now()
             WHERE estimate_id = :eid
            """
        ),
        {"rid": new_rid, "eid": estimate_id},
    )
    _recompute_revision_totals(db, revision_id=new_rid)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.revise", target=str(estimate_id),
        payload={
            "source_revision_id": int(source_rid),
            "new_revision_id": int(new_rid),
            "rev_no": new_rn,
        },
    )
    db.flush()
    return int(new_rid)


def _clone_lines(
    db: Session, *, src_revision_id: int, dst_revision_id: int
) -> None:
    src_lines = db.execute(
        text(
            """
            SELECT line_id, seq, description, qty, unit, has_breakdown,
                   material_cost, labour_cost, unit_sell_override, notes
              FROM estimate_line
             WHERE revision_id = :rid
             ORDER BY seq, line_id
            """
        ),
        {"rid": src_revision_id},
    ).mappings().all()

    for line in src_lines:
        new_line_id = db.execute(
            text(
                """
                INSERT INTO estimate_line(
                    revision_id, seq, description, qty, unit, has_breakdown,
                    material_cost, labour_cost, unit_sell_override, notes
                )
                VALUES (:rid, :seq, :d, :q, :u, :hb, :mc, :lc, :uso, :n)
                RETURNING line_id
                """
            ),
            {
                "rid": dst_revision_id,
                "seq": line["seq"],
                "d": line["description"],
                "q": line["qty"],
                "u": line["unit"],
                "hb": line["has_breakdown"],
                "mc": line["material_cost"],
                "lc": line["labour_cost"],
                "uso": line["unit_sell_override"],
                "n": line["notes"],
            },
        ).scalar()
        db.execute(
            text(
                """
                INSERT INTO estimate_line_part(
                    line_id, material_type, material_id, sku_snapshot,
                    description_snapshot, supplier_snapshot, qty, len_mm,
                    wid_mm, cost_per_unit_snapshot, paint_instruction, comment
                )
                SELECT :nl, material_type, material_id, sku_snapshot,
                       description_snapshot, supplier_snapshot, qty, len_mm,
                       wid_mm, cost_per_unit_snapshot, paint_instruction, comment
                  FROM estimate_line_part
                 WHERE line_id = :ol
                """
            ),
            {"nl": new_line_id, "ol": line["line_id"]},
        )
        db.execute(
            text(
                """
                INSERT INTO estimate_line_hardware(
                    line_id, material_type, material_id, sku_snapshot,
                    description_snapshot, supplier_snapshot, qty,
                    cost_per_unit_snapshot, comment
                )
                SELECT :nl, material_type, material_id, sku_snapshot,
                       description_snapshot, supplier_snapshot, qty,
                       cost_per_unit_snapshot, comment
                  FROM estimate_line_hardware
                 WHERE line_id = :ol
                """
            ),
            {"nl": new_line_id, "ol": line["line_id"]},
        )
        db.execute(
            text(
                """
                INSERT INTO estimate_line_labour(
                    line_id, stage_key, hours, rate_snapshot
                )
                SELECT :nl, stage_key, hours, rate_snapshot
                  FROM estimate_line_labour
                 WHERE line_id = :ol
                """
            ),
            {"nl": new_line_id, "ol": line["line_id"]},
        )


# ============================================================================
# Status transitions
# ============================================================================

_LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "draft":     {"sent", "withdrawn"},
    "sent":      {"accepted", "rejected", "expired", "withdrawn"},
    "accepted":  set(),
    "rejected":  set(),
    "expired":   set(),
    "withdrawn": set(),
}


def transition_revision(
    db: Session, *, revision_id: int, workspace_id: int,
    actor_id: int, target: str, lost_reason: str | None = None,
) -> dict:
    cur = lock_revision_for_update(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if cur is None:
        raise ValueError("NOT_FOUND")
    from_status = cur["status"]
    if target not in _LEGAL_TRANSITIONS.get(from_status, set()):
        raise ValueError(
            json.dumps(
                {"code": "BAD_TRANSITION", "from": from_status, "to": target}
            )
        )
    now = datetime.now(timezone.utc)
    sets = ["status = :tgt"]
    params: dict = {"tgt": target, "rid": revision_id}
    audit_payload: dict = {"from": from_status, "to": target}
    if target == "sent":
        lines = db.execute(
            text(
                """
                SELECT line_id FROM estimate_line WHERE revision_id = :rid
                """
            ),
            {"rid": revision_id},
        ).all()
        if not lines:
            raise ValueError("EMPTY_REVISION")
        rates = db.execute(
            text(
                """
                SELECT stage_key, hourly_rate
                  FROM workspace_labour_rate
                 WHERE workspace_id = :w
                """
            ),
            {"w": workspace_id},
        ).mappings().all()
        rates_json = {r["stage_key"]: float(r["hourly_rate"]) for r in rates}
        sets += [
            "sent_at = :now", "sent_by = :a",
            "locked_at = :now", "locked_by = :a",
            "workspace_stage_rates_snapshot = CAST(:rates AS jsonb)",
        ]
        params["now"] = now
        params["a"] = actor_id
        params["rates"] = json.dumps(rates_json)
        audit_event = "estimate.send"
    elif target == "accepted":
        sets += ["accepted_at = :now"]
        params["now"] = now
        audit_event = "estimate.accept"
    elif target == "rejected":
        sets += ["rejected_at = :now", "lost_reason = :lr"]
        params["now"] = now
        params["lr"] = lost_reason
        audit_event = "estimate.reject"
        audit_payload["lost_reason"] = lost_reason
    elif target == "expired":
        sets += ["lost_reason = :lr"]
        params["lr"] = lost_reason
        audit_event = "estimate.expire"
        audit_payload["lost_reason"] = lost_reason
    elif target == "withdrawn":
        sets += ["lost_reason = :lr"]
        params["lr"] = lost_reason
        audit_event = "estimate.withdraw"
        audit_payload["lost_reason"] = lost_reason
    else:
        raise ValueError(f"unhandled transition target {target!r}")

    db.execute(
        text(
            f"""
            UPDATE estimate_revision
               SET {', '.join(sets)}
             WHERE revision_id = :rid
            """
        ),
        params,
    )
    if target == "sent":
        _recompute_revision_totals(db, revision_id=revision_id)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event=audit_event, target=str(revision_id),
        payload=audit_payload,
    )
    db.flush()
    return get_revision(
        db, revision_id=revision_id, workspace_id=workspace_id
    )


# ============================================================================
# Line CRUD + parts/hardware/labour add/remove
# ============================================================================

def _assert_draft(
    db: Session, *, revision_id: int, workspace_id: int
) -> dict:
    cur = get_revision(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if cur is None:
        raise ValueError("NOT_FOUND")
    if cur["status"] != "draft":
        raise ValueError("REVISION_LOCKED")
    return cur


def _line_in_workspace(
    db: Session, *, line_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT l.*, r.status AS rev_status, r.revision_id,
                   e.workspace_id AS _wid
              FROM estimate_line l
              JOIN estimate_revision r ON r.revision_id = l.revision_id
              JOIN estimate e ON e.estimate_id = r.estimate_id
             WHERE l.line_id = :lid AND e.workspace_id = :w
            """
        ),
        {"lid": line_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def create_line(
    db: Session, *, revision_id: int, workspace_id: int,
    actor_id: int, payload: dict,
) -> int:
    # Locks the revision row for the rest of this transaction, so a second
    # concurrent create_line() on the same revision blocks here instead of
    # reading the same MAX(seq) and inserting a duplicate (the race the
    # company-wide joinery_number_seq / po_number_seq sequences avoid by
    # allocating inside the INSERT — estimate_line has no such sequence,
    # so locking the parent row is the equivalent here).
    cur = lock_revision_for_update(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if cur is None:
        raise ValueError("NOT_FOUND")
    if cur["status"] != "draft":
        raise ValueError("REVISION_LOCKED")
    next_seq = db.execute(
        text(
            """
            SELECT COALESCE(MAX(seq), 0) + 1 FROM estimate_line
             WHERE revision_id = :rid
            """
        ),
        {"rid": revision_id},
    ).scalar()
    lid = db.execute(
        text(
            """
            INSERT INTO estimate_line(
                revision_id, seq, description, qty, unit, notes
            )
            VALUES (:rid, :seq, :d, :q, :u, :n)
            RETURNING line_id
            """
        ),
        {
            "rid": revision_id,
            "seq": int(next_seq),
            "d": payload["description"],
            "q": payload.get("qty", Decimal("1")),
            "u": payload.get("unit", "EA"),
            "n": payload.get("notes"),
        },
    ).scalar()
    _recompute_line_totals(db, line_id=lid)
    _recompute_revision_totals(db, revision_id=revision_id)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.line_add", target=str(lid),
        payload={"revision_id": revision_id, "seq": int(next_seq)},
    )
    db.flush()
    return int(lid)


def patch_line(
    db: Session, *, line_id: int, workspace_id: int,
    actor_id: int, fields: dict[str, Any], clear_unit_sell_override: bool,
) -> dict | None:
    line = _line_in_workspace(db, line_id=line_id, workspace_id=workspace_id)
    if line is None:
        return None
    if line["rev_status"] != "draft":
        raise ValueError("REVISION_LOCKED")

    columns = {
        "description": "description", "qty": "qty", "unit": "unit",
        "unit_sell_override": "unit_sell_override", "notes": "notes",
    }
    set_clauses = [
        f"{columns[k]} = :{k}" for k in fields if k in columns
    ]
    params = {k: v for k, v in fields.items() if k in columns}
    if clear_unit_sell_override:
        set_clauses.append("unit_sell_override = NULL")
    if not set_clauses:
        return line
    set_clauses.append("updated_at = now()")
    db.execute(
        text(
            f"""
            UPDATE estimate_line
               SET {', '.join(set_clauses)}
             WHERE line_id = :lid
            """
        ),
        {**params, "lid": line_id},
    )
    _recompute_line_totals(db, line_id=line_id)
    _recompute_revision_totals(db, revision_id=line["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.line_edit", target=str(line_id),
        payload={"fields": list(fields.keys()),
                 "clear_unit_sell_override": clear_unit_sell_override},
    )
    return _line_in_workspace(
        db, line_id=line_id, workspace_id=workspace_id
    )


def delete_line(
    db: Session, *, line_id: int, workspace_id: int, actor_id: int
) -> bool:
    line = _line_in_workspace(db, line_id=line_id, workspace_id=workspace_id)
    if line is None:
        return False
    if line["rev_status"] != "draft":
        raise ValueError("REVISION_LOCKED")
    db.execute(
        text("DELETE FROM estimate_line WHERE line_id = :lid"),
        {"lid": line_id},
    )
    _recompute_revision_totals(db, revision_id=line["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.line_delete", target=str(line_id),
        payload={"revision_id": line["revision_id"]},
    )
    return True


def reorder_lines(
    db: Session, *, revision_id: int, workspace_id: int,
    actor_id: int, ordered_line_ids: list[int],
) -> None:
    _assert_draft(db, revision_id=revision_id, workspace_id=workspace_id)
    have = {
        int(r) for r in db.execute(
            text(
                "SELECT line_id FROM estimate_line WHERE revision_id = :rid"
            ),
            {"rid": revision_id},
        ).scalars()
    }
    if set(ordered_line_ids) != have:
        raise ValueError("REORDER_SET_MISMATCH")
    for seq, lid in enumerate(ordered_line_ids, start=1):
        db.execute(
            text(
                """
                UPDATE estimate_line SET seq = :s WHERE line_id = :lid
                """
            ),
            {"s": seq, "lid": lid},
        )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.line_reorder", target=str(revision_id),
        payload={"ordered_line_ids": ordered_line_ids},
    )
    db.flush()


def add_part(
    db: Session, *, line_id: int, workspace_id: int, actor_id: int, payload: dict
) -> int:
    line = _line_in_workspace(db, line_id=line_id, workspace_id=workspace_id)
    if line is None:
        raise ValueError("NOT_FOUND")
    if line["rev_status"] != "draft":
        raise ValueError("REVISION_LOCKED")
    snap = _resolve_part_snapshot(
        db, workspace_id=workspace_id,
        material_type=payload["material_type"],
        material_id=payload["material_id"],
    )
    if snap is None:
        raise ValueError("CATALOG_ROW_NOT_FOUND")
    pid = db.execute(
        text(
            """
            INSERT INTO estimate_line_part(
                line_id, material_type, material_id,
                sku_snapshot, description_snapshot, supplier_snapshot,
                qty, len_mm, wid_mm, cost_per_unit_snapshot,
                paint_instruction, comment
            )
            VALUES (:lid, :mt, :mid, :sku, :desc, :sup, :q, :l, :wmm, :c, :pi, :cm)
            RETURNING part_id
            """
        ),
        {
            "lid": line_id,
            "mt": payload["material_type"],
            "mid": payload["material_id"],
            "sku": snap.get("sku"),
            "desc": snap.get("description"),
            "sup": snap.get("supplier"),
            "q": payload.get("qty", Decimal("1")),
            "l": payload.get("len_mm"),
            "wmm": payload.get("wid_mm"),
            "c": snap.get("cost") or 0,
            "pi": payload.get("paint_instruction", "NONE"),
            "cm": payload.get("comment"),
        },
    ).scalar()
    db.execute(
        text(
            "UPDATE estimate_line SET has_breakdown = true WHERE line_id = :lid"
        ),
        {"lid": line_id},
    )
    _recompute_line_totals(db, line_id=line_id)
    _recompute_revision_totals(db, revision_id=line["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.part_add", target=str(pid),
        payload={
            "line_id": line_id,
            "material_type": payload["material_type"],
            "material_id": payload["material_id"],
        },
    )
    db.flush()
    return int(pid)


def remove_part(
    db: Session, *, part_id: int, workspace_id: int, actor_id: int
) -> bool:
    row = db.execute(
        text(
            """
            SELECT p.line_id, l.revision_id, r.status, e.workspace_id AS _wid
              FROM estimate_line_part p
              JOIN estimate_line l ON l.line_id = p.line_id
              JOIN estimate_revision r ON r.revision_id = l.revision_id
              JOIN estimate e ON e.estimate_id = r.estimate_id
             WHERE p.part_id = :pid AND e.workspace_id = :w
            """
        ),
        {"pid": part_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        return False
    if row["status"] != "draft":
        raise ValueError("REVISION_LOCKED")
    db.execute(
        text("DELETE FROM estimate_line_part WHERE part_id = :pid"),
        {"pid": part_id},
    )
    _maybe_clear_has_breakdown(db, line_id=row["line_id"])
    _recompute_line_totals(db, line_id=row["line_id"])
    _recompute_revision_totals(db, revision_id=row["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.part_remove", target=str(part_id),
        payload={"line_id": int(row["line_id"])},
    )
    return True


def patch_part(
    db: Session, *, part_id: int, workspace_id: int, actor_id: int,
    fields: dict[str, Any],
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT p.part_id, p.line_id, l.revision_id, r.status AS rev_status
              FROM estimate_line_part p
              JOIN estimate_line l ON l.line_id = p.line_id
              JOIN estimate_revision r ON r.revision_id = l.revision_id
              JOIN estimate e ON e.estimate_id = r.estimate_id
             WHERE p.part_id = :pid AND e.workspace_id = :w
            """
        ),
        {"pid": part_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        return None
    if row["rev_status"] != "draft":
        raise ValueError("REVISION_LOCKED")
    columns = {
        "qty": "qty", "len_mm": "len_mm", "wid_mm": "wid_mm",
        "paint_instruction": "paint_instruction", "comment": "comment",
    }
    set_clauses = [
        f"{columns[k]} = :{k}" for k in fields if k in columns
    ]
    params = {k: v for k, v in fields.items() if k in columns}
    if not set_clauses:
        return dict(row)
    db.execute(
        text(
            f"""
            UPDATE estimate_line_part
               SET {', '.join(set_clauses)}
             WHERE part_id = :pid
            """
        ),
        {**params, "pid": part_id},
    )
    _recompute_line_totals(db, line_id=int(row["line_id"]))
    _recompute_revision_totals(db, revision_id=int(row["revision_id"]))
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.part_edit", target=str(part_id),
        payload={"line_id": int(row["line_id"]), "fields": list(fields.keys())},
    )
    db.flush()
    return dict(row)


def patch_hardware(
    db: Session, *, hw_id: int, workspace_id: int, actor_id: int,
    fields: dict[str, Any],
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT h.hw_id, h.line_id, l.revision_id, r.status AS rev_status
              FROM estimate_line_hardware h
              JOIN estimate_line l ON l.line_id = h.line_id
              JOIN estimate_revision r ON r.revision_id = l.revision_id
              JOIN estimate e ON e.estimate_id = r.estimate_id
             WHERE h.hw_id = :hid AND e.workspace_id = :w
            """
        ),
        {"hid": hw_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        return None
    if row["rev_status"] != "draft":
        raise ValueError("REVISION_LOCKED")
    columns = {"qty": "qty", "comment": "comment"}
    set_clauses = [
        f"{columns[k]} = :{k}" for k in fields if k in columns
    ]
    params = {k: v for k, v in fields.items() if k in columns}
    if not set_clauses:
        return dict(row)
    db.execute(
        text(
            f"""
            UPDATE estimate_line_hardware
               SET {', '.join(set_clauses)}
             WHERE hw_id = :hid
            """
        ),
        {**params, "hid": hw_id},
    )
    _recompute_line_totals(db, line_id=int(row["line_id"]))
    _recompute_revision_totals(db, revision_id=int(row["revision_id"]))
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.hardware_edit", target=str(hw_id),
        payload={"line_id": int(row["line_id"]), "fields": list(fields.keys())},
    )
    db.flush()
    return dict(row)


def add_hardware(
    db: Session, *, line_id: int, workspace_id: int, actor_id: int, payload: dict
) -> int:
    line = _line_in_workspace(db, line_id=line_id, workspace_id=workspace_id)
    if line is None:
        raise ValueError("NOT_FOUND")
    if line["rev_status"] != "draft":
        raise ValueError("REVISION_LOCKED")
    snap = _resolve_hardware_snapshot(
        db, workspace_id=workspace_id,
        material_type=payload["material_type"],
        material_id=payload["material_id"],
    )
    if snap is None:
        raise ValueError("CATALOG_ROW_NOT_FOUND")
    hid = db.execute(
        text(
            """
            INSERT INTO estimate_line_hardware(
                line_id, material_type, material_id,
                sku_snapshot, description_snapshot, supplier_snapshot,
                qty, cost_per_unit_snapshot, comment
            )
            VALUES (:lid, :mt, :mid, :sku, :desc, :sup, :q, :c, :cm)
            RETURNING hw_id
            """
        ),
        {
            "lid": line_id,
            "mt": payload["material_type"],
            "mid": payload["material_id"],
            "sku": snap.get("sku"),
            "desc": snap.get("description"),
            "sup": snap.get("supplier"),
            "q": payload.get("qty", Decimal("1")),
            "c": snap.get("cost") or 0,
            "cm": payload.get("comment"),
        },
    ).scalar()
    db.execute(
        text(
            "UPDATE estimate_line SET has_breakdown = true WHERE line_id = :lid"
        ),
        {"lid": line_id},
    )
    _recompute_line_totals(db, line_id=line_id)
    _recompute_revision_totals(db, revision_id=line["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.hardware_add", target=str(hid),
        payload={
            "line_id": line_id,
            "material_type": payload["material_type"],
            "material_id": payload["material_id"],
        },
    )
    db.flush()
    return int(hid)


def remove_hardware(
    db: Session, *, hw_id: int, workspace_id: int, actor_id: int
) -> bool:
    row = db.execute(
        text(
            """
            SELECT h.line_id, l.revision_id, r.status, e.workspace_id AS _wid
              FROM estimate_line_hardware h
              JOIN estimate_line l ON l.line_id = h.line_id
              JOIN estimate_revision r ON r.revision_id = l.revision_id
              JOIN estimate e ON e.estimate_id = r.estimate_id
             WHERE h.hw_id = :hid AND e.workspace_id = :w
            """
        ),
        {"hid": hw_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        return False
    if row["status"] != "draft":
        raise ValueError("REVISION_LOCKED")
    db.execute(
        text("DELETE FROM estimate_line_hardware WHERE hw_id = :hid"),
        {"hid": hw_id},
    )
    _maybe_clear_has_breakdown(db, line_id=row["line_id"])
    _recompute_line_totals(db, line_id=row["line_id"])
    _recompute_revision_totals(db, revision_id=row["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.hardware_remove", target=str(hw_id),
        payload={"line_id": int(row["line_id"])},
    )
    return True


def upsert_labour(
    db: Session, *, line_id: int, workspace_id: int, actor_id: int,
    stage_key: str, hours: Decimal,
) -> int:
    line = _line_in_workspace(db, line_id=line_id, workspace_id=workspace_id)
    if line is None:
        raise ValueError("NOT_FOUND")
    if line["rev_status"] != "draft":
        raise ValueError("REVISION_LOCKED")
    rate = db.execute(
        text(
            """
            SELECT hourly_rate
              FROM workspace_labour_rate
             WHERE workspace_id = :w AND stage_key = :s
            """
        ),
        {"w": workspace_id, "s": stage_key},
    ).scalar() or Decimal("0")
    if Decimal(str(hours)) == 0:
        db.execute(
            text(
                """
                DELETE FROM estimate_line_labour
                 WHERE line_id = :lid AND stage_key = :s
                """
            ),
            {"lid": line_id, "s": stage_key},
        )
        _recompute_line_totals(db, line_id=line_id)
        _recompute_revision_totals(db, revision_id=line["revision_id"])
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id,
            event="estimate.labour_clear", target=str(line_id),
            payload={"stage_key": stage_key},
        )
        return 0
    labour_id = db.execute(
        text(
            """
            INSERT INTO estimate_line_labour(
                line_id, stage_key, hours, rate_snapshot
            )
            VALUES (:lid, :s, :h, :r)
            ON CONFLICT (line_id, stage_key) DO UPDATE
              SET hours = EXCLUDED.hours, rate_snapshot = EXCLUDED.rate_snapshot
            RETURNING labour_id
            """
        ),
        {"lid": line_id, "s": stage_key, "h": hours, "r": rate},
    ).scalar()
    _recompute_line_totals(db, line_id=line_id)
    _recompute_revision_totals(db, revision_id=line["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.labour_set", target=str(labour_id),
        payload={
            "line_id": line_id, "stage_key": stage_key,
            "hours": str(hours), "rate_snapshot": str(rate),
        },
    )
    db.flush()
    return int(labour_id)


def _maybe_clear_has_breakdown(db: Session, *, line_id: int) -> None:
    remaining = db.execute(
        text(
            """
            SELECT
              (SELECT COUNT(*) FROM estimate_line_part WHERE line_id = :lid) +
              (SELECT COUNT(*) FROM estimate_line_hardware WHERE line_id = :lid)
              AS n
            """
        ),
        {"lid": line_id},
    ).scalar()
    if not remaining:
        db.execute(
            text(
                "UPDATE estimate_line SET has_breakdown = false WHERE line_id = :lid"
            ),
            {"lid": line_id},
        )


# ============================================================================
# Subtotal recomputation
# ============================================================================

def _recompute_line_totals(db: Session, *, line_id: int) -> None:
    db.execute(
        text(
            """
            UPDATE estimate_line l
               SET material_cost = COALESCE((
                       SELECT SUM(cost_extended)::numeric(12,2)
                         FROM estimate_line_part WHERE line_id = l.line_id
                   ), 0)
                 + COALESCE((
                       SELECT SUM(cost_extended)::numeric(12,2)
                         FROM estimate_line_hardware WHERE line_id = l.line_id
                   ), 0),
                   labour_cost = COALESCE((
                       SELECT SUM(cost_extended)::numeric(12,2)
                         FROM estimate_line_labour WHERE line_id = l.line_id
                   ), 0),
                   updated_at = now()
             WHERE l.line_id = :lid
            """
        ),
        {"lid": line_id},
    )


def _recompute_revision_totals(db: Session, *, revision_id: int) -> None:
    db.execute(
        text(
            """
            UPDATE estimate_revision r
               SET subtotal_cost = COALESCE((
                       SELECT SUM(total_cost * qty)::numeric(14,2)
                         FROM estimate_line
                        WHERE revision_id = r.revision_id
                   ), 0),
                   subtotal_sell = COALESCE((
                       SELECT SUM(
                         CASE
                           WHEN l.unit_sell_override IS NOT NULL THEN l.unit_sell_override * l.qty
                           ELSE l.total_cost * l.qty * (1 + r.markup_pct / 100.0)
                         END
                       )::numeric(14,2)
                         FROM estimate_line l
                        WHERE l.revision_id = r.revision_id
                   ), 0),
                   total_inc_gst = COALESCE((
                       SELECT (SUM(
                         CASE
                           WHEN l.unit_sell_override IS NOT NULL THEN l.unit_sell_override * l.qty
                           ELSE l.total_cost * l.qty * (1 + r.markup_pct / 100.0)
                         END
                       ) * (1 + r.gst_pct / 100.0))::numeric(14,2)
                         FROM estimate_line l
                        WHERE l.revision_id = r.revision_id
                   ), 0)
             WHERE r.revision_id = :rid
            """
        ),
        {"rid": revision_id},
    )


# ============================================================================
# Workspace labour rates
# ============================================================================

def list_labour_rates(db: Session, *, workspace_id: int) -> list[dict]:
    existing = {
        r["stage_key"]: dict(r) for r in db.execute(
            text(
                """
                SELECT stage_key, hourly_rate, effective_from, updated_at
                  FROM workspace_labour_rate
                 WHERE workspace_id = :w
                """
            ),
            {"w": workspace_id},
        ).mappings()
    }
    out = []
    today = datetime.now(timezone.utc).date()
    now_ts = datetime.now(timezone.utc)
    for sk in STAGE_KEYS:
        row = existing.get(sk)
        if row is None:
            out.append(
                {
                    "stage_key": sk,
                    "hourly_rate": Decimal("0"),
                    "effective_from": today,
                    "updated_at": now_ts,
                }
            )
        else:
            out.append(row)
    return out


def patch_labour_rates(
    db: Session, *, workspace_id: int, actor_id: int,
    rates: list[dict],
) -> list[dict]:
    for rate in rates:
        sk = rate["stage_key"]
        if sk not in STAGE_KEYS:
            raise ValueError(f"BAD_STAGE_KEY:{sk}")
        db.execute(
            text(
                """
                INSERT INTO workspace_labour_rate(
                    workspace_id, stage_key, hourly_rate, effective_from,
                    updated_by
                )
                VALUES (:w, :s, :r, CURRENT_DATE, :a)
                ON CONFLICT (workspace_id, stage_key) DO UPDATE
                  SET hourly_rate = EXCLUDED.hourly_rate,
                      effective_from = EXCLUDED.effective_from,
                      updated_at = now(),
                      updated_by = EXCLUDED.updated_by
                """
            ),
            {
                "w": workspace_id, "s": sk,
                "r": rate["hourly_rate"], "a": actor_id,
            },
        )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="it.labour_rate_update", target=None,
        payload={"rates": [
            {"stage_key": r["stage_key"], "hourly_rate": str(r["hourly_rate"])}
            for r in rates
        ]},
    )
    db.flush()
    return list_labour_rates(db, workspace_id=workspace_id)


# ============================================================================
# Detail loaders (used by GET endpoints + PDF + Convert)
# ============================================================================

def revision_detail(
    db: Session, *, revision_id: int, workspace_id: int
) -> dict | None:
    rev = get_revision(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if rev is None:
        return None
    lines = db.execute(
        text(
            """
            SELECT line_id, seq, description, qty, unit, has_breakdown,
                   material_cost, labour_cost, total_cost,
                   unit_sell_override, notes
              FROM estimate_line
             WHERE revision_id = :rid
             ORDER BY seq, line_id
            """
        ),
        {"rid": revision_id},
    ).mappings().all()
    line_ids = [int(l["line_id"]) for l in lines]
    parts_by_line: dict[int, list[dict]] = {lid: [] for lid in line_ids}
    hw_by_line: dict[int, list[dict]] = {lid: [] for lid in line_ids}
    lab_by_line: dict[int, list[dict]] = {lid: [] for lid in line_ids}
    if line_ids:
        for r in db.execute(
            text(
                """
                SELECT part_id, line_id, material_type, material_id,
                       sku_snapshot, description_snapshot, supplier_snapshot,
                       qty, len_mm, wid_mm, cost_per_unit_snapshot,
                       cost_extended, paint_instruction, comment
                  FROM estimate_line_part
                 WHERE line_id = ANY(:ids)
                 ORDER BY part_id
                """
            ),
            {"ids": line_ids},
        ).mappings():
            parts_by_line[int(r["line_id"])].append(dict(r))
        for r in db.execute(
            text(
                """
                SELECT hw_id, line_id, material_type, material_id,
                       sku_snapshot, description_snapshot, supplier_snapshot,
                       qty, cost_per_unit_snapshot, cost_extended, comment
                  FROM estimate_line_hardware
                 WHERE line_id = ANY(:ids)
                 ORDER BY hw_id
                """
            ),
            {"ids": line_ids},
        ).mappings():
            hw_by_line[int(r["line_id"])].append(dict(r))
        for r in db.execute(
            text(
                """
                SELECT labour_id, line_id, stage_key, hours,
                       rate_snapshot, cost_extended
                  FROM estimate_line_labour
                 WHERE line_id = ANY(:ids)
                 ORDER BY stage_key
                """
            ),
            {"ids": line_ids},
        ).mappings():
            lab_by_line[int(r["line_id"])].append(dict(r))

    markup_pct = rev["markup_pct"] or Decimal("0")
    lines_out = []
    for l in lines:
        lid = int(l["line_id"])
        total_cost = Decimal(str(l["total_cost"] or 0))
        if l["unit_sell_override"] is not None:
            unit_sell = Decimal(str(l["unit_sell_override"]))
        else:
            unit_sell = total_cost * (Decimal("1") + Decimal(str(markup_pct)) / Decimal("100"))
        qty = Decimal(str(l["qty"]))
        total_sell = (unit_sell * qty).quantize(Decimal("0.01"))
        lines_out.append(
            {
                **dict(l),
                "unit_sell": unit_sell.quantize(Decimal("0.01")),
                "total_sell": total_sell,
                "parts": parts_by_line[lid],
                "hardware": hw_by_line[lid],
                "labour": lab_by_line[lid],
            }
        )

    subtotal_sell = Decimal(str(rev["subtotal_sell"] or 0))
    total_inc_gst = Decimal(str(rev["total_inc_gst"] or 0))
    gst_amount = (total_inc_gst - subtotal_sell).quantize(Decimal("0.01"))

    return {
        **rev,
        "subtotal_cost": Decimal(str(rev["subtotal_cost"] or 0)),
        "subtotal_sell": subtotal_sell,
        "total_inc_gst": total_inc_gst,
        "gst_amount": gst_amount,
        "lines": lines_out,
    }


def estimate_detail(
    db: Session, *, estimate_id: int, workspace_id: int
) -> dict | None:
    summary = get_estimate_summary(
        db, estimate_id=estimate_id, workspace_id=workspace_id
    )
    if summary is None:
        return None
    cust = get_customer(
        db, customer_id=summary["customer_id"], workspace_id=workspace_id
    )
    rev_rows = db.execute(
        text(
            """
            SELECT revision_id
              FROM estimate_revision
             WHERE estimate_id = :eid
             ORDER BY rev_no DESC
            """
        ),
        {"eid": estimate_id},
    ).scalars().all()
    revisions = [
        revision_detail(db, revision_id=int(rid), workspace_id=workspace_id)
        for rid in rev_rows
    ]
    return {
        **summary,
        "customer": cust,
        "revisions": revisions,
    }


# ============================================================================
# Convert-to-Project
# ============================================================================

_PHC_TYPE_MAP = {
    "HARDWARE":  "HARDWARE",
    "APPLIANCE": "APPLIANCE",
}


def convert_to_project(
    db: Session, *, revision_id: int, workspace_id: int, actor_id: int
) -> dict:
    rev = lock_revision_for_update(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if rev is None:
        raise ValueError("NOT_FOUND")
    if rev["status"] != "accepted":
        raise ValueError(
            json.dumps(
                {"code": "BAD_STATUS", "status": rev["status"]}
            )
        )
    if rev["converted_project_id"] is not None:
        raise ValueError(
            json.dumps(
                {"code": "ALREADY_CONVERTED",
                 "project_id": int(rev["converted_project_id"])}
            )
        )

    est = db.execute(
        text(
            """
            SELECT e.estimate_id, e.estimate_no, e.title, e.site_address,
                   e.customer_id, c.name AS customer_name, c.archived_at
              FROM estimate e
              JOIN customer c ON c.customer_id = e.customer_id
             WHERE e.estimate_id = :eid AND e.workspace_id = :w
            """
        ),
        {"eid": rev["estimate_id"], "w": workspace_id},
    ).mappings().first()
    if est is None:
        raise ValueError("ESTIMATE_NOT_FOUND")
    if est["archived_at"] is not None:
        raise ValueError("CUSTOMER_ARCHIVED")

    detail = revision_detail(
        db, revision_id=revision_id, workspace_id=workspace_id
    )

    failures: list[dict] = []
    for line in detail["lines"]:
        for p in line["parts"]:
            if p.get("material_id") is None:
                continue
            ok = _resolve_part_snapshot(
                db, workspace_id=workspace_id,
                material_type=p["material_type"],
                material_id=int(p["material_id"]),
            )
            if ok is None:
                failures.append({
                    "line_id": int(line["line_id"]),
                    "material_type": p["material_type"],
                    "material_id": int(p["material_id"]),
                    "kind": "part",
                })
        for h in line["hardware"]:
            if h.get("material_id") is None:
                continue
            ok = _resolve_hardware_snapshot(
                db, workspace_id=workspace_id,
                material_type=h["material_type"],
                material_id=int(h["material_id"]),
            )
            if ok is None:
                failures.append({
                    "line_id": int(line["line_id"]),
                    "material_type": h["material_type"],
                    "material_id": int(h["material_id"]),
                    "kind": "hardware",
                })
    if failures:
        raise ValueError(
            json.dumps({"code": "CATALOG_GONE", "failures": failures})
        )

    project_code = est["estimate_no"]
    project_name = f"{est['title']} [{est['estimate_no']}]"
    new_project_id = db.execute(
        text(
            """
            INSERT INTO projects(
                project_code, name, pm_id, workspace_id,
                customer_id, estimate_revision_id, status, created_by
            )
            VALUES (:code, :name, :pm, :w, :cid, :rid, 'Current', :cb)
            RETURNING project_id
            """
        ),
        {
            "code": project_code,
            "name": project_name,
            "pm": actor_id,
            "w": workspace_id,
            "cid": est["customer_id"],
            "rid": revision_id,
            "cb": str(actor_id),
        },
    ).scalar()

    distinct_hw: dict[tuple[str, int], None] = {}
    for line in detail["lines"]:
        for h in line["hardware"]:
            if h.get("material_id") is None:
                continue
            phc_type = _PHC_TYPE_MAP.get(h["material_type"])
            if phc_type is None:
                continue
            distinct_hw[(phc_type, int(h["material_id"]))] = None

    phc_id_by_pair: dict[tuple[str, int], int] = {}
    phc_added = 0
    for (mtype, mid) in distinct_hw:
        cid = db.execute(
            text(
                """
                INSERT INTO project_hardware_catalog(
                    project_id, material_type, material_id, added_by
                )
                VALUES (:p, :mt, :mid, :a)
                RETURNING catalog_id
                """
            ),
            {"p": new_project_id, "mt": mtype, "mid": mid, "a": actor_id},
        ).scalar()
        phc_id_by_pair[(mtype, mid)] = int(cid)
        phc_added += 1

    items_created = 0
    parts_created = 0
    hw_lines_created = 0

    for line in detail["lines"]:
        # `num` comes from the shared `joinery_number_seq` (0027 / Q541).
        #
        # This replaced `SELECT COALESCE(MAX(num), 0) + 1 FROM items`, a
        # read-then-insert with no lock: two conversions running at once both
        # read the same maximum and the loser died on `items_num_key`.
        # Allocating inside the INSERT removes both the race and a round-trip
        # per line.
        item_id = db.execute(
            text(
                """
                INSERT INTO items(
                    num, project_id, description, qty, status
                )
                VALUES (nextval('joinery_number_seq'), :p, :d, :q, 'LIVE')
                RETURNING item_id
                """
            ),
            {
                "p": int(new_project_id),
                "d": line["description"],
                "q": int(Decimal(str(line["qty"])).quantize(Decimal("1"))),
            },
        ).scalar()
        items_created += 1

        for sk in STAGE_KEYS:
            db.execute(
                text(
                    """
                    INSERT INTO item_stages(item_id, stage_key)
                    VALUES (:i, :s)
                    """
                ),
                {"i": item_id, "s": sk},
            )

        write_edit_log(
            db, item_id=int(item_id), actor_id=actor_id,
            field="_create", old_value=None,
            new_value=f"converted from {est['estimate_no']} line {int(line['seq'])}",
        )

        if not line["has_breakdown"]:
            continue

        module_id = db.execute(
            text(
                """
                INSERT INTO modules(item_id, module_no, name)
                VALUES (:i, '1', 'Module 1')
                RETURNING module_id
                """
            ),
            {"i": item_id},
        ).scalar()

        for p in line["parts"]:
            board_mid = (
                int(p["material_id"])
                if p["material_type"] == "BOARD" and p.get("material_id") is not None
                else None
            )
            comment = p.get("comment")
            if p["material_type"] in ("CUSTOM", "BENCHTOP") and p.get("material_id"):
                tag = f"[material: {p['material_type'].lower()}#{int(p['material_id'])}]"
                comment = f"{tag} {comment or ''}".strip()
            db.execute(
                text(
                    """
                    INSERT INTO parts(
                        module_id, seq, qty, part_name, len_mm, wid_mm,
                        board_material_id, paint_instruction, comment
                    )
                    VALUES (:m, :s, :q, :n, :l, :w, :bmid, :pi, :c)
                    """
                ),
                {
                    "m": int(module_id),
                    "s": 1,
                    "q": int(Decimal(str(p["qty"])).quantize(Decimal("1"))),
                    "n": p.get("description_snapshot") or p.get("sku_snapshot") or "part",
                    "l": p.get("len_mm"),
                    "w": p.get("wid_mm"),
                    "bmid": board_mid,
                    "pi": p.get("paint_instruction", "NONE"),
                    "c": comment,
                },
            )
            parts_created += 1

        for h in line["hardware"]:
            if h.get("material_id") is None:
                continue
            phc_type = _PHC_TYPE_MAP[h["material_type"]]
            phc_id = phc_id_by_pair[(phc_type, int(h["material_id"]))]
            db.execute(
                text(
                    """
                    INSERT INTO item_hardware_lines(
                        item_id, qty, catalog_id, note
                    )
                    VALUES (:i, :q, :c, :n)
                    """
                ),
                {
                    "i": item_id,
                    "q": int(Decimal(str(h["qty"])).quantize(Decimal("1"))),
                    "c": phc_id,
                    "n": h.get("comment"),
                },
            )
            hw_lines_created += 1

    db.execute(
        text(
            """
            UPDATE estimate_revision
               SET converted_project_id = :p
             WHERE revision_id = :rid
            """
        ),
        {"p": int(new_project_id), "rid": revision_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.convert", target=str(revision_id),
        payload={
            "revision_id": int(revision_id),
            "estimate_id": int(rev["estimate_id"]),
            "project_id": int(new_project_id),
            "items_created": items_created,
            "parts_created": parts_created,
            "hardware_lines_created": hw_lines_created,
            "project_hardware_catalog_added": phc_added,
        },
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="project.create", target=str(new_project_id),
        payload={
            "from_estimate_revision_id": int(revision_id),
            "estimate_no": est["estimate_no"],
            "customer_id": int(est["customer_id"]),
            "name": project_name,
        },
    )
    db.flush()
    return {
        "project_id": int(new_project_id),
        "project_code": project_code,
        "items_created": items_created,
        "parts_created": parts_created,
        "hardware_lines_created": hw_lines_created,
        "project_hardware_catalog_added": phc_added,
    }
