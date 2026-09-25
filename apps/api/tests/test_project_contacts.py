"""Project contacts (migration 0036): office + site contacts per project.

Pins: CRUD round-trip, list order (kind, then sort_order), audit events,
validation, workspace isolation, and the tracking:{read,write} gates.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app


def _workspace(roles=("manager",)) -> dict:
    slug = f"pc-{uuid.uuid4().hex[:8]}"
    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'PC') RETURNING id"),
                        {"s": slug}).scalar()
        for role in roles:
            s.execute(text("""INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
                              VALUES(:w,:e,:n,:p,:r)"""),
                      {"w": wid, "e": f"{role}@{slug}.test", "n": role.title(),
                       "p": hash_password("pw"), "r": role})
        pid = s.execute(text("""INSERT INTO projects(project_code,name,workspace_id)
                                VALUES(:c,:c,:w) RETURNING project_id"""),
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
    return _workspace(roles=("manager", "editor", "viewer", "purchase_officer"))


def test_create_list_patch_delete_round_trip(ws):
    c = _client(ws)
    r = c.post(f"/projects/{ws['pid']}/contacts",
               json={"kind": "site", "name": "Sam Foreman", "position": "Site lead",
                     "email": "sam@builder.test", "mobile": "0400 000 000"})
    assert r.status_code == 201, r.text
    contact = r.json()
    assert (contact["kind"], contact["name"], contact["sort_order"]) == ("site", "Sam Foreman", 0)

    r = c.patch(f"/contacts/{contact['contact_id']}", json={"mobile": "0499 999 999"})
    assert r.status_code == 200, r.text
    assert r.json()["mobile"] == "0499 999 999"
    assert r.json()["email"] == "sam@builder.test"  # untouched fields survive

    r = c.patch(f"/contacts/{contact['contact_id']}", json={"email": None})
    assert r.json()["email"] is None  # an explicit null clears

    assert c.delete(f"/contacts/{contact['contact_id']}").status_code == 204
    assert c.get(f"/projects/{ws['pid']}/contacts").json() == []
    assert c.delete(f"/contacts/{contact['contact_id']}").status_code == 404

    s = SessionLocal()
    try:
        events = [r[0] for r in s.execute(text(
            "SELECT event FROM audit_log WHERE event LIKE 'project.contact.%' ORDER BY id"))]
    finally:
        s.close()
    assert events == ["project.contact.create", "project.contact.update",
                      "project.contact.update", "project.contact.delete"]


def test_list_orders_by_kind_then_sort_order(ws):
    c = _client(ws)
    for kind, name, order in (("site", "S2", 2), ("office", "O1", 1),
                              ("site", "S1", 1), ("office", "O0", 0)):
        c.post(f"/projects/{ws['pid']}/contacts",
               json={"kind": kind, "name": name, "sort_order": order})
    names = [x["name"] for x in c.get(f"/projects/{ws['pid']}/contacts").json()]
    assert names == ["O0", "O1", "S1", "S2"]


@pytest.mark.parametrize("body", [
    {"kind": "home", "name": "X"},   # kind is office | site
    {"kind": "site", "name": ""},    # name is required
    {"kind": "site"},
])
def test_invalid_contact_is_422(ws, body):
    assert _client(ws).post(f"/projects/{ws['pid']}/contacts", json=body).status_code == 422


def test_other_workspace_is_404(ws):
    other = _workspace()
    theirs = _client(other)
    cid = theirs.post(f"/projects/{other['pid']}/contacts",
                      json={"kind": "office", "name": "Theirs"}).json()["contact_id"]
    c = _client(ws)
    assert c.get(f"/projects/{other['pid']}/contacts").status_code == 404
    assert c.post(f"/projects/{other['pid']}/contacts",
                  json={"kind": "office", "name": "X"}).status_code == 404
    assert c.patch(f"/contacts/{cid}", json={"name": "Hijack"}).status_code == 404
    assert c.delete(f"/contacts/{cid}").status_code == 404
    assert theirs.get(f"/projects/{other['pid']}/contacts").json()[0]["name"] == "Theirs"


@pytest.mark.parametrize("role,status", [
    ("editor", 201), ("viewer", 403), ("purchase_officer", 403),
])
def test_write_needs_tracking_write(ws, role, status):
    c = _client(ws, role)
    assert c.get(f"/projects/{ws['pid']}/contacts").status_code == 200
    r = c.post(f"/projects/{ws['pid']}/contacts", json={"kind": "site", "name": "X"})
    assert r.status_code == status, r.text
