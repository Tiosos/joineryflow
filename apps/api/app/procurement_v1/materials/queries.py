"""Project material rollup query.

Joins demand (item_hardware_lines + parts.board_material_id),
batches (procurement_batches with cancelled_at filter),
and allocations (batch_allocations) into one row per (material_type, material_id),
then enriches with name/sku from the six material catalog tables.

Schema notes (real columns, see migrations 0001 + 0007):
  - board_materials, hardware_materials, custom_made, benchtop_materials,
    appliances: PK = material_id; name = description; sku = sku.
  - equipment_hire: PK = hire_id (not material_id); name = description; sku = sku.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

_ROLLUP_SQL = text(
    """
    WITH demand AS (
      SELECT phc.material_type, phc.material_id,
             SUM(ihl.qty) AS qty_demand
        FROM item_hardware_lines ihl
        JOIN project_hardware_catalog phc ON phc.catalog_id = ihl.catalog_id
        JOIN items i                      ON i.item_id      = ihl.item_id
       WHERE i.project_id = :pid
       GROUP BY phc.material_type, phc.material_id

      UNION ALL

      SELECT 'BOARD', p.board_material_id, SUM(p.qty)
        FROM parts p
        JOIN modules m ON m.module_id = p.module_id
        JOIN items   i ON i.item_id   = m.item_id
       WHERE i.project_id = :pid
         AND p.board_material_id IS NOT NULL
       GROUP BY p.board_material_id
    ),
    batches AS (
      SELECT material_type, material_id,
             SUM(qty_ordered)
               FILTER (WHERE received_date IS NULL AND cancelled_at IS NULL) AS qty_on_order,
             SUM(qty_received)                                               AS qty_received,
             MIN(eta_date)
               FILTER (WHERE received_date IS NULL AND cancelled_at IS NULL) AS earliest_eta
        FROM procurement_batches
       WHERE project_id = :pid
       GROUP BY material_type, material_id
    ),
    allocations AS (
      SELECT pb.material_type, pb.material_id,
             SUM(ba.qty_allocated) AS qty_allocated
        FROM batch_allocations ba
        JOIN procurement_batches pb ON pb.batch_id = ba.batch_id
       WHERE pb.project_id = :pid
       GROUP BY pb.material_type, pb.material_id
    )
    SELECT d.material_type, d.material_id,
           d.qty_demand,
           COALESCE(b.qty_on_order, 0)  AS qty_on_order,
           COALESCE(b.qty_received, 0)  AS qty_received,
           COALESCE(a.qty_allocated, 0) AS qty_allocated,
           GREATEST(d.qty_demand - COALESCE(b.qty_received, 0) - COALESCE(b.qty_on_order, 0), 0) AS shortfall,
           b.earliest_eta
      FROM demand d
      LEFT JOIN batches     b USING (material_type, material_id)
      LEFT JOIN allocations a USING (material_type, material_id)
    """
)

# (table, id_col, name_col, sku_col) — sku_col may be None for tables without a sku.
# Real schema: description is the human-readable name across all six tables;
# equipment_hire uses hire_id as its PK (not material_id).
_CATALOG_LOOKUP = {
    "BOARD":     ("board_materials",    "material_id", "description", "sku"),
    "HARDWARE":  ("hardware_materials", "material_id", "description", "sku"),
    "CUSTOM":    ("custom_made",        "material_id", "description", "sku"),
    "BENCHTOP":  ("benchtop_materials", "material_id", "description", "sku"),
    "APPLIANCE": ("appliances",         "material_id", "description", "sku"),
    "HIRE":      ("equipment_hire",     "hire_id",     "description", "sku"),
}


def project_material_rollup(db: Session, project_id: int) -> list[dict]:
    rows = db.execute(_ROLLUP_SQL, {"pid": project_id}).mappings().all()
    by_type: dict[str, list[int]] = {}
    for r in rows:
        by_type.setdefault(r["material_type"], []).append(r["material_id"])

    name_map: dict[tuple[str, int], tuple[str, str | None]] = {}
    for mt, ids in by_type.items():
        if not ids:
            continue
        table, id_col, name_col, sku_col = _CATALOG_LOOKUP[mt]
        sku_select = f", {sku_col}" if sku_col else ", NULL AS sku"
        sql = text(
            f"SELECT {id_col} AS material_id, {name_col} AS name {sku_select} "
            f"FROM {table} WHERE {id_col} = ANY(:ids)"
        )
        for row in db.execute(sql, {"ids": ids}).mappings():
            name_map[(mt, row["material_id"])] = (row["name"], row["sku"])

    today = db.execute(text("SELECT CURRENT_DATE")).scalar()

    out: list[dict] = []
    for r in rows:
        name, sku = name_map.get((r["material_type"], r["material_id"]), ("(unknown)", None))
        shortfall = float(r["shortfall"])
        eta = r["earliest_eta"]
        if shortfall > 0 and eta is not None and eta < today:
            status = "OVERDUE"
        elif shortfall > 0:
            status = "SHORT"
        else:
            status = "OK"
        out.append(
            {
                "material_type": r["material_type"],
                "material_id":   r["material_id"],
                "name":          name,
                "sku":           sku,
                "qty_demand":    r["qty_demand"],
                "qty_on_order":  r["qty_on_order"],
                "qty_received":  r["qty_received"],
                "qty_allocated": r["qty_allocated"],
                "shortfall":     r["shortfall"],
                "earliest_eta":  eta,
                "status":        status,
            }
        )
    return out
