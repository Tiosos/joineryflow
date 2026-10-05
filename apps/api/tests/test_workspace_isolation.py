"""Cross-workspace isolation tests for the projects.workspace_id direct FK.

These tests live independently of any module's own RBAC/CRUD suite. They
target the question this whole hardening effort exists to answer: a user in
workspace B should never see a project in workspace A, even when that project
has been orphaned (pm_id NULL) — which the legacy
`(p.pm_id IS NULL OR u.workspace_id = :w)` predicate would have leaked.

Migration 0014 added `projects.workspace_id` as a NOT NULL FK and replaced
every join-through-pm_id workspace check with `projects.workspace_id = :wid`.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import truncate_fixture


_cleanup = truncate_fixture()


def _make_workspace_and_user(role: str = "manager") -> tuple[TestClient, int, int, str]:
    """Create a fresh workspace + user with the given role and log in.

    Returns (client, workspace_id, user_id, slug).
    """
    suffix = uuid.uuid4().hex[:8]
    slug = f"iso-{suffix}"
    email = f"u-{suffix}@example.com"
    db = SessionLocal()
    try:
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'Isol') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, :r) RETURNING id
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
        ).scalar()
        db.commit()
    finally:
        db.close()
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    return c, wid, uid, slug


def _create_project_in(workspace_id: int, pm_id: int, code: str = "ISO-A1") -> int:
    """Insert a project directly via SessionLocal (bypassing HTTP) and return project_id."""
    db = SessionLocal()
    try:
        pid = db.execute(
            text(
                """
                INSERT INTO projects(project_code, name, pm_id, workspace_id)
                VALUES (:c, :n, :u, :w) RETURNING project_id
                """
            ),
            {"c": code, "n": f"Project {code}", "u": pm_id, "w": workspace_id},
        ).scalar()
        db.commit()
    finally:
        db.close()
    return pid


# ── /projects/{pid} GET ─────────────────────────────────────────────────────


def test_get_project_cross_workspace_returns_404():
    """Workspace B cannot read a project owned by Workspace A."""
    _c_a, wid_a, uid_a, _slug_a = _make_workspace_and_user()
    pid = _create_project_in(wid_a, uid_a)

    c_b, _wid_b, _uid_b, _slug_b = _make_workspace_and_user()
    r = c_b.get(f"/projects/{pid}")
    assert r.status_code == 404


def test_patch_project_cross_workspace_returns_404():
    """Workspace B cannot mutate a project owned by Workspace A."""
    _c_a, wid_a, uid_a, _slug_a = _make_workspace_and_user()
    pid = _create_project_in(wid_a, uid_a)

    c_b, _wid_b, _uid_b, _slug_b = _make_workspace_and_user()
    r = c_b.patch(f"/projects/{pid}", json={"status": "Closed"})
    assert r.status_code == 404


# ── /projects/{pid}/items GET ───────────────────────────────────────────────


def test_list_items_cross_workspace_returns_404():
    """The tracking-grid endpoint must 404 (not return rows) for a foreign workspace."""
    _c_a, wid_a, uid_a, _slug_a = _make_workspace_and_user()
    pid = _create_project_in(wid_a, uid_a)

    c_b, _wid_b, _uid_b, _slug_b = _make_workspace_and_user()
    r = c_b.get(f"/projects/{pid}/items")
    # The route resolves the project first via projects/queries.get_project,
    # which returns None for a foreign workspace → 404.
    assert r.status_code == 404


# ── /projects/{pid}/shop-drawings GET ───────────────────────────────────────


def test_list_shop_drawings_cross_workspace_returns_404():
    """The shop-drawings list must 404 for a foreign workspace."""
    _c_a, wid_a, uid_a, _slug_a = _make_workspace_and_user()
    pid = _create_project_in(wid_a, uid_a)

    c_b, _wid_b, _uid_b, _slug_b = _make_workspace_and_user()
    r = c_b.get(f"/projects/{pid}/shop-drawings")
    assert r.status_code == 404


def _draft_revision_in(workspace_id: int, uploader_id: int, pid: int) -> tuple[int, int]:
    """A shop drawing with one draft revision in `workspace_id` -> (drawing_id, revision_id)."""
    db = SessionLocal()
    try:
        blob = db.execute(
            text(
                """
                INSERT INTO file_blob(workspace_id, sha256, mime, byte_size,
                                      original_filename, storage_key, uploaded_by)
                VALUES (:w, :h, 'application/pdf', 10, 'a.pdf', 'k', :u)
                RETURNING file_blob_id
                """
            ),
            {"w": workspace_id, "h": uuid.uuid4().hex, "u": uploader_id},
        ).scalar()
        did = db.execute(
            text(
                "INSERT INTO shop_drawing(project_id, title, created_by)"
                " VALUES (:p, 'Plan', :u) RETURNING drawing_id"
            ),
            {"p": pid, "u": uploader_id},
        ).scalar()
        rid = db.execute(
            text(
                """
                INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by)
                VALUES (:d, 1, :b, 'draft', :u) RETURNING revision_id
                """
            ),
            {"d": did, "b": blob, "u": uploader_id},
        ).scalar()
        db.commit()
    finally:
        db.close()
    return did, rid


@pytest.mark.parametrize("action", ["submit", "withdraw", "approve", "reject"])
def test_revision_transitions_cross_workspace_return_404_not_403(action):
    """A foreign workspace must not learn a revision exists: the uploader/reviewer
    403 checks may only run on a revision the caller's workspace owns."""
    _c_a, wid_a, uid_a, _slug_a = _make_workspace_and_user()
    pid = _create_project_in(wid_a, uid_a)
    did, rid = _draft_revision_in(wid_a, uid_a, pid)

    c_b, _wid_b, _uid_b, _slug_b = _make_workspace_and_user("manager")
    body = {"review_note": "x"} if action == "reject" else None
    r = c_b.post(f"/shop-drawings/{did}/revisions/{rid}/{action}", json=body)
    assert r.status_code == 404, r.text
    # Indistinguishable from a revision that does not exist at all.
    ghost = c_b.post(f"/shop-drawings/{did + 1000}/revisions/{rid + 1000}/{action}", json=body)
    assert (r.status_code, r.json()) == (ghost.status_code, ghost.json())


