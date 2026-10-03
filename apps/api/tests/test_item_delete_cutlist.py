"""Deleting an item no longer leaves its emptied cutlist behind (no migration).

Settled with the user, 2026-10-03: when the last item leaves a cutlist through
`DELETE /items/{id}`, the cutlist is deleted **only if it never did production work**.
Deleting a cutlist CASCADEs `worker_assignment` and `stage_completion_log` (`0030`), and
the Actual Costs labour figure is priced from the latter, so a cutlist with any
assignment or completion (undone or cancelled included) is kept as an empty record.
A cutlist that still holds another item is never touched.
"""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app


def _sql(sql: str, params: dict | None = None):
    s = SessionLocal()
    try:
        out = s.execute(text(sql), params or {})
        rows = out.mappings().all() if out.returns_rows else None
        s.commit()
        return rows
    finally:
        s.close()


def _scalar(sql: str, params: dict | None = None):
    rows = _sql(sql, params)
    return list(rows[0].values())[0] if rows else None


def _workspace() -> dict:
    slug = f"dc-{uuid.uuid4().hex[:8]}"
    s = SessionLocal()
    try:
        s.execute(text("INSERT INTO status_options(status_key, sort_order) VALUES('CLEAR',1)"
                       " ON CONFLICT DO NOTHING"))
        s.execute(text("INSERT INTO stages(stage_key, label, sort_order) VALUES('DOWN','Down',40)"
                       " ON CONFLICT DO NOTHING"))
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'DC') RETURNING id"),
                        {"s": slug}).scalar()
        uid = s.execute(
            text("""INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
                    VALUES(:w,:e,'Drafter',:p,'drafter') RETURNING id"""),
            {"w": wid, "e": f"drafter@{slug}.test", "p": hash_password("pw")}).scalar()
        pid = s.execute(text("""INSERT INTO projects(project_code,name,workspace_id)
                                VALUES(:c,:c,:w) RETURNING project_id"""),
                        {"c": slug.upper(), "w": wid}).scalar()
        s.commit()
    finally:
        s.close()
    return {"slug": slug, "wid": wid, "uid": uid, "pid": pid}


def _client(ws: dict) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": ws["slug"],
                                    "email": f"drafter@{ws['slug']}.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return c


def _cutlist(ws: dict) -> int:
    return _scalar("""INSERT INTO cutlist(project_id,cutlist_no,name)
                      VALUES(:p, nextval('joinery_number_seq'), 'CL') RETURNING cutlist_id""",
                   {"p": ws["pid"]})


def _item(ws: dict, cutlist_id: int | None) -> int:
    return _scalar("""INSERT INTO items(num, project_id, description, status, cutlist_id)
                      VALUES (nextval('joinery_number_seq'), :p, 'Item', 'CLEAR', :cl)
                      RETURNING item_id""", {"p": ws["pid"], "cl": cutlist_id})


def _cutlist_exists(cid: int) -> bool:
    return _scalar("SELECT count(*) FROM cutlist WHERE cutlist_id=:c", {"c": cid}) == 1


def _cutlist_deletions(ws: dict) -> int:
    return _scalar("SELECT count(*) FROM audit_log WHERE event='cutlist.delete' AND workspace_id=:w",
                   {"w": ws["wid"]})


def _delete(c: TestClient, iid: int):
    return c.delete(f"/items/{iid}")


def _assignment(ws: dict, cid: int, status: str = "assigned") -> int:
    return _scalar("""INSERT INTO worker_assignment(cutlist_id,stage_key,worker_id,status,assigned_by)
                      VALUES(:c,'DOWN',:u,:s,:u) RETURNING assignment_id""",
                   {"c": cid, "u": ws["uid"], "s": status})


def test_the_last_item_leaving_takes_an_unused_cutlist_with_it():
    ws = _workspace()
    cid = _cutlist(ws)
    iid = _item(ws, cid)
    assert _delete(_client(ws), iid).status_code == 204
    assert _scalar("SELECT count(*) FROM items WHERE item_id=:i", {"i": iid}) == 0
    assert not _cutlist_exists(cid)


def test_the_cutlist_deletion_is_audited_with_its_cause():
    ws = _workspace()
    cid = _cutlist(ws)
    no = _scalar("SELECT cutlist_no FROM cutlist WHERE cutlist_id=:c", {"c": cid})
    iid = _item(ws, cid)
    assert _delete(_client(ws), iid).status_code == 204
    rows = _sql("SELECT actor_id, payload FROM audit_log WHERE event='cutlist.delete' AND target=:t",
                {"t": str(cid)})
    assert len(rows) == 1 and rows[0]["actor_id"] == ws["uid"]
    p = rows[0]["payload"]
    assert (p["cutlist_no"], p["via"], p["item_id"], p["project_id"]) == (no, "item.delete", iid, ws["pid"])


