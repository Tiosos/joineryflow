"""SQL queries for /batches/{bid}/allocations endpoints (Procurement Workbench v1).

Workspace scoping uses `projects.workspace_id` directly (FK added in
migration 0014). The legacy chain through `projects.pm_id -> app_user.id`
was unsafe for projects with NULL pm_id and is no longer used.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session


def list_allocations_for_batch(db: Session, *, batch_id: int) -> list[dict]:
    sql = text(
        """
        SELECT ba.allocation_id, ba.batch_id, ba.item_hardware_line_id,
               ba.qty_allocated, ba.created_at,
               i.code AS item_code, i.description AS item_description
          FROM batch_allocations ba
          JOIN item_hardware_lines ihl ON ihl.line_id = ba.item_hardware_line_id
          JOIN items i                 ON i.item_id   = ihl.item_id
         WHERE ba.batch_id = :bid
         ORDER BY ba.allocation_id
        """
    )
    return [dict(r) for r in db.execute(sql, {"bid": batch_id}).mappings()]


def batch_capacity(db: Session, *, batch_id: int) -> tuple:
    """Returns (qty_received, qty_allocated_total, qty_ordered)."""
    sql = text(
        """
        SELECT pb.qty_received, pb.qty_ordered,
               (SELECT COALESCE(SUM(qty_allocated), 0) FROM batch_allocations a
                  WHERE a.batch_id = pb.batch_id) AS qty_alloc
          FROM procurement_batches pb
         WHERE pb.batch_id = :bid
        """
    )
    r = db.execute(sql, {"bid": batch_id}).mappings().first()
    return (r["qty_received"], r["qty_alloc"], r["qty_ordered"]) if r else (0, 0, 0)


def line_belongs_to_batch_project(db: Session, *, batch_id: int, line_id: int) -> bool:
    sql = text(
        """
        SELECT EXISTS(
          SELECT 1
            FROM item_hardware_lines ihl
            JOIN items i                ON i.item_id     = ihl.item_id
            JOIN procurement_batches pb ON pb.project_id = i.project_id
           WHERE pb.batch_id = :bid AND ihl.line_id = :lid
        )
        """
    )
    return bool(db.execute(sql, {"bid": batch_id, "lid": line_id}).scalar())


def create_allocation(db: Session, *, batch_id: int, line_id: int, qty: float) -> int:
    return db.execute(
        text(
            "INSERT INTO batch_allocations(batch_id, item_hardware_line_id, qty_allocated) "
            "VALUES(:b, :l, :q) RETURNING allocation_id"
        ),
        {"b": batch_id, "l": line_id, "q": qty},
    ).scalar()


def patch_allocation(db: Session, *, allocation_id: int, qty: float) -> int:
    return db.execute(
        text(
            "UPDATE batch_allocations SET qty_allocated = :q "
            "WHERE allocation_id = :aid RETURNING allocation_id"
        ),
        {"q": qty, "aid": allocation_id},
    ).scalar()


def get_allocation(db: Session, *, allocation_id: int, workspace_id: int) -> dict | None:
    sql = text(
        """
        SELECT ba.allocation_id, ba.batch_id, ba.item_hardware_line_id,
               ba.qty_allocated, ba.created_at,
               i.code AS item_code, i.description AS item_description
          FROM batch_allocations ba
          JOIN procurement_batches pb  ON pb.batch_id  = ba.batch_id
          JOIN projects p              ON p.project_id = pb.project_id
          JOIN item_hardware_lines ihl ON ihl.line_id  = ba.item_hardware_line_id
          JOIN items i                 ON i.item_id    = ihl.item_id
         WHERE ba.allocation_id = :aid AND p.workspace_id = :w
        """
    )
    r = db.execute(sql, {"aid": allocation_id, "w": workspace_id}).mappings().first()
    return dict(r) if r else None


def delete_allocation(db: Session, *, allocation_id: int) -> int:
    return db.execute(
        text("DELETE FROM batch_allocations WHERE allocation_id = :aid RETURNING allocation_id"),
        {"aid": allocation_id},
    ).scalar()
