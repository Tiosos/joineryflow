"""PO approval (migration 0054).

An order needs approval when its total is above the workspace's limit (default 2000, set by a
purchase officer) or the project manager flagged it (`requires_approval`). One approval is
enough. `orders.queries` computes `needs_approval` in SQL; this module owns the transitions:

    Draft | Rejected --request--> Pending --approve--> Approved
                                          \\--reject---> Rejected

For an order that needs approval, `Pending` / `Approved` / `Rejected` are reached only through
these functions (a plain status PATCH is refused, see `queries.patch_order`). Approving posts a
`Commitment` against the order's cost centre when it has one, and does nothing when it has none.

Who may approve is the `orderbook:approve` grant (purchase officer, manager, admin); the route
checks it. The approver may not be the person who requested approval.
"""
from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..concurrency import bump_field_versions
from .queries import get_approval_threshold, get_order


def set_approval_threshold(
    db: Session, *, workspace_id: int, amount: Decimal, actor_id: int
) -> Decimal:
    before = get_approval_threshold(db, workspace_id=workspace_id)
    db.execute(
        text(
            """
            INSERT INTO workspace_order_setting (workspace_id, approval_threshold, updated_by)
            VALUES (:w, :a, :u)
            ON CONFLICT (workspace_id) DO UPDATE
               SET approval_threshold = EXCLUDED.approval_threshold,
                   updated_by = EXCLUDED.updated_by, updated_at = now()
            """
        ),
        {"w": workspace_id, "a": amount, "u": actor_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="order.approval_limit.set", target=str(workspace_id),
        payload={"from": str(before), "to": str(amount)},
    )
    return amount


def _set_status(
    db: Session, *, order: dict, status: str, extra_sql: str, params: dict
) -> None:
    versions = bump_field_versions(order.get("field_versions"), ["status"])
    db.execute(
        text(
            f"UPDATE purchase_orders SET status = :st, {extra_sql},"
            " field_versions = CAST(:fv AS jsonb), updated_at = now() WHERE po_id = :o"
        ),
        {"st": status, "fv": json.dumps(versions), "o": order["po_id"], **params},
    )


def request_approval(
    db: Session, *, po_id: int, workspace_id: int, actor_id: int
) -> tuple[str, dict | None]:
    """Codes: 'OK' | 'NOT_FOUND' | 'NOT_REQUIRED' (this order does not need approval) |
    'NOT_REQUESTABLE' (`data` is {status}: only a Draft or a Rejected order can be requested)."""
    order = get_order(db, po_id=po_id, workspace_id=workspace_id, for_update=True)
    if order is None:
        return "NOT_FOUND", None
    if not order["needs_approval"]:
        return "NOT_REQUIRED", None
    if order["status"] not in ("Draft", "Rejected"):
        return "NOT_REQUESTABLE", {"status": order["status"]}
    _set_status(
        db, order=order, status="Pending",
        extra_sql=(
            "approval_requested_by = :u, approval_requested_at = now(),"
            " approval_decided_by = NULL, approval_decided_at = NULL, approval_note = NULL"
        ),
        params={"u": actor_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="order.approval.request", target=str(po_id),
        payload={"po_number": order["po_number"], "total_amount": str(order["total_amount"])},
    )
    return "OK", get_order(db, po_id=po_id, workspace_id=workspace_id)


def decide(
    db: Session, *, po_id: int, workspace_id: int, actor_id: int, approve: bool, note: str | None
) -> tuple[str, dict | None]:
    """Codes: 'OK' | 'NOT_FOUND' | 'NOT_PENDING' (`data` is {status}) | 'SELF_APPROVAL'
    (the approver requested it) | 'NOTE_REQUIRED' (rejecting without a note)."""
    note = (note or "").strip() or None
    order = get_order(db, po_id=po_id, workspace_id=workspace_id, for_update=True)
    if order is None:
        return "NOT_FOUND", None
    if order["status"] != "Pending":
        return "NOT_PENDING", {"status": order["status"]}
    if order["approval_requested_by"] == actor_id:
        return "SELF_APPROVAL", None
    if not approve and note is None:
        return "NOTE_REQUIRED", None
    _set_status(
        db, order=order, status="Approved" if approve else "Rejected",
        extra_sql="approval_decided_by = :u, approval_decided_at = now(), approval_note = :n",
        params={"u": actor_id, "n": note},
    )
    committed = _commit_budget(db, order=order, workspace_id=workspace_id, actor_id=actor_id) if approve else False
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="order.approval.approve" if approve else "order.approval.reject",
        target=str(po_id),
        payload={"po_number": order["po_number"], "note": note, "commitment_posted": committed},
    )
    return "OK", get_order(db, po_id=po_id, workspace_id=workspace_id)


def _commit_budget(db: Session, *, order: dict, workspace_id: int, actor_id: int) -> bool:
    """Post the order's total as a `Commitment` against its cost centre. No cost centre (or one
    from another workspace, or a total that is not positive): nothing is posted."""
    amount = order["total_amount"]
    cc = db.execute(
        text("SELECT cost_center_id FROM purchase_orders WHERE po_id = :o"),
        {"o": order["po_id"]},
    ).scalar()
    if cc is None or amount is None or amount <= 0:
        return False
    in_workspace = db.execute(
        text("SELECT 1 FROM cost_centers WHERE cost_center_id = :c AND workspace_id = :w"),
        {"c": cc, "w": workspace_id},
    ).first()
    if in_workspace is None:
        return False
    db.execute(
        text(
            """
            INSERT INTO budget_transactions
                (cost_center_id, po_id, amount, transaction_type, description,
                 transaction_date, created_by)
            VALUES (:c, :o, :a, 'Commitment', 'PO approved', CURRENT_DATE, :u)
            """
        ),
        {"c": cc, "o": order["po_id"], "a": amount, "u": actor_id},
    )
    return True
