"""Customers, estimates, revisions, the 12-stage tender lifecycle and subtotal recomputation.

Part of the estimating queries facade (see `queries.py`)."""
from __future__ import annotations

from datetime import datetime
from datetime import timezone
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Any
import json
from ..auth.audit import write_audit


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