# ── NULL-pm scenario (the legacy bypass) ────────────────────────────────────


def test_get_project_cross_workspace_404_even_after_pm_id_nulled():
    """Set pm_id NULL after creation; cross-workspace must still 404.

    This is the exact bypass migration 0014 closes: the old predicate
    `(p.pm_id IS NULL OR u.workspace_id = :w)` would have read TRUE for
    workspace B when pm_id became NULL, leaking the project. After 0014 the
    project's workspace_id column remains anchored to workspace A regardless
    of pm_id state.
    """
    _c_a, wid_a, uid_a, _slug_a = _make_workspace_and_user()
    pid = _create_project_in(wid_a, uid_a)

    # Null out pm_id (mimicking a deleted PM with ON DELETE SET NULL).
    db = SessionLocal()
    try:
        db.execute(text("UPDATE projects SET pm_id = NULL WHERE project_id = :p"),
                   {"p": pid})
        db.commit()
    finally:
        db.close()

    c_b, _wid_b, _uid_b, _slug_b = _make_workspace_and_user()
    r = c_b.get(f"/projects/{pid}")
    assert r.status_code == 404
    # PATCH must also stay denied.
    r2 = c_b.patch(f"/projects/{pid}", json={"status": "Closed"})
    assert r2.status_code == 404


def test_get_project_same_workspace_still_visible_after_pm_id_nulled():
    """Same-workspace user must still see the project after pm_id is nulled.

    This proves the workspace_id FK is the sole source of truth — losing the
    PM does not orphan the project from its own workspace.
    """
    c_a, wid_a, uid_a, _slug_a = _make_workspace_and_user()
    pid = _create_project_in(wid_a, uid_a)

    db = SessionLocal()
    try:
        db.execute(text("UPDATE projects SET pm_id = NULL WHERE project_id = :p"),
                   {"p": pid})
        db.commit()
    finally:
        db.close()

    r = c_a.get(f"/projects/{pid}")
    assert r.status_code == 200, r.text
    assert r.json()["pm_id"] is None
