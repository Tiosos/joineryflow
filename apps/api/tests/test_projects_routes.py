import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        s.execute(
            text(
                "TRUNCATE audit_log, session, project_favourites, projects, app_user, workspace RESTART IDENTITY CASCADE"
            )
        )
        s.commit()
    finally:
        s.close()


def _login(role: str):
    """Create a fresh workspace + user with the given role, return (client, workspace_id, user_id)."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"h-{suffix}"
    email = f"u-{suffix}@example.com"
    db = SessionLocal()
    try:
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'H') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, :r)
                RETURNING id
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
        ).scalar()
        db.commit()
    finally:
        db.close()
    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": email, "password": "pw"},
    )
    assert r.status_code == 200, r.text
    return c, wid, uid


def test_list_empty_returns_empty():
    c, _wid, _uid = _login("manager")
    r = c.get("/projects")
    assert r.status_code == 200
    assert r.json() == {"projects": []}


def test_create_project_defaults_pm_to_self():
    c, _wid, uid = _login("manager")
    r = c.post(
        "/projects",
        json={"project_code": "HJ-001", "name": "Block B Kitchen"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["pm_id"] == uid
    assert data["project_code"] == "HJ-001"
    assert data["item_count"] == 0
    assert data["is_favourite"] is False


def test_create_forbidden_for_editor():
    c, _wid, _uid = _login("editor")
    r = c.post(
        "/projects",
        json={"project_code": "HJ-002", "name": "Should Be Blocked"},
    )
    assert r.status_code == 403


def test_get_one_404_for_other_workspace():
    """A project whose pm_id belongs to workspace A is invisible to workspace B."""
    c_a, wid_a, uid_a = _login("manager")
    # Create project in workspace A (pm_id = uid_a, which belongs to wid_a).
    r = c_a.post(
        "/projects",
        json={"project_code": "WS-A-001", "name": "Workspace A Project"},
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    # Workspace B user tries to fetch the same project ID.
    c_b, _wid_b, _uid_b = _login("manager")
    r2 = c_b.get(f"/projects/{pid}")
    assert r2.status_code == 404


def test_patch_status_writes_audit():
    c, _wid, _uid = _login("manager")
    r = c.post(
        "/projects",
        json={"project_code": "HJ-003", "name": "Audit Test Project"},
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    r2 = c.patch(f"/projects/{pid}", json={"status": "Closed"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "Closed"

    # Verify at least one audit row with a project.patch event exists.
    db = SessionLocal()
    try:
        count = db.execute(
            text("SELECT COUNT(*) FROM audit_log WHERE event LIKE 'project.%'")
        ).scalar()
    finally:
        db.close()
    assert count >= 1


def test_list_fav_only_filters_to_favourites():
    c, _wid, uid = _login("manager")
    # Create two projects.
    r1 = c.post("/projects", json={"project_code": "FAV-001", "name": "Fav Project"})
    assert r1.status_code == 201, r1.text
    pid1 = r1.json()["id"]

    r2 = c.post("/projects", json={"project_code": "FAV-002", "name": "Not Fav"})
    assert r2.status_code == 201, r2.text

    # Pre-insert a favourite row for project 1 only.
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO project_favourites(user_id, project_id) VALUES(:u, :p)"
            ),
            {"u": uid, "p": pid1},
        )
        db.commit()
    finally:
        db.close()

    # fav_only=true should return only the favourited project.
    r3 = c.get("/projects", params={"fav_only": "true"})
    assert r3.status_code == 200, r3.text
    projects = r3.json()["projects"]
    assert len(projects) == 1
    assert projects[0]["id"] == pid1
    assert projects[0]["is_favourite"] is True


def test_patch_404_for_other_workspace():
    """PATCH from workspace B on workspace A's project must not mutate it."""
    c_a, _wid_a, _uid_a = _login("manager")
    r = c_a.post("/projects", json={"project_code": "WS-A-FIX", "name": "A's project"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    original_status = r.json()["status"]

    c_b, _wid_b, _uid_b = _login("manager")
    r2 = c_b.patch(f"/projects/{pid}", json={"status": "Closed"})
    assert r2.status_code == 404

    # Verify A's project was NOT mutated.
    r3 = c_a.get(f"/projects/{pid}")
    assert r3.json()["status"] == original_status


def test_patch_pm_id_to_other_workspace_rejected():
    """Supplying a pm_id that belongs to another workspace must be rejected with 422."""
    c_a, _wid_a, _uid_a = _login("manager")
    r = c_a.post("/projects", json={"project_code": "WS-A-PM", "name": "A's project"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    # uid_b is a user in workspace B — not in workspace A.
    _c_b, _wid_b, uid_b = _login("manager")
    r2 = c_a.patch(f"/projects/{pid}", json={"pm_id": uid_b})
    assert r2.status_code == 422


def test_patch_pm_id_explicit_null_rejected():
    """PATCH with pm_id: null must be rejected with 422 (Pydantic validator)."""
    c, _wid, _uid = _login("manager")
    r = c.post("/projects", json={"project_code": "WS-NULL", "name": "X"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r2 = c.patch(f"/projects/{pid}", json={"pm_id": None})
    assert r2.status_code == 422


def test_add_fav_then_list_with_fav_true_returns_it():
    c, _, uid = _login("manager")
    r = c.post("/projects", json={"project_code": "FAV-001", "name": "Fav project"})
    pid = r.json()["id"]

    # POST favourite
    r2 = c.post(f"/projects/{pid}/favourites")
    assert r2.status_code == 204

    # List with fav_only=true returns it
    r3 = c.get("/projects", params={"fav_only": "true"})
    assert r3.status_code == 200
    pids = [p["id"] for p in r3.json()["projects"]]
    assert pid in pids

    # ProjectOut.is_favourite is true
    r4 = c.get(f"/projects/{pid}")
    assert r4.json()["is_favourite"] is True


def test_remove_fav_idempotent_no_404():
    c, _, _ = _login("manager")
    r = c.post("/projects", json={"project_code": "FAV-002", "name": "Fav project"})
    pid = r.json()["id"]

    # DELETE on a non-favourited project: 204 (idempotent), not 404
    r2 = c.delete(f"/projects/{pid}/favourites")
    assert r2.status_code == 204

    # Add then remove twice — second remove still 204
    c.post(f"/projects/{pid}/favourites")
    r3 = c.delete(f"/projects/{pid}/favourites")
    assert r3.status_code == 204
    r4 = c.delete(f"/projects/{pid}/favourites")
    assert r4.status_code == 204


def test_fav_cross_workspace_404():
    """Workspace-B user cannot favourite workspace-A's project."""
    c_a, _, _ = _login("manager")
    r = c_a.post("/projects", json={"project_code": "WS-A-FAV", "name": "A's project"})
    pid = r.json()["id"]

    c_b, _, _ = _login("manager")
    r2 = c_b.post(f"/projects/{pid}/favourites")
    assert r2.status_code == 404
    r3 = c_b.delete(f"/projects/{pid}/favourites")
    assert r3.status_code == 404
