"""The bell's "waiting for you" list (Q613): one typed `attention` list, merged for every list a
person qualifies for, derived on every call (no rows, no read state). Kinds, in display order:
`lock_request`, `variation`, `order`, `task`. The per-list rules have their own files
(test_lock_requests_waiting_notification, test_orders_waiting_notification, test_tasks,
test_variations_waiting_notification); this file is about the merge itself."""
import pytest

from .conftest import truncate_fixture
from .helpers_tasks import client, sql, workspace

_cleanup = truncate_fixture("budget_transactions", "cost_centers", "purchase_orders", "vendors",
                            "item_lock_request", "items")


@pytest.fixture
def ws():
    w = workspace()
    sql("INSERT INTO project_contract(project_id, original_value) VALUES (:p, 1000)", p=w["pid"])
    w["vendor"] = sql("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w)"
                      " RETURNING vendor_id", w=w["wid"])
    return w


def _bell(c, **params):
    r = c.get("/notifications", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _kinds(body):
    return [a["kind"] for a in body["attention"]]


def _lock_request(ws):
    """The manager's first save claims the item's lock; the drafter's save is held as a request."""
    assert client(ws, "manager").patch(f"/items/{ws['iid']}", json={"description": "Owner edit"}).status_code == 200
    r = client(ws, "drafter").patch(f"/items/{ws['iid']}", json={"description": "Proposal"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "LOCK_REQUEST_CREATED", r.text


def _variation(ws, desc="Extra shelf"):
    r = client(ws, "drafter").post(f"/projects/{ws['pid']}/contract/variations",
                                   json={"description": desc, "amount_delta": "10", "reason": "r"})
    assert r.status_code == 201, r.text


def _order(ws):
    r = client(ws, "drafter").post("/orders", json={"vendor_id": ws["vendor"], "description": "Board",
                                                    "total_amount": "10.00"})
    assert r.status_code == 201, r.text


def _task(ws, assignee_role):
    r = client(ws, "manager").post("/tasks", json={"title": f"for {assignee_role}",
                                                   "assignee_id": ws["uid"][assignee_role]})
    assert r.status_code == 201, r.text


def test_the_reply_carries_one_typed_list_and_none_of_the_old_per_list_fields(ws):
    _task(ws, "manager")
    body = _bell(client(ws, "manager"))
    assert set(body) == {"notifications", "unread_count", "attention", "attention_totals", "attention_count"}
    item = body["attention"][0]
    assert set(item) == {"kind", "key", "title", "detail", "url", "created_at"}
    assert item["kind"] == "task" and item["key"].startswith("task:") and item["url"].startswith("/tasks?task=")


def test_a_manager_gets_every_list_they_qualify_for_not_just_the_first(ws):
    _lock_request(ws)
    _variation(ws)
    _order(ws)                                  # not the manager's: the purchase officer's
    _task(ws, "manager")
    body = _bell(client(ws, "manager"))
    assert _kinds(body) == ["lock_request", "variation", "task"]       # decisions first, tasks last
    assert body["attention_totals"] == {"lock_request": 1, "variation": 1, "task": 1}
    assert body["attention_count"] == 3


def test_a_purchase_officer_gets_orders_and_tasks_together(ws):
    _order(ws)
    _task(ws, "purchase_officer")
    body = _bell(client(ws, "purchase_officer"))
    assert _kinds(body) == ["order", "task"]
    assert body["attention_totals"] == {"order": 1, "task": 1} and body["attention_count"] == 2


def test_a_role_with_nothing_to_decide_gets_an_empty_list(ws):
    _lock_request(ws)
    _variation(ws)
    _order(ws)
    for role in ("viewer", "editor", "estimator"):
        body = _bell(client(ws, role))
        # everyone has the tasks kind (a task is assigned to a person); these roles qualify for no other
        assert (body["attention"], body["attention_totals"], body["attention_count"]) == ([], {"task": 0}, 0), role


def test_each_kind_shows_at_most_twenty_and_counts_all_of_them(ws):
    for i in range(22):
        _variation(ws, f"v{i}")
    body = _bell(client(ws, "manager"))
    assert body["attention_totals"]["variation"] == 22 and body["attention_count"] == 22
    assert _kinds(body).count("variation") == 20


def test_paged_and_unread_only_calls_carry_no_attention_list(ws):
    _task(ws, "manager")
    assert _bell(client(ws, "manager"))["attention_count"] == 1
    for params in ({"unread_only": True}, {"offset": 1}):
        body = _bell(client(ws, "manager"), **params)
        assert (body["attention"], body["attention_totals"], body["attention_count"]) == ([], {}, 0), params


def test_another_workspaces_items_are_not_counted(ws):
    _variation(ws)
    other = workspace()
    assert _bell(client(other, "manager"))["attention_count"] == 0
