"""Item queries (migration 0036): one question, one answer, per row.

Pins: anyone who can read the list may ask (list:read); answering needs
list:write; a second answer is 409 unless PATCHed as an edit; newest first;
audit events; workspace isolation.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app


def _workspace(roles=("drafter",)) -> dict:
    slug = f"iq-{uuid.uuid4().hex[:8]}"
    s = SessionLocal()
    try:
        s.execute(text("INSERT INTO status_options(status_key, sort_order)"
                       " VALUES('CLEAR',1) ON CONFLICT DO NOTHING"))
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'IQ') RETURNING id"),
                        {"s": slug}).scalar()
        for role in roles:
            s.execute(text("""INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
                              VALUES(:w,:e,:n,:p,:r)"""),
                      {"w": wid, "e": f"{role}@{slug}.test", "n": role.title(),
                       "p": hash_password("pw"), "r": role})
        pid = s.execute(text("""INSERT INTO projects(project_code,name,workspace_id)
                                VALUES(:c,:c,:w) RETURNING project_id"""),
                        {"c": slug.upper(), "w": wid}).scalar()
        iid = s.execute(text("""INSERT INTO items(num, project_id, description, status)
                                VALUES (nextval('joinery_number_seq'), :p, 'Vanity', 'CLEAR')
                                RETURNING item_id"""), {"p": pid}).scalar()
        s.commit()
    finally:
        s.close()
    return {"slug": slug, "wid": wid, "iid": iid}


def _client(ws: dict, role: str = "drafter") -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": ws["slug"],
                                    "email": f"{role}@{ws['slug']}.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def ws(truncate_all):
    truncate_all()
    return _workspace(roles=("drafter", "editor", "viewer"))


def test_ask_answer_edit_round_trip(ws):
    asker, answerer = _client(ws, "viewer"), _client(ws, "drafter")

    r = asker.post(f"/items/{ws['iid']}/queries", json={"question": "Handle finish?"})
    assert r.status_code == 201, r.text  # a viewer may ask: list:read is enough
    q = r.json()
    assert (q["asked_by_name"], q["answer"], q["answered_by"]) == ("Viewer", None, None)

    r = answerer.post(f"/queries/{q['query_id']}/answer", json={"answer": "Brushed nickel"})
    assert r.status_code == 200, r.text
    assert (r.json()["answer"], r.json()["answered_by_name"]) == ("Brushed nickel", "Drafter")

    r = answerer.post(f"/queries/{q['query_id']}/answer", json={"answer": "Matte black"})
    assert r.status_code == 409  # answering twice must be an explicit edit

    r = answerer.patch(f"/queries/{q['query_id']}/answer", json={"answer": "Matte black"})
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == "Matte black"

    s = SessionLocal()
    try:
        events = [r[0] for r in s.execute(text(
            "SELECT event FROM audit_log WHERE event LIKE 'item.query.%' ORDER BY id"))]
    finally:
        s.close()
    assert events == ["item.query.create", "item.query.answer", "item.query.edit_answer"]


def test_list_is_newest_first(ws):
    c = _client(ws)
    for question in ("First?", "Second?", "Third?"):
        c.post(f"/items/{ws['iid']}/queries", json={"question": question})
    assert [q["question"] for q in c.get(f"/items/{ws['iid']}/queries").json()] == [
        "Third?", "Second?", "First?"]


@pytest.mark.parametrize("path,body", [
    ("/items/{iid}/queries", {"question": ""}),
    ("/queries/{qid}/answer", {"answer": ""}),
])
def test_empty_text_is_422(ws, path, body):
    c = _client(ws)
    qid = c.post(f"/items/{ws['iid']}/queries", json={"question": "Q?"}).json()["query_id"]
    r = c.post(path.format(iid=ws["iid"], qid=qid), json=body)
    assert r.status_code == 422


@pytest.mark.parametrize("role,status", [("editor", 200), ("viewer", 403)])
def test_answering_needs_list_write(ws, role, status):
    qid = _client(ws).post(f"/items/{ws['iid']}/queries",
                           json={"question": "Q?"}).json()["query_id"]
    r = _client(ws, role).post(f"/queries/{qid}/answer", json={"answer": "A"})
    assert r.status_code == status, r.text


def test_other_workspace_is_404(ws):
    other = _workspace()
    theirs = _client(other)
    qid = theirs.post(f"/items/{other['iid']}/queries",
                      json={"question": "Theirs?"}).json()["query_id"]
    c = _client(ws)
    assert c.get(f"/items/{other['iid']}/queries").status_code == 404
    assert c.post(f"/items/{other['iid']}/queries", json={"question": "X"}).status_code == 404
    assert c.post(f"/queries/{qid}/answer", json={"answer": "X"}).status_code == 404
    assert c.patch(f"/queries/{qid}/answer", json={"answer": "X"}).status_code == 404
    assert theirs.get(f"/items/{other['iid']}/queries").json()[0]["answer"] is None
