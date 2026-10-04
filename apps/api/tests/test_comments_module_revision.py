"""Comment threads on Modules and Shop-drawing revisions (migration 0043,
Plan V1 §29 — Component = a Module, Revision = a shop-drawing revision).

The point of the change is that a thread is governed by the module its object
lives under, not by `tracking`: a Module by `list`, a revision by `shop_dwgs`.
So these tests mostly pin *who* may do what, in both directions:

* a group with only `list` grants can read and post on a module thread; one with
  only `tracking` cannot even read it (and the same for `shop_dwgs`);
* edit / delete / reply resolve the comment's own module, so revoking `list:
  comment` stops the author editing a module comment;
* mentions and the inbox follow the same per-type modules.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.db import SessionLocal

from .helpers_comments import (  # noqa: F401
    _ID, _client, _extend, _inbox, _restrict, _set_grants, _sql, _t, _workspace, module_revision_ws,
    post_module as _post,
)






KINDS = ("module", "revision")






def _thread(c, ws, kind):
    r = c.get("/comments", params=_t(ws, kind))
    assert r.status_code == 200, r.text
    return r.json()["comments"]


# ------------------------------------------------------------------ basics ---

@pytest.mark.parametrize("kind", KINDS)
def test_module_and_revision_threads_round_trip(ws, kind):
    d = _client(ws, "drafter")
    out = _post(d, ws, "First!", kind)
    assert out.status_code == 201, out.text
    body = out.json()
    assert body["object_type"] == kind and body["object_id"] == ws[_ID[kind]]
    assert [c["body"] for c in _thread(d, ws, kind)] == ["First!"]
    r = d.post("/comments", json={"parent_id": body["comment_id"], "body": "re"})
    assert r.status_code == 201 and r.json()["object_type"] == kind
    assert [x["body"] for x in _thread(d, ws, kind)[0]["replies"]] == ["re"]


def test_threads_are_per_object_across_all_six_types(ws):
    d = _client(ws, "drafter")
    for kind in ("item", "project", *KINDS):
        _post(d, ws, f"on {kind}", kind)
    for kind in ("item", "project", *KINDS):
        assert [c["body"] for c in _thread(d, ws, kind)] == [f"on {kind}"]


def test_the_database_holds_exactly_one_object(ws):
    """The CHECK now covers six columns, and `object_type` is regenerated."""
    s = SessionLocal()
    try:
        with pytest.raises(IntegrityError):
            s.execute(text("""INSERT INTO comment(workspace_id, module_id, revision_id, body)
                              VALUES (:w, :m, :v, 'x')"""),
                      {"w": ws["wid"], "m": ws["mid"], "v": ws["vid"]})
        s.rollback()
        with pytest.raises(IntegrityError):
            s.execute(text("INSERT INTO comment(workspace_id, body) VALUES (:w, 'x')"),
                      {"w": ws["wid"]})
        s.rollback()
        types = {r[0] for r in s.execute(text("""
            INSERT INTO comment(workspace_id, module_id, body) VALUES (:w, :m, 'a')
            RETURNING object_type"""), {"w": ws["wid"], "m": ws["mid"]})}
        types |= {r[0] for r in s.execute(text("""
            INSERT INTO comment(workspace_id, revision_id, body) VALUES (:w, :v, 'b')
            RETURNING object_type"""), {"w": ws["wid"], "v": ws["vid"]})}
        assert types == {"module", "revision"}
    finally:
        s.rollback()
        s.close()


def test_a_related_parts_module_has_no_thread(ws):
    """Joinery Items only: the module's thread links to the item editor."""
    d = _client(ws, "drafter")
    t = {"object_type": "module", "object_id": ws["rp_mid"]}
    assert d.get("/comments", params=t).status_code == 404
    assert d.post("/comments", json={**t, "body": "x"}).status_code == 404


