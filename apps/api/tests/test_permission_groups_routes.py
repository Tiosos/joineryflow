"""Tests for the RBAC-engine admin CRUD API (Plan V1 §3.4, Q466-473)."""
import uuid

import pytest
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.auth.rbac_engine import seed_system_groups
from app.db import SessionLocal

from .helpers import login



pytestmark = pytest.mark.usefixtures("truncate_after")


def _login(role: str = "admin"):
    c, wid, _ = login(role)
    return c, wid



def _seed_groups(wid: int) -> None:
    db = SessionLocal()
    try:
        seed_system_groups(db, workspace_id=wid)
        db.commit()
    finally:
        db.close()


def _group_id(wid: int, name: str) -> int:
    db = SessionLocal()
    try:
        return db.execute(
            text("SELECT group_id FROM permission_group WHERE workspace_id=:w AND name=:n"),
            {"w": wid, "n": name},
        ).scalar()
    finally:
        db.close()


# --- access control --------------------------------------------------------

def test_non_admin_cannot_list_groups():
    c, wid = _login(role="drafter")
    r = c.get("/permission-groups")
    assert r.status_code == 403


def test_manager_can_read_but_not_write():
    c, wid = _login(role="manager")
    assert c.get("/permission-groups").status_code == 200
    r = c.post("/permission-groups", json={"name": "new-group"})
    assert r.status_code == 403


def test_admin_can_read_and_write():
    c, wid = _login(role="admin")
    assert c.get("/permission-groups").status_code == 200
    r = c.post("/permission-groups", json={"name": "kitchen-team"})
    assert r.status_code == 201


# --- group CRUD -------------------------------------------------------------

def test_list_groups_returns_seeded_system_groups_with_grants():
    c, wid = _login(role="admin")
    _seed_groups(wid)
    rows = c.get("/permission-groups").json()
    names = {r["name"] for r in rows}
    assert names == {"admin", "manager", "editor", "drafter", "estimator", "purchase_officer", "viewer"}
    admin_row = next(r for r in rows if r["name"] == "admin")
    assert admin_row["is_system"] is True
    # 12 modules x 4 actions since migration 0039 added qc (was 11 x 4 = 44).
    assert len(admin_row["grants"]) == 48


def test_create_group_duplicate_name_returns_existing_id():
    c, wid = _login(role="admin")
    r1 = c.post("/permission-groups", json={"name": "kitchen-team"})
    gid = r1.json()["group_id"]
    r2 = c.post("/permission-groups", json={"name": "kitchen-team"})
    assert r2.status_code == 409
    assert r2.json()["detail"]["group_id"] == gid


def test_set_grants_replaces_full_set():
    c, wid = _login(role="admin")
    gid = c.post("/permission-groups", json={"name": "kitchen-team"}).json()["group_id"]
    r = c.put(
        f"/permission-groups/{gid}/grants",
        json={"grants": [{"module": "tracking", "action": "read"}, {"module": "tracking", "action": "write"}]},
    )
    assert r.status_code == 200
    assert {(g["module"], g["action"]) for g in r.json()["grants"]} == {("tracking", "read"), ("tracking", "write")}

    # Replacing again drops what isn't listed.
    r2 = c.put(
        f"/permission-groups/{gid}/grants",
        json={"grants": [{"module": "catalog", "action": "read"}]},
    )
    assert {(g["module"], g["action"]) for g in r2.json()["grants"]} == {("catalog", "read")}


def test_set_grants_rejects_unknown_module():
    c, wid = _login(role="admin")
    gid = c.post("/permission-groups", json={"name": "kitchen-team"}).json()["group_id"]
    r = c.put(
        f"/permission-groups/{gid}/grants",
        json={"grants": [{"module": "not_a_module", "action": "read"}]},
    )
    assert r.status_code == 422


def test_delete_group_blocks_system_group():
    c, wid = _login(role="admin")
    _seed_groups(wid)
    gid = _group_id(wid, "viewer")
    r = c.delete(f"/permission-groups/{gid}")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "SYSTEM_GROUP"


