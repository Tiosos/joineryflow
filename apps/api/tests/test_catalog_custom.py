"""Custom's UM, website and picture on `custom_made` (migration 0073)."""
import pytest

from .helpers import login
from .conftest import truncate_fixture

_cleanup = truncate_fixture("custom_made", "appliances")
pytestmark = pytest.mark.usefixtures("_cleanup")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
FIELDS = {"um": "Tot", "product_website": "https://e.test/c"}


def _mk(c, sku="c-1", **extra):
    r = c.post("/catalog/custom-made", json={"internal_ref": sku, "sku": sku, "description": f"Custom {sku}", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_custom_fields_are_created_listed_patched_and_cleared():
    c, _, _ = login("drafter")
    row = _mk(c, **FIELDS)
    mid = row["material_id"]
    assert {k: row[k] for k in FIELDS} == FIELDS and row["has_image"] is False
    assert [x["material_id"] for x in c.get("/catalog/custom-made").json()["rows"]] == [mid]
    r = c.patch(f"/catalog/custom-made/{mid}", json={"product_website": "https://e.test/d", "um": None})
    assert r.status_code == 200 and r.json()["product_website"] == "https://e.test/d" and r.json()["um"] is None
    assert c.patch(f"/catalog/custom-made/{mid}", json={"um": "x" * 33}).status_code == 422


def test_other_tables_do_not_take_custom_fields():
    c, _, _ = login("drafter")
    mid = c.post("/catalog/appliances", json={"model_number": "a-1", "sku": "a-1", "description": "Oven"}).json()["material_id"]
    r = c.patch(f"/catalog/appliances/{mid}", json={"brand": "Blum"})   # every table has a UM since 0077
    assert r.status_code == 200 and "brand" not in r.json()


def test_custom_image_is_stored_served_and_removed():
    c, _, _ = login("drafter")
    mid = _mk(c)["material_id"]
    assert c.get(f"/catalog/custom-made/{mid}/image").status_code == 404
    assert c.put(f"/catalog/custom-made/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 204
    assert c.get(f"/catalog/custom-made/{mid}/image").content == PNG
    assert c.get(f"/catalog/custom-made/{mid}").json()["has_image"] is True
    assert c.delete(f"/catalog/custom-made/{mid}/image").status_code == 204
    assert c.get(f"/catalog/custom-made/{mid}").json()["has_image"] is False


def test_custom_image_of_another_workspace_is_a_404():
    a, _, _ = login("drafter")
    mid = _mk(a)["material_id"]
    a.put(f"/catalog/custom-made/{mid}/image", files={"file": ("p.png", PNG)})
    b, _, _ = login("admin")
    assert b.get(f"/catalog/custom-made/{mid}/image").status_code == 404
    assert b.put(f"/catalog/custom-made/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 404
    assert b.delete(f"/catalog/custom-made/{mid}/image").status_code == 404
    assert a.get(f"/catalog/custom-made/{mid}/image").content == PNG
