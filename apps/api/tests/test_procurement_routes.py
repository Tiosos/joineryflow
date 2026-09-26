"""Workspace isolation for the legacy /procurement/* module.

This namespace (apps/api/app/procurement/) was ported from a single-tenant
MySQL app and had NO workspace scoping anywhere until this fix:
  - purchase_orders / po_line_items / po_attachments / approval_workflows
    resolve through the same project-or-vendor join
    apps/api/app/orders/queries.py already uses for the v1 order layer.
  - budget_transactions / v_budget_utilisation resolve through
    cost_centers.workspace_id (added by migration 0029).

No prior test file existed for this module.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import TRUNCATE_TABLES

# Nothing in TRUNCATE_TABLES cascades into cost_centers/budget_transactions
# (they're referenced BY purchase_orders, not the other way around).
_EXTRA_TABLES = ("budget_transactions", "cost_centers")


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        all_tables = ", ".join(list(_EXTRA_TABLES) + list(TRUNCATE_TABLES))
        s.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _login(role: str = "purchase_officer") -> dict:
    """Create a fresh workspace with a user, vendor and cost center."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"proc-{suffix}"
    email = f"u-{suffix}@example.com"
    s = SessionLocal()
    try:
        wid = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'Proc WS') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = s.execute(
            text(
                """INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                   VALUES (:w, :e, 'U', :p, :r) RETURNING id"""
            ),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
        ).scalar()
        vendor_id = s.execute(
            text("INSERT INTO vendors(name, category, workspace_id)"
                 " VALUES('Vendor', 'Office', :w) RETURNING vendor_id"),
            {"w": wid},
        ).scalar()
        cc_id = s.execute(
            text(
                """INSERT INTO cost_centers(workspace_id, code, name, fiscal_year, budget_amount)
                   VALUES (:w, 'GEN', 'General', 2026, 10000) RETURNING cost_center_id"""
            ),
            {"w": wid},
        ).scalar()
        s.commit()
    finally:
        s.close()
    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": email, "password": "pw"},
    )
    assert r.status_code == 200, r.text
    return {"client": c, "wid": wid, "uid": uid, "vendor_id": vendor_id, "cc_id": cc_id}


