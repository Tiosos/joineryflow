"""SQL queries for /batches endpoints (Procurement Workbench v1).

Workspace scoping: `projects.workspace_id` is the direct FK (added in
migration 0014). Older revisions of this file routed through
`projects.pm_id -> app_user.workspace_id`; that path was unsafe for projects
with NULL pm_id and is no longer used.
"""
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# Derived status: cancelled > delivered > in-transit > open.
# Qualified with `pb.` so it can be reused in WHERE clauses against the
# `procurement_batches AS pb` alias used in list_batches/get_batch.
_STATUS_CASE = (
    "CASE "
    "  WHEN pb.cancelled_at  IS NOT NULL THEN 'CANCELLED' "
    "  WHEN pb.received_date IS NOT NULL THEN 'DELIVERED' "
    "  WHEN pb.ordered_date  IS NOT NULL THEN 'IN_TRANSIT' "
    "  ELSE 'OPEN' "
    "END"
)

_BATCH_COLS = (
    "pb.batch_id, pb.project_id, pb.material_type, pb.material_id, "
    "pb.supplier, pb.po_ref, "
    "pb.qty_ordered, pb.qty_received, pb.cost_per_unit, "
    "pb.ordered_date, pb.eta_date, pb.received_date, pb.cancelled_at, pb.notes, "
    f"{_STATUS_CASE} AS status, "
    "(SELECT COALESCE(SUM(a.qty_allocated), 0) FROM batch_allocations a "
    "  WHERE a.batch_id = pb.batch_id) AS qty_allocated"
)


def list_batches(
    db: Session,
    *,
    workspace_id: int,
    project_id: int | None = None,
    supplier: str | None = None,
    status: str | None = None,
) -> list[dict]:
    sql = (
        f"SELECT {_BATCH_COLS} FROM procurement_batches pb "
        "JOIN projects p   ON p.project_id = pb.project_id "
        "WHERE p.workspace_id = :w "
    )
    params: dict[str, Any] = {"w": workspace_id}
    if project_id is not None:
        sql += " AND pb.project_id = :pid"
        params["pid"] = project_id
    if supplier:
        sql += " AND pb.supplier ILIKE :s"
        params["s"] = supplier
    if status:
        sql += f" AND {_STATUS_CASE} = :st"
        params["st"] = status
    sql += (
        " ORDER BY COALESCE(pb.eta_date, pb.ordered_date,"
        "                   pb.created_at::date) ASC,"
        " pb.batch_id ASC"
    )
    return [dict(r) for r in db.execute(text(sql), params).mappings()]


def get_batch(db: Session, *, batch_id: int, workspace_id: int) -> dict | None:
    sql = text(
        f"SELECT {_BATCH_COLS} FROM procurement_batches pb "
        "JOIN projects p   ON p.project_id = pb.project_id "
        "WHERE pb.batch_id = :bid AND p.workspace_id = :w"
    )
    row = db.execute(sql, {"bid": batch_id, "w": workspace_id}).mappings().first()
    return dict(row) if row else None


def create_batch(db: Session, *, payload: dict, project_id: int) -> int:
    sql = text(
        """
        INSERT INTO procurement_batches
          (project_id, material_type, material_id, supplier, po_ref,
           qty_ordered, qty_received, cost_per_unit,
           ordered_date, eta_date, received_date, notes)
        VALUES
          (:project_id, :material_type, :material_id, :supplier, :po_ref,
           :qty_ordered, :qty_received, :cost_per_unit,
           :ordered_date, :eta_date, :received_date, :notes)
        RETURNING batch_id
        """
    )
    return db.execute(sql, {**payload, "project_id": project_id}).scalar()


def patch_batch(db: Session, *, batch_id: int, fields: dict) -> int:
    if not fields:
        return batch_id
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    sql = text(
        f"UPDATE procurement_batches SET {sets}, updated_at = now() "
        "WHERE batch_id = :bid RETURNING batch_id"
    )
    return db.execute(sql, {**fields, "bid": batch_id}).scalar()


def soft_cancel_batch(db: Session, *, batch_id: int) -> int:
    return db.execute(
        text(
            "UPDATE procurement_batches SET cancelled_at = now(), updated_at = now() "
            "WHERE batch_id = :bid AND cancelled_at IS NULL RETURNING batch_id"
        ),
        {"bid": batch_id},
    ).scalar()


def batch_has_allocations(db: Session, *, batch_id: int) -> bool:
    sql = text(
        "SELECT EXISTS(SELECT 1 FROM batch_allocations "
        "  WHERE batch_id = :bid AND qty_allocated > 0)"
    )
    return bool(db.execute(sql, {"bid": batch_id}).scalar())
