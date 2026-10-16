"""Laminate Benchtop's fields on `benchtop_materials` (migration 0071), as Board's (0068)."""
import pytest

from .helpers import login
from .conftest import truncate_fixture

_cleanup = truncate_fixture("benchtop_materials", "hardware_materials")
pytestmark = pytest.mark.usefixtures("_cleanup")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
TEXT = {"colour": "WHITE 200", "underside": "Aquaban", "edge_details": "Square Edge", "laminate_supplier": "Laminex",
        "laminate_code": "200", "finish": "Natural", "um": "Tot", "product_website": "https://e.test/b"}
NUMS = {"bench_length_mm": 3000, "bench_width_mm": 600, "thickness_mm": 33, "pieces": 4, "joins": 3, "cable_entry": 5}


def _mk(c, slab="b-1", **extra):
    r = c.post("/catalog/benchtop-materials",
               json={"slab_id": slab, "sku": slab, "description": f"Bench {slab}", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_benchtop_fields_are_created_listed_patched_and_cleared():
    c, _, _ = login("drafter")
    row = _mk(c, **TEXT, **NUMS, shaped=True)
    mid = row["material_id"]
    assert {k: row[k] for k in TEXT} == TEXT and row["shaped"] is True and row["has_image"] is False
    assert {k: row[k] for k in NUMS} == NUMS                                    # JSON numbers
    assert [x["material_id"] for x in c.get("/catalog/benchtop-materials").json()["rows"]] == [mid]

    r = c.patch(f"/catalog/benchtop-materials/{mid}", json={"colour": "Black", "joins": 4, "finish": None})
    assert r.status_code == 200 and r.json()["colour"] == "Black" and r.json()["joins"] == 4
    assert r.json()["finish"] is None and r.json()["underside"] == "Aquaban"     # null clears only what it names
    r = c.patch(f"/catalog/benchtop-materials/{mid}", json={"pieces": None, "bench_width_mm": None, "shaped": False})
    assert r.json()["pieces"] is None and r.json()["bench_width_mm"] is None and r.json()["shaped"] is False
    assert c.patch(f"/catalog/benchtop-materials/{mid}", json={"shaped": None}).json()["shaped"] is False   # NOT NULL
    assert c.patch(f"/catalog/benchtop-materials/{mid}", json={"cable_entry": -1}).status_code == 422
    # what the table already had keeps working
    assert c.patch(f"/catalog/benchtop-materials/{mid}", json={"grain_locked": True}).json()["grain_locked"] is True


def test_other_tables_do_not_take_benchtop_fields():
    c, _, _ = login("drafter")
    mid = c.post("/catalog/hardware-materials", json={"sku": "hw-b", "description": "Hinge"}).json()["material_id"]
    r = c.patch(f"/catalog/hardware-materials/{mid}", json={"underside": "Aquaban"})
    assert r.status_code == 200 and "underside" not in r.json()


def test_benchtop_image_is_stored_served_and_removed():
    c, _, _ = login("drafter")
    mid = _mk(c)["material_id"]
    assert c.get(f"/catalog/benchtop-materials/{mid}/image").status_code == 404
    assert c.put(f"/catalog/benchtop-materials/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 204
    assert c.get(f"/catalog/benchtop-materials/{mid}/image").content == PNG
    assert c.get(f"/catalog/benchtop-materials/{mid}").json()["has_image"] is True
    assert c.delete(f"/catalog/benchtop-materials/{mid}/image").status_code == 204
    assert c.get(f"/catalog/benchtop-materials/{mid}").json()["has_image"] is False


def test_benchtop_image_of_another_workspace_is_a_404():
    a, _, _ = login("drafter")
    mid = _mk(a)["material_id"]
    a.put(f"/catalog/benchtop-materials/{mid}/image", files={"file": ("p.png", PNG)})
    b, _, _ = login("admin")
    assert b.get(f"/catalog/benchtop-materials/{mid}/image").status_code == 404
    assert b.put(f"/catalog/benchtop-materials/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 404
    assert b.delete(f"/catalog/benchtop-materials/{mid}/image").status_code == 404
    assert a.get(f"/catalog/benchtop-materials/{mid}/image").content == PNG
