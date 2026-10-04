"""Comment counts on Modules and shop-drawing revisions.

The Areas & Rooms card has had badges since §29 shipped; a module and a revision
had none, so their threads were found only by opening them. The counts ride on
payloads the screens already fetch — `GET /items/{id}` (each module) and
`GET /shop-drawings/{id}` (each revision) — so each is gated by the route whose
read rule already matches its thread's (`list:read`, `shop_dwgs:read`).

A count is the thread's **live** comments, replies included, deleted ones not:
the rule the Areas & Rooms badges and the register's per-drawing count follow.
"""
from sqlalchemy import text

from app.db import SessionLocal

from .test_comments import _client
from .test_comments_module_revision import _post, ws  # noqa: F401


def _item_modules(c, ws) -> dict[int, dict]:
    r = c.get(f"/items/{ws['iid']}")
    assert r.status_code == 200, r.text
    return {m["id"]: m for m in r.json()["modules"]}


def _revisions(c, ws) -> dict[int, dict]:
    r = c.get(f"/shop-drawings/{ws['did']}")
    assert r.status_code == 200, r.text
    return {x["revision_id"]: x for x in r.json()["revisions"]}


def _second_module(ws) -> int:
    s = SessionLocal()
    try:
        mid = s.execute(text("""INSERT INTO modules(item_id, module_no, name)
                                VALUES (:i, 'M02', 'Wall') RETURNING module_id"""),
                        {"i": ws["iid"]}).scalar()
        s.commit()
        return mid
    finally:
        s.close()


def _second_revision(ws) -> int:
    """Revision 2 of the drawing. Revision 1 is approved first: at most one draft /
    pending revision may exist per drawing."""
    s = SessionLocal()
    try:
        s.execute(text("UPDATE shop_drawing_revision SET status = 'approved' WHERE revision_id = :v"),
                  {"v": ws["vid"]})
        blob = s.execute(text("SELECT file_blob_id FROM shop_drawing_revision WHERE revision_id = :v"),
                         {"v": ws["vid"]}).scalar()
        vid = s.execute(text("""INSERT INTO shop_drawing_revision(
                                    drawing_id, rev_no, file_blob_id, status, uploaded_by)
                                VALUES (:d, 2, :b, 'draft', :u) RETURNING revision_id"""),
                        {"d": ws["did"], "b": blob, "u": ws["uid"]["drafter"]}).scalar()
        s.commit()
        return vid
    finally:
        s.close()


# ------------------------------------------------------------------ modules ---

def test_a_module_with_no_comments_reads_zero(ws):
    assert _item_modules(_client(ws, "viewer"), ws)[ws["mid"]]["comment_count"] == 0


def test_a_modules_count_is_its_live_thread_replies_included(ws):
    d = _client(ws, "drafter")
    first = _post(d, ws, "one", "module").json()["comment_id"]
    _post(d, ws, "two", "module")
    d.post("/comments", json={"parent_id": first, "body": "a reply"})

    assert _item_modules(d, ws)[ws["mid"]]["comment_count"] == 3


def test_counts_are_per_module_not_per_item(ws):
    other = _second_module(ws)
    d = _client(ws, "drafter")
    _post(d, ws, "on the base", "module")

    mods = _item_modules(d, ws)
    assert mods[ws["mid"]]["comment_count"] == 1
    assert mods[other]["comment_count"] == 0


def test_item_and_project_threads_do_not_count_toward_a_module(ws):
    d = _client(ws, "drafter")
    _post(d, ws, "on the item", "item")
    _post(d, ws, "on the project", "project")

    assert _item_modules(d, ws)[ws["mid"]]["comment_count"] == 0


def test_a_deleted_comment_is_not_counted(ws):
    d = _client(ws, "drafter")
    gone = _post(d, ws, "gone", "module").json()["comment_id"]
    _post(d, ws, "kept", "module")
    assert _item_modules(d, ws)[ws["mid"]]["comment_count"] == 2

    assert d.delete(f"/comments/{gone}").status_code == 204

    assert _item_modules(d, ws)[ws["mid"]]["comment_count"] == 1


