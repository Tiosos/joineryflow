"""Material catalog snapshot resolvers and shared stage/type constants.

Part of the estimating queries facade (see `queries.py`)."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


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
    generation typically happens well after the quote was priced.

    **Archived rows are resolved too** (flagged `archived`): a quote that priced
    a material before it was archived still needs it ordered, and treating the
    row as missing would send it to "unassigned" with its stale snapshot even
    when it is linked to a supplier."""
    cfg = _CATALOG_BY_TYPE.get(material_type)
    if cfg is None or not material_ids:
        return {}
    table, id_col, sku_col, _supplier_col, cost_col = cfg
    sql = text(
        f"""
        SELECT t.{id_col} AS material_id, t.{sku_col} AS sku, t.description,
               t.{cost_col} AS cost,
               t.default_supplier_id AS supplier_id, v.name AS supplier_name,
               (t.archived_at IS NOT NULL) AS archived
          FROM {table} t
          LEFT JOIN vendors v
            ON v.vendor_id = t.default_supplier_id AND v.workspace_id = :w
         WHERE t.{id_col} = ANY(:ids) AND t.workspace_id = :w
        """
    )
    rows = db.execute(sql, {"ids": material_ids, "w": workspace_id}).mappings().all()
    return {int(r["material_id"]): dict(r) for r in rows}