@pytest.mark.parametrize("kind", KINDS)
def test_workspace_isolation(ws, kind, truncate_all):
    other = _extend(_workspace())
    mine, theirs = _client(ws, "manager"), _client(other, "manager")
    cid = _post(mine, ws, "secret", kind).json()["comment_id"]
    assert theirs.get("/comments", params=_t(ws, kind)).status_code == 404
    assert _post(theirs, ws, "x", kind).status_code == 404
    assert theirs.patch(f"/comments/{cid}", json={"body": "x"}).status_code == 404
    assert theirs.delete(f"/comments/{cid}").status_code == 404
    assert theirs.post("/comments", json={"parent_id": cid, "body": "r"}).status_code == 404


def test_deleting_the_module_or_revision_takes_its_thread_with_it(ws):
    d = _client(ws, "drafter")
    _post(d, ws, "m", "module")
    _post(d, ws, "v", "revision")
    s = SessionLocal()
    try:
        s.execute(text("DELETE FROM modules WHERE module_id = :m"), {"m": ws["mid"]})
        s.execute(text("DELETE FROM shop_drawing_revision WHERE revision_id = :v"), {"v": ws["vid"]})
        s.commit()
        assert s.execute(text("SELECT count(*) FROM comment WHERE workspace_id = :w"),
                         {"w": ws["wid"]}).scalar() == 0
    finally:
        s.close()


@pytest.mark.parametrize("kind,table,col", [("module", "modules", "module_id"),
                                            ("revision", "shop_drawing_revision", "revision_id")])
def test_creating_a_comment_locks_its_object_against_a_racing_delete(ws, kind, table, col):
    """As for the original four: the existence check takes FOR KEY SHARE, so a
    concurrent DELETE waits instead of turning the INSERT into a raw FK 500."""
    from app.comments import queries as cq
    holder, deleter = SessionLocal(), SessionLocal()
    try:
        assert cq._object_in_workspace(holder, object_type=kind, object_id=ws[_ID[kind]],
                                       workspace_id=ws["wid"], lock=True)
        deleter.execute(text("SET LOCAL lock_timeout = '300ms'"))
        with pytest.raises(OperationalError):
            deleter.execute(text(f"DELETE FROM {table} WHERE {col} = :i"), {"i": ws[_ID[kind]]})
    finally:
        deleter.rollback(); deleter.close()
        holder.rollback(); holder.close()


# -------------------------------------------------- each type's own module ---

def test_default_roles_follow_list_and_shop_dwgs_not_tracking(ws):
    """purchase_officer holds tracking:comment but only *read* on `list` and
    `shop_dwgs`: it can comment on an item, and read but not write a module or
    revision thread. Under the old fixed `tracking` gate it could have done all."""
    po, viewer = _client(ws, "purchase_officer"), _client(ws, "viewer")
    assert _post(po, ws, "fine", "item").status_code == 201
    for kind in KINDS:
        assert po.get("/comments", params=_t(ws, kind)).status_code == 200
        assert _post(po, ws, "no", kind).status_code == 403
        assert viewer.get("/comments", params=_t(ws, kind)).status_code == 200
        assert _post(viewer, ws, "no", kind).status_code == 403
    for role in ("editor", "drafter", "manager"):
        for kind in KINDS:
            assert _post(_client(ws, role), ws, "ok", kind).status_code == 201


@pytest.mark.parametrize("kind,module", [("module", "list"), ("revision", "shop_dwgs")])
def test_a_group_with_only_the_objects_own_module_can_read_and_post(ws, kind, module):
    """No `tracking` grant at all — the thread is not gated on it."""
    _restrict(ws, "editor", [(module, "read"), (module, "comment")])
    e = _client(ws, "editor")
    assert _thread(e, ws, kind) == []
    assert _post(e, ws, "hi", kind).status_code == 201
    other = "revision" if kind == "module" else "module"
    assert e.get("/comments", params=_t(ws, other)).status_code == 403
    assert e.get("/comments", params=_t(ws, "project")).status_code == 403


@pytest.mark.parametrize("kind", KINDS)
def test_tracking_alone_does_not_reach_a_module_or_revision_thread(ws, kind):
    _restrict(ws, "editor", [("tracking", "read"), ("tracking", "comment")])
    e = _client(ws, "editor")
    assert e.get("/comments", params=_t(ws, kind)).status_code == 403
    assert _post(e, ws, "x", kind).status_code == 403
    assert _post(e, ws, "x", "project").status_code == 201


