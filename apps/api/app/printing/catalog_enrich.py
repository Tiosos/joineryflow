"""Resolve hardware lines into per-material-type groups for the print template.

Reuses the same `_TYPE_MAP` shape as procurement_v1/materials/queries.py.
Extracted here (rather than imported) so the printing module is self-contained
and the procurement_v1 module is free to evolve its internal helpers.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

# Maps catalog material_type → (table_name, pk_column, name_column, sku_column).
_TYPE_MAP: dict[str, tuple[str, str, str, str]] = {
    "BOARD":     ("board_materials",    "material_id", "description", "sku"),
    "HARDWARE":  ("hardware_materials", "material_id", "description", "sku"),
    "CUSTOM":    ("custom_made",        "material_id", "description", "sku"),
    "BENCHTOP":  ("benchtop_materials", "material_id", "description", "sku"),
    "APPLIANCE": ("appliances",         "material_id", "description", "sku"),
    "HIRE":      ("equipment_hire",     "hire_id",     "description", "sku"),
}


def group_hardware_for_print(db: Session, lines: list[dict]) -> list[dict]:
    """Group hardware lines by material_type, enriched with name + sku.

    Input rows are dicts with keys: qty, note, material_type, material_id, catalog_id.
    Output is a list of group dicts in canonical order:
        { "material_type": ..., "lines": [{qty, sku, description, note}, ...], "qty_total": int }
    """
    if not lines:
        return []

    by_type: dict[str, list[int]] = {}
    for line in lines:
        by_type.setdefault(line["material_type"], []).append(line["material_id"])

    name_map: dict[tuple[str, int], tuple[str, str | None]] = {}
    for material_type, ids in by_type.items():
        if material_type not in _TYPE_MAP:
            continue
        table, pk, name_col, sku_col = _TYPE_MAP[material_type]
        rows = db.execute(
            text(f"SELECT {pk} AS mid, {name_col} AS name, {sku_col} AS sku "
                 f"FROM {table} WHERE {pk} = ANY(:ids)"),
            {"ids": ids},
        ).mappings().all()
        for r in rows:
            name_map[(material_type, r["mid"])] = (r["name"], r["sku"])

    # Build groups in canonical order matching _TYPE_MAP keys.
    groups: list[dict] = []
    for material_type in _TYPE_MAP.keys():
        type_lines = [line for line in lines if line["material_type"] == material_type]
        if not type_lines:
            continue
        enriched: list[dict] = []
        qty_total = 0
        for line in type_lines:
            name, sku = name_map.get((material_type, line["material_id"]), ("(unknown)", None))
            enriched.append({
                "qty": line["qty"], "sku": sku, "description": name, "note": line.get("note"),
            })
            qty_total += line["qty"] or 0
        groups.append({"material_type": material_type, "lines": enriched, "qty_total": qty_total})

    return groups
