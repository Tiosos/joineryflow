"""Generate a Material Take's starting lines from an item's live data (spec §4).

`estimate_sheets` and `pick_sheet_size` are pure and hold the arithmetic
Q581 decided; `generate_lines` is the one read of the database. Generation
never writes — not parts, not hardware lines, not stock (Q501), not the nest.

Boards are counted in **sheets**, not parts: the existing project rollup's
`SUM(parts.qty)` is a part count, and nobody orders "12 parts" of board.
Per item the count is fractional; whole sheets happen once, at the summary.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..procurement_v1.materials.queries import _CATALOG_LOOKUP


@dataclass(frozen=True)
class SheetSize:
    len_mm: int
    wid_mm: int

    @property
    def area(self) -> int:
        return self.len_mm * self.wid_mm


_CENT = Decimal("0.01")


def estimate_sheets(area_mm2: int, sheet: SheetSize | None) -> tuple[str, Decimal]:
    """(unit, qty) for a board: **fractional** sheets when a size is known,
    else m², both rounded *up* to 2 dp so a small part never reads as zero.

    Fractional, not whole (Q586): items share sheets, so rounding each item up
    and then adding overcounts — on the seed's ALF-001, six items' MDF would sum
    to 6 whole sheets against 3 actually needed. The summary rounds up once,
    over the project (`summary_sheets`)."""
    if sheet is None or sheet.area <= 0:
        return "m2", (Decimal(area_mm2) / Decimal(1_000_000)).quantize(_CENT, ROUND_CEILING)
    return "sheet", (Decimal(area_mm2) / Decimal(sheet.area)).quantize(_CENT, ROUND_CEILING)


def summary_sheets(fractional: list[Decimal]) -> Decimal:
    """Whole sheets to order for a project: one round-up over the sum."""
    return sum(fractional, Decimal(0)).to_integral_value(ROUND_CEILING)


def pick_sheet_size(inventory: list[tuple[int, int, int]],
                    catalog: tuple[int | None, int | None]) -> SheetSize | None:
    """Q581's order, as clarified by the plan: largest in-stock size, then
    largest recorded size (a zero-stock row still names a real size), then the
    catalog row's size, else unknown. `inventory` is (len, wid, qty_on_hand)."""
    for rows in ([r for r in inventory if r[2] > 0], inventory):
        if rows:
            ln, wd, _ = max(rows, key=lambda r: (r[0] * r[1], r[2]))
            return SheetSize(ln, wd)
    ln, wd = catalog
    if ln and wd:
        return SheetSize(ln, wd)
    return None


def _descriptions(db: Session, keys: set[tuple[str, int]]) -> dict[tuple[str, int], str]:
    out: dict[tuple[str, int], str] = {}
    by_type: dict[str, list[int]] = {}
    for mt, mid in keys:
        by_type.setdefault(mt, []).append(mid)
    for mt, ids in by_type.items():
        table, id_col, name_col, sku_col = _CATALOG_LOOKUP[mt]
        for r in db.execute(text(
            f"SELECT {id_col} AS id, {name_col} AS name, {sku_col} AS sku "
            f"FROM {table} WHERE {id_col} = ANY(:ids)"), {"ids": ids}).mappings():
            out[(mt, r["id"])] = r["name"] or r["sku"] or f"{mt} #{r['id']}"
    return out


def generate_lines(db: Session, item_id: int, workspace_id: int) -> list[dict]:
    """The generated lines for one Joinery Item, in a stable order."""
    boards = db.execute(text("""
        SELECT p.board_material_id AS mid,
               SUM(COALESCE(p.len_mm, 0)::bigint * COALESCE(p.wid_mm, 0) * COALESCE(p.qty, 0)) AS area,
               bm.sheet_len_mm, bm.sheet_wid_mm
          FROM parts p
          JOIN modules m ON m.module_id = p.module_id
          JOIN board_materials bm ON bm.material_id = p.board_material_id
         WHERE m.item_id = :i AND p.board_material_id IS NOT NULL
         GROUP BY p.board_material_id, bm.sheet_len_mm, bm.sheet_wid_mm
         ORDER BY p.board_material_id"""), {"i": item_id}).mappings().all()

    stock: dict[int, list[tuple[int, int, int]]] = {}
    if boards:
        for r in db.execute(text("""
            SELECT material_id, len_mm, wid_mm, qty_on_hand FROM board_inventory
             WHERE workspace_id = :w AND material_id = ANY(:ids)"""),
                {"w": workspace_id, "ids": [b["mid"] for b in boards]}):
            stock.setdefault(r[0], []).append((r[1], r[2], r[3]))

    hardware = db.execute(text("""
        SELECT phc.material_type AS mt, phc.material_id AS mid, SUM(ihl.qty) AS qty
          FROM item_hardware_lines ihl
          JOIN project_hardware_catalog phc ON phc.catalog_id = ihl.catalog_id
         WHERE ihl.item_id = :i
         GROUP BY phc.material_type, phc.material_id
         ORDER BY phc.material_type, phc.material_id"""), {"i": item_id}).mappings().all()

    names = _descriptions(db, {("BOARD", b["mid"]) for b in boards}
                          | {(h["mt"], h["mid"]) for h in hardware})

    lines: list[dict] = []
    for b in boards:
        size = pick_sheet_size(stock.get(b["mid"], []), (b["sheet_len_mm"], b["sheet_wid_mm"]))
        unit, qty = estimate_sheets(int(b["area"]), size)
        lines.append(_line("BOARD", b["mid"], names[("BOARD", b["mid"])], unit, qty))
    for h in hardware:
        lines.append(_line(h["mt"], h["mid"], names.get((h["mt"], h["mid"]), f"{h['mt']} #{h['mid']}"),
                           "each", Decimal(h["qty"] or 0)))
    return lines


def _line(mt: str, mid: int, desc: str, unit: str, qty: Decimal) -> dict:
    return {"material_type": mt, "material_id": mid, "description": desc, "unit": unit,
            "qty_generated": qty, "wastage_pct": Decimal(0), "qty": qty,
            "source": "generated", "note": None}


def generated_signature(lines: list[dict]) -> list[tuple]:
    """What drift compares (B4): the generated lines only, never manual lines
    or a person's adjusted qty / wastage."""
    return sorted((l["material_type"], l["material_id"], l["unit"], Decimal(l["qty_generated"]))
                  for l in lines if l["source"] == "generated")
