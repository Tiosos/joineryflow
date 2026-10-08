"""Deleting an item is a soft delete (migration 0052).

Settled with the user, 2026-10-05, replacing the 2026-10-03 rule (a hard delete that also
dropped an unused cutlist): `DELETE /items/{id}` flags the item, its related parts and,
once no live item is left in it, its cutlist. Nothing is removed, so production history,
QC records and audit stay, a deleted item answers 404 everywhere, and a manager/admin can
restore it. There is no IN_USE refusal any more, and `items.code` has never been unique.
"""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app
from .helpers import log_in


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
    log_in(ws["slug"], f"drafter@{ws['slug']}.test", client=c)
    return c


def _cutlist(ws: dict) -> int:
    return _scalar("""INSERT INTO cutlist(project_id,cutlist_no,name)
                      VALUES(:p, nextval('joinery_number_seq'), 'CL') RETURNING cutlist_id""",
                   {"p": ws["pid"]})


def _item(ws: dict, cutlist_id: int | None) -> int:
    return _scalar("""INSERT INTO items(num, project_id, description, status, cutlist_id)
                      VALUES (nextval('joinery_number_seq'), :p, 'Item', 'CLEAR', :cl)
                      RETURNING item_id""", {"p": ws["pid"], "cl": cutlist_id})


def _flag(table: str, col: str, i: int) -> bool:
    return _scalar(f"SELECT deleted FROM {table} WHERE {col}=:i", {"i": i})


def _login_as(ws: dict, role: str) -> TestClient:
    email = f"{role}-{uuid.uuid4().hex[:6]}@{ws['slug']}.test"
    _sql("""INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
            VALUES(:w,:e,:r,:p,:r)""", {"w": ws["wid"], "e": email, "r": role, "p": hash_password("pw")})
    c = TestClient(app)
    log_in(ws["slug"], email, client=c)
    return c


def _delete(c: TestClient, iid: int):
    return c.delete(f"/items/{iid}")


def _listed(c: TestClient, ws: dict, *, deleted: bool = False) -> set[int]:
    r = c.get(f"/projects/{ws['pid']}/items", params={"deleted": str(deleted).lower()})
    assert r.status_code == 200, r.text
    return {row["id"] for row in r.json()["items"]}


def test_delete_flags_the_item_and_keeps_the_row():
    ws = _workspace()
    iid = _item(ws, None)
    c = _client(ws)
    assert _delete(c, iid).status_code == 204
    assert _scalar("SELECT count(*) FROM items WHERE item_id=:i", {"i": iid}) == 1
    assert _flag("items", "item_id", iid) is True


def test_a_deleted_item_leaves_the_live_list_and_shows_in_the_deleted_one():
    ws = _workspace()
    keep, gone = _item(ws, None), _item(ws, None)
    c = _client(ws)
    assert _delete(c, gone).status_code == 204
    assert _listed(c, ws) == {keep}
    assert _listed(c, ws, deleted=True) == {gone}


def test_a_deleted_item_answers_404_everywhere():
    ws = _workspace()
    iid = _item(ws, _cutlist(ws))
    c = _client(ws)
    assert _delete(c, iid).status_code == 204
    # The row is still there; it is the flag that makes every route answer 404.
    assert _scalar("SELECT count(*) FROM items WHERE item_id=:i", {"i": iid}) == 1
    for method, url, body in [
        ("get", f"/items/{iid}", None),
        ("get", f"/items/{iid}/availability", None),
        ("patch", f"/items/{iid}", {"description": "x"}),
        ("patch", f"/items/{iid}/status", {"status": "LIVE", "note": "n"}),
        ("post", f"/items/{iid}/duplicate", None),
        ("get", f"/items/{iid}/orders", None),
        ("get", f"/items/{iid}/queries", None),
        ("get", f"/items/{iid}/related-parts", None),
        ("delete", f"/items/{iid}", None),
    ]:
        r = c.request(method, url, json=body)
        assert r.status_code == 404, (method, url, r.status_code, r.text)


def test_bulk_status_reports_a_deleted_item_as_not_found():
    ws = _workspace()
    iid = _item(ws, None)
    c = _client(ws)
    assert _delete(c, iid).status_code == 204
    assert _scalar("SELECT count(*) FROM items WHERE item_id=:i", {"i": iid}) == 1
    r = c.post("/items/bulk-status", json={"item_ids": [iid], "status": "LIVE", "note": "n"})
    assert r.status_code == 200, r.text
    assert r.json()["not_found"] == [iid]


def test_the_last_item_leaving_flags_its_cutlist_and_hides_it():
    ws = _workspace()
    cid = _cutlist(ws)
    iid = _item(ws, cid)
    c = _client(ws)
    assert _delete(c, iid).status_code == 204
    assert _scalar("SELECT count(*) FROM cutlist WHERE cutlist_id=:c", {"c": cid}) == 1
    assert _flag("cutlist", "cutlist_id", cid) is True
    assert c.get(f"/cutlists/{cid}").status_code == 404
    listed = c.get(f"/projects/{ws['pid']}/cutlists").json()["cutlists"]
    assert cid not in {x["cutlist_id"] for x in listed}


