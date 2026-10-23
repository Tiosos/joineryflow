"""The bell's "waiting for you" list (Q613): one typed list of derived attention items.

Each kind is worked out on every call from the tables that hold the thing waiting, so nothing is
stored and nothing has a read state: an item leaves when the underlying thing is decided or done. A
person gets every kind they qualify for (the recipients are fixed in code here, no rule table:
Q472), each capped at `PER_KIND` newest with its true total beside it. Kinds come out in
`KINDS` order: decisions first, the person's own tasks last.

Only the first, unfiltered page carries the list (the bell and the notifications page ask for
that); a paged or unread-only call has no use for it.
"""
from urllib.parse import quote

from sqlalchemy.orm import Session

from ..auth.rbac_engine import has_permission_db
from ..auth.sessions import AuthUser
from ..items.queries import lock_requests_waiting_for_decision
from ..orders.queries import orders_waiting_for_decision
from ..project_contracts.queries import variations_waiting_for_approval
from ..tasks.queries import list_tasks

PER_KIND = 20
KINDS = ("lock_request", "variation", "order", "task")


def _item(kind: str, ident: int, *, title: str, url: str, detail: str | None = None, created_at=None) -> dict:
    return {"kind": kind, "key": f"{kind}:{ident}", "title": title, "detail": detail, "url": url,
            "created_at": created_at}


def _lock_requests(db: Session, user: AuthUser):
    # The people `decide_lock_request` lets decide, who can act on it (`tracking:write`) and open
    # the item the entry links to (`list:read`).
    if not (user.auth_role in ("drafter", "manager", "admin")
            and has_permission_db(db, user, "tracking", "write")
            and has_permission_db(db, user, "list", "read")):
        return None
    total, rows = lock_requests_waiting_for_decision(db, user=user, limit=PER_KIND)
    return total, [
        _item("lock_request", r["request_id"], url=f"/items/{r['item_id']}",
              title=" · ".join([f"#{r['item_number']}" if r["item_number"] is not None else f"Item {r['item_id']}",
                                r["project_code"] or "no project",
                                *([r["requested_by_name"]] if r["requested_by_name"] else [])]),
              detail=f"Changes {', '.join(r['fields'])}", created_at=r["created_at"])
        for r in rows
    ]


def _variations(db: Session, user: AuthUser):
    # The people `POST …/variations/{id}/decision` lets decide, with Tracking write to act on it.
    if not (user.auth_role in ("manager", "admin")
            and has_permission_db(db, user, "tracking", "write")
            and has_permission_db(db, user, "tracking", "read")):
        return None
    total, rows = variations_waiting_for_approval(db, workspace_id=user.workspace_id, limit=PER_KIND)
    return total, [
        _item("variation", r["variation_id"], url=f"/projects/{r['project_id']}",
              title=" · ".join([f"VAR-{r['number']:03d}", r["project_code"],
                                *([r["created_by_name"]] if r["created_by_name"] else [])]),
              detail=r["description"], created_at=r["created_at"])
        for r in rows
    ]


def _orders(db: Session, user: AuthUser):
    # The purchase officer's, by the customer's choice (not everyone with `orderbook:approve`).
    if not (user.auth_role == "purchase_officer" and has_permission_db(db, user, "orderbook", "read")):
        return None
    total, rows = orders_waiting_for_decision(db, workspace_id=user.workspace_id, limit=PER_KIND)
    return total, [
        _item("order", r["po_id"], url=f"/orderbook?order={quote(r['po_number'])}",
              title=" · ".join([r["po_number"], r["vendor_name"] or "no supplier",
                                *([r["requester_name"]] if r["requester_name"] else [])]),
              detail=r["description"], created_at=r["created_at"])
        for r in rows
    ]


def _tasks(db: Session, user: AuthUser):
    # Every role: a task is assigned to a person. Visibility is the tasks module's own, so a task on
    # a target they can no longer read is left out.
    mine = list_tasks(
        db, actor=user, assignee_id=user.id, status="active", project_id=None,
        item_id=None, cutlist_id=None, due_before=None, limit=PER_KIND, offset=0,
    )
    return mine["total"], [
        _item("task", t["task_id"], title=t["title"], url=f"/tasks?task={t['task_id']}",
              detail=" · ".join(x for x in (f"Due {t['due_date']}" if t["due_date"] else None,
                                            t["target_label"]) if x) or "No due date")
        for t in mine["items"]
    ]


_KIND_FUNCTIONS = {"lock_request": _lock_requests, "variation": _variations, "order": _orders, "task": _tasks}


def attention_for(db: Session, user: AuthUser) -> dict:
    items: list[dict] = []
    totals: dict[str, int] = {}
    for kind in KINDS:
        got = _KIND_FUNCTIONS[kind](db, user)
        if got is None:
            continue
        totals[kind], rows = got
        items += rows
    return {"attention": items, "attention_totals": totals, "attention_count": sum(totals.values())}
