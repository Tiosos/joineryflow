"""Equipment Hire's UM, website and picture on `equipment_hire` (migration 0076)."""
import pytest

from app.db import SessionLocal

from .helpers import login, create_project
from .conftest import truncate_fixture

_cleanup = truncate_fixture("equipment_hire", "appliances")
pytestmark = pytest.mark.usefixtures("_cleanup")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
FIELDS = {"um": "ea", "product_website": "https://e.test/eh"}


def _project(uid):
    db = SessionLocal()
    try:
        return create_project(db, uid=uid)
    finally:
        db.close()


def _mk(c, pid, sku="eh-1", **extra):
    r = c.post("/catalog/equipment-hire", json={
        "contract_ref": sku, "sku": sku, "description": f"Hire {sku}", "project_id": pid, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_hire_fields_are_created_listed_patched_and_cleared():
    c, _, uid = login("drafter")
    row = _mk(c, _project(uid), **FIELDS)
    hid = row["hire_id"]
    assert {k: row[k] for k in FIELDS} == FIELDS and row["has_image"] is False
    assert [x["hire_id"] for x in c.get("/catalog/equipment-hire").json()["rows"]] == [hid]
    r = c.patch(f"/catalog/equipment-hire/{hid}", json={"product_website": "https://e.test/d", "um": None})
    assert r.status_code == 200 and r.json()["product_website"] == "https://e.test/d" and r.json()["um"] is None
    assert c.patch(f"/catalog/equipment-hire/{hid}", json={"um": "x" * 33}).status_code == 422


def test_other_tables_do_not_take_hire_fields():
    c, _, _ = login("drafter")
    mid = c.post("/catalog/appliances", json={"model_number": "a-1", "sku": "a-1", "description": "Oven"}).json()["material_id"]
    r = c.patch(f"/catalog/appliances/{mid}", json={"brand": "Blum"})   # every table has a UM since 0077
    assert r.status_code == 200 and "brand" not in r.json()


def test_hire_image_is_stored_served_and_removed():
    c, _, uid = login("drafter")
    hid = _mk(c, _project(uid))["hire_id"]
    assert c.get(f"/catalog/equipment-hire/{hid}/image").status_code == 404
    assert c.put(f"/catalog/equipment-hire/{hid}/image", files={"file": ("p.png", PNG)}).status_code == 204
    assert c.get(f"/catalog/equipment-hire/{hid}/image").content == PNG
    assert c.get(f"/catalog/equipment-hire/{hid}").json()["has_image"] is True
    assert c.delete(f"/catalog/equipment-hire/{hid}/image").status_code == 204
    assert c.get(f"/catalog/equipment-hire/{hid}").json()["has_image"] is False


def test_hire_image_of_another_workspace_is_a_404():
    a, _, uid = login("drafter")
    hid = _mk(a, _project(uid))["hire_id"]
    a.put(f"/catalog/equipment-hire/{hid}/image", files={"file": ("p.png", PNG)})
    b, _, _ = login("admin")
    assert b.get(f"/catalog/equipment-hire/{hid}/image").status_code == 404
    assert b.put(f"/catalog/equipment-hire/{hid}/image", files={"file": ("p.png", PNG)}).status_code == 404
    assert b.delete(f"/catalog/equipment-hire/{hid}/image").status_code == 404
    assert a.get(f"/catalog/equipment-hire/{hid}/image").content == PNG
