"""Project Detail 2.0 (migration 0036): enriched ProjectOut and close-out.

Pins: the FileMaker-era columns round-trip through PATCH / GET, the detail
payload hydrates contacts + lift access + labour hours, and close-out is
manager/admin only, once, workspace-scoped and audited.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app


def _workspace(roles=("manager",)) -> dict:
    slug = f"pe-{uuid.uuid4().hex[:8]}"
    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'PE') RETURNING id"),
                        {"s": slug}).scalar()
        for role in roles:
            s.execute(text("""INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
                              VALUES(:w,:e,:n,:p,:r)"""),
                      {"w": wid, "e": f"{role}@{slug}.test", "n": role.title(),
                       "p": hash_password("pw"), "r": role})
        pid = s.execute(text("""INSERT INTO projects(project_code,name,workspace_id,status)
                                VALUES(:c,:c,:w,'Current') RETURNING project_id"""),
                        {"c": slug.upper(), "w": wid}).scalar()
        s.commit()
    finally:
        s.close()
    return {"slug": slug, "wid": wid, "pid": pid}


def _client(ws: dict, role: str = "manager") -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": ws["slug"],
                                    "email": f"{role}@{ws['slug']}.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def ws(truncate_all):
    truncate_all()
    return _workspace(roles=("manager", "admin", "drafter"))


def test_enrichment_fields_round_trip(ws):
    c = _client(ws)
    body = {
        "builder": "Hansen Yuncken", "classification": "Health",
        "site_street": "1 Main St", "site_suburb": "Carlton",
        "site_postcode": "3053", "site_state": "VIC",
        "tg_project_manager": "Rin Park", "tg_coordinator": "Ada Lee",
    }
    r = c.patch(f"/projects/{ws['pid']}", json=body)
    assert r.status_code == 200, r.text
    assert {k: r.json()[k] for k in body} == body
    assert {k: c.get(f"/projects/{ws['pid']}").json()[k] for k in body} == body


def test_detail_hydrates_contacts_lift_access_and_labour_hours(ws):
    c = _client(ws)
    got = c.get(f"/projects/{ws['pid']}").json()
    assert got["contacts"] == []
    assert got["lift_access"] is None
    assert got["labour_hours"] == {"site_install": 0, "assembly": 0, "administration": 0}

    c.post(f"/projects/{ws['pid']}/contacts", json={"kind": "office", "name": "Pat PM"})
    c.put(f"/projects/{ws['pid']}/lift-access", json={"notes": "Goods lift, 2.4 m"})
    got = c.get(f"/projects/{ws['pid']}").json()
    assert [x["name"] for x in got["contacts"]] == ["Pat PM"]
    assert got["lift_access"]["notes"] == "Goods lift, 2.4 m"


@pytest.mark.parametrize("role", ["manager", "admin"])
def test_close_out_once(ws, role):
    c = _client(ws, role)
    r = c.post(f"/projects/{ws['pid']}/close-out")
    assert r.status_code == 200, r.text
    assert r.json()["closed_by_name"] == role.title()
    assert r.json()["closed_at"] is not None

    got = c.get(f"/projects/{ws['pid']}").json()
    assert got["status"] == "Closed"
    assert got["closed_by_name"] == role.title()

    assert c.post(f"/projects/{ws['pid']}/close-out").status_code == 409

    s = SessionLocal()
    try:
        n = s.execute(text("SELECT count(*) FROM audit_log WHERE event = 'project.close_out'"
                           " AND target = :t"), {"t": str(ws["pid"])}).scalar()
    finally:
        s.close()
    assert n == 1


def test_close_out_is_manager_or_admin_only(ws):
    assert _client(ws, "drafter").post(f"/projects/{ws['pid']}/close-out").status_code == 403
    assert _client(ws).get(f"/projects/{ws['pid']}").json()["closed_at"] is None


def test_close_out_other_workspace_is_404(ws):
    other = _workspace()
    assert _client(ws).post(f"/projects/{other['pid']}/close-out").status_code == 404
    assert _client(other).get(f"/projects/{other['pid']}").json()["closed_at"] is None


def test_patch_to_closed_is_refused_close_out_is_the_only_path(ws):
    c = _client(ws)
    r = c.patch(f"/projects/{ws['pid']}", json={"status": "Closed"})
    assert r.status_code == 422, r.text
    assert "close-out" in r.json()["detail"]
    got = c.get(f"/projects/{ws['pid']}").json()
    assert (got["status"], got["closed_at"]) == ("Current", None)


@pytest.mark.parametrize("new_status", ["Current", "Hold"])
def test_patch_status_reopens_and_clears_the_close_out_stamp(ws, new_status):
    c = _client(ws)
    assert c.post(f"/projects/{ws['pid']}/close-out").status_code == 200

    r = c.patch(f"/projects/{ws['pid']}", json={"status": new_status})
    assert r.status_code == 200, r.text
    got = r.json()
    assert (got["status"], got["closed_at"], got["closed_by"]) == (new_status, None, None)

    # Re-opened for real: it can be closed out again.
    assert c.post(f"/projects/{ws['pid']}/close-out").status_code == 200


def test_patch_without_status_keeps_the_close_out_stamp(ws):
    c = _client(ws)
    c.post(f"/projects/{ws['pid']}/close-out")
    got = c.patch(f"/projects/{ws['pid']}", json={"builder": "Late edit"}).json()
    assert got["status"] == "Closed"
    assert got["closed_at"] is not None
