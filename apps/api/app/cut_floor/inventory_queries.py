"""Board sheet-stock queries (migration 0025).

`board_inventory` counts physical sheets per (board material, sheet size) so
the optimiser can default its sheet dimensions from real stock and report when
a nest needs more sheets than the workspace holds.

Read-only as far as `/optimise` is concerned — nothing here reserves or
decrements stock; only the explicit CRUD routes mutate it.

Routes own the transaction boundary; queries flush only.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


_SELECT = """
    SELECT bi.inventory_id, bi.material_id, bi.len_mm, bi.wid_mm,
           bi.qty_on_hand, bi.location, bi.notes,
           bi.created_at, bi.updated_at,
           bm.sku         AS material_sku,
           bm.description AS material_description,
           bm.grain_locked
      FROM board_inventory bi
      JOIN board_materials bm ON bm.material_id = bi.material_id
"""


def list_inventory(
    db: Session,
    *,
    workspace_id: int,
    material_sku: str | None = None,
    in_stock_only: bool = False,
) -> list[dict]:
    conds = ["bi.workspace_id = :w"]
    params: dict[str, Any] = {"w": workspace_id}
    if material_sku:
        conds.append("bm.sku = :sku")
        params["sku"] = material_sku
    if in_stock_only:
        conds.append("bi.qty_on_hand > 0")
    rows = db.execute(
        text(
            _SELECT
            + f" WHERE {' AND '.join(conds)}"
            + " ORDER BY bm.sku, bi.len_mm DESC, bi.wid_mm DESC"
        ),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


def get_inventory(
    db: Session, *, workspace_id: int, inventory_id: int
) -> dict | None:
    row = db.execute(
        text(_SELECT + " WHERE bi.inventory_id = :iid AND bi.workspace_id = :w"),
        {"iid": inventory_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def material_by_sku(
    db: Session, *, workspace_id: int, sku: str
) -> int | None:
    """Resolve a board material SKU to its id, workspace-scoped."""
    row = db.execute(
        text(
            "SELECT material_id FROM board_materials "
            "WHERE workspace_id = :w AND sku = :sku"
        ),
        {"w": workspace_id, "sku": sku},
    ).first()
    return row[0] if row else None


def upsert_inventory(
    db: Session,
    *,
    workspace_id: int,
    material_id: int,
    len_mm: int,
    wid_mm: int,
    qty_on_hand: int,
    location: str | None,
    notes: str | None,
    actor_id: int,
) -> int:
    """Create the (material, size) stock row, or set its quantity if it already
    exists. The UNIQUE constraint makes this the natural 'record stock' verb —
    callers should not have to know whether the row exists yet."""
    return db.execute(
        text(
            """
            INSERT INTO board_inventory(
                workspace_id, material_id, len_mm, wid_mm,
                qty_on_hand, location, notes, created_by
            )
            VALUES (:w, :mid, :len, :wid, :qty, :loc, :notes, :a)
            ON CONFLICT (workspace_id, material_id, len_mm, wid_mm)
            DO UPDATE SET qty_on_hand = EXCLUDED.qty_on_hand,
                          location    = COALESCE(EXCLUDED.location, board_inventory.location),
                          notes       = COALESCE(EXCLUDED.notes, board_inventory.notes),
                          updated_at  = now()
            RETURNING inventory_id
            """
        ),
        {
            "w": workspace_id, "mid": material_id, "len": len_mm, "wid": wid_mm,
            "qty": qty_on_hand, "loc": location, "notes": notes, "a": actor_id,
        },
    ).scalar()


_PATCHABLE: frozenset[str] = frozenset({"qty_on_hand", "location", "notes"})


def patch_inventory(
    db: Session, *, workspace_id: int, inventory_id: int, fields: dict[str, Any]
) -> int | None:
    use = {k: v for k, v in fields.items() if k in _PATCHABLE}
    if not use:
        return inventory_id
    sets = ", ".join(f"{c} = :{c}" for c in use)
    return db.execute(
        text(
            f"UPDATE board_inventory SET {sets}, updated_at = now() "
            "WHERE inventory_id = :iid AND workspace_id = :w "
            "RETURNING inventory_id"
        ),
        {**use, "iid": inventory_id, "w": workspace_id},
    ).scalar()


def delete_inventory(
    db: Session, *, workspace_id: int, inventory_id: int
) -> bool:
    res = db.execute(
        text(
            "DELETE FROM board_inventory "
            "WHERE inventory_id = :iid AND workspace_id = :w"
        ),
        {"iid": inventory_id, "w": workspace_id},
    )
    db.flush()
    return (res.rowcount or 0) > 0


# ---- Optimiser support -----------------------------------------------------

def best_stock_for_sku(
    db: Session, *, workspace_id: int, sku: str
) -> dict | None:
    """The sheet size to nest on for `sku`, chosen from stock on hand.

    Picks the largest in-stock sheet (by area), tie-broken by quantity: a
    bigger sheet yields better nesting, and where sizes tie we prefer the pile
    we have most of. Returns None when the SKU is unknown or wholly out of
    stock — the caller then falls back to explicitly supplied dimensions."""
    row = db.execute(
        text(
            """
            SELECT bi.len_mm, bi.wid_mm, bi.qty_on_hand
              FROM board_inventory bi
              JOIN board_materials bm ON bm.material_id = bi.material_id
             WHERE bi.workspace_id = :w
               AND bm.sku = :sku
               AND bi.qty_on_hand > 0
             ORDER BY (bi.len_mm::bigint * bi.wid_mm) DESC, bi.qty_on_hand DESC
             LIMIT 1
            """
        ),
        {"w": workspace_id, "sku": sku},
    ).mappings().first()
    return dict(row) if row else None


def total_sheets_for_size(
    db: Session, *, workspace_id: int, sku: str, len_mm: float, wid_mm: float
) -> int:
    """Sheets on hand of exactly this size — used to report a shortfall when a
    nest needs more sheets than the workspace holds. Sizes are compared as
    integers because stock is recorded in whole millimetres."""
    row = db.execute(
        text(
            """
            SELECT COALESCE(SUM(bi.qty_on_hand), 0)
              FROM board_inventory bi
              JOIN board_materials bm ON bm.material_id = bi.material_id
             WHERE bi.workspace_id = :w
               AND bm.sku = :sku
               AND bi.len_mm = :len
               AND bi.wid_mm = :wid
            """
        ),
        {"w": workspace_id, "sku": sku, "len": int(len_mm), "wid": int(wid_mm)},
    ).first()
    return int(row[0]) if row else 0
