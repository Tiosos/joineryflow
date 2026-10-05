"""Shop Drawings — register fields (migration 0044): numbering, new columns,
queues, assigned_to workspace isolation, history."""
import io
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app

PDF = b"%PDF-1.4\n%abc\n" + b"x" * 100 + b"\n%%EOF\n"


@pytest.fixture(autouse=True)
def reset(truncate_all, tmp_path: Path, monkeypatch):
    truncate_all()
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    truncate_all()
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def client():
    return TestClient(app)


def _user(s, wid, email, role):
    from app.auth.passwords import hash_password
    return s.execute(text("""
        INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
        VALUES (:w, :e, :n, :p, :r) RETURNING id
    """), {"w": wid, "e": email, "n": email.split("@")[0], "p": hash_password("pw"), "r": role}).scalar()


def _setup(client, role="drafter"):
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('hartwood','HW') RETURNING id")).scalar()
        uid = _user(s, wid, f"{role}@hw.test", role)
        mgr = _user(s, wid, "mgr@hw.test", "manager")
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES('COLES', 'Coles', :u, :w) RETURNING project_id
        """), {"u": uid, "w": wid}).scalar()
        s.commit()
    finally:
        s.close()
    r = client.post("/auth/login", json={"workspace_slug": "hartwood", "email": f"{role}@hw.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return {"wid": wid, "uid": uid, "mgr": mgr, "pid": pid}


def _blob(client):
    r = client.post("/files", files={"file": ("a.pdf", io.BytesIO(PDF), "application/pdf")})
    return r.json()["file_blob_id"]


def _create(client, pid, **kw):
    body = {"title": "T", "file_blob_id": _blob(client), **kw}
    r = client.post(f"/projects/{pid}/shop-drawings", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_allocates_sequential_register_numbers(client):
    ids = _setup(client)
    a = _create(client, ids["pid"])
    b = _create(client, ids["pid"])
    assert (a["drawing_no"], b["drawing_no"]) == ("COLES-001", "COLES-002")
    assert a["type"] == "IFA"  # default


def test_register_fields_round_trip_on_create_and_detail(client):
    ids = _setup(client)
    d = _create(client, ids["pid"], type="IFC", level=" Level 01 ", joinery_id="J07-017",
                zone="Z2", room_no="R4", assigned_to=ids["mgr"], due_date="2026-09-25")
    assert (d["type"], d["level"], d["joinery_id"], d["zone"], d["room_no"]) == \
        ("IFC", "Level 01", "J07-017", "Z2", "R4")
    assert d["assigned_to"] == ids["mgr"] and d["assigned_to_name"] == "mgr"
    assert d["due_date"] == "2026-09-25" and d["submitted_at"] is None
    got = client.get(f"/shop-drawings/{d['drawing_id']}").json()
    assert got["drawing_no"] == d["drawing_no"] and got["joinery_id"] == "J07-017"


def test_bad_type_is_422_not_500(client):
    ids = _setup(client)
    r = client.post(f"/projects/{ids['pid']}/shop-drawings",
                    json={"title": "T", "file_blob_id": _blob(client), "type": "XYZ"})
    assert r.status_code == 422


def test_assigned_to_must_be_in_workspace(client):
    from app.db import SessionLocal
    ids = _setup(client)
    s = SessionLocal()
    try:
        w2 = s.execute(text("INSERT INTO workspace(slug,name) VALUES('other','O') RETURNING id")).scalar()
        foreign = _user(s, w2, "x@o.test", "manager")
        s.commit()
    finally:
        s.close()
    r = client.post(f"/projects/{ids['pid']}/shop-drawings",
                    json={"title": "T", "file_blob_id": _blob(client), "assigned_to": foreign})
    assert r.status_code == 422
    d = _create(client, ids["pid"])
    r = client.patch(f"/shop-drawings/{d['drawing_id']}", json={"assigned_to": foreign})
    assert r.status_code == 422
    assert client.get(f"/shop-drawings/{d['drawing_id']}").json()["assigned_to"] is None


def test_patch_register_fields_audits_and_null_title_is_422(client):
    ids = _setup(client)
    d = _create(client, ids["pid"])
    did = d["drawing_id"]
    r = client.patch(f"/shop-drawings/{did}", json={
        "due_date": "2026-10-01", "submitted_at": "2026-10-02", "type": "IFC", "level": "L3"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["due_date"], b["submitted_at"], b["type"], b["level"]) == \
        ("2026-10-01", "2026-10-02", "IFC", "L3")
    for bad in ({"title": None}, {"type": None}):
        assert client.patch(f"/shop-drawings/{did}", json=bad).status_code == 422
    # an explicit null CAN clear a nullable field
    assert client.patch(f"/shop-drawings/{did}", json={"level": None}).json()["level"] is None
    ev = client.get(f"/shop-drawings/{did}/history").json()["events"]
    assert any(e["event"] == "shop_drawing.update" for e in ev)
    assert ev[-1]["event"] == "shop_drawing.create"


def test_queues_and_counts(client):
    ids = _setup(client)
    _create(client, ids["pid"], title="draft")
    _create(client, ids["pid"], title="pend", submit_immediately=True)
    rej = _create(client, ids["pid"], title="rej", submit_immediately=True)
    appr = _create(client, ids["pid"], title="appr", submit_immediately=True)
    sub = _create(client, ids["pid"], title="sub", submit_immediately=True)
    arch = _create(client, ids["pid"], title="arch")

    # review as the manager (uploader cannot review their own)
    client.post("/auth/logout")
    assert client.post("/auth/login", json={"workspace_slug": "hartwood",
                       "email": "mgr@hw.test", "password": "pw"}).status_code == 200
    rid = lambda d: d["revisions"][0]["revision_id"]
    assert client.post(f"/shop-drawings/{rej['drawing_id']}/revisions/{rid(rej)}/reject",
                       json={"review_note": "redo"}).status_code == 200
    for d in (appr, sub):
        assert client.post(f"/shop-drawings/{d['drawing_id']}/revisions/{rid(d)}/approve").status_code == 200
    assert client.patch(f"/shop-drawings/{sub['drawing_id']}",
                        json={"submitted_at": "2026-10-01"}).status_code == 200
    assert client.post(f"/shop-drawings/{arch['drawing_id']}/archive").status_code == 204

    def titles(queue):
        r = client.get(f"/projects/{ids['pid']}/shop-drawings", params={"queue": queue})
        assert r.status_code == 200, r.text
        return sorted(x["title"] for x in r.json()["drawings"])

    assert titles("being_drawn") == ["draft"]
    assert titles("internal_review") == ["pend"]
    assert titles("update_required") == ["rej"]
    assert titles("completed") == ["appr", "sub"]
    assert titles("awaiting_submission") == ["appr"]
    assert titles("submitted") == ["sub"]
    assert titles("archive") == ["arch"]
    assert titles("all") == ["appr", "draft", "pend", "rej", "sub"]

    body = client.get(f"/projects/{ids['pid']}/shop-drawings", params={"queue": "all"}).json()
    assert body["queues"] == {"being_drawn": 1, "internal_review": 1, "update_required": 1,
                              "completed": 2, "awaiting_submission": 1, "submitted": 1, "archive": 1}
    by = {d["title"]: d["queue"] for d in body["drawings"]}
    assert by == {"draft": "being_drawn", "pend": "internal_review", "rej": "update_required",
                  "appr": "completed", "sub": "completed"}
    assert client.get(f"/projects/{ids['pid']}/shop-drawings",
                      params={"queue": "bogus"}).status_code == 422


def test_search_and_assigned_filters(client):
    ids = _setup(client)
    _create(client, ids["pid"], title="One", joinery_id="J07-017", assigned_to=ids["mgr"])
    _create(client, ids["pid"], title="Two")
    g = lambda **p: sorted(x["title"] for x in client.get(
        f"/projects/{ids['pid']}/shop-drawings", params={"queue": "all", **p}).json()["drawings"])
    assert g(q="J07-017") == ["One"]
    assert g(q="COLES-002") == ["Two"]
    assert g(assigned_to=ids["mgr"]) == ["One"]


def test_comment_count_on_card(client):
    ids = _setup(client)
    d = _create(client, ids["pid"])
    r = client.post("/comments", json={"object_type": "revision",
                    "object_id": d["revisions"][0]["revision_id"], "body": "hi"})
    assert r.status_code == 201, r.text
    card = client.get(f"/projects/{ids['pid']}/shop-drawings", params={"queue": "all"}).json()["drawings"][0]
    assert card["comment_count"] == 1


def test_history_is_workspace_scoped(client):
    _setup(client)
    assert client.get("/shop-drawings/999999/history").status_code == 404
