"""Tests for the DB-backed permission engine (Plan V1 §3.4, Q466-473).

Covers `app.auth.rbac_engine` directly (resolution, project scoping,
most-permissive-wins, the MATRIX fallback, seeding, and the auth_role-change
membership swap) plus an HTTP-level proof that `require_permission`'s new
`project_param` actually differentiates access per project.
"""
import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.auth.permissions import MATRIX, _ALL_MODULES
from app.auth.rbac import require_permission
from app.auth.rbac_engine import (
    effective_actions,
    effective_permissions,
    seed_system_groups,
    swap_default_group_membership,
)
from app.auth.sessions import AuthUser, create_session
from app.db import SessionLocal
from app.main import app

from .conftest import TRUNCATE_TABLES


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        s.execute(text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _workspace_and_user(db, role: str = "viewer") -> tuple[int, int]:
    suffix = uuid.uuid4().hex[:8]
    wid = db.execute(
        text("INSERT INTO workspace(slug, name) VALUES (:s, 'T') RETURNING id"),
        {"s": f"w-{suffix}"},
    ).scalar()
    uid = db.execute(
        text(
            """
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'U', :p, :r) RETURNING id
            """
        ),
        {"w": wid, "e": f"u-{suffix}@t", "p": hash_password("x"), "r": role},
    ).scalar()
    return wid, uid


def _auth_user(uid: int, wid: int, role: str) -> AuthUser:
    return AuthUser(id=uid, workspace_id=wid, email="x@t", full_name="U", auth_role=role)


def _project(db, wid: int, code: str) -> int:
    return db.execute(
        text(
            "INSERT INTO projects(project_code, name, workspace_id) "
            "VALUES (:c, :c, :w) RETURNING project_id"
        ),
        {"c": code, "w": wid},
    ).scalar()


# --- fallback to the static matrix ---------------------------------------

def test_fallback_to_matrix_when_no_membership():
    """A user with zero group memberships (the common case in this test
    suite, since fresh test workspaces never go through migration 0037's
    backfill) is governed by the static matrix exactly as before."""
    db = SessionLocal()
    try:
        wid, uid = _workspace_and_user(db, role="drafter")
        db.commit()
        user = _auth_user(uid, wid, "drafter")
        assert effective_actions(db, user, "tracking") == MATRIX["drafter"]["tracking"]
        assert effective_actions(db, user, "it_management") == set()
    finally:
        db.close()


def test_membership_overrides_fallback_even_when_result_is_empty():
    """Once a user holds ANY membership, an empty result is a real "no" —
    it must not silently fall back to a matrix grant that would otherwise
    apply."""
    db = SessionLocal()
    try:
        wid, uid = _workspace_and_user(db, role="viewer")
        seed_system_groups(db, workspace_id=wid)
        gid = db.execute(
            text(
                "SELECT group_id FROM permission_group WHERE workspace_id=:w AND name='viewer'"
            ),
            {"w": wid},
        ).scalar()
        db.execute(
            text(
                "INSERT INTO user_group_membership(user_id, group_id, project_id) "
                "VALUES (:u, :g, NULL)"
            ),
            {"u": uid, "g": gid},
        )
        # Revoke tracking:read from viewer's own group so the DB and the
        # static matrix now disagree.
        db.execute(
            text("DELETE FROM group_module_grant WHERE group_id = :g AND module = 'tracking'"),
            {"g": gid},
        )
        db.commit()
        assert MATRIX["viewer"]["tracking"] == {"read"}
        user = _auth_user(uid, wid, "viewer")
        assert effective_actions(db, user, "tracking") == set()
    finally:
        db.close()


# --- seed_system_groups ---------------------------------------------------

def test_seed_system_groups_matches_matrix_exactly():
    db = SessionLocal()
    try:
        wid, _ = _workspace_and_user(db, role="admin")
        seed_system_groups(db, workspace_id=wid)
        db.commit()
        for role in MATRIX:
            gid = db.execute(
                text(
                    "SELECT group_id FROM permission_group WHERE workspace_id=:w AND name=:n"
                ),
                {"w": wid, "n": role},
            ).scalar()
            assert gid is not None, role
            got = {
                (m, a)
                for m, a in db.execute(
                    text("SELECT module, action FROM group_module_grant WHERE group_id=:g"),
                    {"g": gid},
                ).all()
            }
            want = {(m, a) for m in _ALL_MODULES for a in MATRIX[role].get(m, set())}
            assert got == want, role
    finally:
        db.close()


def test_seed_system_groups_is_idempotent():
    db = SessionLocal()
    try:
        wid, _ = _workspace_and_user(db, role="admin")
        seed_system_groups(db, workspace_id=wid)
        seed_system_groups(db, workspace_id=wid)
        db.commit()
        count = db.execute(
            text("SELECT count(*) FROM permission_group WHERE workspace_id=:w"), {"w": wid}
        ).scalar()
        assert count == 7
    finally:
        db.close()


# --- project scoping (Q466) -----------------------------------------------

def test_project_scoped_membership_does_not_grant_elsewhere():
    db = SessionLocal()
    try:
        wid, uid = _workspace_and_user(db, role="viewer")
        pid_a = _project(db, wid, "A-1")
        pid_b = _project(db, wid, "B-1")
        gid = db.execute(
            text(
                "INSERT INTO permission_group(workspace_id, name, is_system) "
                "VALUES (:w, 'kitchen-team', false) RETURNING group_id"
            ),
            {"w": wid},
        ).scalar()
        db.execute(
            text("INSERT INTO group_module_grant(group_id, module, action) VALUES (:g, 'tracking', 'write')"),
            {"g": gid},
        )
        db.execute(
            text(
                "INSERT INTO user_group_membership(user_id, group_id, project_id) "
                "VALUES (:u, :g, :p)"
            ),
            {"u": uid, "g": gid, "p": pid_a},
        )
        db.commit()
        user = _auth_user(uid, wid, "viewer")
        assert "write" in effective_actions(db, user, "tracking", pid_a)
        assert "write" not in effective_actions(db, user, "tracking", pid_b)
        assert "write" not in effective_actions(db, user, "tracking", None)
    finally:
        db.close()


def test_most_permissive_wins_across_groups():
    db = SessionLocal()
    try:
        wid, uid = _workspace_and_user(db, role="viewer")
        g1 = db.execute(
            text("INSERT INTO permission_group(workspace_id,name,is_system) VALUES (:w,'g1',false) RETURNING group_id"),
            {"w": wid},
        ).scalar()
        g2 = db.execute(
            text("INSERT INTO permission_group(workspace_id,name,is_system) VALUES (:w,'g2',false) RETURNING group_id"),
            {"w": wid},
        ).scalar()
        db.execute(text("INSERT INTO group_module_grant(group_id,module,action) VALUES (:g,'tracking','read')"), {"g": g1})
        db.execute(text("INSERT INTO group_module_grant(group_id,module,action) VALUES (:g,'tracking','write')"), {"g": g2})
        db.execute(text("INSERT INTO user_group_membership(user_id,group_id,project_id) VALUES (:u,:g,NULL)"), {"u": uid, "g": g1})
        db.execute(text("INSERT INTO user_group_membership(user_id,group_id,project_id) VALUES (:u,:g,NULL)"), {"u": uid, "g": g2})
        db.commit()
        user = _auth_user(uid, wid, "viewer")
        assert effective_actions(db, user, "tracking") == {"read", "write"}
    finally:
        db.close()


# --- swap_default_group_membership (Q468, auth_role change) --------------

def test_swap_default_group_membership_moves_grants():
    db = SessionLocal()
    try:
        wid, uid = _workspace_and_user(db, role="viewer")
        seed_system_groups(db, workspace_id=wid)
        viewer_gid = db.execute(
            text("SELECT group_id FROM permission_group WHERE workspace_id=:w AND name='viewer'"),
            {"w": wid},
        ).scalar()
        db.execute(
            text("INSERT INTO user_group_membership(user_id,group_id,project_id) VALUES (:u,:g,NULL)"),
            {"u": uid, "g": viewer_gid},
        )
        db.commit()
        assert effective_actions(db, _auth_user(uid, wid, "viewer"), "tracking") == {"read"}

        swap_default_group_membership(
            db, workspace_id=wid, user_id=uid, old_role="viewer", new_role="drafter"
        )
        db.commit()

        assert effective_actions(db, _auth_user(uid, wid, "drafter"), "tracking") == MATRIX["drafter"]["tracking"]
        left = db.execute(
            text("SELECT count(*) FROM user_group_membership WHERE user_id=:u"), {"u": uid}
        ).scalar()
        assert left == 1  # old membership was removed, not just superseded
    finally:
        db.close()


def test_patch_user_auth_role_change_swaps_membership_via_http():
    """End-to-end: PATCH /users/{uid} changing auth_role must not leave the
    old role's DB grants in effect."""
    db = SessionLocal()
    try:
        wid, admin_uid = _workspace_and_user(db, role="admin")
        target_uid = db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, 'target@t.example', 'Target', :p, 'viewer') RETURNING id
                """
            ),
            {"w": wid, "p": hash_password("x")},
        ).scalar()
        seed_system_groups(db, workspace_id=wid)
        viewer_gid = db.execute(
            text("SELECT group_id FROM permission_group WHERE workspace_id=:w AND name='viewer'"),
            {"w": wid},
        ).scalar()
        db.execute(
            text("INSERT INTO user_group_membership(user_id,group_id,project_id) VALUES (:u,:g,NULL)"),
            {"u": target_uid, "g": viewer_gid},
        )
        tok = create_session(db, admin_uid)
        db.commit()
    finally:
        db.close()

    c = TestClient(app)
    r = c.patch(
        f"/users/{target_uid}",
        json={"auth_role": "manager"},
        cookies={"jf_session": tok},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT g.name FROM user_group_membership m
                JOIN permission_group g ON g.group_id = m.group_id
                WHERE m.user_id = :u AND m.project_id IS NULL
                """
            ),
            {"u": target_uid},
        ).scalar()
        assert row == "manager"
    finally:
        db.close()


