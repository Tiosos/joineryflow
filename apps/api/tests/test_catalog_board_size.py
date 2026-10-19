"""Board's sheet size and thickness (`sheet_len_mm`, `sheet_wid_mm`, `thickness_mm`): columns on `board_materials` since
`0001`, shown and edited from the catalog (no migration). All nullable; JSON numbers on the wire."""
import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers import login
from .conftest import truncate_fixture

_cleanup = truncate_fixture("board_materials", "hardware_materials")
pytestmark = pytest.mark.usefixtures("_cleanup")

SIZE = ("sheet_len_mm", "sheet_wid_mm", "thickness_mm")


def _mk(c, code="BS-1", **extra):
    r = c.post("/catalog/board-materials", json={"code": code, "sku": code.lower(), "description": f"Sheet {code}", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_size_is_created_listed_patched_and_cleared_as_json_numbers():
    c, _, _ = login("drafter")
    row = _mk(c, sheet_len_mm=3600, sheet_wid_mm=1200, thickness_mm=0.7, colour="White")
    mid = row["material_id"]
    assert [row[k] for k in SIZE] == [3600, 1200, 0.7]
    assert all(isinstance(row[k], (int, float)) and not isinstance(row[k], str) for k in SIZE)   # numeric(6,2) too
    listed = c.get("/catalog/board-materials").json()["rows"][0]
    assert [listed[k] for k in SIZE] == [3600, 1200, 0.7]
    assert c.get("/catalog/by-type", params={"product_type": "Board"}).status_code == 200

    r = c.patch(f"/catalog/board-materials/{mid}", json={"thickness_mm": 18, "sheet_len_mm": 2400})
    assert r.status_code == 200
    assert [r.json()[k] for k in SIZE] == [2400, 1200, 18] and r.json()["colour"] == "White"
    r = c.patch(f"/catalog/board-materials/{mid}", json={"sheet_wid_mm": None})      # null clears only what it names
    assert r.json()["sheet_wid_mm"] is None and r.json()["sheet_len_mm"] == 2400
    r = c.patch(f"/catalog/board-materials/{mid}", json={"sheet_len_mm": None, "thickness_mm": None})
    assert [r.json()[k] for k in SIZE] == [None, None, None] and r.json()["colour"] == "White"


def test_a_board_without_a_size_still_works_and_the_size_is_null():
    c, _, _ = login("drafter")
    row = _mk(c)
    assert [row[k] for k in SIZE] == [None, None, None]


def test_invalid_sizes_are_422():
    c, _, _ = login("drafter")
    mid = _mk(c)["material_id"]
    for bad in ({"sheet_len_mm": -1}, {"sheet_wid_mm": 1200.5}, {"sheet_len_mm": "wide"}, {"sheet_len_mm": 10 ** 7},
                {"thickness_mm": -0.5}, {"thickness_mm": 12345.5}, {"thickness_mm": 0.123}):
        assert c.patch(f"/catalog/board-materials/{mid}", json=bad).status_code == 422, bad
        assert c.post("/catalog/board-materials", json={"code": "BAD", "sku": "bad", "description": "x", **bad}
                      ).status_code == 422, bad
    assert [c.get(f"/catalog/board-materials/{mid}").json()[k] for k in SIZE] == [None, None, None]


def test_other_tables_do_not_take_the_board_sheet_size():
    c, _, _ = login("drafter")
    mid = c.post("/catalog/hardware-materials", json={"sku": "hw-s", "description": "Hinge"}).json()["material_id"]
    r = c.patch(f"/catalog/hardware-materials/{mid}", json={"sheet_len_mm": 2400})
    assert r.status_code == 200 and "sheet_len_mm" not in r.json()


def test_bulk_import_stays_all_or_nothing_with_and_without_a_size():
    c, _, _ = login("drafter")
    ok = [{"code": "BK-1", "sku": "bk-1", "description": "A", "sheet_len_mm": 2400, "sheet_wid_mm": 1200, "thickness_mm": 16},
          {"code": "BK-2", "sku": "bk-2", "description": "B"}]
    r = c.post("/catalog/board-materials/bulk", json={"rows": ok})
    assert r.status_code in (200, 201) and r.json()["created"] == 2 and r.json()["errors"] == []
    rows = {x["sku"]: x for x in c.get("/catalog/board-materials").json()["rows"]}
    assert [rows["bk-1"][k] for k in SIZE] == [2400, 1200, 16] and [rows["bk-2"][k] for k in SIZE] == [None] * 3
    bad = [{"code": "BK-3", "sku": "bk-3", "description": "C"},
           {"code": "BK-4", "sku": "bk-4", "description": "D", "sheet_len_mm": -5}]
    r = c.post("/catalog/board-materials/bulk", json={"rows": bad})
    assert r.json()["created"] == 0 and [e["row_index"] for e in r.json()["errors"]] == [1]
    assert sorted(rows) == ["bk-1", "bk-2"] and len(c.get("/catalog/board-materials").json()["rows"]) == 2


def test_size_columns_are_the_ones_the_cut_plan_and_material_take_read():
    c, _, _ = login("drafter")
    mid = _mk(c, sheet_len_mm=2750, sheet_wid_mm=1830, thickness_mm=18)["material_id"]
    db = SessionLocal()
    try:
        got = db.execute(text("SELECT sheet_len_mm, sheet_wid_mm, thickness_mm FROM board_materials WHERE material_id = :m"),
                         {"m": mid}).one()
    finally:
        db.close()
    assert tuple(got) == (2750, 1830, 18)
