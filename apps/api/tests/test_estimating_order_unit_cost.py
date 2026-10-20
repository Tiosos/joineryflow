"""Generate Orders starts an order line's price from the catalog `unit_cost`, and from the
table's own cost column only when `unit_cost` is NULL (user decision, 2026-10-20).

The quote's own snapshotted cost is a separate path and must keep reading the own column."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers_estimating_orders import _advance_to_won, _bootstrap, _convert

pytestmark = pytest.mark.usefixtures("truncate_after")

# kind -> (table, own cost column, extra NOT NULL code column, is a quote part)
_KINDS = {
    "BOARD": ("board_materials", "cost_per_sheet", "code", True),
    "CUSTOM": ("custom_made", "cost", "internal_ref", True),
    "BENCHTOP": ("benchtop_materials", "cost_per_slab", "slab_id", True),
    "GLASS": ("glass_materials", "cost_per_unit", None, True),
    "TIMBER": ("timber_materials", "cost_per_unit", None, True),
    "HARDWARE": ("hardware_materials", "cost_per_unit", None, False),
    "APPLIANCE": ("appliances", "cost_per_unit", "model_number", False),
    "EDGING": ("edging_materials", "cost_per_unit", None, False),
}
# scenario -> (unit_cost, own cost, price the order line must start from)
_SCENARIOS = {
    "unit_cost_only": ("12.3456", None, Decimal("12.3456")),
    "own_only": (None, "7.50", Decimal("7.5000")),
    "both": ("12.3456", "7.50", Decimal("12.3456")),
}


def _material(wid, vendor, table, own_col, code_col, unit_cost, own):
    sku = f"UC{uuid.uuid4().hex[:10]}"
    cols = ["workspace_id", "sku", "description", "default_supplier_id", "unit_cost", own_col]
    vals = [":w", ":sku", "'uc test'", ":v", ":uc", ":own"]
    if code_col:
        cols.append(code_col)
        vals.append(":sku")
    s = SessionLocal()
    try:
        mid = s.execute(
            text(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING material_id"),
            {"w": wid, "sku": sku, "v": vendor, "uc": unit_cost, "own": own},
        ).scalar()
        s.commit()
        return mid
    finally:
        s.close()


def _generate():
    ctx = _bootstrap()
    c = ctx["client"]
    cust = c.post("/customers", json={"name": "UC"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "UC"}).json()
    rid = est["current_revision_id"]
    line = c.post(f"/revisions/{rid}/lines", json={"description": "All", "qty": 1}).json()
    made = {}  # (kind, scenario) -> (table, material_id)
    for kind, (table, own_col, code_col, is_part) in _KINDS.items():
        for name, (uc, own, _expected) in _SCENARIOS.items():
            mid = _material(ctx["wid"], ctx["vendor_a"], table, own_col, code_col, uc, own)
            made[(kind, name)] = (table, mid)
            r = c.post(f"/lines/{line['line_id']}/{'parts' if is_part else 'hardware'}",
                       json={"material_type": kind, "material_id": mid, "qty": 2})
            assert r.status_code == 201, (kind, name, r.text)
    _advance_to_won(c, rid)
    _convert(c, rid)
    return ctx, c, rid, made


def _price(table, mid):
    s = SessionLocal()
    try:
        return s.execute(
            text("SELECT unit_price FROM po_line_items WHERE material_table = :t AND material_id = :m"),
            {"t": table, "m": mid},
        ).scalar()
    finally:
        s.close()


@pytest.mark.parametrize("kind", list(_KINDS))
def test_generate_orders_price_is_unit_cost_first_then_the_own_cost_column(kind):
    ctx, c, rid, made = _generate()
    preview = c.get(f"/revisions/{rid}/order-preview")
    assert preview.status_code == 200, preview.text
    assert c.post(f"/revisions/{rid}/generate-orders").status_code == 200
    for name, (_uc, _own, expected) in _SCENARIOS.items():
        table, mid = made[(kind, name)]
        got = _price(table, mid)
        assert got is not None, (kind, name)
        assert Decimal(got) == expected, (kind, name, got)


def test_the_order_preview_shows_the_same_price_as_the_order_line():
    ctx, c, rid, made = _generate()
    body = c.get(f"/revisions/{rid}/order-preview").json()
    shown = {(l["material_type"], l["material_id"]): Decimal(str(l["unit_cost"]))
             for g in body["groups"] for l in g["lines"]}
    for (kind, name), (_table, mid) in made.items():
        assert shown[(kind, mid)] == _SCENARIOS[name][2], (kind, name)


def test_the_quote_snapshot_still_reads_the_own_cost_column():
    ctx, c, rid, made = _generate()
    s = SessionLocal()
    try:
        for kind, (table, own_col, _code, is_part) in _KINDS.items():
            child = "estimate_line_part" if is_part else "estimate_line_hardware"
            for name, (_uc, own, _exp) in _SCENARIOS.items():
                _t, mid = made[(kind, name)]
                snap = s.execute(
                    text(f"SELECT cost_per_unit_snapshot FROM {child} WHERE material_type = :k AND material_id = :m"),
                    {"k": kind, "m": mid},
                ).scalar()
                want = Decimal("0") if own is None else Decimal(own)  # a NULL own column snapshots as 0
                assert Decimal(snap or 0) == want, (kind, name, snap)
    finally:
        s.close()
