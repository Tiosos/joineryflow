"""A PATCH takes a SKU as long as its own table's CREATE does (code-review fix, 2026-10-20).

`PatchBaseIn.sku` was capped at 64 for every table, so a valid 200-character Glass or Timber SKU
(`varchar(255)`, `CreateGlassIn` / `CreateTimberIn` allow 255) could be created but never edited.
"""
import pytest

from .conftest import truncate_fixture
from .helpers import login

_cleanup = truncate_fixture("glass_materials", "timber_materials", "edging_materials")
pytestmark = pytest.mark.usefixtures("_cleanup")


@pytest.mark.parametrize("slug,limit", [
    ("glass-materials", 255), ("timber-materials", 255), ("edging-materials", 64),
    ("hardware-materials", 64),
])
def test_patch_sku_cap_matches_the_create_cap_of_the_same_table(slug, limit):
    c, _, _ = login("admin")
    long_sku = "k" * limit
    made = c.post(f"/catalog/{slug}", json={"sku": long_sku, "description": "d"})
    assert made.status_code == 201, made.text            # the create cap is the table's cap
    mid = made.json()["material_id"]
    new_sku = "z" * limit
    r = c.patch(f"/catalog/{slug}/{mid}", json={"sku": new_sku})
    assert r.status_code == 200, r.text
    assert c.get(f"/catalog/{slug}/{mid}").json()["sku"] == new_sku
    over = c.patch(f"/catalog/{slug}/{mid}", json={"sku": "y" * (limit + 1)})
    assert over.status_code == 422


def test_other_tables_keep_the_64_character_patch_cap():
    c, _, _ = login("admin")
    mid = c.post("/catalog/custom-made", json={"internal_ref": "c1", "sku": "c1", "description": "d"}).json()["material_id"]
    assert c.patch(f"/catalog/custom-made/{mid}", json={"sku": "y" * 65}).status_code == 422
    assert c.patch(f"/catalog/custom-made/{mid}", json={"sku": "y" * 64}).status_code == 200
