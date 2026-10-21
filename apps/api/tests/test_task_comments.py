"""Comment threads on a Task (migration 0082; spec docs/archive/2026-10-21-tasks.md).

A task's thread follows the task, not a module: it is visible to whoever can see the task (a 404 for
anyone else), and posting needs `comment` on the target's module, or just seeing the task when it has
no target. Mentions and notifications follow the same visibility.
"""
import pytest

from app.auth import rbac_engine

from .conftest import truncate_fixture
from .helpers_tasks import client, sql, workspace

_cleanup = truncate_fixture()


@pytest.fixture
def ws():
    return workspace()


def _task(c, **body):
    body.setdefault("title", "Chase the hinge supplier")
    r = c.post("/tasks", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _thread(c, tid):
    r = c.get("/comments", params={"object_type": "task", "object_id": tid})
    assert r.status_code == 200, r.text
    return r.json()["comments"]


def _post(c, tid, body="Rang them, back Friday", **extra):
    return c.post("/comments", json={"object_type": "task", "object_id": tid, "body": body, **extra})


# --- a targeted task: the module's grants -----------------------------------------------------

def test_a_thread_on_an_item_task_posts_replies_edits_deletes_and_counts(ws):
    mgr, editor = client(ws, "manager"), client(ws, "editor")
    t = _task(mgr, item_id=ws["iid"])
    r = _post(editor, t["task_id"])
    assert r.status_code == 201, r.text
    first = r.json()
    assert (first["object_type"], first["object_id"]) == ("task", t["task_id"])
    reply = editor.post("/comments", json={"parent_id": first["comment_id"], "body": "and again"})
    assert reply.status_code == 201 and reply.json()["object_type"] == "task"
    thread = _thread(mgr, t["task_id"])
    assert [c["body"] for c in thread] == ["Rang them, back Friday"]
    assert [c["body"] for c in thread[0]["replies"]] == ["and again"]
    # the task row carries the count and the caller's right to post
    row = mgr.get(f"/tasks/{t['task_id']}").json()
    assert row["comment_count"] == 2 and row["can_comment"] is True
    # editing is the author's, deleting the author's or a manager's
    assert mgr.patch(f"/comments/{first['comment_id']}", json={"body": "x"}).status_code == 403
    assert editor.patch(f"/comments/{first['comment_id']}", json={"body": "edited"}).status_code == 200
    assert mgr.delete(f"/comments/{reply.json()['comment_id']}").status_code == 204
    assert mgr.get(f"/tasks/{t['task_id']}").json()["comment_count"] == 1
    # an item task's thread is on the item's edit log too, like the task's own writes
    assert sql("SELECT count(*) FROM item_edit_log WHERE item_id = :i AND field LIKE '_comment%'",
               i=ws["iid"]) == 3
    assert sql("SELECT count(*) FROM audit_log WHERE event LIKE 'comment.%'"
               " AND target = :t", t=f"task:{t['task_id']}") == 4


def test_reading_needs_the_task_module_and_posting_needs_comment(ws):
    mgr, viewer = client(ws, "manager"), client(ws, "viewer")
    on_item = _task(mgr, item_id=ws["iid"])
    on_cutlist = _task(mgr, cutlist_id=ws["cid"], title="Cut the hinge sheet")
    assert _post(mgr, on_item["task_id"]).status_code == 201
    assert len(_thread(viewer, on_item["task_id"])) == 1                  # a viewer reads
    r = _post(viewer, on_item["task_id"])
    assert r.status_code == 403                                           # but may not post
    assert viewer.get(f"/tasks/{on_item['task_id']}").json()["can_comment"] is False
    po = client(ws, "purchase_officer")                                   # list: read only
    assert po.get("/comments", params={"object_type": "task", "object_id": on_cutlist["task_id"]}).status_code == 200
    assert _post(po, on_cutlist["task_id"]).status_code == 403
    assert _post(po, on_item["task_id"]).status_code == 201               # tracking:comment


def test_a_task_the_caller_cannot_read_has_no_thread(ws, monkeypatch):
    mgr, viewer = client(ws, "manager"), client(ws, "viewer")
    t = _task(mgr, cutlist_id=ws["cid"])
    assert _post(mgr, t["task_id"]).status_code == 201
    matrix = {**rbac_engine.MATRIX, "viewer": {**rbac_engine.MATRIX["viewer"], "list": set()}}
    monkeypatch.setattr(rbac_engine, "MATRIX", matrix)
    r = viewer.get("/comments", params={"object_type": "task", "object_id": t["task_id"]})
    ghost = viewer.get("/comments", params={"object_type": "task", "object_id": 2_000_000_000})
    assert (r.status_code, r.json()) == (ghost.status_code, ghost.json()) == (404, {"detail": "not found"})


# --- a task with no target: its people ---------------------------------------------------------

def test_a_private_tasks_thread_is_its_creators_assignees_and_managers(ws):
    viewer = client(ws, "viewer")                  # no tracking:comment, but the task is theirs
    own = _task(viewer)
    assert _post(viewer, own["task_id"], "mine").status_code == 201       # seeing it is enough
    assert _post(client(ws, "manager"), own["task_id"], "noted").status_code == 201
    assert viewer.get(f"/tasks/{own['task_id']}").json()["can_comment"] is True

    editor = client(ws, "editor")
    t = _task(editor, assignee_id=ws["uid"]["drafter"])
    tid = t["task_id"]
    assert _post(editor, tid, "for you").status_code == 201
    assert _post(client(ws, "drafter"), tid, "on it").status_code == 201  # the assignee
    assert len(_thread(client(ws, "admin"), tid)) == 2                    # an admin
    stranger = client(ws, "estimator")             # has tracking:comment, but is not on the task
    ghost = stranger.get("/comments", params={"object_type": "task", "object_id": 2_000_000_000})
    r = stranger.get("/comments", params={"object_type": "task", "object_id": tid})
    assert (r.status_code, r.json()) == (ghost.status_code, ghost.json()) == (404, {"detail": "not found"})
    assert _post(stranger, tid).status_code == 404
    first = _thread(editor, tid)[0]["comment_id"]
    assert stranger.patch(f"/comments/{first}", json={"body": "x"}).status_code == 404
    assert stranger.delete(f"/comments/{first}").status_code == 404
    assert stranger.post("/comments", json={"parent_id": first, "body": "x"}).status_code == 404


def test_a_soft_deleted_item_hides_the_thread_of_its_tasks(ws):
    mgr = client(ws, "manager")
    t = _task(mgr, item_id=ws["iid"])
    assert _post(mgr, t["task_id"]).status_code == 201
    sql("UPDATE items SET deleted = true WHERE item_id = :i", i=ws["iid"])
    assert mgr.get("/comments", params={"object_type": "task", "object_id": t["task_id"]}).status_code == 404
    assert _post(mgr, t["task_id"]).status_code == 404


def test_another_workspaces_task_thread_answers_like_a_missing_one(ws):
    other = workspace()
    t = _task(client(other, "admin"), item_id=other["iid"])
    assert _post(client(other, "admin"), t["task_id"]).status_code == 201
    admin = client(ws, "admin")
    real = admin.get("/comments", params={"object_type": "task", "object_id": t["task_id"]})
    ghost = admin.get("/comments", params={"object_type": "task", "object_id": 2_000_000_000})
    assert (real.status_code, real.json()) == (ghost.status_code, ghost.json())
    r, g = _post(admin, t["task_id"]), _post(admin, 2_000_000_000)
    assert (r.status_code, r.json()) == (g.status_code, g.json()) == (404, {"detail": "not found"})


# --- mentions and notifications ----------------------------------------------------------------

def test_only_people_who_can_see_the_task_can_be_mentioned(ws):
    editor = client(ws, "editor")
    t = _task(editor, assignee_id=ws["uid"]["drafter"])                    # private to editor + drafter
    r = _post(editor, t["task_id"], "cc", mentioned_user_ids=[ws["uid"]["estimator"]])
    assert r.status_code == 422 and r.json()["detail"] == {
        "code": "BAD_MENTION", "user_ids": [ws["uid"]["estimator"]]}
    ok = _post(editor, t["task_id"], "cc", mentioned_user_ids=[ws["uid"]["drafter"], ws["uid"]["manager"]])
    assert ok.status_code == 201, ok.text


def test_a_mention_and_a_reply_reach_the_inbox_and_open_the_task(ws):
    editor, drafter = client(ws, "editor"), client(ws, "drafter")
    t = _task(editor, item_id=ws["iid"], title="Order the plinth")
    first = _post(editor, t["task_id"], "@Drafter please", mentioned_user_ids=[ws["uid"]["drafter"]]).json()
    inbox = drafter.get("/notifications").json()
    n = [x for x in inbox["notifications"] if x["object_type"] == "task"]
    assert len(n) == 1 and inbox["unread_count"] == 1
    assert (n[0]["kind"], n[0]["object_id"], n[0]["object_label"]) == ("mention", t["task_id"], "Order the plinth")
    assert n[0]["url"] == f"/tasks?task={t['task_id']}"
    reply = drafter.post("/comments", json={"parent_id": first["comment_id"], "body": "on it"})
    assert reply.status_code == 201
    kinds = [x["kind"] for x in editor.get("/notifications").json()["notifications"] if x["object_type"] == "task"]
    assert kinds == ["reply"]


def test_a_task_notification_is_hidden_once_the_recipient_cannot_see_the_task(ws):
    mgr, drafter = client(ws, "manager"), client(ws, "drafter")
    t = _task(mgr, item_id=ws["iid"])
    assert _post(mgr, t["task_id"], "hi", mentioned_user_ids=[ws["uid"]["drafter"]]).status_code == 201
    assert drafter.get("/notifications").json()["unread_count"] == 1
    sql("UPDATE items SET deleted = true WHERE item_id = :i", i=ws["iid"])
    body = drafter.get("/notifications").json()
    assert body["unread_count"] == 0 and [x for x in body["notifications"] if x["object_type"] == "task"] == []
    sql("UPDATE items SET deleted = false WHERE item_id = :i", i=ws["iid"])           # it reappears
    assert drafter.get("/notifications").json()["unread_count"] == 1