def test_a_cutlist_still_holding_a_live_item_is_not_flagged():
    ws = _workspace()
    cid = _cutlist(ws)
    a, b = _item(ws, cid), _item(ws, cid)
    c = _client(ws)
    assert _delete(c, a).status_code == 204
    assert _flag("cutlist", "cutlist_id", cid) is False
    assert c.get(f"/cutlists/{cid}").json()["item_count"] == 1
    assert _delete(c, b).status_code == 204          # the second delete empties it
    assert _flag("cutlist", "cutlist_id", cid) is True


def test_production_history_stays_when_the_item_is_deleted():
    ws = _workspace()
    cid = _cutlist(ws)
    iid = _item(ws, cid)
    _sql("INSERT INTO stage_completion_log(cutlist_id,stage_key,worker_id) VALUES(:c,'DOWN',:u)",
         {"c": cid, "u": ws["uid"]})
    _sql("""INSERT INTO worker_assignment(cutlist_id,stage_key,worker_id,status,assigned_by)
            VALUES(:c,'DOWN',:u,'cancelled',:u)""", {"c": cid, "u": ws["uid"]})
    assert _delete(_client(ws), iid).status_code == 204
    assert _flag("cutlist", "cutlist_id", cid) is True          # hidden, yet its history is intact
    assert _scalar("SELECT count(*) FROM stage_completion_log WHERE cutlist_id=:c", {"c": cid}) == 1
    assert _scalar("SELECT count(*) FROM worker_assignment WHERE cutlist_id=:c", {"c": cid}) == 1




def test_related_parts_follow_their_parent_and_come_back_with_it():
    ws = _workspace()
    parent = _item(ws, _cutlist(ws))
    part = _scalar("""INSERT INTO items(num, project_id, description, status, row_type,
                                         parent_item_id, related_part_type_key)
                      VALUES (nextval('joinery_number_seq'), :p, 'RP', 'CLEAR', 'related_part', :par,
                              (SELECT type_key FROM related_part_type LIMIT 1))
                      RETURNING item_id""", {"p": ws["pid"], "par": parent})
    c = _client(ws)
    assert part in _listed(c, ws)
    assert _delete(c, parent).status_code == 204
    assert _flag("items", "item_id", part) is True
    assert _listed(c, ws) == set()
    assert _listed(c, ws, deleted=True) == {parent, part}
    assert _login_as(ws, "manager").post(f"/items/{parent}/restore").status_code == 204
    assert _listed(c, ws) == {parent, part}


def test_restore_brings_back_the_item_and_its_cutlist_and_is_audited():
    ws = _workspace()
    cid = _cutlist(ws)
    iid = _item(ws, cid)
    c = _client(ws)
    assert _delete(c, iid).status_code == 204
    mgr = _login_as(ws, "manager")
    assert mgr.post(f"/items/{iid}/restore").status_code == 204
    assert _flag("items", "item_id", iid) is False
    assert _flag("cutlist", "cutlist_id", cid) is False
    assert c.get(f"/items/{iid}").status_code == 200
    assert c.get(f"/cutlists/{cid}").status_code == 200
    events = [r["event"] for r in _sql(
        "SELECT event FROM audit_log WHERE workspace_id=:w AND target=:t ORDER BY id",
        {"w": ws["wid"], "t": str(iid)})]
    assert events == ["item.delete", "item.restore"]
    fields = [r["field"] for r in _sql(
        "SELECT field FROM item_edit_log WHERE item_id=:i ORDER BY 1", {"i": iid})]
    assert "_delete" in fields and "_restore" in fields


def test_restore_is_manager_or_admin_only():
    ws = _workspace()
    iid = _item(ws, None)
    c = _client(ws)                                       # a drafter
    assert _delete(c, iid).status_code == 204
    assert c.post(f"/items/{iid}/restore").status_code == 403
    assert _flag("items", "item_id", iid) is True
    assert _login_as(ws, "admin").post(f"/items/{iid}/restore").status_code == 204


def test_restoring_a_live_or_missing_item_is_refused():
    ws = _workspace()
    iid = _item(ws, None)
    mgr = _login_as(ws, "manager")
    r = mgr.post(f"/items/{iid}/restore")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ITEM_NOT_DELETED"
    assert mgr.post("/items/999999999/restore").status_code == 404


def test_another_workspace_cannot_restore_it():
    ws, other = _workspace(), _workspace()
    iid = _item(ws, None)
    assert _delete(_client(ws), iid).status_code == 204
    assert _login_as(other, "admin").post(f"/items/{iid}/restore").status_code == 404
    assert _flag("items", "item_id", iid) is True