# --- require_permission(project_param=...) over HTTP ---------------------

def _project_scoped_app() -> FastAPI:
    a = FastAPI()

    @a.get("/projects/{pid}/widget")
    def widget(_=Depends(require_permission("tracking", "write", project_param="pid"))):
        return {"ok": True}

    return a


def test_project_param_grants_only_on_the_scoped_project():
    db = SessionLocal()
    try:
        wid, uid = _workspace_and_user(db, role="viewer")
        pid_a = _project(db, wid, "A-1")
        pid_b = _project(db, wid, "B-1")
        gid = db.execute(
            text(
                "INSERT INTO permission_group(workspace_id, name, is_system) "
                "VALUES (:w, 'kitchen-team', false) RETURNING group_id"
            ),
            {"w": wid},
        ).scalar()
        db.execute(
            text("INSERT INTO group_module_grant(group_id, module, action) VALUES (:g, 'tracking', 'write')"),
            {"g": gid},
        )
        db.execute(
            text("INSERT INTO user_group_membership(user_id, group_id, project_id) VALUES (:u, :g, :p)"),
            {"u": uid, "g": gid, "p": pid_a},
        )
        tok = create_session(db, uid)
        db.commit()
    finally:
        db.close()

    c = TestClient(_project_scoped_app())
    ok = c.get(f"/projects/{pid_a}/widget", cookies={"jf_session": tok})
    denied = c.get(f"/projects/{pid_b}/widget", cookies={"jf_session": tok})
    assert ok.status_code == 200, ok.text
    assert denied.status_code == 403


