"""Appliance's UM, website and picture on `appliances` (migration 0077)."""
import pytest

from .helpers import login
from .conftest import truncate_fixture

_cleanup = truncate_fixture("appliances", "hardware_materials")
pytestmark = pytest.mark.usefixtures("_cleanup")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
FIELDS = {"um": "ea", "product_website": "https://e.test/ap"}


def _mk(c, sku="ap-1", **extra):
    r = c.post("/catalog/appliances", json={
        "model_number": sku, "sku": sku, "description": f"Dishwasher {sku}", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_appliance_fields_are_created_listed_patched_and_cleared():
    c, _, _ = login("drafter")
    row = _mk(c, **FIELDS)
    mid = row["material_id"]
    assert {k: row[k] for k in FIELDS} == FIELDS and row["has_image"] is False
    listed = {r["material_id"]: r for r in c.get("/catalog/appliances").json()["rows"]}
    assert {k: listed[mid][k] for k in FIELDS} == FIELDS
    r = c.patch(f"/catalog/appliances/{mid}", json={"um": "Tot", "product_website": "https://e.test/x"})
    assert r.status_code == 200 and r.json()["um"] == "Tot" and r.json()["product_website"] == "https://e.test/x"
    r = c.patch(f"/catalog/appliances/{mid}", json={"product_website": None})
    assert r.status_code == 200 and r.json()["product_website"] is None and r.json()["um"] == "Tot"
    assert c.patch(f"/catalog/appliances/{mid}", json={"um": "x" * 33}).status_code == 422
    assert c.post("/catalog/appliances", json={
        "model_number": "ap-2", "sku": "ap-2", "description": "D", "um": "x" * 33}).status_code == 422


def test_other_tables_do_not_take_appliance_fields():
    c, _, _ = login("drafter")
    # Every table now has a UM, so use the field only Appliance (here) lacks: Hardware's brand is not Appliance's.
    mid = _mk(c)["material_id"]
    r = c.patch(f"/catalog/appliances/{mid}", json={"brand": "Fisher Paykel"})
    assert r.status_code == 200 and "brand" not in r.json()
    hw = c.post("/catalog/hardware-materials", json={"sku": "hw-ap", "description": "Hinge"}).json()["material_id"]
    r = c.patch(f"/catalog/hardware-materials/{hw}", json={"um": "ea"})
    assert r.status_code == 200 and r.json()["um"] == "ea"


def test_appliance_image_is_stored_served_and_removed():
    c, _, _ = login("drafter")
    mid = _mk(c)["material_id"]
    assert c.get(f"/catalog/appliances/{mid}/image").status_code == 404
    assert c.put(f"/catalog/appliances/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 204
    assert c.get(f"/catalog/appliances/{mid}/image").content == PNG
    assert c.get(f"/catalog/appliances/{mid}").json()["has_image"] is True
    assert c.delete(f"/catalog/appliances/{mid}/image").status_code == 204
    assert c.get(f"/catalog/appliances/{mid}").json()["has_image"] is False
    assert c.get(f"/catalog/appliances/{mid}/image").status_code == 404


def test_appliance_image_of_another_workspace_is_a_404():
    a, _, _ = login("drafter")
    mid = _mk(a)["material_id"]
    a.put(f"/catalog/appliances/{mid}/image", files={"file": ("p.png", PNG)})
    b, _, _ = login("admin")
    assert b.get(f"/catalog/appliances/{mid}/image").status_code == 404
    assert b.put(f"/catalog/appliances/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 404
    assert b.delete(f"/catalog/appliances/{mid}/image").status_code == 404
    assert a.get(f"/catalog/appliances/{mid}/image").content == PNG
