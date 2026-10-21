"""Tasks (migration 0080, Plan V1 §10, Q524): create / read / edit / status, who may do
what, and what a soft-deleted target does. Spec: docs/archive/2026-10-21-tasks.md."""
import pytest

from app.auth import rbac_engine

from .conftest import truncate_fixture
from .helpers_tasks import client, sql, workspace

_cleanup = truncate_fixture()


@pytest.fixture
def ws():
    return workspace()


def _make(c, **body):
    body.setdefault("title", "Chase the hinge supplier")
    r = c.post("/tasks", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# --- create -------------------------------------------------------------------------------

def test_create_on_an_item_returns_the_task_and_writes_audit_and_edit_log(ws):
    mgr = client(ws, "manager")
    t = _make(mgr, item_id=ws["iid"], assignee_id=ws["uid"]["drafter"], due_date="2026-11-01")
    assert t["status"] == "open" and t["source"] == "manual"
    assert t["target_type"] == "item" and t["item_id"] == ws["iid"] and t["target_label"]
    assert t["assignee_name"] == "Drafter" and t["created_by"] == ws["uid"]["manager"]
    assert t["due_date"] == "2026-11-01" and t["field_versions"] == {}
    assert sql("SELECT count(*) FROM audit_log WHERE event = 'task.create'"
               " AND target = :t", t=f"task:{t['task_id']}") == 1
    assert sql("SELECT count(*) FROM item_edit_log WHERE item_id = :i AND field = '_task_create'",
               i=ws["iid"]) == 1


@pytest.mark.parametrize("target", ["project_id", "cutlist_id"])
def test_create_on_a_project_or_cutlist(ws, target):
    key = {"project_id": "pid", "cutlist_id": "cid"}[target]
    t = _make(client(ws, "manager"), **{target: ws[key]})
    assert t["target_type"] == target.removesuffix("_id")


def test_create_with_no_target_and_no_assignee(ws):
    t = _make(client(ws, "viewer"))
    assert t["target_type"] is None and t["assignee_id"] is None


def test_title_is_stripped_and_blank_or_two_targets_are_422(ws):
    mgr = client(ws, "manager")
    assert _make(mgr, title="  spaced  ")["title"] == "spaced"
    assert mgr.post("/tasks", json={"title": "   "}).status_code == 422
    assert mgr.post("/tasks", json={"title": "x", "item_id": ws["iid"],
                                    "project_id": ws["pid"]}).status_code == 422


@pytest.mark.parametrize("which", ["related_part", "ghost", "deleted_item", "deleted_cutlist"])
def test_a_missing_deleted_or_related_part_target_is_404(ws, which):
    mgr = client(ws, "manager")
    if which == "deleted_item":
        sql("UPDATE items SET deleted = true WHERE item_id = :i", i=ws["iid"])
    if which == "deleted_cutlist":
        sql("UPDATE cutlist SET deleted = true WHERE cutlist_id = :c", c=ws["cid"])
    body = {"related_part": {"item_id": ws["rp"]}, "ghost": {"item_id": 2_000_000_000},
            "deleted_item": {"item_id": ws["iid"]}, "deleted_cutlist": {"cutlist_id": ws["cid"]}}[which]
    r = mgr.post("/tasks", json={"title": "x", **body})
    assert r.status_code == 404 and r.json() == {"detail": "not found"}


def test_another_workspace_target_and_assignee_answer_like_missing_ones(ws):
    other = workspace()
    mgr = client(ws, "manager")
    foreign_item = mgr.post("/tasks", json={"title": "x", "item_id": other["iid"]})
    ghost_item = mgr.post("/tasks", json={"title": "x", "item_id": 2_000_000_000})
    assert (foreign_item.status_code, foreign_item.json()) == (ghost_item.status_code, ghost_item.json())
    foreign_user = mgr.post("/tasks", json={"title": "x", "assignee_id": other["uid"]["editor"]})
    ghost_user = mgr.post("/tasks", json={"title": "x", "assignee_id": 2_000_000_000})
    assert foreign_user.status_code == ghost_user.status_code == 404
    assert foreign_user.json() == ghost_user.json()


# --- who may create -----------------------------------------------------------------------

def test_a_viewer_cannot_make_a_targeted_task_but_can_make_their_own(ws):
    viewer = client(ws, "viewer")
    assert viewer.post("/tasks", json={"title": "x", "item_id": ws["iid"]}).status_code == 403
    _make(viewer)                                              # no target, for themselves
    r = viewer.post("/tasks", json={"title": "x", "assignee_id": ws["uid"]["editor"]})
    assert r.status_code == 403                                # giving it away needs tracking:comment


def test_cutlist_tasks_need_comment_on_list(ws):
    po = client(ws, "purchase_officer")                        # list: read only
    assert po.post("/tasks", json={"title": "x", "cutlist_id": ws["cid"]}).status_code == 403
    assert po.post("/tasks", json={"title": "x", "item_id": ws["iid"]}).status_code == 201


def test_the_assignee_must_be_able_to_read_the_target(ws, monkeypatch):
    matrix = {**rbac_engine.MATRIX,
              "viewer": {**rbac_engine.MATRIX["viewer"], "tracking": set()}}
    monkeypatch.setattr(rbac_engine, "MATRIX", matrix)
    mgr = client(ws, "manager")
    r = mgr.post("/tasks", json={"title": "x", "item_id": ws["iid"],
                                 "assignee_id": ws["uid"]["viewer"]})
    assert r.status_code == 409 and r.json()["detail"] == {"code": "ASSIGNEE_CANNOT_READ_TARGET"}
    # no target: nothing to read, so it is allowed
    assert mgr.post("/tasks", json={"title": "x", "assignee_id": ws["uid"]["viewer"]}).status_code == 201


# --- read ---------------------------------------------------------------------------------

def test_a_task_with_no_target_is_private_to_creator_assignee_and_managers(ws):
    t = _make(client(ws, "editor"), assignee_id=ws["uid"]["drafter"])
    tid = t["task_id"]
    assert client(ws, "editor").get(f"/tasks/{tid}").status_code == 200       # creator
    assert client(ws, "drafter").get(f"/tasks/{tid}").status_code == 200      # assignee
    assert client(ws, "manager").get(f"/tasks/{tid}").status_code == 200
    assert client(ws, "admin").get(f"/tasks/{tid}").status_code == 200
    assert client(ws, "estimator").get(f"/tasks/{tid}").status_code == 404
    ids = [x["task_id"] for x in client(ws, "estimator").get("/tasks").json()["items"]]
    assert tid not in ids


def test_a_targeted_task_needs_read_on_the_targets_module(ws, monkeypatch):
    t = _make(client(ws, "manager"), cutlist_id=ws["cid"])
    assert client(ws, "viewer").get(f"/tasks/{t['task_id']}").status_code == 200
    matrix = {**rbac_engine.MATRIX, "viewer": {**rbac_engine.MATRIX["viewer"], "list": set()}}
    monkeypatch.setattr(rbac_engine, "MATRIX", matrix)
    assert client(ws, "viewer").get(f"/tasks/{t['task_id']}").status_code == 404


def test_list_filters_and_orders_open_first_then_by_due_date(ws):
    mgr = client(ws, "manager")
    _make(mgr, item_id=ws["iid"], title="late", due_date="2026-12-01", assignee_id=ws["uid"]["manager"])
    _make(mgr, item_id=ws["iid"], title="soon", due_date="2026-11-01")
    _make(mgr, project_id=ws["pid"], title="undated")
    done = _make(mgr, item_id=ws["iid"], title="done", due_date="2026-10-01")
    assert mgr.post(f"/tasks/{done['task_id']}/status", json={"status": "done"}).status_code == 200
    body = mgr.get("/tasks").json()
    assert [x["title"] for x in body["items"]] == ["soon", "late", "undated", "done"]
    assert body["total"] == 4
    assert [x["title"] for x in mgr.get("/tasks?assignee=me").json()["items"]] == ["late"]
    assert [x["title"] for x in mgr.get("/tasks?status=done").json()["items"]] == ["done"]
    assert {x["title"] for x in mgr.get(f"/tasks?project_id={ws['pid']}").json()["items"]} == \
        {"late", "soon", "undated", "done"}
    assert [x["title"] for x in mgr.get("/tasks?due_before=2026-11-15").json()["items"]] == ["soon", "done"]
    assert [x["title"] for x in mgr.get(f"/items/{ws['iid']}/tasks").json()["items"]] == \
        ["soon", "late", "done"]
    assert mgr.get("/tasks?assignee=nobody").status_code == 422
    for param in (f"item_id={ws['rp']}", "project_id=2000000000", "cutlist_id=2000000000"):
        assert mgr.get(f"/tasks?{param}").status_code == 404           # a filter on a missing record
    assert mgr.get("/items/2000000000/tasks").status_code == 404


def test_a_soft_deleted_item_hides_its_tasks_everywhere(ws):
    mgr = client(ws, "manager")
    t = _make(mgr, item_id=ws["iid"])
    sql("UPDATE items SET deleted = true WHERE item_id = :i", i=ws["iid"])
    assert mgr.get(f"/tasks/{t['task_id']}").status_code == 404
    assert mgr.get("/tasks").json() == {"items": [], "total": 0}
    assert mgr.patch(f"/tasks/{t['task_id']}", json={"title": "y"}).status_code == 404
    assert mgr.post(f"/tasks/{t['task_id']}/status", json={"status": "done"}).status_code == 404


def test_another_workspaces_task_is_a_404(ws):
    other = workspace()
    t = _make(client(other, "admin"), item_id=other["iid"])
    admin = client(ws, "admin")
    ghost = admin.get("/tasks/2000000000")
    for r in (admin.get(f"/tasks/{t['task_id']}"),
              admin.patch(f"/tasks/{t['task_id']}", json={"title": "y"}),
              admin.post(f"/tasks/{t['task_id']}/status", json={"status": "done"})):
        assert r.status_code == 404 and r.json() == ghost.json()
    assert admin.get("/tasks").json()["total"] == 0


# --- edit ---------------------------------------------------------------------------------

def test_patch_changes_fields_bumps_versions_and_clears_with_null(ws):
    mgr = client(ws, "manager")
    t = _make(mgr, item_id=ws["iid"], description="d", due_date="2026-11-01")
    r = mgr.patch(f"/tasks/{t['task_id']}", json={"title": "New", "description": None,
                                                  "due_date": None})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["title"] == "New" and b["description"] is None and b["due_date"] is None
    assert b["field_versions"] == {"title": 1, "description": 1, "due_date": 1}
    again = mgr.patch(f"/tasks/{t['task_id']}", json={"title": "New"}).json()   # unchanged: no bump
    assert again["field_versions"]["title"] == 1


def test_patch_null_title_is_422_and_an_empty_patch_is_a_no_op(ws):
    mgr = client(ws, "manager")
    t = _make(mgr)
    assert mgr.patch(f"/tasks/{t['task_id']}", json={"title": None}).status_code == 422
    assert mgr.patch(f"/tasks/{t['task_id']}", json={}).status_code == 200


def test_patch_with_a_stale_expected_version_is_a_field_conflict(ws):
    mgr = client(ws, "manager")
    t = _make(mgr)
    assert mgr.patch(f"/tasks/{t['task_id']}", json={"title": "one"}).status_code == 200
    r = mgr.patch(f"/tasks/{t['task_id']}", json={"title": "two", "expected_versions": {"title": 0}})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "FIELD_CONFLICT"
    assert r.json()["detail"]["conflicts"]["title"]["current_value"] == "one"
    ok = mgr.patch(f"/tasks/{t['task_id']}", json={"title": "two", "expected_versions": {"title": 1}})
    assert ok.status_code == 200 and ok.json()["title"] == "two"


def test_patch_moves_a_task_between_targets_and_off_one(ws):
    mgr = client(ws, "manager")
    t = _make(mgr, item_id=ws["iid"])
    r = mgr.patch(f"/tasks/{t['task_id']}", json={"cutlist_id": ws["cid"]})
    assert r.json()["target_type"] == "cutlist" and r.json()["item_id"] is None
    r = mgr.patch(f"/tasks/{t['task_id']}", json={"item_id": None})
    assert r.json()["target_type"] is None
    assert mgr.patch(f"/tasks/{t['task_id']}", json={"item_id": ws["rp"]}).status_code == 404


def test_only_creator_assignee_or_a_manager_may_edit(ws):
    t = _make(client(ws, "editor"), item_id=ws["iid"], assignee_id=ws["uid"]["drafter"])
    path = f"/tasks/{t['task_id']}"
    assert client(ws, "estimator").patch(path, json={"title": "y"}).status_code == 403
    assert client(ws, "drafter").patch(path, json={"title": "y"}).status_code == 200      # assignee
    assert client(ws, "editor").patch(path, json={"title": "z"}).status_code == 200       # creator
    assert client(ws, "manager").patch(path, json={"title": "m"}).status_code == 200


def test_reassigning_checks_the_new_assignee(ws):
    mgr = client(ws, "manager")
    t = _make(mgr, item_id=ws["iid"])
    r = mgr.patch(f"/tasks/{t['task_id']}", json={"assignee_id": ws["uid"]["editor"]})
    assert r.status_code == 200 and r.json()["assignee_name"] == "Editor"
    assert mgr.patch(f"/tasks/{t['task_id']}", json={"assignee_id": 2_000_000_000}).status_code == 404
    assert mgr.patch(f"/tasks/{t['task_id']}", json={"assignee_id": None}).json()["assignee_id"] is None


# --- status -------------------------------------------------------------------------------

def test_status_stamps_complete_and_cancel_and_reopening_clears_them(ws):
    mgr = client(ws, "manager")
    t = _make(mgr, assignee_id=ws["uid"]["drafter"])
    path = f"/tasks/{t['task_id']}/status"
    r = client(ws, "drafter").post(path, json={"status": "in_progress"})        # the assignee
    assert r.status_code == 200 and r.json()["status"] == "in_progress"
    done = mgr.post(path, json={"status": "done"}).json()
    assert done["completed_at"] and done["cancelled_at"] is None
    cancelled = mgr.post(path, json={"status": "cancelled"}).json()
    assert cancelled["cancelled_at"] and cancelled["completed_at"] is None
    reopened = client(ws, "drafter").post(path, json={"status": "open"}).json()
    assert reopened["status"] == "open" and reopened["cancelled_at"] is None
    assert reopened["field_versions"]["status"] == 4
    assert mgr.post(path, json={"status": "open"}).json()["field_versions"]["status"] == 4   # no-op
    assert sql("SELECT count(*) FROM audit_log WHERE event = 'task.status'") == 4


def test_a_stranger_cannot_change_status_and_a_bad_status_is_422(ws):
    t = _make(client(ws, "manager"), item_id=ws["iid"])
    path = f"/tasks/{t['task_id']}/status"
    assert client(ws, "estimator").post(path, json={"status": "done"}).status_code == 403
    assert client(ws, "manager").post(path, json={"status": "finished"}).status_code == 422


def test_editing_a_closed_task_is_refused_until_it_is_reopened(ws):
    mgr = client(ws, "manager")
    t = _make(mgr)
    mgr.post(f"/tasks/{t['task_id']}/status", json={"status": "done"})
    r = mgr.patch(f"/tasks/{t['task_id']}", json={"title": "late"})
    assert r.status_code == 409 and r.json()["detail"] == {"code": "TASK_CLOSED"}
    mgr.post(f"/tasks/{t['task_id']}/status", json={"status": "open"})
    assert mgr.patch(f"/tasks/{t['task_id']}", json={"title": "late"}).status_code == 200


def test_unauthenticated_requests_are_401(ws):
    from fastapi.testclient import TestClient

    from app.main import app
    anon = TestClient(app)
    assert anon.get("/tasks").status_code == 401
    assert anon.post("/tasks", json={"title": "x"}).status_code == 401


# --- the bell: GET /notifications carries the caller's open tasks --------------------------

def test_notifications_carry_my_open_tasks_soonest_due_first(ws):
    mgr = client(ws, "manager")
    mine = ws["uid"]["drafter"]
    _make(mgr, title="later", assignee_id=mine, due_date="2026-12-01", item_id=ws["iid"])
    soon = _make(mgr, title="soon", assignee_id=mine, due_date="2026-11-01")
    done = _make(mgr, title="done", assignee_id=mine)
    _make(mgr, title="not mine", assignee_id=ws["uid"]["editor"])
    mgr.post(f"/tasks/{done['task_id']}/status", json={"status": "done"})
    r = client(ws, "drafter").get("/notifications").json()
    assert r["tasks_open_count"] == 2
    assert [t["title"] for t in r["tasks_open"]] == ["soon", "later"]
    assert r["tasks_open"][1]["target_label"] and r["tasks_open"][0]["url"] == f"/tasks?task={soon['task_id']}"
    # not on a paged or unread-only call
    assert client(ws, "drafter").get("/notifications?unread_only=true").json()["tasks_open"] == []
    assert client(ws, "drafter").get("/notifications?offset=1").json()["tasks_open_count"] == 0
    # a finished task leaves the bell
    client(ws, "drafter").post(f"/tasks/{soon['task_id']}/status", json={"status": "in_progress"})
    assert client(ws, "drafter").get("/notifications").json()["tasks_open_count"] == 2
    client(ws, "drafter").post(f"/tasks/{soon['task_id']}/status", json={"status": "cancelled"})
    assert client(ws, "drafter").get("/notifications").json()["tasks_open_count"] == 1


def test_a_purchase_officer_and_a_manager_get_tasks_beside_their_waiting_lists(ws):
    mgr = client(ws, "manager")
    _make(mgr, title="for po", assignee_id=ws["uid"]["purchase_officer"])
    _make(mgr, title="for mgr", assignee_id=ws["uid"]["manager"])
    assert client(ws, "purchase_officer").get("/notifications").json()["tasks_open_count"] == 1
    body = mgr.get("/notifications").json()
    assert body["tasks_open_count"] == 1 and "lock_requests_waiting" in body
