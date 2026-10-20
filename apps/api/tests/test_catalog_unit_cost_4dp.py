"""`unit_cost` keeps four decimals and the API limit matches the column (migration 0078).

Code-review fix (2026-10-20): the API accepted 15 digits / 4 dp while every catalog column was
numeric(12,2): a big value was a 500 and a 4 dp value was silently rounded to cents.
"""

import pytest

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers import create_project, login

_cleanup = truncate_fixture("equipment_hire", "glass_materials", "timber_materials", "edging_materials")
pytestmark = pytest.mark.usefixtures("_cleanup")

# slug -> extra required create fields
_SLUGS = {
    "board-materials": {"code": "B1"},
    "hardware-materials": {},
    "custom-made": {"internal_ref": "C1"},
    "benchtop-materials": {"slab_id": "S1"},
    "appliances": {"model_number": "M1"},
    "equipment-hire": {"contract_ref": "H1"},
    "edging-materials": {},
    "glass-materials": {},
    "timber-materials": {},
}


def _body(slug: str, pid: int, **extra) -> dict:
    body = {"sku": f"U-{slug}", "description": f"d {slug}", **_SLUGS[slug], **extra}
    if slug == "equipment-hire":
        body["project_id"] = pid
    return body


@pytest.mark.parametrize("slug", list(_SLUGS))
def test_unit_cost_keeps_four_decimals_on_every_catalog_table(slug):
    c, _, uid = login("admin")
    pid = 0
    if slug == "equipment-hire":
        db = SessionLocal()
        try:
            pid = create_project(db, uid=uid)
        finally:
            db.close()
    r = c.post(f"/catalog/{slug}", json=_body(slug, pid, unit_cost=1.2345))
    assert r.status_code == 201, r.text
    assert r.json()["unit_cost"] == 1.2345
    mid = r.json().get("material_id") or r.json()["hire_id"]
    got = c.get(f"/catalog/{slug}/{mid}").json()
    assert got["unit_cost"] == 1.2345
    r = c.patch(f"/catalog/{slug}/{mid}", json={"unit_cost": 0.0001})
    assert r.status_code == 200 and r.json()["unit_cost"] == 0.0001


@pytest.mark.parametrize("slug", ["glass-materials", "hardware-materials"])
def test_unit_cost_over_ten_whole_digits_is_a_422_not_a_500(slug):
    c, _, _ = login("admin")
    pid = 0
    r = c.post(f"/catalog/{slug}", json=_body(slug, pid, unit_cost="12345678901.5"))
    assert r.status_code == 422, r.text
    ok = c.post(f"/catalog/{slug}", json=_body(slug, pid, unit_cost="9999999999.9999"))
    assert ok.status_code == 201, ok.text
    mid = ok.json()["material_id"]
    assert c.patch(f"/catalog/{slug}/{mid}", json={"unit_cost": "10000000000"}).status_code == 422
