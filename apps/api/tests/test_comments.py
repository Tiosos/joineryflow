"""Comments + mentions + in-app notifications (migration 0042, Plan V1 §29).

Pins: one thread entity over Project / Area / Room / Joinery Item; one-level
replies (a DB rule); `tracking:read` to read and `tracking:comment` to write
(the first place the `comment` action is enforced); author-only edit,
author-or-manager delete (soft); mentions validated against the workspace and
the RBAC engine; a notification per (recipient, comment, kind); workspace
isolation; audit + item_edit_log.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

ROLES = ("manager", "drafter", "editor", "purchase_officer", "viewer")


def _workspace() -> dict:
    slug = f"cm-{uuid.uuid4().hex[:8]}"
    s = SessionLocal()
    try:
        s.execute(text("INSERT INTO status_options(status_key, sort_order)"
                       " VALUES('CLEAR',1) ON CONFLICT DO NOTHING"))
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'CM') RETURNING id"),
                        {"s": slug}).scalar()
        uids = {}
        for role in ROLES:
            uids[role] = s.execute(
                text("""INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
                        VALUES(:w,:e,:n,:p,:r) RETURNING id"""),
                {"w": wid, "e": f"{role}@{slug}.test", "n": role.title(),
                 "p": hash_password("pw"), "r": role}).scalar()
        pid = s.execute(text("""INSERT INTO projects(project_code,name,workspace_id)
                                VALUES(:c,:c,:w) RETURNING project_id"""),
                        {"c": slug.upper(), "w": wid}).scalar()
        aid = s.execute(text("INSERT INTO area(project_id, name) VALUES(:p,'Level 1') RETURNING area_id"),
                        {"p": pid}).scalar()
        rid = s.execute(text("INSERT INTO room(area_id, rm_no) VALUES(:a,'R01') RETURNING room_id"),
                        {"a": aid}).scalar()
        iid = s.execute(text("""INSERT INTO items(num, project_id, description, status)
                                VALUES (nextval('joinery_number_seq'), :p, 'Vanity', 'CLEAR')
                                RETURNING item_id"""), {"p": pid}).scalar()
        rp = s.execute(text("""INSERT INTO items(num, project_id, description, status, row_type,
                                                 parent_item_id, related_part_type_key)
                               VALUES (nextval('joinery_number_seq'), :p, 'Top', 'CLEAR',
                                       'related_part', :par, 'benchtop')
                               RETURNING item_id"""), {"p": pid, "par": iid}).scalar()
        s.commit()
    finally:
        s.close()
    return {"slug": slug, "wid": wid, "pid": pid, "aid": aid, "rid": rid,
            "iid": iid, "rp": rp, "uid": uids}


def _client(ws: dict, role: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": ws["slug"],
                                    "email": f"{role}@{ws['slug']}.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def ws(truncate_all):
    truncate_all()
    return _workspace()


def _target(ws, kind):
    return {"object_type": kind, "object_id": ws[{"project": "pid", "area": "aid",
                                                   "room": "rid", "item": "iid"}[kind]]}


def _post(c, ws, body="Hello", kind="item", **extra):
    return c.post("/comments", json={**_target(ws, kind), "body": body, **extra})


def _sql(query, **params):
    s = SessionLocal()
    try:
        return s.execute(text(query), params).all()
    finally:
        s.close()


def _thread(c, ws, kind="item"):
    r = c.get("/comments", params=_target(ws, kind))
    assert r.status_code == 200, r.text
    return r.json()["comments"]


# ---------------------------------------------------------------- basics ----

@pytest.mark.parametrize("kind", ["project", "area", "room", "item"])
def test_comment_on_each_object_type_round_trips(ws, kind):
    drafter = _client(ws, "drafter")
    r = _post(drafter, ws, "First!", kind)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["object_type"] == kind and out["author_name"] == "Drafter"
    assert [c["body"] for c in _thread(drafter, ws, kind)] == ["First!"]


def test_threads_are_per_object(ws):
    d = _client(ws, "drafter")
    _post(d, ws, "on item", "item")
    _post(d, ws, "on project", "project")
    assert [c["body"] for c in _thread(d, ws, "item")] == ["on item"]
    assert [c["body"] for c in _thread(d, ws, "project")] == ["on project"]


def test_comment_action_is_enforced(ws):
    """The point of Q473: `comment` stops being a dead grant. A viewer holds
    tracking:read only — can read a thread, cannot write to it."""
    viewer = _client(ws, "viewer")
    assert viewer.get("/comments", params=_target(ws, "item")).status_code == 200
    assert _post(viewer, ws).status_code == 403
    cid = _post(_client(ws, "drafter"), ws).json()["comment_id"]
    assert viewer.patch(f"/comments/{cid}", json={"body": "x"}).status_code == 403
    assert viewer.delete(f"/comments/{cid}").status_code == 403
    for role in ("editor", "purchase_officer", "manager"):
        assert _post(_client(ws, role), ws).status_code == 201


def test_body_is_trimmed_and_bounded(ws):
    d = _client(ws, "drafter")
    assert _post(d, ws, "  padded  ").json()["body"] == "padded"
    assert _post(d, ws, "   ").status_code == 422
    assert _post(d, ws, "x" * 5001).status_code == 422


def test_related_part_has_no_thread(ws):
    d = _client(ws, "drafter")
    assert d.get("/comments", params={"object_type": "item", "object_id": ws["rp"]}).status_code == 404
    assert d.post("/comments", json={"object_type": "item", "object_id": ws["rp"],
                                     "body": "x"}).status_code == 404


def test_workspace_isolation(ws, truncate_all):
    other = _workspace()
    mine = _client(ws, "manager")
    theirs = _client(other, "manager")
    cid = _post(mine, ws).json()["comment_id"]
    for kind in ("project", "area", "room", "item"):
        assert theirs.get("/comments", params=_target(ws, kind)).status_code == 404
        assert theirs.post("/comments", json={**_target(ws, kind), "body": "x"}).status_code == 404
    assert theirs.patch(f"/comments/{cid}", json={"body": "x"}).status_code == 404
    assert theirs.delete(f"/comments/{cid}").status_code == 404
    assert [c["body"] for c in _thread(mine, ws)] == ["Hello"]


def test_unknown_object_and_bad_shapes(ws):
    d = _client(ws, "drafter")
    assert d.post("/comments", json={"object_type": "item", "object_id": 999999, "body": "x"}).status_code == 404
    assert d.get("/comments", params={"object_type": "nope", "object_id": 1}).status_code == 422
    assert d.post("/comments", json={"body": "x"}).status_code == 422                       # no target
    assert d.post("/comments", json={"object_type": "item", "body": "x"}).status_code == 422  # half a target


# --------------------------------------------------------------- replies ----

def test_reply_nests_and_inherits_the_object(ws):
    d, m = _client(ws, "drafter"), _client(ws, "manager")
    top = _post(d, ws, "top", "room").json()
    r = m.post("/comments", json={"parent_id": top["comment_id"], "body": "reply"})
    assert r.status_code == 201, r.text
    assert r.json()["object_type"] == "room" and r.json()["parent_comment_id"] == top["comment_id"]
    thread = _thread(d, ws, "room")
    assert [c["body"] for c in thread] == ["top"]
    assert [c["body"] for c in thread[0]["replies"]] == ["reply"]


def test_reply_to_a_reply_is_refused(ws):
    d = _client(ws, "drafter")
    top = _post(d, ws).json()["comment_id"]
    reply = d.post("/comments", json={"parent_id": top, "body": "r"}).json()["comment_id"]
    r = d.post("/comments", json={"parent_id": reply, "body": "rr"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "REPLY_TO_REPLY"


def test_reply_cannot_name_an_object(ws):
    d = _client(ws, "drafter")
    top = _post(d, ws).json()["comment_id"]
    r = d.post("/comments", json={"parent_id": top, "body": "r", **_target(ws, "project")})
    assert r.status_code == 422


def test_reply_to_unknown_or_foreign_parent_is_404(ws):
    d = _client(ws, "drafter")
    assert d.post("/comments", json={"parent_id": 999999, "body": "r"}).status_code == 404


def test_db_rejects_reply_to_reply_and_two_objects(ws):
    d = _client(ws, "drafter")
    top = _post(d, ws).json()["comment_id"]
    reply = d.post("/comments", json={"parent_id": top, "body": "r"}).json()["comment_id"]
    s = SessionLocal()
    try:
        with pytest.raises(IntegrityError):
            s.execute(text("""INSERT INTO comment(workspace_id, item_id, parent_comment_id, body)
                              VALUES (:w, :i, :p, 'deep')"""),
                      {"w": ws["wid"], "i": ws["iid"], "p": reply})
        s.rollback()
        with pytest.raises(IntegrityError):
            s.execute(text("""INSERT INTO comment(workspace_id, item_id, project_id, body)
                              VALUES (:w, :i, :p, 'two')"""),
                      {"w": ws["wid"], "i": ws["iid"], "p": ws["pid"]})
        s.rollback()
        with pytest.raises(IntegrityError):
            s.execute(text("INSERT INTO comment(workspace_id, body) VALUES (:w, 'none')"),
                      {"w": ws["wid"]})
    finally:
        s.rollback()
        s.close()


def test_deleting_the_object_takes_its_thread_with_it(ws):
    d = _client(ws, "drafter")
    _post(d, ws, "bye", "item")
    s = SessionLocal()
    try:
        s.execute(text("DELETE FROM items WHERE item_id = :i"), {"i": ws["iid"]})
        s.commit()
        assert s.execute(text("SELECT count(*) FROM comment WHERE workspace_id = :w"),
                         {"w": ws["wid"]}).scalar() == 0
    finally:
        s.close()


# -------------------------------------------------- mentions + notifications ---

def _inbox(ws, role, **params):
    r = _client(ws, role).get("/notifications", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_mention_notifies_the_mentioned_user_and_not_the_author(ws):
    d = _client(ws, "drafter")
    r = _post(d, ws, "@Manager @Drafter look", mentioned_user_ids=[ws["uid"]["manager"], ws["uid"]["drafter"]])
    assert r.status_code == 201, r.text
    assert sorted(m["full_name"] for m in r.json()["mentions"]) == ["Drafter", "Manager"]
    inbox = _inbox(ws, "manager")
    assert inbox["unread_count"] == 1
    n = inbox["notifications"][0]
    assert n["kind"] == "mention" and n["actor_name"] == "Drafter"
    assert n["object_type"] == "item" and n["object_id"] == ws["iid"]
    assert n["url"] == f"/items/{ws['iid']}?tab=comments" and "Vanity" in n["object_label"]
    assert _inbox(ws, "drafter")["unread_count"] == 0          # no self-notification


def test_reply_notifies_the_parent_author(ws):
    d, m = _client(ws, "drafter"), _client(ws, "manager")
    top = _post(d, ws).json()["comment_id"]
    m.post("/comments", json={"parent_id": top, "body": "answer"})
    n = _inbox(ws, "drafter")["notifications"]
    assert [x["kind"] for x in n] == ["reply"] and n[0]["actor_name"] == "Manager"
    assert _inbox(ws, "manager")["unread_count"] == 0            # replying to yourself is silent


def test_a_mention_beats_a_reply_notification(ws):
    d, m = _client(ws, "drafter"), _client(ws, "manager")
    top = _post(d, ws).json()["comment_id"]
    m.post("/comments", json={"parent_id": top, "body": "@Drafter", "mentioned_user_ids": [ws["uid"]["drafter"]]})
    assert [x["kind"] for x in _inbox(ws, "drafter")["notifications"]] == ["mention"]


def test_project_thread_links_to_the_project_page_and_area_has_no_link(ws):
    d = _client(ws, "drafter")
    _post(d, ws, "p", "project", mentioned_user_ids=[ws["uid"]["manager"]])
    _post(d, ws, "a", "area", mentioned_user_ids=[ws["uid"]["manager"]])
    urls = {n["object_type"]: n["url"] for n in _inbox(ws, "manager")["notifications"]}
    assert urls == {"project": f"/projects/{ws['pid']}", "area": None}


@pytest.mark.parametrize("who", ["foreign", "inactive", "unknown"])
def test_bad_mentions_are_refused_whole(ws, who):
    other = _workspace()
    d = _client(ws, "drafter")
    if who == "foreign":
        bad = other["uid"]["manager"]
    elif who == "unknown":
        bad = 999999
    else:
        bad = ws["uid"]["editor"]
        s = SessionLocal()
        try:
            s.execute(text("UPDATE app_user SET is_active = false WHERE id = :u"), {"u": bad})
            s.commit()
        finally:
            s.close()
    r = _post(d, ws, "hi", mentioned_user_ids=[ws["uid"]["manager"], bad])
    assert r.status_code == 422
    assert r.json()["detail"] == {"code": "BAD_MENTION", "user_ids": [bad]}
    assert _thread(d, ws) == []                      # nothing was written
    assert _inbox(ws, "manager")["unread_count"] == 0


def test_mentioning_someone_who_cannot_read_tracking_is_refused(ws):
    """A notification linking a user to a record they cannot open is worse than
    refusing. Checked against the RBAC engine: this user's only group grants
    nothing on tracking."""
    uid = ws["uid"]["viewer"]
    s = SessionLocal()
    try:
        gid = s.execute(text("""INSERT INTO permission_group(workspace_id, name, is_system)
                                VALUES (:w, 'nothing', false) RETURNING group_id"""),
                        {"w": ws["wid"]}).scalar()
        s.execute(text("INSERT INTO user_group_membership(user_id, group_id, project_id)"
                       " VALUES (:u, :g, NULL)"), {"u": uid, "g": gid})
        s.commit()
    finally:
        s.close()
    r = _post(_client(ws, "drafter"), ws, "hi", mentioned_user_ids=[uid])
    assert r.status_code == 422 and r.json()["detail"]["user_ids"] == [uid]


def test_editing_notifies_only_newly_added_mentions(ws):
    d = _client(ws, "drafter")
    cid = _post(d, ws, "v1", mentioned_user_ids=[ws["uid"]["manager"]]).json()["comment_id"]
    r = d.patch(f"/comments/{cid}", json={"body": "v2",
                                          "mentioned_user_ids": [ws["uid"]["manager"], ws["uid"]["editor"]]})
    assert r.status_code == 200 and r.json()["edited_at"] is not None
    assert _inbox(ws, "manager")["unread_count"] == 1     # not pinged a second time
    assert _inbox(ws, "editor")["unread_count"] == 1
    # dropping a mention removes it from the comment but not the notice already sent
    r = d.patch(f"/comments/{cid}", json={"body": "v2", "mentioned_user_ids": [ws["uid"]["editor"]]})
    assert [m["full_name"] for m in r.json()["mentions"]] == ["Editor"]
    assert _inbox(ws, "manager")["unread_count"] == 1


def test_inbox_read_state(ws):
    d = _client(ws, "drafter")
    for i in range(3):
        _post(d, ws, f"c{i}", mentioned_user_ids=[ws["uid"]["manager"]])
    m = _client(ws, "manager")
    inbox = m.get("/notifications").json()
    assert inbox["unread_count"] == 3 and len(inbox["notifications"]) == 3
    first = inbox["notifications"][0]["notification_id"]           # newest first
    assert inbox["notifications"][0]["excerpt"] == "c2"
    assert m.post(f"/notifications/{first}/read").status_code == 204
    assert m.post(f"/notifications/{first}/read").status_code == 204   # idempotent
    after = m.get("/notifications", params={"unread_only": True}).json()
    assert after["unread_count"] == 2 and len(after["notifications"]) == 2
    assert m.post("/notifications/read-all").json() == {"marked": 2}
    assert m.get("/notifications").json()["unread_count"] == 0
    assert len(m.get("/notifications").json()["notifications"]) == 3   # still listed, now read


def test_you_cannot_touch_someone_elses_notification(ws):
    d = _client(ws, "drafter")
    _post(d, ws, "hi", mentioned_user_ids=[ws["uid"]["manager"]])
    nid = _inbox(ws, "manager")["notifications"][0]["notification_id"]
    assert d.post(f"/notifications/{nid}/read").status_code == 404
    assert _inbox(ws, "manager")["unread_count"] == 1
    assert d.post("/notifications/read-all").json() == {"marked": 0}
    assert _inbox(ws, "manager")["unread_count"] == 1


def test_notifications_require_login(ws):
    assert TestClient(app).get("/notifications").status_code == 401


# ------------------------------------------------------------- edit / delete ---

def test_only_the_author_can_edit_even_a_manager(ws):
    d, m = _client(ws, "drafter"), _client(ws, "manager")
    cid = _post(d, ws, "mine").json()["comment_id"]
    r = m.patch(f"/comments/{cid}", json={"body": "hijack"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "NOT_AUTHOR"
    assert d.patch(f"/comments/{cid}", json={"body": "fixed"}).json()["body"] == "fixed"


def test_unchanged_edit_is_a_noop(ws):
    d = _client(ws, "drafter")
    cid = _post(d, ws, "same").json()["comment_id"]
    out = d.patch(f"/comments/{cid}", json={"body": "same"}).json()
    assert out["edited_at"] is None
    assert not _sql("SELECT 1 FROM audit_log WHERE event = 'comment.edit'")


def test_author_or_manager_may_delete_others_may_not(ws):
    d, e, m = _client(ws, "drafter"), _client(ws, "editor"), _client(ws, "manager")
    cid = _post(d, ws, "x").json()["comment_id"]
    r = e.delete(f"/comments/{cid}")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "FORBIDDEN"
    assert d.delete(f"/comments/{cid}").status_code == 204
    cid2 = _post(d, ws, "y").json()["comment_id"]
    assert m.delete(f"/comments/{cid2}").status_code == 204          # manager moderates
    r = m.delete(f"/comments/{cid2}")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ALREADY_DELETED"


def test_deleted_comment_cannot_be_edited_or_replied_to(ws):
    d = _client(ws, "drafter")
    cid = _post(d, ws).json()["comment_id"]
    d.delete(f"/comments/{cid}")
    r = d.patch(f"/comments/{cid}", json={"body": "back"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "COMMENT_DELETED"
    r = d.post("/comments", json={"parent_id": cid, "body": "r"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "PARENT_DELETED"


def test_deleted_thread_shapes(ws):
    d, m = _client(ws, "drafter"), _client(ws, "manager")
    with_reply = _post(d, ws, "secret", mentioned_user_ids=[ws["uid"]["manager"]]).json()["comment_id"]
    m.post("/comments", json={"parent_id": with_reply, "body": "kept"})
    lonely = _post(d, ws, "lonely").json()["comment_id"]
    gone_reply = m.post("/comments", json={"parent_id": with_reply, "body": "gone"}).json()["comment_id"]
    d.delete(f"/comments/{with_reply}")
    d.delete(f"/comments/{lonely}")
    m.delete(f"/comments/{gone_reply}")
    thread = _thread(d, ws)
    assert len(thread) == 1                                # `lonely` vanished
    top = thread[0]
    assert top["deleted"] is True and top["body"] == "" and top["mentions"] == []
    assert [r["body"] for r in top["replies"]] == ["kept"]  # the deleted reply vanished
    # its notification is hidden, not counted
    assert _inbox(ws, "manager")["unread_count"] == 0
    assert [n["excerpt"] for n in _inbox(ws, "manager")["notifications"]] == []


def test_audit_and_item_edit_log(ws):
    d = _client(ws, "drafter")
    cid = _post(d, ws, "v1").json()["comment_id"]
    d.patch(f"/comments/{cid}", json={"body": "v2"})
    d.delete(f"/comments/{cid}")
    events = [r[0] for r in _sql("SELECT event FROM audit_log WHERE event LIKE 'comment.%' ORDER BY id")]
    assert events == ["comment.create", "comment.edit", "comment.delete"]
    fields = [r[0] for r in _sql("SELECT field FROM item_edit_log WHERE item_id = :i ORDER BY 1",
                                 i=ws["iid"])]
    assert sorted(fields) == sorted(["_comment_create", f"comment.{cid}", "_comment_delete"])


def test_project_comment_writes_audit_but_no_item_edit_log(ws):
    d = _client(ws, "drafter")
    _post(d, ws, "p", "project")
    assert _sql("SELECT 1 FROM audit_log WHERE event = 'comment.create'")
    assert not _sql("SELECT 1 FROM item_edit_log")


# ------------------------------------------- access is re-checked, not assumed ---

def _restrict(ws, role, grants):
    """Make `role`'s user governed by the DB alone, holding only `grants`
    (list of (module, action)). Returns the group id so a test can change it."""
    s = SessionLocal()
    try:
        gid = s.execute(text("""INSERT INTO permission_group(workspace_id, name, is_system)
                                VALUES (:w, :n, false) RETURNING group_id"""),
                        {"w": ws["wid"], "n": f"only-{role}-{uuid.uuid4().hex[:4]}"}).scalar()
        for module, action in grants:
            s.execute(text("INSERT INTO group_module_grant(group_id, module, action)"
                           " VALUES (:g, :m, :a)"), {"g": gid, "m": module, "a": action})
        s.execute(text("INSERT INTO user_group_membership(user_id, group_id, project_id)"
                       " VALUES (:u, :g, NULL)"), {"u": ws["uid"][role], "g": gid})
        s.commit()
    finally:
        s.close()
    return gid


def _set_grants(gid, grants):
    s = SessionLocal()
    try:
        s.execute(text("DELETE FROM group_module_grant WHERE group_id = :g"), {"g": gid})
        for module, action in grants:
            s.execute(text("INSERT INTO group_module_grant(group_id, module, action)"
                           " VALUES (:g, :m, :a)"), {"g": gid, "m": module, "a": action})
        s.commit()
    finally:
        s.close()


def test_item_thread_needs_list_read_as_well_as_tracking(ws):
    """The notification for an item opens the item editor (`GET /items/{id}` is
    gated on `list`), so an item thread needs both; a project thread only
    tracking. A tracking-only user is neither shown, allowed to post to, nor
    mentionable on an item."""
    _restrict(ws, "editor", [("tracking", "read"), ("tracking", "comment")])
    editor, drafter = _client(ws, "editor"), _client(ws, "drafter")
    assert editor.get("/comments", params=_target(ws, "item")).status_code == 403
    assert _post(editor, ws, "x", "item").status_code == 403
    assert editor.get("/comments", params=_target(ws, "project")).status_code == 200
    assert _post(editor, ws, "fine", "project").status_code == 201
    r = _post(drafter, ws, "hi", "item", mentioned_user_ids=[ws["uid"]["editor"]])
    assert r.status_code == 422 and r.json()["detail"]["user_ids"] == [ws["uid"]["editor"]]
    assert _post(drafter, ws, "hi", "project", mentioned_user_ids=[ws["uid"]["editor"]]).status_code == 201


def test_an_unchanged_mention_never_blocks_an_edit(ws):
    """The UI resends every `@Name` still in the text. One whose owner has since
    lost access must not make an unrelated typo fix a 422 — only *newly added*
    mentions are validated."""
    d = _client(ws, "drafter")
    cid = _post(d, ws, "@Manager see this", mentioned_user_ids=[ws["uid"]["manager"]]).json()["comment_id"]
    _restrict(ws, "manager", [])                                   # manager loses tracking:read
    r = d.patch(f"/comments/{cid}", json={"body": "@Manager see this, please",
                                          "mentioned_user_ids": [ws["uid"]["manager"]]})
    assert r.status_code == 200, r.text
    _restrict(ws, "editor", [])
    r = d.patch(f"/comments/{cid}", json={"body": "again",
                                          "mentioned_user_ids": [ws["uid"]["manager"], ws["uid"]["editor"]]})
    assert r.status_code == 422 and r.json()["detail"]["user_ids"] == [ws["uid"]["editor"]]


def test_a_reply_is_not_sent_to_a_parent_author_who_lost_access(ws):
    m, d = _client(ws, "manager"), _client(ws, "drafter")
    top = _post(m, ws, "top").json()["comment_id"]
    _restrict(ws, "manager", [])
    r = d.post("/comments", json={"parent_id": top, "body": "reply"})
    assert r.status_code == 201                                     # the reply itself is fine
    assert _sql("SELECT 1 FROM notification WHERE recipient_id = :u", u=ws["uid"]["manager"]) == []


def test_the_inbox_hides_what_the_recipient_can_no_longer_read(ws):
    d = _client(ws, "drafter")
    _post(d, ws, "on item", "item", mentioned_user_ids=[ws["uid"]["manager"]])
    _post(d, ws, "on project", "project", mentioned_user_ids=[ws["uid"]["manager"]])
    gid = _restrict(ws, "manager", [("tracking", "read"), ("list", "read")])
    assert _inbox(ws, "manager")["unread_count"] == 2
    _set_grants(gid, [("tracking", "read")])                         # loses list:read
    inbox = _inbox(ws, "manager")
    assert inbox["unread_count"] == 1
    assert [n["object_type"] for n in inbox["notifications"]] == ["project"]
    _set_grants(gid, [])                                             # loses tracking:read too
    assert _inbox(ws, "manager") == {"notifications": [], "unread_count": 0}
    _set_grants(gid, [("tracking", "read"), ("list", "read")])       # hidden, not deleted
    assert _inbox(ws, "manager")["unread_count"] == 2


def test_marking_read_is_audited_once_per_real_change(ws):
    d, m = _client(ws, "drafter"), _client(ws, "manager")
    for i in range(3):
        _post(d, ws, f"c{i}", mentioned_user_ids=[ws["uid"]["manager"]])
    first = _inbox(ws, "manager")["notifications"][0]["notification_id"]
    assert m.post(f"/notifications/{first}/read").status_code == 204
    assert m.post(f"/notifications/{first}/read").status_code == 204   # already read: no new row
    assert m.post("/notifications/read-all").json() == {"marked": 2}
    assert m.post("/notifications/read-all").json() == {"marked": 0}   # nothing changed: no row
    events = [r[0] for r in _sql(
        "SELECT event FROM audit_log WHERE event LIKE 'notification.%' ORDER BY id")]
    assert events == ["notification.read", "notification.read_all"]
    assert _sql("SELECT payload->>'marked' FROM audit_log WHERE event = 'notification.read_all'") == [("2",)]


def test_creating_a_comment_locks_its_object_against_a_racing_delete(ws):
    """Without the lock, a delete landing between the existence check and the
    INSERT turned the FK violation into a raw 500. The check now takes a
    FOR KEY SHARE lock, so a concurrent DELETE waits for the comment's txn."""
    from app.comments import queries as cq
    holder, deleter = SessionLocal(), SessionLocal()
    try:
        assert cq._object_in_workspace(holder, object_type="item", object_id=ws["iid"],
                                       workspace_id=ws["wid"], lock=True)
        deleter.execute(text("SET LOCAL lock_timeout = '300ms'"))
        with pytest.raises(OperationalError):
            deleter.execute(text("DELETE FROM items WHERE item_id = :i"), {"i": ws["iid"]})
    finally:
        deleter.rollback(); deleter.close()
        holder.rollback(); holder.close()


def test_a_comment_can_mention_at_most_twenty_people(ws):
    d = _client(ws, "drafter")
    r = _post(d, ws, "x", mentioned_user_ids=list(range(1, 22)))
    # rejected by the schema (a validation-error list), not by BAD_MENTION (a dict)
    assert r.status_code == 422 and isinstance(r.json()["detail"], list)
