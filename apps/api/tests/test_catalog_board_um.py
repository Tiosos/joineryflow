"""Board's `um` on `board_materials` (migration 0075). Laminate is a tab over the same table (no table of its own)."""
import pytest

from .helpers import login
from .conftest import truncate_fixture

_cleanup = truncate_fixture("board_materials", "hardware_materials")
pytestmark = pytest.mark.usefixtures("_cleanup")


def _mk(c, code="L-1", **extra):
    r = c.post("/catalog/board-materials",
               json={"code": code, "sku": code.lower(), "description": f"Lam {code}", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_board_um_is_created_listed_patched_and_cleared():
    c, _, _ = login("drafter")
    row = _mk(c, um="sht", colour="White")
    mid = row["material_id"]
    assert row["um"] == "sht"
    assert [x["um"] for x in c.get("/catalog/board-materials").json()["rows"]] == ["sht"]
    r = c.patch(f"/catalog/board-materials/{mid}", json={"um": "m2"})
    assert r.status_code == 200 and r.json()["um"] == "m2" and r.json()["colour"] == "White"
    r = c.patch(f"/catalog/board-materials/{mid}", json={"um": None})            # null clears only what it names
    assert r.status_code == 200 and r.json()["um"] is None and r.json()["colour"] == "White"
    assert c.patch(f"/catalog/board-materials/{mid}", json={"um": "x" * 33}).status_code == 422


def test_laminate_typed_board_row_shows_um_in_by_type():
    c, _, _ = login("drafter")
    mid = _mk(c, product_type="Laminate", um="sht", colour="Oak")["material_id"]
    groups = c.get("/catalog/by-type", params={"product_type": "Laminate"}).json()["groups"]
    rows = [r for g in groups for r in g["rows"]]
    assert [(r["material_id"], r["um"], r["colour"]) for r in rows] == [(mid, "sht", "Oak")]


def test_other_tables_ignore_board_um():
    c, _, _ = login("drafter")
    mid = c.post("/catalog/hardware-materials", json={"sku": "hw-um", "description": "Hinge"}).json()["material_id"]
    r = c.patch(f"/catalog/hardware-materials/{mid}", json={"um": "ea"})        # Hardware has its own um (0072)
    assert r.status_code == 200 and r.json()["um"] == "ea"
    a = c.post("/catalog/appliances", json={"model_number": "a-1", "sku": "a-1", "description": "Oven"}).json()["material_id"]
    r = c.patch(f"/catalog/appliances/{a}", json={"um": "ea"})
    assert r.status_code == 200 and "um" not in r.json()