def test_a_deleted_parent_with_a_live_reply_counts_only_the_reply(ws):
    """The parent survives as a blanked placeholder but is not a live comment."""
    d = _client(ws, "drafter")
    parent = _post(d, ws, "parent", "module").json()["comment_id"]
    d.post("/comments", json={"parent_id": parent, "body": "reply"})
    assert d.delete(f"/comments/{parent}").status_code == 204

    assert _item_modules(d, ws)[ws["mid"]]["comment_count"] == 1


def test_module_create_and_patch_responses_carry_the_true_count(ws):
    d = _client(ws, "drafter")
    _post(d, ws, "one", "module")
    _post(d, ws, "two", "module")

    patched = d.patch(f"/modules/{ws['mid']}", json={"name": "Base renamed"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["comment_count"] == 2

    created = d.post(f"/items/{ws['iid']}/modules", json={"module_no": "M09", "name": "New"})
    assert created.status_code == 201, created.text
    assert created.json()["comment_count"] == 0


def test_a_read_only_role_sees_the_same_module_count(ws):
    _post(_client(ws, "drafter"), ws, "hi", "module")
    assert _item_modules(_client(ws, "viewer"), ws)[ws["mid"]]["comment_count"] == 1


# ---------------------------------------------------------------- revisions ---

def test_a_revision_with_no_comments_reads_zero(ws):
    assert _revisions(_client(ws, "viewer"), ws)[ws["vid"]]["comment_count"] == 0


def test_a_revisions_count_is_its_live_thread_replies_included(ws):
    m = _client(ws, "manager")
    first = _post(m, ws, "one", "revision").json()["comment_id"]
    _post(m, ws, "two", "revision")
    m.post("/comments", json={"parent_id": first, "body": "a reply"})

    assert _revisions(m, ws)[ws["vid"]]["comment_count"] == 3


def test_counts_are_per_revision_not_per_drawing(ws):
    v2 = _second_revision(ws)
    m = _client(ws, "manager")
    _post(m, ws, "on v1", "revision")

    revs = _revisions(m, ws)
    assert revs[ws["vid"]]["comment_count"] == 1
    assert revs[v2]["comment_count"] == 0


def test_other_threads_do_not_count_toward_a_revision(ws):
    m = _client(ws, "manager")
    _post(m, ws, "on the item", "item")
    _post(m, ws, "on the module", "module")

    assert _revisions(m, ws)[ws["vid"]]["comment_count"] == 0


def test_a_deleted_revision_comment_is_not_counted(ws):
    m = _client(ws, "manager")
    gone = _post(m, ws, "gone", "revision").json()["comment_id"]
    _post(m, ws, "kept", "revision")
    assert _revisions(m, ws)[ws["vid"]]["comment_count"] == 2

    assert m.delete(f"/comments/{gone}").status_code == 204

    assert _revisions(m, ws)[ws["vid"]]["comment_count"] == 1


def test_every_route_returning_a_drawing_detail_carries_the_count(ws):
    """PATCH answers with the same detail the GET does, so its revisions must not
    read zero while the thread has comments."""
    d = _client(ws, "drafter")
    _post(d, ws, "one", "revision")

    r = d.patch(f"/shop-drawings/{ws['did']}", json={"title": "Vanity plan v2"})

    assert r.status_code == 200, r.text
    assert {x["revision_id"]: x["comment_count"] for x in r.json()["revisions"]} == {ws["vid"]: 1}


def test_counts_do_not_cross_workspaces(ws):
    from .test_comments_module_revision import _extend
    from .test_comments import _workspace

    other = _extend(_workspace())
    _post(_client(other, "manager"), other, "theirs", "module")
    _post(_client(other, "manager"), other, "theirs", "revision")

    assert _item_modules(_client(ws, "manager"), ws)[ws["mid"]]["comment_count"] == 0
    assert _revisions(_client(ws, "manager"), ws)[ws["vid"]]["comment_count"] == 0
