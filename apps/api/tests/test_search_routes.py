"""GET /search and GET /search/health (plan tasks D1, D2; spec §5)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import permissions, rbac_engine
from app.auth.rbac_engine import seed_system_groups
from app.db import SessionLocal
from app.main import app
from app.search.index import FakeIndex
from app.search.routes import search_index

from .helpers import login
from .conftest import truncate_fixture


@pytest.fixture
def index():
    fake = FakeIndex()
    app.dependency_overrides[search_index] = lambda: fake
    yield fake
    app.dependency_overrides.pop(search_index, None)


_cleanup = truncate_fixture()


def _login(role="manager"):
    c, wid, _ = login(role, prefix="srch")
    return c, wid



def _doc(i, ws, type_="item", title="Kitchen island bench", archived=False, project_id=7):
    return {"id": f"{type_}-{i}", "type": type_, "entity_id": i, "workspace_id": ws,
            "project_id": project_id, "project_code": "ALF-001", "codes": [str(297800 + i)],
            "title": title, "subtitle": "ALF-001", "body": "", "status": "LIVE",
            "archived": archived, "updated_at": 0, "url": f"/items/{i}"}


def test_requires_login(index):
    assert TestClient(app).get("/search", params={"q": "x"}).status_code == 401


def test_hits_are_trimmed_to_public_fields(index):
    c, w = _login()
    index.upsert([_doc(1, w)])
    body = c.get("/search", params={"q": "kitchen"}).json()
    assert body["total"] == 1
    assert set(body["hits"][0]) == {"type", "entity_id", "title", "subtitle", "codes",
                                    "status", "archived", "url", "project_code"}


def test_workspace_isolation(index):
    """A record in another workspace is never returned — the core guarantee."""
    c1, w1 = _login()
    c2, w2 = _login()
    index.upsert([_doc(1, w1, title="Shared words"), _doc(2, w2, title="Shared words")])
    assert [h["entity_id"] for h in c1.get("/search", params={"q": "shared"}).json()["hits"]] == [1]
    assert [h["entity_id"] for h in c2.get("/search", params={"q": "shared"}).json()["hits"]] == [2]


def test_types_param_narrows_but_counts_cover_all_readable(index):
    c, w = _login()
    index.upsert([_doc(1, w), _doc(2, w, type_="order")])
    body = c.get("/search", params={"q": "kitchen", "types": "order"}).json()
    assert [h["type"] for h in body["hits"]] == ["order"]
    assert body["type_counts"] == {"item": 1, "order": 1}


def test_unreadable_type_is_dropped_silently(index, monkeypatch):
    # `_login()`'s user has zero `user_group_membership` rows, so
    # `readable_types` (backed by the Dynamic RBAC engine) falls back to
    # `MATRIX` for them exactly as the static matrix once did directly —
    # but `rbac_engine.py` bound its own `MATRIX` name at import time
    # (`from .permissions import MATRIX`), so the fallback the engine
    # actually reads lives there, not on `permissions.MATRIX`.
    c, w = _login("viewer")
    matrix = {**permissions.MATRIX, "viewer": {**permissions.MATRIX["viewer"], "orderbook": set()}}
    monkeypatch.setattr(rbac_engine, "MATRIX", matrix)
    index.upsert([_doc(1, w), _doc(2, w, type_="order")])
    body = c.get("/search", params={"q": "kitchen"}).json()
    assert [h["type"] for h in body["hits"]] == ["item"]
    assert "order" not in body["type_counts"]
    # Asking for it explicitly is not an error and still reveals nothing.
    r = c.get("/search", params={"q": "kitchen", "types": "order"})
    assert r.status_code == 200 and r.json() == {"hits": [], "total": 0, "type_counts": {}}


def test_group_grant_revoked_via_admin_ui_hides_the_type(index):
    """The gap this closes: before, `readable_types` read the static `MATRIX`
    directly, so a workspace admin revoking `orderbook:read` from a group via
    the Permission Groups admin UI (real `group_module_grant` rows, not
    `MATRIX`) had no effect on what search shows a member of that group —
    only `effective_actions` (the Dynamic RBAC engine) sees that revocation.
    This user has a REAL `user_group_membership`, so it is governed by the
    DB, never MATRIX."""
    c, w = _login("viewer")
    db = SessionLocal()
    try:
        seed_system_groups(db, workspace_id=w)
        gid = db.execute(
            text("SELECT group_id FROM permission_group WHERE workspace_id=:w AND name='viewer'"),
            {"w": w},
        ).scalar()
        uid = db.execute(
            text("SELECT id FROM app_user WHERE workspace_id=:w"), {"w": w}
        ).scalar()
        db.execute(
            text("INSERT INTO user_group_membership(user_id, group_id, project_id)"
                 " VALUES (:u, :g, NULL)"),
            {"u": uid, "g": gid},
        )
        db.execute(
            text("DELETE FROM group_module_grant WHERE group_id = :g AND module = 'orderbook'"),
            {"g": gid},
        )
        db.commit()
    finally:
        db.close()

    index.upsert([_doc(1, w), _doc(2, w, type_="order")])
    body = c.get("/search", params={"q": "kitchen"}).json()
    assert [h["type"] for h in body["hits"]] == ["item"]
    assert "order" not in body["type_counts"]


def _member_of_custom_group(role, *, grants, project_id=None):
    """A user whose ONLY membership is a non-system group with `grants`
    (list of (module, action)), so the DB — never MATRIX — governs them."""
    c, w = _login(role)
    db = SessionLocal()
    try:
        uid = db.execute(text("SELECT id FROM app_user WHERE workspace_id=:w"), {"w": w}).scalar()
        gid = db.execute(
            text("INSERT INTO permission_group(workspace_id, name, is_system)"
                 " VALUES (:w, 'custom', false) RETURNING group_id"), {"w": w}).scalar()
        for module, action in grants:
            db.execute(text("INSERT INTO group_module_grant(group_id, module, action)"
                            " VALUES (:g, :m, :a)"), {"g": gid, "m": module, "a": action})
        pid = None
        if project_id:
            pid = db.execute(
                text("INSERT INTO projects(workspace_id, name, project_code) VALUES (:w, 'P', 'P-1')"
                     " RETURNING project_id"), {"w": w}).scalar()
        db.execute(text("INSERT INTO user_group_membership(user_id, group_id, project_id)"
                        " VALUES (:u, :g, :p)"), {"u": uid, "g": gid, "p": pid})
        db.commit()
    finally:
        db.close()
    return c, w


def test_custom_group_governs_in_both_directions(index):
    """A group granting `orderbook:read` alone shows order types and hides
    item types — even though MATRIX gives this viewer both."""
    c, w = _member_of_custom_group("viewer", grants=[("orderbook", "read")])
    index.upsert([_doc(1, w), _doc(2, w, type_="order")])
    body = c.get("/search", params={"q": "kitchen"}).json()
    assert [h["type"] for h in body["hits"]] == ["order"]
    assert body["type_counts"] == {"order": 1}
    # narrowing with types= cannot reach past the DB grant either
    assert c.get("/search", params={"q": "kitchen", "types": "item"}).json()["hits"] == []


def test_project_scoped_only_membership_sees_no_types(index):
    """Documented ceiling: search checks workspace-wide grants only, so a
    membership scoped to one project does not unlock any result type."""
    c, w = _member_of_custom_group(
        "viewer", grants=[("tracking", "read"), ("orderbook", "read")], project_id=True)
    index.upsert([_doc(1, w)])
    assert c.get("/search", params={"q": "kitchen"}).json()["hits"] == []


@pytest.mark.parametrize("params", [
    {"q": "kitchen", "types": "item] OR workspace_id != 0 OR type IN [item"},
    {"q": "kitchen", "types": "item,order,nope"},
])
def test_injection_through_types_is_inert(index, params):
    c, w = _login()
    index.upsert([_doc(1, w), _doc(2, w + 1000)])
    assert [h["entity_id"] for h in c.get("/search", params=params).json()["hits"]] in ([1], [])


def test_non_integer_project_id_is_rejected(index):
    c, _ = _login()
    r = c.get("/search", params={"q": "x", "project_id": "1 OR workspace_id = 2"})
    assert r.status_code == 422


def test_project_filter_and_archived_toggle(index):
    c, w = _login()
    index.upsert([_doc(1, w), _doc(2, w, project_id=8), _doc(3, w, archived=True)])
    ids = lambda **p: {h["entity_id"] for h in c.get("/search", params={"q": "kitchen", **p}).json()["hits"]}  # noqa: E731
    assert ids() == {1, 2}
    assert ids(project_id=8) == {2}
    assert ids(include_archived="true") == {1, 2, 3}


@pytest.mark.parametrize("q", ["", "   ", "x" * 201])
def test_bad_queries_are_422(index, q):
    c, _ = _login()
    assert c.get("/search", params={"q": q}).status_code == 422


def test_outage_is_503(index):
    c, _ = _login()
    index.down = True
    r = c.get("/search", params={"q": "kitchen"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "SEARCH_UNAVAILABLE"


def test_health_for_admin(index):
    c, _ = _login("admin")
    s = SessionLocal()
    try:
        s.execute(text("TRUNCATE search_outbox"))
        s.execute(text("INSERT INTO search_outbox(entity_type, entity_id) VALUES ('project', 1)"))
        s.commit()
    finally:
        s.close()
    body = c.get("/search/health").json()
    assert body["meili"] == "ok" and body["outbox_depth"] == 1
    assert body["oldest_enqueued_at"] is not None
    index.down = True
    assert c.get("/search/health").json()["meili"] == "down"


@pytest.mark.parametrize("role,code", [("admin", 200), ("manager", 200), ("viewer", 403),
                                       ("editor", 403)])
def test_health_follows_it_management_read(index, role, code):
    """Gated on ("it_management","read"), which the matrix gives manager too."""
    c, _ = _login(role)
    assert c.get("/search/health").status_code == code
