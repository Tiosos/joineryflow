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
from ..orders import queries as orders_q
from ..orders.schemas import CreateOrderIn, CreateOrderLineIn


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


# One catalog table per material_type, for PO generation (below). Merges
# _PART_CATALOG_BY_TYPE and _HW_CATALOG_BY_TYPE — their keys never overlap.
_CATALOG_BY_TYPE: dict[str, tuple[str, str, str, str, str]] = {
    **_PART_CATALOG_BY_TYPE, **_HW_CATALOG_BY_TYPE,
}

# Purchasing unit per material_type — there is no `unit`/`cost_unit` column
# on any of the six catalog tables (CLAUDE.md's "abstract interface" note:
# verify before relying on it), so this is a fixed, sensible default rather
# than a DB lookup.
_ORDER_UNIT_BY_TYPE: dict[str, str] = {
    "BOARD": "sheet", "CUSTOM": "EA", "BENCHTOP": "slab",
    "HARDWARE": "EA", "APPLIANCE": "EA",
}


def _resolve_order_sources_batch(
    db: Session, *, workspace_id: int, material_type: str, material_ids: list[int],
) -> dict[int, dict]:
    """Live sku/description/cost/supplier for every given catalog row of one
    material_type, in a single query — the same batched-by-table shape
    `revision_detail()` already uses for parts/hardware/labour (`WHERE
    line_id = ANY(:ids)`), so a quote referencing N distinct materials costs
    at most 5 queries (one per catalog table) instead of N. Unlike
    `_resolve_part_snapshot` / `_resolve_hardware_snapshot`, this also
    resolves the real vendor — `default_supplier_id` (migration 0029), not
    the free-text `default_supplier` those two read — because a purchase
    order needs a real `vendors.vendor_id` to attach to, not a name string.
    Reads **current** catalog pricing deliberately: Plan V1 §21 requires
    stale project-specific pricing to be caught before PO creation, and
    generation typically happens well after the quote was priced."""
    cfg = _CATALOG_BY_TYPE.get(material_type)
    if cfg is None or not material_ids:
        return {}
    table, id_col, sku_col, _supplier_col, cost_col = cfg
    sql = text(
        f"""
        SELECT t.{id_col} AS material_id, t.{sku_col} AS sku, t.description,
               t.{cost_col} AS cost,
               t.default_supplier_id AS supplier_id, v.name AS supplier_name
          FROM {table} t
          LEFT JOIN vendors v
            ON v.vendor_id = t.default_supplier_id AND v.workspace_id = :w
         WHERE t.{id_col} = ANY(:ids) AND t.workspace_id = :w
           AND t.archived_at IS NULL
        """
    )
    rows = db.execute(sql, {"ids": material_ids, "w": workspace_id}).mappings().all()
    return {int(r["material_id"]): dict(r) for r in rows}


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
    # "Active" is every non-terminal stage plus WON: a won quote stays
    # actionable (pending handover) rather than filed away. "Archive" is
    # the two outcomes that end the tender without a project — LOST also
    # covers a lapsed (expired) quote (Q548).
    active_set = (
        "('OPPORTUNITY','INITIAL_REVIEW','GO_NO_GO','INFO_REQUESTED',"
        "'DOCS_RECEIVED','ESTIMATING','SUPPLIER_PRICING','INTERNAL_REVIEW',"
        "'QUOTE_PREPARED','MGMT_APPROVAL','SUBMITTED','WON')"
    )
    archive_set = "('LOST','WITHDRAWN')"
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
            VALUES (:eid, :rn, 'OPPORTUNITY', 0, 10.00, :a)
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
    if (set(fields.keys()) & draft_only_keys) and cur["locked_at"] is not None:
        raise ValueError("REVISION_LOCKED")
    if "expires_at" in fields and cur["status"] != "SUBMITTED":
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
    if cur["locked_at"] is None:
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
    """Clone the current revision into a new one, starting at ESTIMATING
    rather than OPPORTUNITY (Plan V1 does not say where a revision restarts;
    recorded here as the chosen default) — the opportunity/review/go-no-go/
    information-gathering work already happened for this tender and does
    not need repeating just because the price is being redone."""
    cur_summary = get_estimate_summary(
        db, estimate_id=estimate_id, workspace_id=workspace_id
    )
    if cur_summary is None:
        raise ValueError("NOT_FOUND")
    existing_draft = db.execute(
        text(
            """
            SELECT revision_id FROM estimate_revision
             WHERE estimate_id = :eid AND locked_at IS NULL
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
            VALUES (:eid, :rn, 'ESTIMATING', :markup, :gst, :terms, :a)
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
# Status transitions — the 12-stage tender lifecycle (Plan V1 §5, Q487/488/548)
# ============================================================================
#
# 11 sequential pipeline stages, then a 12th, terminal position resolving to
# one of WON / LOST / WITHDRAWN. `advance_revision()` walks the sequential
# chain one stage at a time via the single generic action below — Plan V1
# names these 9 early stages but specifies no data or gate for any of them
# individually, so they are bare pipeline-position markers. The one step
# with real business logic (locking the revision, snapshotting labour
# rates) is MGMT_APPROVAL -> SUBMITTED — the moment the quote actually goes
# to the client — and that logic lives in `transition_revision`'s
# `target == "SUBMITTED"` branch, which fires whether reached via
# `advance_revision()` or directly, so no separate "send" entry point is
# needed. `accept` / `reject` / `expire` resolve a SUBMITTED revision;
# `withdraw` is legal from any non-terminal stage at any time (Plan V1 gives
# no separate "No-Go" outcome — a Go/No-Go decision of "No" is the same act
# as a withdrawal at any other stage).

TENDER_STAGE_ORDER: tuple[str, ...] = (
    "OPPORTUNITY", "INITIAL_REVIEW", "GO_NO_GO", "INFO_REQUESTED",
    "DOCS_RECEIVED", "ESTIMATING", "SUPPLIER_PRICING", "INTERNAL_REVIEW",
    "QUOTE_PREPARED", "MGMT_APPROVAL", "SUBMITTED",
)
TERMINAL_STATUSES: frozenset[str] = frozenset({"WON", "LOST", "WITHDRAWN"})

_LEGAL_TRANSITIONS: dict[str, set[str]] = {
    **{
        stage: {TENDER_STAGE_ORDER[i + 1], "WITHDRAWN"}
        for i, stage in enumerate(TENDER_STAGE_ORDER[:-1])
    },
    "SUBMITTED": {"WON", "LOST", "WITHDRAWN"},
    "WON": set(), "LOST": set(), "WITHDRAWN": set(),
}


def next_tender_stage(current: str) -> str | None:
    """The stage `advance()` would move to, or None if `current` has no
    single well-defined next stage (SUBMITTED resolves via accept/reject/
    expire, not advance; a terminal status has no next stage)."""
    if current in TENDER_STAGE_ORDER[:-1]:
        return TENDER_STAGE_ORDER[TENDER_STAGE_ORDER.index(current) + 1]
    return None


def transition_revision(
    db: Session, *, revision_id: int, workspace_id: int,
    actor_id: int, target: str, lost_reason: str | None = None,
    lost_kind: str = "rejected",
) -> dict:
    """`lost_kind` distinguishes `reject` from `expire` when `target ==
    "LOST"` — both collapse onto the same status (Q548), but the route
    invoked (client said no vs. the validity window lapsed) is still worth
    a distinct audit event name, so the caller states it explicitly rather
    than it being inferred from `lost_reason`'s text."""
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
    if target == "SUBMITTED":
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
    elif target == "WON":
        sets += ["accepted_at = :now"]
        params["now"] = now
        audit_event = "estimate.accept"
    elif target == "LOST":
        sets += ["rejected_at = :now", "lost_reason = :lr"]
        params["now"] = now
        params["lr"] = lost_reason
        audit_event = "estimate.expire" if lost_kind == "expired" else "estimate.reject"
        audit_payload["lost_reason"] = lost_reason
    elif target == "WITHDRAWN":
        sets += ["lost_reason = :lr"]
        params["lr"] = lost_reason
        audit_event = "estimate.withdraw"
        audit_payload["lost_reason"] = lost_reason
    else:
        # One of the 9 bare sequential advances (OPPORTUNITY..QUOTE_PREPARED
        # -> the next stage). No dedicated column, no gate beyond the graph
        # above — Plan V1 names these stages but specifies nothing else.
        audit_event = "estimate.advance"

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
    if target == "SUBMITTED":
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


def advance_revision(
    db: Session, *, revision_id: int, workspace_id: int, actor_id: int,
) -> dict:
    """Move a revision to the next stage in the sequential pipeline
    (OPPORTUNITY..MGMT_APPROVAL -> the following stage). One generic action
    covers all 10 forward steps, including MGMT_APPROVAL -> SUBMITTED: that
    step's lock-and-snapshot business logic lives in `transition_revision`'s
    `target == "SUBMITTED"` branch, so it fires here too without a separate
    entry point."""
    cur = get_revision(db, revision_id=revision_id, workspace_id=workspace_id)
    if cur is None:
        raise ValueError("NOT_FOUND")
    nxt = next_tender_stage(cur["status"])
    if nxt is None:
        raise ValueError(
            json.dumps({"code": "BAD_TRANSITION", "from": cur["status"], "to": None})
        )
    return transition_revision(
        db, revision_id=revision_id, workspace_id=workspace_id,
        actor_id=actor_id, target=nxt,
    )


# ============================================================================
# Line CRUD + parts/hardware/labour add/remove
# ============================================================================

def _assert_unlocked(
    db: Session, *, revision_id: int, workspace_id: int
) -> dict:
    cur = get_revision(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if cur is None:
        raise ValueError("NOT_FOUND")
    if cur["locked_at"] is not None:
        raise ValueError("REVISION_LOCKED")
    return cur


def _line_in_workspace(
    db: Session, *, line_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT l.*, r.status AS rev_status, r.locked_at AS rev_locked_at,
                   r.revision_id, e.workspace_id AS _wid
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
    if cur["locked_at"] is not None:
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
    if line["rev_locked_at"] is not None:
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
    if line["rev_locked_at"] is not None:
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
    _assert_unlocked(db, revision_id=revision_id, workspace_id=workspace_id)
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
    if line["rev_locked_at"] is not None:
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
            SELECT p.line_id, l.revision_id, r.locked_at, e.workspace_id AS _wid
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
    if row["locked_at"] is not None:
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
            SELECT p.part_id, p.line_id, l.revision_id, r.locked_at AS rev_locked_at
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
    if row["rev_locked_at"] is not None:
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
            SELECT h.hw_id, h.line_id, l.revision_id, r.locked_at AS rev_locked_at
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
    if row["rev_locked_at"] is not None:
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
    if line["rev_locked_at"] is not None:
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
            SELECT h.line_id, l.revision_id, r.locked_at, e.workspace_id AS _wid
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
    if row["locked_at"] is not None:
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
    if line["rev_locked_at"] is not None:
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
                   unit_sell_override, notes, included_at_convert
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


def handover_preview(
    db: Session, *, revision_id: int, workspace_id: int
) -> dict | None:
    """What Q490's PM review screen shows before Convert: the lines that
    would become Joinery Items, and the contract value Convert will set by
    default (the quote's own GST-inclusive total — nothing to re-enter)."""
    rev = get_revision(db, revision_id=revision_id, workspace_id=workspace_id)
    if rev is None:
        return None
    detail = revision_detail(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    return {
        "revision_id": revision_id,
        "status": rev["status"],
        "already_converted_project_id": (
            int(rev["converted_project_id"])
            if rev["converted_project_id"] is not None else None
        ),
        "proposed_contract_value": detail["total_inc_gst"],
        "lines": [
            {
                "line_id": int(l["line_id"]),
                "seq": l["seq"],
                "description": l["description"],
                "qty": l["qty"],
                "has_breakdown": l["has_breakdown"],
                "total_sell": l["total_sell"],
            }
            for l in detail["lines"]
        ],
    }


def convert_to_project(
    db: Session, *, revision_id: int, workspace_id: int, actor_id: int,
    include_line_ids: list[int] | None = None,
    contract_value: Decimal | None = None,
) -> dict:
    """Q490: `include_line_ids` (default: every line) is the PM's selection
    from the handover-preview screen — an excluded line simply becomes no
    Joinery Item, everything else about it (its place in the quote) is
    unaffected. `contract_value` (default: the quote's own GST-inclusive
    total) becomes the immutable `project_contract.original_value` (Q491) —
    it is independent of which lines were included, since a lump-sum line
    left out of the Item list can still be part of what the client is
    paying for."""
    rev = lock_revision_for_update(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if rev is None:
        raise ValueError("NOT_FOUND")
    if rev["status"] != "WON":
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
    total_inc_gst = detail["total_inc_gst"]
    all_line_ids = {int(l["line_id"]) for l in detail["lines"]}
    if include_line_ids is None:
        selected_ids = all_line_ids
    else:
        unknown = set(include_line_ids) - all_line_ids
        if unknown:
            raise ValueError(
                json.dumps({"code": "UNKNOWN_LINE_IDS", "line_ids": sorted(unknown)})
            )
        selected_ids = set(include_line_ids)
    detail["lines"] = [l for l in detail["lines"] if int(l["line_id"]) in selected_ids]
    final_contract_value = (
        contract_value if contract_value is not None else total_inc_gst
    )
    # Records which lines actually became Joinery Items — `generate_orders`
    # (below) defaults to this set rather than every line in the revision,
    # so a line the PM excluded here never gets its materials ordered.
    if selected_ids:
        db.execute(
            text(
                "UPDATE estimate_line SET included_at_convert = true"
                " WHERE line_id = ANY(:ids)"
            ),
            {"ids": list(selected_ids)},
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

    db.execute(
        text(
            """
            INSERT INTO project_contract(project_id, original_value, created_by)
            VALUES (:p, :v, :a)
            """
        ),
        {"p": int(new_project_id), "v": final_contract_value, "a": actor_id},
    )

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

        for part_seq, p in enumerate(line["parts"], start=1):
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
                    # Fixed later. Was hardcoded 1 for every part in a
                    # module — fine while every seed/test fixture had at
                    # most one part per line, but `uq_parts_module_seq`
                    # (module_id, seq) rejects a second part with the same
                    # seq, so any WON quote line with more than one part
                    # failed to convert. Found live-testing PO generation
                    # (#13's `test_generate_orders_creates_one_po_per_
                    # supplier_with_consolidated_lines`-style fixture, a
                    # line with two different BOARD parts).
                    "s": part_seq,
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
            "included_line_ids": sorted(selected_ids),
            "excluded_line_ids": sorted(all_line_ids - selected_ids),
            "contract_value": str(final_contract_value),
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
        "contract_value": final_contract_value,
    }


# ============================================================================
# Generate Orders — PO generation from a won quote
# ============================================================================
#
# Sources from the revision's own line breakdown (estimate_line_part /
# estimate_line_hardware), not the converted project's items: `parts` only
# retains a real material FK for BOARD (Q447's `board_material_id`), so
# CUSTOM/BENCHTOP catalog links survive only as a comment string there —
# reading the revision directly keeps every material_id real. Also not from
# the Material Summary (#12): Q585 confirmed "no create-order-from-line in
# v1" for that surface.

def _collect_order_materials(lines: list[dict]) -> dict[tuple[str, int], dict]:
    """Consolidates every parts/hardware breakdown row with a real
    material_id across `lines`, summing qty per distinct (material_type,
    material_id) — the same SKU quoted on five different lines becomes one
    PO line for the total quantity, not five. Cut dimensions (len_mm/wid_mm)
    are deliberately dropped: they're cutting information for Production,
    not purchasing information for a PO."""
    materials: dict[tuple[str, int], dict] = {}
    for line in lines:
        for r in line["parts"] + line["hardware"]:
            if r.get("material_id") is None:
                continue
            key = (r["material_type"], int(r["material_id"]))
            m = materials.setdefault(key, {
                "material_type": r["material_type"],
                "material_id": int(r["material_id"]),
                "qty": Decimal("0"),
                "fallback_sku": r.get("sku_snapshot"),
                "fallback_description": r.get("description_snapshot"),
                "fallback_cost": r.get("cost_per_unit_snapshot"),
            })
            m["qty"] += Decimal(str(r["qty"]))
    return materials


def _build_order_groups(
    db: Session, *, workspace_id: int, lines: list[dict],
) -> tuple[dict[int, dict], list[dict]]:
    """Groups every distinct material referenced by `lines` by its live
    default supplier. Returns (groups keyed by supplier_id, unassigned
    list) — a material with no default supplier can't become a PO line
    automatically (`purchase_orders.vendor_id` is NOT NULL) and is
    surfaced for the PM to order by hand instead of blocking the suppliers
    that DO have one."""
    materials = _collect_order_materials(lines)
    ids_by_type: dict[str, list[int]] = {}
    for mtype, mid in materials:
        ids_by_type.setdefault(mtype, []).append(mid)
    sources: dict[tuple[str, int], dict] = {}
    for mtype, ids in ids_by_type.items():
        batch = _resolve_order_sources_batch(
            db, workspace_id=workspace_id, material_type=mtype, material_ids=ids,
        )
        for mid, src in batch.items():
            sources[(mtype, mid)] = src

    groups: dict[int, dict] = {}
    unassigned: list[dict] = []
    for (mtype, mid), m in materials.items():
        src = sources.get((mtype, mid))
        entry = {
            "material_type": mtype,
            "material_id": mid,
            "sku": src["sku"] if src else m["fallback_sku"],
            "description": src["description"] if src else m["fallback_description"],
            "qty": m["qty"],
            "unit": _ORDER_UNIT_BY_TYPE.get(mtype, "EA"),
            "unit_cost": (
                (src["cost"] if src else m["fallback_cost"]) or Decimal("0")
            ),
        }
        supplier_id = src["supplier_id"] if src else None
        if supplier_id is None:
            unassigned.append(entry)
            continue
        group = groups.setdefault(int(supplier_id), {
            "supplier_id": int(supplier_id),
            "supplier_name": src["supplier_name"],
            "lines": [],
            "_type_counts": {},
        })
        group["lines"].append(entry)
        group["_type_counts"][mtype] = group["_type_counts"].get(mtype, 0) + 1
    for group in groups.values():
        # The PO header's category is the material_type most represented in
        # it — most suppliers specialise, so this is a group's dominant type
        # in practice, not an arbitrary pick. Values match order_category's
        # joinery keys (0031) exactly: "BOARD".capitalize() == "Board", etc.
        dominant = max(group["_type_counts"].items(), key=lambda kv: kv[1])[0]
        group["category"] = dominant.capitalize()
        del group["_type_counts"]
    return groups, unassigned


def order_preview(
    db: Session, *, revision_id: int, workspace_id: int
) -> dict | None:
    """The review screen before `generate_orders`: every distinct material
    across the revision's lines, grouped by its live default supplier —
    same shape Convert's own `handover_preview` established for Q490. Once
    converted, only lines actually included at Convert are considered
    (`included_at_convert`) — a line the PM excluded there has no Joinery
    Item in the project and shouldn't have materials ordered for it either.
    Before conversion nothing has been decided yet, so every line is shown
    as a what-if preview."""
    rev = get_revision(db, revision_id=revision_id, workspace_id=workspace_id)
    if rev is None:
        return None
    detail = revision_detail(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    lines = detail["lines"]
    if rev["converted_project_id"] is not None:
        lines = [l for l in lines if l.get("included_at_convert")]
    groups, unassigned = _build_order_groups(
        db, workspace_id=workspace_id, lines=lines,
    )
    return {
        "revision_id": revision_id,
        "status": rev["status"],
        "converted_project_id": (
            int(rev["converted_project_id"])
            if rev["converted_project_id"] is not None else None
        ),
        "orders_generated_at": rev["orders_generated_at"],
        "groups": sorted(
            groups.values(), key=lambda g: g["supplier_name"] or ""
        ),
        "unassigned": unassigned,
    }


def generate_orders(
    db: Session, *, revision_id: int, workspace_id: int, actor_id: int,
    include_line_ids: list[int] | None = None,
) -> dict:
    """Plan V1 §21's "Create PO" (Q505) made real: materialises the
    revision's material breakdown into draft purchase orders, one per
    supplier, reusing the existing orders module end-to-end (`create_order`
    / `add_line`) rather than inventing a parallel order entity — the same
    "purchase_orders + po_line_items ARE the order layer" stance Q502/Q553
    already established for #10.

    Requires the revision already converted (a PO needs a real project to
    attach to — `409 NOT_CONVERTED` otherwise) and runs at most once per
    revision (`409 ORDERS_ALREADY_GENERATED` on a second call) —
    `orders_generated_at` is set here and never cleared, mirroring the
    "quote is frozen" stance `locked_at` already takes; there is no
    legitimate reason to regenerate from a breakdown that cannot change.
    Materials with no default supplier are returned as `unassigned` rather
    than blocking the suppliers that DO have orders generated for them."""
    rev = lock_revision_for_update(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if rev is None:
        raise ValueError("NOT_FOUND")
    if rev["converted_project_id"] is None:
        raise ValueError("NOT_CONVERTED")
    if rev["orders_generated_at"] is not None:
        raise ValueError("ORDERS_ALREADY_GENERATED")

    estimate_no = db.execute(
        text("SELECT estimate_no FROM estimate WHERE estimate_id = :eid"),
        {"eid": rev["estimate_id"]},
    ).scalar()

    detail = revision_detail(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    all_line_ids = {int(l["line_id"]) for l in detail["lines"]}
    if include_line_ids is None:
        # Only lines actually included at Convert (`included_at_convert`) —
        # not every line in the revision. A line the PM excluded at Convert
        # has no Joinery Item in the project; defaulting to the whole
        # revision would purchase-order materials for work that isn't
        # part of the project.
        selected_ids = {
            int(l["line_id"]) for l in detail["lines"] if l.get("included_at_convert")
        }
    else:
        unknown = set(include_line_ids) - all_line_ids
        if unknown:
            raise ValueError(
                json.dumps({"code": "UNKNOWN_LINE_IDS", "line_ids": sorted(unknown)})
            )
        selected_ids = set(include_line_ids)
    selected_lines = [l for l in detail["lines"] if int(l["line_id"]) in selected_ids]

    groups, unassigned = _build_order_groups(
        db, workspace_id=workspace_id, lines=selected_lines,
    )

    po_ids: list[int] = []
    lines_created = 0
    for group in groups.values():
        code, order = orders_q.create_order(
            db, workspace_id=workspace_id,
            payload=CreateOrderIn(
                vendor_id=group["supplier_id"],
                description=(
                    f"Materials for {estimate_no} — "
                    f"{group['supplier_name'] or 'supplier'}"
                ),
                category=group["category"],
                project_id=int(rev["converted_project_id"]),
                attributes={"generated_from_revision_id": revision_id},
            ),
            actor_id=actor_id,
        )
        if code != "OK":
            # Every default_supplier_id write path today keeps the vendor
            # workspace-consistent, so this shouldn't be reachable — but
            # the FK itself carries no workspace check, and failing loudly
            # beats an unhandled TypeError on `order["po_id"]` below.
            raise ValueError(
                json.dumps({"code": code, "supplier_id": group["supplier_id"]})
            )
        po_ids.append(int(order["po_id"]))
        for entry in group["lines"]:
            orders_q.add_line(
                db, po_id=order["po_id"], workspace_id=workspace_id,
                payload=CreateOrderLineIn(
                    item_description=entry["description"] or entry["sku"] or "material",
                    quantity=entry["qty"],
                    unit_price=entry["unit_cost"],
                    sku=entry["sku"],
                    unit=entry["unit"],
                    material_table=_CATALOG_BY_TYPE[entry["material_type"]][0],
                    material_id=entry["material_id"],
                ),
                actor_id=actor_id,
            )
            lines_created += 1

    db.execute(
        text(
            "UPDATE estimate_revision SET orders_generated_at = now()"
            " WHERE revision_id = :rid"
        ),
        {"rid": revision_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.generate_orders", target=str(revision_id),
        payload={
            "revision_id": revision_id,
            "project_id": int(rev["converted_project_id"]),
            "orders_created": len(po_ids),
            "lines_created": lines_created,
            "po_ids": po_ids,
            "unassigned_count": len(unassigned),
            "included_line_ids": sorted(selected_ids),
        },
    )
    db.flush()
    return {
        "orders_created": len(po_ids),
        "lines_created": lines_created,
        "po_ids": po_ids,
        "unassigned": unassigned,
    }