def test_an_item_code_can_be_reused_while_the_old_one_is_deleted():
    ws = _workspace()
    c = _client(ws)
    a = c.post(f"/projects/{ws['pid']}/items", json={"description": "A", "code": "K-1", "qty": 1})
    assert a.status_code == 201, a.text
    assert _delete(c, a.json()["id"]).status_code == 204
    b = c.post(f"/projects/{ws['pid']}/items", json={"description": "B", "code": "K-1", "qty": 1})
    assert b.status_code == 201, b.text


def test_duplicate_then_delete_flags_only_the_copys_cutlist():
    """A copy gets its own cutlist; deleting the copy must not touch the source's."""
    ws = _workspace()
    src_cl = _cutlist(ws)
    src = _item(ws, src_cl)
    c = _client(ws)
    copy = c.post(f"/items/{src}/duplicate")
    assert copy.status_code == 201, copy.text
    copy_id = copy.json()["id"]
    copy_cl = _scalar("SELECT cutlist_id FROM items WHERE item_id=:i", {"i": copy_id})
    assert copy_cl != src_cl
    assert _delete(c, copy_id).status_code == 204
    assert _flag("cutlist", "cutlist_id", copy_cl) is True
    assert _flag("cutlist", "cutlist_id", src_cl) is False


# --- follow-ups settled 2026-10-07: Hard Lock blocks delete; related parts soft-delete too ----

def _hard_lock(iid: int) -> None:
    _sql("UPDATE items SET hard_locked_at = now() WHERE item_id=:i", {"i": iid})


def test_a_hard_locked_item_cannot_be_deleted_by_anyone():
    ws = _workspace()
    iid = _item(ws, None)
    _hard_lock(iid)
    for c in (_client(ws), _login_as(ws, "manager"), _login_as(ws, "admin")):
        r = _delete(c, iid)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "HARD_LOCKED", r.text
    assert _flag("items", "item_id", iid) is False
    assert _scalar("SELECT count(*) FROM audit_log WHERE event='item.delete' AND target=:t",
                   {"t": str(iid)}) == 0                      # a refused delete writes nothing


def test_clearing_the_hard_lock_lets_the_delete_through():
    ws = _workspace()
    iid = _item(ws, None)
    _hard_lock(iid)
    mgr = _login_as(ws, "manager")
    assert mgr.delete(f"/items/{iid}/hard-lock").status_code == 200
    assert _delete(_client(ws), iid).status_code == 204


def test_the_approval_lock_does_not_stop_a_delete():
    ws = _workspace()
    iid = _item(ws, None)
    _sql("UPDATE items SET status='APPROVED' WHERE item_id=:i", {"i": iid})
    assert _delete(_client(ws), iid).status_code == 204


def test_restore_is_not_stopped_by_a_hard_lock():
    ws = _workspace()
    iid = _item(ws, None)
    assert _delete(_client(ws), iid).status_code == 204
    _hard_lock(iid)
    assert _login_as(ws, "manager").post(f"/items/{iid}/restore").status_code == 204


def _related_part(ws: dict, parent: int) -> int:
    return _scalar("""INSERT INTO items(num, project_id, description, status, row_type,
                                        parent_item_id, related_part_type_key)
                      VALUES (nextval('joinery_number_seq'), :p, 'RP', 'CLEAR', 'related_part', :par,
                              (SELECT type_key FROM related_part_type LIMIT 1))
                      RETURNING item_id""", {"p": ws["pid"], "par": parent})


def test_a_related_part_delete_is_a_soft_delete_and_can_be_restored():
    ws = _workspace()
    parent = _item(ws, None)
    part = _related_part(ws, parent)
    c = _client(ws)
    assert c.delete(f"/related-parts/{part}").status_code == 204
    assert _scalar("SELECT count(*) FROM items WHERE item_id=:i", {"i": part}) == 1
    assert _flag("items", "item_id", part) is True
    assert c.get(f"/related-parts/{part}").status_code == 404
    assert _listed(c, ws) == {parent} and _listed(c, ws, deleted=True) == {part}
    assert _login_as(ws, "manager").post(f"/items/{part}/restore").status_code == 204
    assert c.get(f"/related-parts/{part}").status_code == 200
    assert _listed(c, ws) == {parent, part}


def test_a_related_part_cannot_be_restored_while_its_parent_is_deleted():
    ws = _workspace()
    parent = _item(ws, None)
    part = _related_part(ws, parent)
    c = _client(ws)
    assert c.delete(f"/related-parts/{part}").status_code == 204
    assert _delete(c, parent).status_code == 204
    mgr = _login_as(ws, "manager")
    r = mgr.post(f"/items/{part}/restore")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "PARENT_DELETED", r.text
    assert _flag("items", "item_id", part) is True
    assert mgr.post(f"/items/{parent}/restore").status_code == 204     # the parent first
    assert _flag("items", "item_id", part) is False                    # and it brings its parts back