def test_project_param_omitted_falls_back_to_workspace_wide_only():
    """No project_param at all (every pre-0037 call site) must keep checking
    workspace-wide grants only — proves backward compatibility."""
    db = SessionLocal()
    try:
        wid, uid = _workspace_and_user(db, role="admin")
        tok = create_session(db, uid)
        db.commit()
    finally:
        db.close()

    a = FastAPI()

    @a.get("/it")
    def it(_=Depends(require_permission("it_management", "write"))):
        return {"ok": True}

    c = TestClient(a)
    assert c.get("/it", cookies={"jf_session": tok}).status_code == 200


# --- effective_permissions: the map /auth/me serves ------------------------

def _group(db, wid: int, name: str, grants: list[tuple[str, str]]) -> int:
    gid = db.execute(
        text(
            "INSERT INTO permission_group(workspace_id, name, is_system) "
            "VALUES (:w, :n, false) RETURNING group_id"
        ),
        {"w": wid, "n": name},
    ).scalar()
    for module, action in grants:
        db.execute(
            text("INSERT INTO group_module_grant(group_id, module, action) VALUES (:g,:m,:a)"),
            {"g": gid, "m": module, "a": action},
        )
    return gid


def _join(db, uid: int, gid: int, project_id: int | None = None) -> None:
    db.execute(
        text("INSERT INTO user_group_membership(user_id, group_id, project_id) VALUES (:u,:g,:p)"),
        {"u": uid, "g": gid, "p": project_id},
    )