def test_delete_group_blocks_when_it_has_members():
    c, wid = _login(role="admin")
    gid = c.post("/permission-groups", json={"name": "kitchen-team"}).json()["group_id"]
    other_uid = _make_workspace_user(wid, "viewer")
    c.post(f"/permission-groups/{gid}/memberships", json={"user_id": other_uid})
    r = c.delete(f"/permission-groups/{gid}")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "GROUP_HAS_MEMBERS"


def test_delete_group_succeeds_when_empty():
    c, wid = _login(role="admin")
    gid = c.post("/permission-groups", json={"name": "kitchen-team"}).json()["group_id"]
    r = c.delete(f"/permission-groups/{gid}")
    assert r.status_code == 204


# --- memberships ------------------------------------------------------------

def _make_workspace_user(wid: int, role: str) -> int:
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]
        uid = db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'Member', :p, :r) RETURNING id
                """
            ),
            {"w": wid, "e": f"m-{suffix}@t", "p": hash_password("x"), "r": role},
        ).scalar()
        db.commit()
        return uid
    finally:
        db.close()


def test_create_membership_workspace_wide():
    c, wid = _login(role="admin")
    gid = c.post("/permission-groups", json={"name": "kitchen-team"}).json()["group_id"]
    uid = _make_workspace_user(wid, "viewer")
    r = c.post(f"/permission-groups/{gid}/memberships", json={"user_id": uid})
    assert r.status_code == 201
    assert r.json()["project_id"] is None


def test_create_membership_rejects_foreign_user():
    c, wid = _login(role="admin")
    gid = c.post("/permission-groups", json={"name": "kitchen-team"}).json()["group_id"]
    other_c, other_wid = _login(role="admin")
    other_uid = _make_workspace_user(other_wid, "viewer")
    r = c.post(f"/permission-groups/{gid}/memberships", json={"user_id": other_uid})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UNKNOWN_USER"


def test_create_membership_rejects_foreign_project():
    c, wid = _login(role="admin")
    gid = c.post("/permission-groups", json={"name": "kitchen-team"}).json()["group_id"]
    uid = _make_workspace_user(wid, "viewer")
    other_c, other_wid = _login(role="admin")
    db = SessionLocal()
    try:
        other_pid = db.execute(
            text("INSERT INTO projects(project_code, name, workspace_id) VALUES ('X','X',:w) RETURNING project_id"),
            {"w": other_wid},
        ).scalar()
        db.commit()
    finally:
        db.close()
    r = c.post(f"/permission-groups/{gid}/memberships", json={"user_id": uid, "project_id": other_pid})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UNKNOWN_PROJECT"


def test_create_membership_duplicate_returns_existing():
    c, wid = _login(role="admin")
    gid = c.post("/permission-groups", json={"name": "kitchen-team"}).json()["group_id"]
    uid = _make_workspace_user(wid, "viewer")
    r1 = c.post(f"/permission-groups/{gid}/memberships", json={"user_id": uid})
    mid = r1.json()["membership_id"]
    r2 = c.post(f"/permission-groups/{gid}/memberships", json={"user_id": uid})
    assert r2.status_code == 409
    assert r2.json()["detail"]["membership_id"] == mid


def test_delete_membership():
    c, wid = _login(role="admin")
    gid = c.post("/permission-groups", json={"name": "kitchen-team"}).json()["group_id"]
    uid = _make_workspace_user(wid, "viewer")
    mid = c.post(f"/permission-groups/{gid}/memberships", json={"user_id": uid}).json()["membership_id"]
    assert c.delete(f"/permission-groups/memberships/{mid}").status_code == 204
    assert c.delete(f"/permission-groups/memberships/{mid}").status_code == 404


def test_list_user_memberships():
    c, wid = _login(role="admin")
    _seed_groups(wid)
    uid = _make_workspace_user(wid, "viewer")
    viewer_gid = _group_id(wid, "viewer")
    c.post(f"/permission-groups/{viewer_gid}/memberships", json={"user_id": uid})
    rows = c.get(f"/permission-groups/users/{uid}/memberships").json()
    assert len(rows) == 1
    assert rows[0]["group_name"] == "viewer"
