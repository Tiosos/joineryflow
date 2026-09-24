"""GET /search and GET /search/health (plan tasks D1, D2; spec §5)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import permissions
from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app
from app.search.index import FakeIndex
from app.search.routes import search_index

from .conftest import TRUNCATE_TABLES


@pytest.fixture
def index():
    fake = FakeIndex()
    app.dependency_overrides[search_index] = lambda: fake
    yield fake
    app.dependency_overrides.pop(search_index, None)


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        s.execute(text("TRUNCATE " + ", ".join(TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _login(role="manager"):
    suffix = uuid.uuid4().hex[:8]
    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'Search WS')"
                             " RETURNING id"), {"s": f"srch-{suffix}"}).scalar()
        email = f"u-{suffix}@x.test"
        s.execute(text("INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)"
                       " VALUES (:w,:e,'U',:p,:r)"),
                  {"w": wid, "e": email, "p": hash_password("pw"), "r": role})
        s.commit()
    finally:
        s.close()
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": f"srch-{suffix}", "email": email,
                                    "password": "pw"})
    assert r.status_code == 200, r.text
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
    c, w = _login("viewer")
    matrix = {**permissions.MATRIX, "viewer": {**permissions.MATRIX["viewer"], "orderbook": set()}}
    monkeypatch.setattr(permissions, "MATRIX", matrix)
    index.upsert([_doc(1, w), _doc(2, w, type_="order")])
    body = c.get("/search", params={"q": "kitchen"}).json()
    assert [h["type"] for h in body["hits"]] == ["item"]
    assert "order" not in body["type_counts"]
    # Asking for it explicitly is not an error and still reveals nothing.
    r = c.get("/search", params={"q": "kitchen", "types": "order"})
    assert r.status_code == 200 and r.json() == {"hits": [], "total": 0, "type_counts": {}}


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
