"""Every material kind a quote can hold is accepted where it is used.

Code-review fixes (2026-10-20): Glass is a *part* kind, so a hardware line may not be
GLASS (the 0069 CHECK refused it: a 500), and "ordered by hand" must accept every kind
that can be pending on a quote line (GLASS was missing: the line stayed pending).
"""
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers_estimating_orders import _advance_to_won, _bootstrap, _convert, _sql_scalar

pytestmark = pytest.mark.usefixtures("truncate_after")

# (kind, table, extra NOT NULL columns)
_PARTS = {
    "BOARD": ("board_materials", "code", None),
    "CUSTOM": ("custom_made", "internal_ref", None),
    "BENCHTOP": ("benchtop_materials", "slab_id", None),
    "GLASS": ("glass_materials", None, None),
    "TIMBER": ("timber_materials", None, None),
}
_HW = {
    "HARDWARE": ("hardware_materials", None),
    "APPLIANCE": ("appliances", "model_number"),
    "EDGING": ("edging_materials", None),
}


def _row(table: str, wid: int, extra_col: str | None, cost_col: str) -> int:
    sku = f"K{uuid.uuid4().hex[:8]}"
    cols = ["workspace_id", "sku", "description", cost_col]
    vals = [":w", ":sku", "'kind test'", "10"]
    if extra_col:
        cols.append(extra_col)
        vals.append(":sku")
    s = SessionLocal()
    try:
        mid = s.execute(
            text(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING material_id"),
            {"w": wid, "sku": sku},
        ).scalar()
        s.commit()
        return mid
    finally:
        s.close()


_COST = {"board_materials": "cost_per_sheet", "custom_made": "cost", "benchtop_materials": "cost_per_slab"}


def test_a_hardware_line_of_kind_glass_is_refused_never_a_500():
    # Review finding 1 claimed a 500 here (it never was one). Glass is a quote *part* kind, not a
    # hardware kind: HardwareMaterialType omits it, so the request is a plain 422 and nothing is
    # written (the 0069 CHECK on estimate_line_hardware refuses GLASS as well).
    ctx = _bootstrap()
    c = ctx["client"]
    cust = c.post("/customers", json={"name": "K"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "K"}).json()
    line = c.post(f"/revisions/{est['current_revision_id']}/lines",
                  json={"description": "L", "qty": 1}).json()
    gid = _row("glass_materials", ctx["wid"], None, "cost_per_unit")

    r = c.post(f"/lines/{line['line_id']}/hardware",
               json={"material_type": "GLASS", "material_id": gid, "qty": 1})

    assert r.status_code == 422, r.text
    assert _sql_scalar("SELECT count(*) FROM estimate_line_hardware WHERE line_id = :l",
                       l=line["line_id"]) == 0
    # the same material is fine as a part
    assert c.post(f"/lines/{line['line_id']}/parts",
                  json={"material_type": "GLASS", "material_id": gid, "qty": 1}).status_code == 201


def test_every_kind_on_a_quote_line_can_be_marked_ordered_by_hand_and_restored():
    ctx = _bootstrap()
    c = ctx["client"]
    cust = c.post("/customers", json={"name": "K"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "K"}).json()
    rid = est["current_revision_id"]
    line = c.post(f"/revisions/{rid}/lines", json={"description": "All kinds", "qty": 1}).json()
    lid = line["line_id"]
    kinds: list[tuple[str, int]] = []
    for kind, (table, extra, _) in _PARTS.items():
        mid = _row(table, ctx["wid"], extra, _COST.get(table, "cost_per_unit"))
        r = c.post(f"/lines/{lid}/parts", json={"material_type": kind, "material_id": mid, "qty": 1})
        assert r.status_code == 201, (kind, r.text)
        kinds.append((kind, mid))
    for kind, (table, extra) in _HW.items():
        mid = _row(table, ctx["wid"], extra, "cost_per_unit")
        r = c.post(f"/lines/{lid}/hardware", json={"material_type": kind, "material_id": mid, "qty": 1})
        assert r.status_code == 201, (kind, r.text)
        kinds.append((kind, mid))
    _advance_to_won(c, rid)
    _convert(c, rid)

    base = f"/revisions/{rid}/lines/{lid}/materials"
    for kind, mid in kinds:
        r = c.post(f"{base}/{kind}/{mid}/order-dismissal", json={"reason": "by hand"})
        assert r.status_code == 204, (kind, r.status_code, r.text)
    # every material is settled, so the line is done
    s = SessionLocal()
    try:
        assert s.execute(
            text("SELECT orders_dismissed_at IS NOT NULL FROM estimate_line WHERE line_id = :l"),
            {"l": lid}).scalar() is True
    finally:
        s.close()
    for kind, mid in kinds:
        assert c.delete(f"{base}/{kind}/{mid}/order-dismissal").status_code == 204, kind
