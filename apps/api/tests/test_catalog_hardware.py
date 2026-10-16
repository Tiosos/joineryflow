"""Hardware's fields on `hardware_materials` (migration 0072): brand, hardware type, UM, website, picture."""
import pytest

from .helpers import login
from .conftest import truncate_fixture

_cleanup = truncate_fixture("hardware_materials", "appliances")
pytestmark = pytest.mark.usefixtures("_cleanup")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
FIELDS = {"brand": "Blum", "hardware_type": "Hinge", "um": "ea", "product_website": "https://e.test/h"}


def _mk(c, sku="h-1", **extra):
    r = c.post("/catalog/hardware-materials", json={"sku": sku, "description": f"Hw {sku}", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_hardware_fields_are_created_listed_patched_and_cleared():
    c, _, _ = login("drafter")
    row = _mk(c, **FIELDS)
    mid = row["material_id"]
    assert {k: row[k] for k in FIELDS} == FIELDS and row["has_image"] is False
    assert [x["material_id"] for x in c.get("/catalog/hardware-materials").json()["rows"]] == [mid]
    r = c.patch(f"/catalog/hardware-materials/{mid}", json={"brand": "Hettich", "um": None})
    assert r.status_code == 200 and r.json()["brand"] == "Hettich" and r.json()["um"] is None
    assert r.json()["hardware_type"] == "Hinge"                               # null clears only what it names
    assert c.patch(f"/catalog/hardware-materials/{mid}", json={"hardware_type": "x" * 65}).status_code == 422


def test_other_tables_do_not_take_hardware_fields():
    c, _, _ = login("drafter")
    mid = c.post("/catalog/appliances", json={"model_number": "a-1", "sku": "a-1", "description": "Oven"}).json()["material_id"]
    r = c.patch(f"/catalog/appliances/{mid}", json={"brand": "Blum"})
    assert r.status_code == 200 and "brand" not in r.json()


def test_hardware_image_is_stored_served_and_removed():
    c, _, _ = login("drafter")
    mid = _mk(c)["material_id"]
    assert c.get(f"/catalog/hardware-materials/{mid}/image").status_code == 404
    assert c.put(f"/catalog/hardware-materials/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 204
    assert c.get(f"/catalog/hardware-materials/{mid}/image").content == PNG
    assert c.get(f"/catalog/hardware-materials/{mid}").json()["has_image"] is True
    assert c.delete(f"/catalog/hardware-materials/{mid}/image").status_code == 204
    assert c.get(f"/catalog/hardware-materials/{mid}").json()["has_image"] is False


def test_hardware_image_of_another_workspace_is_a_404():
    a, _, _ = login("drafter")
    mid = _mk(a)["material_id"]
    a.put(f"/catalog/hardware-materials/{mid}/image", files={"file": ("p.png", PNG)})
    b, _, _ = login("admin")
    assert b.get(f"/catalog/hardware-materials/{mid}/image").status_code == 404
    assert b.put(f"/catalog/hardware-materials/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 404
    assert b.delete(f"/catalog/hardware-materials/{mid}/image").status_code == 404
    assert a.get(f"/catalog/hardware-materials/{mid}/image").content == PNG