def _assert_parity(db, user: AuthUser) -> dict[str, list[str]]:
    """The one-query map must equal twelve `effective_actions` calls."""
    perms = effective_permissions(db, user)
    assert set(perms) == set(_ALL_MODULES)
    for module in _ALL_MODULES:
        assert perms[module] == sorted(effective_actions(db, user, module)), module
    return perms


def test_effective_permissions_agrees_with_effective_actions():
    """Pins the two resolvers together across every fallback branch, so the
    single-query shortcut can never drift from the engine's own rule."""
    db = SessionLocal()
    try:
        # 1. zero memberships -> the MATRIX row
        wid, uid = _workspace_and_user(db, role="editor")
        user = _auth_user(uid, wid, "editor")
        perms = _assert_parity(db, user)
        assert perms["tracking"] == sorted(MATRIX["editor"]["tracking"])

        # 2. a membership whose group grants only some modules: the granted
        #    ones use the grants, every other module is a real "no" (not a
        #    fallback to the editor's MATRIX row)
        gid = _group(db, wid, "narrow", [("orderbook", "read")])
        _join(db, uid, gid)
        db.commit()
        perms = _assert_parity(db, user)
        assert perms["orderbook"] == ["read"]
        assert perms["tracking"] == []

        # 3. a project-scoped membership adds nothing to the workspace-wide map
        pid = _project(db, wid, "P-1")
        wide = _group(db, wid, "wide", [("cut_floor", "write")])
        _join(db, uid, wide, pid)
        db.commit()
        perms = _assert_parity(db, user)
        assert perms["cut_floor"] == []

        # 4. most-permissive-wins across two workspace-wide groups
        more = _group(db, wid, "more", [("orderbook", "write"), ("tracking", "read")])
        _join(db, uid, more)
        db.commit()
        perms = _assert_parity(db, user)
        assert perms["orderbook"] == ["read", "write"]
        assert perms["tracking"] == ["read"]
    finally:
        db.close()


def test_effective_permissions_project_scoped_only_membership_is_empty():
    """The ceiling Global Search already documents: a user whose only
    membership is project-scoped is DB-governed, and the workspace-wide map
    has nothing to show for them."""
    db = SessionLocal()
    try:
        wid, uid = _workspace_and_user(db, role="admin")
        pid = _project(db, wid, "P-1")
        gid = _group(db, wid, "only-here", [("tracking", "write")])
        _join(db, uid, gid, pid)
        db.commit()
        perms = effective_permissions(db, _auth_user(uid, wid, "admin"))
        assert all(v == [] for v in perms.values())
    finally:
        db.close()


def test_effective_permissions_matches_seeded_system_group_for_every_role():
    db = SessionLocal()
    try:
        for role in MATRIX:
            wid, uid = _workspace_and_user(db, role=role)
            seed_system_groups(db, workspace_id=wid)
            gid = db.execute(
                text("SELECT group_id FROM permission_group WHERE workspace_id=:w AND name=:n"),
                {"w": wid, "n": role},
            ).scalar()
            _join(db, uid, gid)
            db.commit()
            perms = _assert_parity(db, _auth_user(uid, wid, role))
            assert perms == {m: sorted(MATRIX[role].get(m, set())) for m in _ALL_MODULES}, role
    finally:
        db.close()


def test_auth_me_follows_customised_group_grants():
    """`/auth/me` feeds the tab strip and every `can()` gate: a grant an admin
    revokes must disappear from it, not linger from the static matrix."""
    db = SessionLocal()
    try:
        wid, uid = _workspace_and_user(db, role="viewer")
        seed_system_groups(db, workspace_id=wid)
        gid = db.execute(
            text("SELECT group_id FROM permission_group WHERE workspace_id=:w AND name='viewer'"),
            {"w": wid},
        ).scalar()
        _join(db, uid, gid)
        tok = create_session(db, uid)
        db.commit()
        c = TestClient(app)
        before = c.get("/auth/me", cookies={"jf_session": tok}).json()["permissions"]
        assert before["orderbook"] == ["read"]

        db.execute(
            text("DELETE FROM group_module_grant WHERE group_id=:g AND module='orderbook'"),
            {"g": gid},
        )
        db.commit()
        after = c.get("/auth/me", cookies={"jf_session": tok}).json()["permissions"]
        assert after["orderbook"] == []
        assert after["tracking"] == ["read"]
        assert set(after) == set(_ALL_MODULES)
    finally:
        db.close()