def test_a_cutlist_still_holding_another_item_is_not_touched():
    ws = _workspace()
    cid = _cutlist(ws)
    a, b = _item(ws, cid), _item(ws, cid)
    c = _client(ws)
    assert _delete(c, a).status_code == 204
    assert _cutlist_exists(cid)
    assert _scalar("SELECT cutlist_id FROM items WHERE item_id=:i", {"i": b}) == cid
    assert _cutlist_deletions(ws) == 0
    # the second delete empties it, and only then does it go
    assert _delete(c, b).status_code == 204
    assert not _cutlist_exists(cid)


def test_a_cutlist_with_a_stage_completion_is_kept_and_so_is_its_history():
    ws = _workspace()
    cid = _cutlist(ws)
    iid = _item(ws, cid)
    _sql("""INSERT INTO stage_completion_log(cutlist_id,stage_key,worker_id)
            VALUES(:c,'DOWN',:u)""", {"c": cid, "u": ws["uid"]})
    assert _delete(_client(ws), iid).status_code == 204
    assert _cutlist_exists(cid)
    assert _scalar("SELECT count(*) FROM stage_completion_log WHERE cutlist_id=:c", {"c": cid}) == 1
    assert _cutlist_deletions(ws) == 0


def test_an_undone_completion_still_counts_as_history():
    ws = _workspace()
    cid = _cutlist(ws)
    iid = _item(ws, cid)
    _sql("""INSERT INTO stage_completion_log(cutlist_id,stage_key,worker_id,undone_at,undone_by)
            VALUES(:c,'DOWN',:u,now(),:u)""", {"c": cid, "u": ws["uid"]})
    assert _delete(_client(ws), iid).status_code == 204
    assert _cutlist_exists(cid)


def test_a_cutlist_with_only_a_cancelled_assignment_is_kept():
    ws = _workspace()
    cid = _cutlist(ws)
    iid = _item(ws, cid)
    _assignment(ws, cid, status="cancelled")
    assert _delete(_client(ws), iid).status_code == 204
    assert _cutlist_exists(cid)
    assert _scalar("SELECT count(*) FROM worker_assignment WHERE cutlist_id=:c", {"c": cid}) == 1


def test_an_item_with_no_cutlist_deletes_as_before():
    ws = _workspace()
    iid = _item(ws, None)
    other = _cutlist(ws)                      # an unrelated, empty cutlist must not be swept up
    assert _delete(_client(ws), iid).status_code == 204
    assert _cutlist_exists(other)
    assert _cutlist_deletions(ws) == 0


def test_a_refused_delete_leaves_the_cutlist(monkeypatch):
    """IN_USE (hardware allocated) returns before anything is removed."""
    ws = _workspace()
    cid = _cutlist(ws)
    iid = _item(ws, cid)
    import app.items.routes as routes
    monkeypatch.setattr(routes, "delete_item", lambda *a, **k: "IN_USE")
    assert _delete(_client(ws), iid).status_code == 409
    assert _cutlist_exists(cid)
    assert _scalar("SELECT count(*) FROM items WHERE item_id=:i", {"i": iid}) == 1


def test_duplicate_then_delete_leaves_only_the_sources_cutlist():
    """The case that found this: a copy gets its own cutlist, and deleting the copy used
    to leave that cutlist behind."""
    ws = _workspace()
    src_cl = _cutlist(ws)
    src = _item(ws, src_cl)
    c = _client(ws)
    before = _scalar("SELECT count(*) FROM cutlist WHERE project_id=:p", {"p": ws["pid"]})
    copy = c.post(f"/items/{src}/duplicate")
    assert copy.status_code == 201, copy.text
    copy_id = copy.json()["id"]
    assert _scalar("SELECT count(*) FROM cutlist WHERE project_id=:p", {"p": ws["pid"]}) == before + 1
    assert _delete(c, copy_id).status_code == 204
    assert _scalar("SELECT count(*) FROM cutlist WHERE project_id=:p", {"p": ws["pid"]}) == before
    assert _cutlist_exists(src_cl)
    assert _scalar("SELECT cutlist_id FROM items WHERE item_id=:i", {"i": src}) == src_cl