@pytest.mark.parametrize("kind,module", [("module", "list"), ("revision", "shop_dwgs")])
def test_comment_without_read_is_refused(ws, kind, module):
    """`comment` alone is not enough: the notification link must be openable."""
    _restrict(ws, "editor", [(module, "comment")])
    assert _post(_client(ws, "editor"), ws, "x", kind).status_code == 403


@pytest.mark.parametrize("kind,module", [("module", "list"), ("revision", "shop_dwgs")])
def test_edit_and_delete_follow_the_comments_own_module(ws, kind, module):
    """Revoking the object's `comment` grant stops the author editing or deleting
    — the routes resolve the comment's type before checking, since the module
    that governs it depends on what it is a comment on."""
    gid = _restrict(ws, "editor", [(module, "read"), (module, "comment"), ("tracking", "comment")])
    e = _client(ws, "editor")
    cid = _post(e, ws, "mine", kind).json()["comment_id"]
    assert e.patch(f"/comments/{cid}", json={"body": "v2"}).status_code == 200
    _set_grants(gid, [(module, "read"), ("tracking", "comment")])   # tracking:comment is not it
    assert e.patch(f"/comments/{cid}", json={"body": "v3"}).status_code == 403
    assert e.delete(f"/comments/{cid}").status_code == 403
    _set_grants(gid, [(module, "read"), (module, "comment")])
    assert e.delete(f"/comments/{cid}").status_code == 204


def test_edit_or_delete_of_an_unknown_comment_is_404(ws):
    d = _client(ws, "drafter")
    assert d.patch("/comments/999999", json={"body": "x"}).status_code == 404
    assert d.delete("/comments/999999").status_code == 404


@pytest.mark.parametrize("kind", KINDS)
def test_a_reply_needs_comment_on_the_parents_module(ws, kind):
    top = _post(_client(ws, "drafter"), ws, "top", kind).json()["comment_id"]
    reply = {"parent_id": top, "body": "re"}
    assert _client(ws, "purchase_officer").post("/comments", json=reply).status_code == 403
    assert _client(ws, "viewer").post("/comments", json=reply).status_code == 403
    assert _client(ws, "editor").post("/comments", json=reply).status_code == 201


def test_a_reply_on_an_item_thread_now_needs_list_read_too(ws):
    """Replies used to skip the read check (a reply names no object, so the route
    had no type to check). The type now comes from the parent, so the documented
    rule — an item thread needs `tracking` *and* `list` — holds for replies."""
    top = _post(_client(ws, "drafter"), ws, "top", "item").json()["comment_id"]
    _restrict(ws, "editor", [("tracking", "read"), ("tracking", "comment")])
    r = _client(ws, "editor").post("/comments", json={"parent_id": top, "body": "re"})
    assert r.status_code == 403


# ---------------------------------------------------------------- mentions ---

@pytest.mark.parametrize("kind,module", [("module", "list"), ("revision", "shop_dwgs")])
def test_mentions_need_read_on_the_objects_module(ws, kind, module):
    d = _client(ws, "drafter")
    _restrict(ws, "editor", [("tracking", "read")])                 # cannot open it
    r = _post(d, ws, "hi", kind, mentioned_user_ids=[ws["uid"]["editor"]])
    assert r.status_code == 422 and r.json()["detail"]["user_ids"] == [ws["uid"]["editor"]]
    _restrict(ws, "manager", [(module, "read")])                    # can, with no tracking
    ok = _post(d, ws, "hi", kind, mentioned_user_ids=[ws["uid"]["manager"]])
    assert ok.status_code == 201
    assert not _sql("SELECT 1 FROM comment WHERE body = 'hi' AND EXISTS ("
                    "SELECT 1 FROM comment_mention m WHERE m.comment_id = comment.comment_id"
                    " AND m.user_id = :u)", u=ws["uid"]["editor"])