def _create_order(ctx: dict, **overrides) -> dict:
    body = {
        "vendor_id": ctx["vendor_id"],
        "requester_id": ctx["uid"],
        "cost_center_id": ctx["cc_id"],
        "description": "widgets",
        "category": "Office",
        **overrides,
    }
    r = ctx["client"].post("/procurement/orders", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_list_orders_excludes_other_workspaces():
    mine = _login()
    other = _login()
    mine_po = _create_order(mine)
    _create_order(other)

    rows = mine["client"].get("/procurement/orders").json()
    assert [r["po_id"] for r in rows] == [mine_po["po_id"]]


def test_get_order_cross_workspace_is_404():
    mine = _login()
    other = _login()
    other_po = _create_order(other)

    r = mine["client"].get(f"/procurement/orders/{other_po['po_id']}")
    assert r.status_code == 404, r.text

    r = other["client"].get(f"/procurement/orders/{other_po['po_id']}")
    assert r.status_code == 200, r.text


def test_create_order_rejects_foreign_vendor():
    mine = _login()
    other = _login()

    r = mine["client"].post(
        "/procurement/orders",
        json={
            "vendor_id": other["vendor_id"],
            "requester_id": mine["uid"],
            "cost_center_id": mine["cc_id"],
            "description": "widgets",
            "category": "Office",
        },
    )
    assert r.status_code == 422, r.text


def test_create_order_rejects_foreign_cost_center():
    mine = _login()
    other = _login()

    r = mine["client"].post(
        "/procurement/orders",
        json={
            "vendor_id": mine["vendor_id"],
            "requester_id": mine["uid"],
            "cost_center_id": other["cc_id"],
            "description": "widgets",
            "category": "Office",
        },
    )
    assert r.status_code == 422, r.text


def test_create_order_rejects_foreign_requester():
    mine = _login()
    other = _login()

    r = mine["client"].post(
        "/procurement/orders",
        json={
            "vendor_id": mine["vendor_id"],
            "requester_id": other["uid"],
            "cost_center_id": mine["cc_id"],
            "description": "widgets",
            "category": "Office",
        },
    )
    assert r.status_code == 422, r.text


def test_submit_for_approval_rejects_foreign_approver():
    mine = _login()
    other = _login()
    mine_po = _create_order(mine)

    r = mine["client"].patch(
        f"/procurement/orders/{mine_po['po_id']}/submit",
        params={"approver_id": other["uid"]},
    )
    assert r.status_code == 422, r.text


def test_update_and_cancel_cross_workspace_are_404():
    mine = _login()
    other = _login()
    other_po = _create_order(other)

    r = mine["client"].patch(
        f"/procurement/orders/{other_po['po_id']}", json={"description": "hijacked"}
    )
    assert r.status_code == 404, r.text

    r = mine["client"].delete(f"/procurement/orders/{other_po['po_id']}")
    assert r.status_code == 404, r.text


def test_filter_rto_excludes_other_workspace():
    mine = _login()
    other = _login()
    mine_po = _create_order(mine)
    other_po = _create_order(other)
    for c, po in ((mine["client"], mine_po), (other["client"], other_po)):
        r = c.patch(f"/procurement/orders/{po['po_id']}", json={"status": "Next"})
        assert r.status_code == 200, r.text

    rows = mine["client"].get("/procurement/orders/filter/rto").json()
    assert [r["po_id"] for r in rows] == [mine_po["po_id"]]


def test_attachments_list_cross_workspace_is_404():
    mine = _login()
    other = _login()
    other_po = _create_order(other)

    r = mine["client"].get(f"/procurement/orders/{other_po['po_id']}/attachments")
    assert r.status_code == 404, r.text


def test_pending_approvals_excludes_other_workspace():
    mine = _login()
    other = _login()
    mine_po = _create_order(mine)
    other_po = _create_order(other)
    mine["client"].patch(
        f"/procurement/orders/{mine_po['po_id']}/submit",
        params={"approver_id": mine["uid"]},
    )
    other["client"].patch(
        f"/procurement/orders/{other_po['po_id']}/submit",
        params={"approver_id": mine["uid"]},
    )

    rows = mine["client"].get(
        "/procurement/approvals/pending", params={"approver_id": mine["uid"]}
    ).json()
    assert [r["po_id"] for r in rows] == [mine_po["po_id"]]


def test_decide_approval_cross_workspace_is_404():
    mine = _login()
    other = _login()
    other_po = _create_order(other)
    other["client"].patch(
        f"/procurement/orders/{other_po['po_id']}/submit",
        params={"approver_id": other["uid"]},
    )
    workflow_id = other["client"].get(
        f"/procurement/orders/{other_po['po_id']}"
    ).json()["workflow"][0]["workflow_id"]

    r = mine["client"].post(
        f"/procurement/approvals/{workflow_id}/decide",
        json={"approver_id": mine["uid"], "decision": "approve"},
    )
    assert r.status_code == 404, r.text


def test_budget_list_excludes_other_workspace():
    mine = _login()
    other = _login()

    rows = mine["client"].get("/procurement/budget").json()
    assert [r["cost_center_id"] for r in rows] == [mine["cc_id"]]
    assert other["cc_id"] not in [r["cost_center_id"] for r in rows]


def test_budget_summary_excludes_other_workspace():
    mine = _login()
    _login()  # another workspace's cost center must not enter the sum

    summary = mine["client"].get("/procurement/budget/summary").json()
    assert float(summary["total_budget"]) == 10000.0


def test_cost_center_transactions_cross_workspace_is_empty():
    mine = _login()
    other = _login()
    other_po = _create_order(other)
    s = SessionLocal()
    try:
        s.execute(
            text(
                """INSERT INTO budget_transactions
                       (cost_center_id, po_id, amount, transaction_type, transaction_date)
                   VALUES (:cc, :po, 500, 'Commitment', CURRENT_DATE)"""
            ),
            {"cc": other["cc_id"], "po": other_po["po_id"]},
        )
        s.commit()
    finally:
        s.close()

    # The transaction is real — visible from its own workspace...
    own = other["client"].get(f"/procurement/budget/{other['cc_id']}/transactions").json()
    assert len(own) == 1

    # ...but invisible when a different workspace asks for that cost_center_id.
    r = mine["client"].get(f"/procurement/budget/{other['cc_id']}/transactions")
    assert r.status_code == 200, r.text
    assert r.json() == []
