"""SQL queries for /procurement-queue (Procurement Workbench v1, Task 13).

Cross-project rollup of all in-flight procurement batches in the workspace.

Workspace scoping uses `projects.workspace_id` directly (FK added in
migration 0014). The legacy chain through `projects.pm_id -> app_user.id`
was unsafe for projects with NULL pm_id and is no longer used.

Material name enrichment is a second-pass per-type lookup. All six material
catalog tables expose a `description` column; `equipment_hire` uses `hire_id`
as its PK while the other five use `material_id`.
"""
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# (table, id_column, name_column) per material_type. All catalog tables use
# `description` as their human-readable label; only `equipment_hire` deviates
# from the `material_id` PK convention (it uses `hire_id`).
_NAME_LOOKUP = {
    "BOARD":     ("board_materials",    "material_id", "description"),
    "HARDWARE":  ("hardware_materials", "material_id", "description"),
    "CUSTOM":    ("custom_made",        "material_id", "description"),
    "BENCHTOP":  ("benchtop_materials", "material_id", "description"),
    "APPLIANCE": ("appliances",         "material_id", "description"),
    "HIRE":      ("equipment_hire",     "hire_id",     "description"),
}

# Derived status: cancelled > delivered > in-transit > open.
_STATUS_CASE = (
    "CASE "
    "  WHEN pb.cancelled_at  IS NOT NULL THEN 'CANCELLED' "
    "  WHEN pb.received_date IS NOT NULL THEN 'DELIVERED' "
    "  WHEN pb.ordered_date  IS NOT NULL THEN 'IN_TRANSIT' "
    "  ELSE 'OPEN' "
    "END"
)


def _enrich_names(db: Session, rows: list[dict]) -> list[dict]:
    """Second-pass lookup of material_name per (material_type, material_id)."""
    by_type: dict[str, list[int]] = {}
    for r in rows:
        by_type.setdefault(r["material_type"], []).append(r["material_id"])
    name_map: dict[tuple, str] = {}
    for mt, ids in by_type.items():
        table, id_col, name_col = _NAME_LOOKUP[mt]
        result = db.execute(
            text(
                f"SELECT {id_col} AS id, {name_col} AS name "
                f"FROM {table} WHERE {id_col} = ANY(:ids)"
            ),
            {"ids": ids},
        ).mappings()
        for r in result:
            name_map[(mt, r["id"])] = r["name"]
    for r in rows:
        r["material_name"] = name_map.get((r["material_type"], r["material_id"]))
    return rows


def queue(
    db: Session,
    *,
    workspace_id: int,
    status: str | None = None,
    supplier: str | None = None,
    project_id: int | None = None,
) -> list[dict]:
    sql = (
        "SELECT pb.batch_id, pb.project_id, p.project_code, p.name AS project_name, "
        "       pb.supplier, pb.po_ref, pb.material_type, pb.material_id, "
        "       pb.qty_ordered, pb.qty_received, pb.eta_date, "
        f"      {_STATUS_CASE} AS status "
        "  FROM procurement_batches pb "
        "  JOIN projects p   ON p.project_id = pb.project_id "
        " WHERE p.workspace_id = :w "
    )
    params: dict[str, Any] = {"w": workspace_id}
    if status:
        sql += f" AND {_STATUS_CASE} = :st"
        params["st"] = status
    if supplier:
        sql += " AND pb.supplier ILIKE :sup"
        params["sup"] = supplier
    if project_id:
        sql += " AND pb.project_id = :pid"
        params["pid"] = project_id
    sql += (
        " ORDER BY pb.supplier NULLS LAST, "
        "         COALESCE(pb.eta_date, pb.ordered_date, pb.created_at::date)"
    )
    rows = [dict(r) for r in db.execute(text(sql), params).mappings()]
    return _enrich_names(db, rows)