# ------------------------------------------------------------ notifications ---

def test_notifications_link_to_the_module_and_the_revision(ws):
    d = _client(ws, "drafter")
    for kind in KINDS:
        _post(d, ws, kind, kind, mentioned_user_ids=[ws["uid"]["manager"]])
    by_type = {n["object_type"]: n for n in _inbox(ws, "manager")["notifications"]}
    m, v = by_type["module"], by_type["revision"]
    assert m["object_id"] == ws["mid"] and v["object_id"] == ws["vid"]
    assert m["url"] == f"/items/{ws['iid']}?tab=cutlist&module={ws['mid']}"
    assert v["url"] == (f"/shop-dwgs?project={ws['pid']}&drawing={ws['did']}"
                        f"&rev={ws['vid']}&comments=1")
    assert m["object_label"] == f"M01 Base (#{ws['num']})"
    assert v["object_label"] == "Vanity plan · v1"


def test_a_reply_notifies_the_parent_author_on_a_revision(ws):
    top = _post(_client(ws, "drafter"), ws, "top", "revision").json()["comment_id"]
    _client(ws, "editor").post("/comments", json={"parent_id": top, "body": "re"})
    n = _inbox(ws, "drafter")["notifications"]
    assert [(x["kind"], x["object_type"]) for x in n] == [("reply", "revision")]


def test_the_inbox_follows_each_types_own_modules(ws):
    d = _client(ws, "drafter")
    for kind in ("project", *KINDS):
        _post(d, ws, kind, kind, mentioned_user_ids=[ws["uid"]["manager"]])
    gid = _restrict(ws, "manager", [("tracking", "read"), ("list", "read"), ("shop_dwgs", "read")])
    assert _inbox(ws, "manager")["unread_count"] == 3
    _set_grants(gid, [("tracking", "read"), ("list", "read")])            # loses shop_dwgs
    assert sorted(n["object_type"] for n in _inbox(ws, "manager")["notifications"]) == ["module", "project"]
    _set_grants(gid, [("tracking", "read"), ("shop_dwgs", "read")])       # loses list
    assert sorted(n["object_type"] for n in _inbox(ws, "manager")["notifications"]) == ["project", "revision"]
    _set_grants(gid, [("list", "read")])                                  # no tracking at all
    inbox = _inbox(ws, "manager")
    assert [n["object_type"] for n in inbox["notifications"]] == ["module"]
    assert inbox["unread_count"] == 1
    _set_grants(gid, [])
    assert _inbox(ws, "manager") == {"notifications": [], "unread_count": 0}
    _set_grants(gid, [("tracking", "read"), ("list", "read"), ("shop_dwgs", "read")])
    assert _inbox(ws, "manager")["unread_count"] == 3                     # hidden, not deleted


# --------------------------------------------------------- audit + edit log ---

def test_a_module_comment_logs_against_its_item_and_a_revision_comment_does_not(ws):
    d = _client(ws, "drafter")
    cid = _post(d, ws, "v1", "module").json()["comment_id"]
    d.patch(f"/comments/{cid}", json={"body": "v2"})
    d.delete(f"/comments/{cid}")
    fields = [r[0] for r in _sql("SELECT field FROM item_edit_log WHERE item_id = :i", i=ws["iid"])]
    assert sorted(fields) == sorted(["_comment_create", f"comment.{cid}", "_comment_delete"])
    assert [r[0] for r in _sql("SELECT event FROM audit_log WHERE event LIKE 'comment.%' ORDER BY id")] \
        == ["comment.create", "comment.edit", "comment.delete"]
    targets = {r[0] for r in _sql("SELECT target FROM audit_log WHERE event LIKE 'comment.%'")}
    assert targets == {f"module:{ws['mid']}"}

    before = len(_sql("SELECT 1 FROM item_edit_log"))
    _post(d, ws, "on the drawing", "revision")
    assert len(_sql("SELECT 1 FROM item_edit_log")) == before
    assert _sql("SELECT 1 FROM audit_log WHERE target = :t", t=f"revision:{ws['vid']}")
