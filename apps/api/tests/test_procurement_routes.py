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
import re
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.procurement import routes as proc_routes

from .helpers import login
from .conftest import truncate_fixture

# Nothing in TRUNCATE_TABLES cascades into cost_centers/budget_transactions
# (they're referenced BY purchase_orders, not the other way around).
_EXTRA_TABLES = ("budget_transactions", "cost_centers")


_cleanup = truncate_fixture(*_EXTRA_TABLES)


def _login(role: str = "purchase_officer") -> dict:
    """A logged-in user in a fresh workspace with a vendor and cost center."""
    c, wid, uid = login(role, prefix="proc")
    s = SessionLocal()
    try:
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
    # Staged directly: PATCH no longer moves the status of a live order (see the audit tests).
    for po in (mine_po, other_po):
        _set_status(po["po_id"], "Next")

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


def test_decide_refuses_an_approver_from_another_workspace_and_writes_nothing():
    """`approver_id` is written into the order's changelog (and later joined to a name), so
    a user of another workspace, or a nonexistent one, is refused like the same id on
    submit: 422, with the order, the workflow and the changelog untouched."""
    mine = _login()
    other = _login()
    po_id, wf = _submitted_order(mine)
    before = (_po_and_workflow_state(po_id, wf), _order_row(po_id)["changelog"])

    for approver in (other["uid"], 2_000_000_000):
        r = mine["client"].post(
            f"/procurement/approvals/{wf}/decide",
            json={"approver_id": approver, "decision": "approve"},
        )
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == "approver not found in this workspace"
        assert (_po_and_workflow_state(po_id, wf), _order_row(po_id)["changelog"]) == before


def _submitted_order(ctx: dict, *, cost_centre: bool = True) -> tuple[int, int]:
    po = _create_order(ctx)
    if not cost_centre:
        # Orders can have none since 0031 (Q563); POST /procurement/orders still requires one.
        s = SessionLocal()
        try:
            s.execute(text("UPDATE purchase_orders SET cost_center_id = NULL WHERE po_id = :p"), {"p": po["po_id"]})
            s.commit()
        finally:
            s.close()
    r = ctx["client"].patch(f"/procurement/orders/{po['po_id']}/submit", params={"approver_id": ctx["uid"]})
    assert r.status_code == 200, r.text
    s = SessionLocal()
    try:
        wf = s.execute(text("SELECT workflow_id FROM approval_workflows WHERE po_id = :p"), {"p": po["po_id"]}).scalar()
    finally:
        s.close()
    return po["po_id"], wf


def _po_and_workflow_state(po_id: int, workflow_id: int) -> tuple:
    s = SessionLocal()
    try:
        return (
            s.execute(text("SELECT status FROM purchase_orders WHERE po_id = :p"), {"p": po_id}).scalar(),
            s.execute(text("SELECT status FROM approval_workflows WHERE workflow_id = :w"), {"w": workflow_id}).scalar(),
            s.execute(text("SELECT count(*) FROM budget_transactions WHERE po_id = :p"), {"p": po_id}).scalar(),
        )
    finally:
        s.close()


def _decide(ctx: dict, wf: int, decision: str):
    return ctx["client"].post(
        f"/procurement/approvals/{wf}/decide",
        json={"approver_id": ctx["uid"], "decision": decision},
    )


def _order_row(po_id: int) -> dict:
    s = SessionLocal()
    try:
        row = s.execute(
            text("SELECT status, changelog, grand_total FROM purchase_orders WHERE po_id = :p"), {"p": po_id}
        ).mappings().one()
        return dict(row)
    finally:
        s.close()


def _budget_rows(po_id: int) -> list[tuple]:
    s = SessionLocal()
    try:
        return [
            tuple(r)
            for r in s.execute(
                text("SELECT transaction_type, amount FROM budget_transactions WHERE po_id = :p ORDER BY 1"),
                {"p": po_id},
            )
        ]
    finally:
        s.close()


def _approved_order(ctx: dict, *, cost_centre: bool = True) -> int:
    po_id, wf = _submitted_order(ctx, cost_centre=cost_centre)
    assert _decide(ctx, wf, "approve").status_code == 200
    return po_id


def test_approving_an_order_with_no_cost_centre_succeeds_without_a_commitment():
    # 0031 made cost_center_id nullable (Q563) and no route can assign one afterwards, so an
    # order with none belongs to no cost-centre budget: approval goes through, nothing is
    # committed. (This used to be a 500, then — briefly — a 409; see CLAUDE.md.)
    ctx = _login()
    po_id, wf = _submitted_order(ctx, cost_centre=False)

    r = _decide(ctx, wf, "approve")

    assert r.status_code == 200, r.text
    assert _po_and_workflow_state(po_id, wf) == ("Approved", "Approved", 0)
    assert "no cost centre — no commitment posted" in _order_row(po_id)["changelog"]


def test_rejecting_an_order_with_no_cost_centre_still_works():
    ctx = _login()
    po_id, wf = _submitted_order(ctx, cost_centre=False)

    r = ctx["client"].post(
        f"/procurement/approvals/{wf}/decide",
        json={"approver_id": ctx["uid"], "decision": "reject"},
    )

    assert r.status_code == 200, r.text
    assert _po_and_workflow_state(po_id, wf)[:2] == ("Rejected", "Rejected")


def test_approving_an_order_with_a_cost_centre_commits_budget():
    ctx = _login()
    po_id, wf = _submitted_order(ctx)

    r = ctx["client"].post(
        f"/procurement/approvals/{wf}/decide",
        json={"approver_id": ctx["uid"], "decision": "approve"},
    )

    assert r.status_code == 200, r.text
    status, wf_status, budget_rows = _po_and_workflow_state(po_id, wf)
    assert (status, wf_status, budget_rows) == ("Approved", "Approved", 1)


def test_delivering_an_approved_order_posts_the_expenditure():
    ctx = _login()
    po_id = _approved_order(ctx)

    r = ctx["client"].patch(f"/procurement/orders/{po_id}/deliver")

    assert r.status_code == 200, r.text
    row = _order_row(po_id)
    assert row["status"] == "Delivered"
    assert _budget_rows(po_id) == [("Commitment", row["grand_total"]), ("Expenditure", row["grand_total"])]


def test_delivering_an_order_with_no_cost_centre_delivers_without_an_expenditure():
    ctx = _login()
    po_id = _approved_order(ctx, cost_centre=False)

    r = ctx["client"].patch(f"/procurement/orders/{po_id}/deliver")

    assert r.status_code == 200, r.text
    row = _order_row(po_id)
    assert row["status"] == "Delivered"
    assert _budget_rows(po_id) == []
    assert "no cost centre — no expenditure posted" in row["changelog"]


def test_delivering_a_draft_order_is_refused_and_writes_nothing():
    # The UPDATE was guarded by status = 'Approved' but the expenditure and the changelog
    # were not, so a Draft order answered 200 "Delivered", stayed Draft and got an Expenditure.
    ctx = _login()
    po = _create_order(ctx)
    before = _order_row(po["po_id"])

    r = ctx["client"].patch(f"/procurement/orders/{po['po_id']}/deliver")

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "BAD_STATUS"
    assert _order_row(po["po_id"]) == before
    assert _budget_rows(po["po_id"]) == []


def test_delivering_twice_posts_one_expenditure():
    ctx = _login()
    po_id = _approved_order(ctx)
    assert ctx["client"].patch(f"/procurement/orders/{po_id}/deliver").status_code == 200

    again = ctx["client"].patch(f"/procurement/orders/{po_id}/deliver")

    assert again.status_code == 409, again.text
    assert [t for t, _ in _budget_rows(po_id)].count("Expenditure") == 1


def test_delivering_another_workspaces_order_is_404():
    mine = _login()
    other = _login()
    other_po = _approved_order(other)

    assert mine["client"].patch(f"/procurement/orders/{other_po}/deliver").status_code == 404
    assert _order_row(other_po)["status"] == "Approved"


def test_order_with_no_cost_centre_is_visible_to_the_legacy_reads():
    # v_po_summary used to INNER JOIN cost_centers (0006/0009), so such an order was a 404 here
    # and absent from every listing although the row existed. 0045 makes it a LEFT JOIN.
    ctx = _login()
    po_id, _wf = _submitted_order(ctx, cost_centre=False)

    r = ctx["client"].get(f"/procurement/orders/{po_id}")
    assert r.status_code == 200, r.text
    order = r.json()["order"]
    assert order["po_id"] == po_id
    assert order["cost_center_id"] is None
    assert order["cost_center"] is None
    assert r.json()["workflow"][0]["status"] == "Pending"

    listed = ctx["client"].get("/procurement/orders").json()
    assert po_id in [o["po_id"] for o in listed]

    pending = ctx["client"].get("/procurement/approvals/pending", params={"approver_id": ctx["uid"]})
    assert pending.status_code == 200, pending.text
    assert po_id in [p["po_id"] for p in pending.json()]


def test_order_with_a_cost_centre_still_names_it_in_the_legacy_reads():
    ctx = _login()
    po_id, _wf = _submitted_order(ctx)

    order = ctx["client"].get(f"/procurement/orders/{po_id}").json()["order"]
    assert order["cost_center_id"] == ctx["cc_id"]
    assert order["cost_center"] == "General"
    assert order["cost_center_code"] == "GEN"


def test_other_workspaces_order_with_no_cost_centre_stays_hidden():
    # The LEFT JOIN widens what the view returns, never whose it is: workspace scoping
    # still resolves through the project-or-vendor join.
    mine = _login()
    other = _login()
    other_po, _ = _submitted_order(other, cost_centre=False)

    assert mine["client"].get(f"/procurement/orders/{other_po}").status_code == 404
    assert other_po not in [o["po_id"] for o in mine["client"].get("/procurement/orders").json()]


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


# ═══════════════════════════════════════════════════════════════════════════════
# Audit of the legacy namespace: PO numbers, totals, the budget ledger, status
# rules and attachments. Each test names the measured bug it pins.
# ═══════════════════════════════════════════════════════════════════════════════
def _sql(query: str, **params) -> list[dict]:
    s = SessionLocal()
    try:
        result = s.execute(text(query), params)
        rows = [dict(r) for r in result.mappings()] if result.returns_rows else []
        s.commit()
        return rows
    finally:
        s.close()


def _set_status(po_id: int, status: str) -> None:
    _sql("UPDATE purchase_orders SET status = :s WHERE po_id = :p", s=status, p=po_id)


def _lines(*pairs: tuple) -> list[dict]:
    return [
        {"line_number": i + 1, "item_description": f"item {i + 1}", "quantity": q, "unit_price": p}
        for i, (q, p) in enumerate(pairs)
    ]


def _totals(po_id: int) -> dict:
    return _sql("SELECT total_amount, grand_total FROM purchase_orders WHERE po_id = :p", p=po_id)[0]


def _committed(cc_id: int) -> Decimal:
    return _sql(
        "SELECT total_committed FROM v_budget_utilisation WHERE cost_center_id = :c", c=cc_id
    )[0]["total_committed"]


def _v1_order(ctx: dict):
    return ctx["client"].post(
        "/orders",
        json={"vendor_id": ctx["vendor_id"], "description": "v1 order", "category": "Office"},
    )


# ── PO numbers ────────────────────────────────────────────────────────────────
def test_legacy_po_numbers_come_from_the_sequence_and_never_collide_with_v1():
    # Legacy create / duplicate used MAX(seq)+1; the v1 module uses po_number_seq; both write
    # purchase_orders. After a legacy create handed out the number the sequence was about to
    # give, the next v1 POST /orders failed with a unique violation.
    ctx = _login()
    _sql("SELECT setval('po_number_seq', 40, true)")

    numbers = [_v1_order(ctx).json()["po_number"]]
    legacy = _create_order(ctx)
    numbers.append(legacy["po_number"])
    numbers.append(_v1_order(ctx).json()["po_number"])  # the sequence's next value
    dup = ctx["client"].post(f"/procurement/orders/{legacy['po_id']}/duplicate")
    assert dup.status_code == 201, dup.text
    numbers.append(dup.json()["po_number"])
    r = _v1_order(ctx)
    assert r.status_code == 201, r.text
    numbers.append(r.json()["po_number"])

    assert len(set(numbers)) == len(numbers), numbers
    assert all(re.fullmatch(r"PO-\d{4}-\d{4}", n) for n in numbers), numbers


# ── Totals ────────────────────────────────────────────────────────────────────
def test_legacy_create_sums_the_lines_into_the_total_and_commits_it():
    # 0002 did not port the MySQL triggers that summed the lines into total_amount and left it
    # to the application; this route never did, so every approval committed $0.
    ctx = _login()
    po = _create_order(ctx, line_items=_lines((2, 50), (1, 25.5)))

    assert _totals(po["po_id"])["total_amount"] == Decimal("125.50")
    assert _totals(po["po_id"])["grand_total"] == Decimal("138.05")  # + 10% GST
    ctx["client"].patch(f"/procurement/orders/{po['po_id']}/submit", params={"approver_id": ctx["uid"]})
    wf_id = _sql("SELECT workflow_id FROM approval_workflows WHERE po_id = :p", p=po["po_id"])[0]["workflow_id"]
    assert _decide(ctx, wf_id, "approve").status_code == 200
    assert _budget_rows(po["po_id"]) == [("Commitment", Decimal("138.05"))]


def test_an_order_without_lines_keeps_a_zero_total():
    ctx = _login()
    po = _create_order(ctx)
    assert _totals(po["po_id"])["total_amount"] == Decimal("0.00")


def test_duplicate_recomputes_the_total_from_the_copied_lines():
    ctx = _login()
    po = _create_order(ctx, line_items=_lines((2, 50)))
    _sql("UPDATE purchase_orders SET total_amount = 0 WHERE po_id = :p", p=po["po_id"])  # a stale source

    dup = ctx["client"].post(f"/procurement/orders/{po['po_id']}/duplicate").json()

    assert _totals(dup["po_id"])["total_amount"] == Decimal("100.00")
    assert _sql("SELECT count(*) n FROM po_line_items WHERE po_id = :p", p=dup["po_id"])[0]["n"] == 1


# ── The budget ledger ─────────────────────────────────────────────────────────
def test_delivering_releases_the_commitment_so_the_order_counts_once():
    # v_budget_utilisation sums Commitment and Expenditure; delivery posted an Expenditure
    # and never released the Commitment, so a $110 order read as $220.
    ctx = _login()
    po = _create_order(ctx, line_items=_lines((2, 50)))
    ctx["client"].patch(f"/procurement/orders/{po['po_id']}/submit", params={"approver_id": ctx["uid"]})
    wf = _sql("SELECT workflow_id FROM approval_workflows WHERE po_id = :p", p=po["po_id"])[0]["workflow_id"]
    assert _decide(ctx, wf, "approve").status_code == 200
    assert _committed(ctx["cc_id"]) == Decimal("110.00")

    assert ctx["client"].patch(f"/procurement/orders/{po['po_id']}/deliver").status_code == 200

    assert _budget_rows(po["po_id"]) == [
        ("Commitment", Decimal("110.00")),
        ("Expenditure", Decimal("110.00")),
        ("Release", Decimal("-110.00")),
    ]
    assert _committed(ctx["cc_id"]) == Decimal("110.00")


def test_delivering_an_order_with_no_outstanding_commitment_posts_no_release():
    ctx = _login()
    po_id = _approved_order(ctx)  # no lines: committed at $0

    assert ctx["client"].patch(f"/procurement/orders/{po_id}/deliver").status_code == 200

    assert "Release" not in [t for t, _ in _budget_rows(po_id)]


def test_a_release_is_limited_to_what_is_still_outstanding():
    ctx = _login()
    po = _create_order(ctx, line_items=_lines((2, 50)))
    ctx["client"].patch(f"/procurement/orders/{po['po_id']}/submit", params={"approver_id": ctx["uid"]})
    wf = _sql("SELECT workflow_id FROM approval_workflows WHERE po_id = :p", p=po["po_id"])[0]["workflow_id"]
    _decide(ctx, wf, "approve")
    _sql(
        "INSERT INTO budget_transactions (cost_center_id, po_id, amount, transaction_type, transaction_date)"
        " VALUES (:c, :p, -30, 'Release', CURRENT_DATE)",
        c=ctx["cc_id"], p=po["po_id"],
    )

    ctx["client"].patch(f"/procurement/orders/{po['po_id']}/deliver")

    assert sum(a for _t, a in _budget_rows(po["po_id"]) if _t in ("Commitment", "Release")) == Decimal("0.00")
    assert ("Release", Decimal("-80.00")) in _budget_rows(po["po_id"])


# ── PATCH rules ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("target", ["Approved", "Delivered", "Cancelled"])
def test_patch_cannot_move_a_live_order_to_another_status(target):
    # PATCH status used to jump Draft -> Approved (no workflow, no commitment) or Delivered (no
    # expenditure); status moves through submit / decide / deliver / delete, which post the budget.
    ctx = _login()
    po = _create_order(ctx)
    before = _order_row(po["po_id"])

    r = ctx["client"].patch(f"/procurement/orders/{po['po_id']}", json={"status": target})

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "STATUS_NOT_PATCHABLE"
    assert _order_row(po["po_id"]) == before
    assert _budget_rows(po["po_id"]) == []


def test_patch_cannot_cancel_an_approved_order_and_strand_its_commitment():
    ctx = _login()
    po = _create_order(ctx, line_items=_lines((2, 50)))
    ctx["client"].patch(f"/procurement/orders/{po['po_id']}/submit", params={"approver_id": ctx["uid"]})
    wf = _sql("SELECT workflow_id FROM approval_workflows WHERE po_id = :p", p=po["po_id"])[0]["workflow_id"]
    _decide(ctx, wf, "approve")

    r = ctx["client"].patch(f"/procurement/orders/{po['po_id']}", json={"status": "Cancelled"})

    assert r.status_code == 409, r.text
    assert _order_row(po["po_id"])["status"] == "Approved"
    assert _budget_rows(po["po_id"]) == [("Commitment", Decimal("110.00"))]


def test_patch_still_edits_ordinary_fields_of_a_live_order():
    ctx = _login()
    po = _create_order(ctx)

    r = ctx["client"].patch(
        f"/procurement/orders/{po['po_id']}", json={"notes": "call before delivery", "description": "renamed"}
    )

    assert r.status_code == 200, r.text
    row = _sql("SELECT notes, description FROM purchase_orders WHERE po_id = :p", p=po["po_id"])[0]
    assert row == {"notes": "call before delivery", "description": "renamed"}
    changelog = _order_row(po["po_id"])["changelog"]
    assert "Updated fields:" in changelog and "notes" in changelog and "description" in changelog


@pytest.mark.parametrize("frozen", ["Cancelled", "Delivered"])
def test_a_frozen_order_is_read_only_except_for_status(frozen):
    ctx = _login()
    po = _create_order(ctx)
    _set_status(po["po_id"], frozen)
    before = _order_row(po["po_id"])

    r = ctx["client"].patch(f"/procurement/orders/{po['po_id']}", json={"notes": "late edit"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == {"code": "ORDER_LOCKED", "status": frozen, "blocked_fields": ["notes"]}

    # a mixed PATCH is refused whole, the way the v1 module does it
    mixed = ctx["client"].patch(
        f"/procurement/orders/{po['po_id']}", json={"status": "Draft", "notes": "late edit"}
    )
    assert mixed.status_code == 409, mixed.text
    assert _order_row(po["po_id"]) == before


def test_status_is_the_way_back_in_for_a_frozen_order():
    ctx = _login()
    po = _create_order(ctx)
    _set_status(po["po_id"], "Delivered")

    r = ctx["client"].patch(f"/procurement/orders/{po['po_id']}", json={"status": "Approved"})

    assert r.status_code == 200, r.text
    row = _order_row(po["po_id"])
    assert row["status"] == "Approved"
    assert "status Delivered → Approved" in row["changelog"]
    assert ctx["client"].patch(f"/procurement/orders/{po['po_id']}", json={"notes": "ok now"}).status_code == 200


def test_patch_cannot_overwrite_the_changelog():
    ctx = _login()
    po = _create_order(ctx)
    before = _order_row(po["po_id"])

    r = ctx["client"].patch(
        f"/procurement/orders/{po['po_id']}", json={"changelog": "tampered", "notes": "x"}
    )

    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["loc"][-1] == "changelog"
    assert _order_row(po["po_id"]) == before


# ── DELETE (cancel) ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("status", ["Approved", "Pending", "Delivered"])
def test_cancelling_an_order_that_cannot_be_cancelled_is_a_409_and_changes_nothing(status):
    # It answered 200 {"status": "Cancelled"} and logged "Cancelled" for any status, with the
    # order untouched.
    ctx = _login()
    po = _create_order(ctx)
    _set_status(po["po_id"], status)
    before = _order_row(po["po_id"])

    r = ctx["client"].delete(f"/procurement/orders/{po['po_id']}")

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "BAD_STATUS"
    assert _order_row(po["po_id"]) == before


@pytest.mark.parametrize("status", ["Draft", "Rejected", "Hold"])
def test_cancelling_a_draft_rejected_or_held_order_still_works_once(status):
    ctx = _login()
    po = _create_order(ctx)
    _set_status(po["po_id"], status)

    r = ctx["client"].delete(f"/procurement/orders/{po['po_id']}")

    assert r.status_code == 200, r.text
    assert _order_row(po["po_id"])["status"] == "Cancelled"
    assert ctx["client"].delete(f"/procurement/orders/{po['po_id']}").status_code == 409


# ── Decisions ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_only_a_pending_order_can_be_decided(decision):
    # Approving a Cancelled order made it Approved again (and committed budget for it).
    ctx = _login()
    po_id, wf = _submitted_order(ctx)
    _set_status(po_id, "Cancelled")

    r = _decide(ctx, wf, decision)

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "BAD_STATUS"
    assert _po_and_workflow_state(po_id, wf) == ("Cancelled", "Pending", 0)


def test_the_pending_queue_omits_workflows_whose_order_is_no_longer_pending():
    ctx = _login()
    live, _ = _submitted_order(ctx)
    gone, _ = _submitted_order(ctx)
    _set_status(gone, "Cancelled")

    ids = [p["po_id"] for p in ctx["client"].get(
        "/procurement/approvals/pending", params={"approver_id": ctx["uid"]}).json()]

    assert live in ids and gone not in ids


# ── Attachments ───────────────────────────────────────────────────────────────
# Uploads go through the shared file store (`FILE_STORE_ROOT`), like every other upload, and
# the file must pass the same sniff as POST /files — so test content is a real PDF header.
def _pdf(tag: bytes = b"") -> bytes:
    return b"%PDF-1.4\n" + tag


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    return tmp_path


def _files_on_disk(root) -> list:
    return [p for p in root.rglob("*") if p.is_file()]


def _upload(ctx: dict, po_id: int, name: str = "quote.pdf", content: bytes | None = None, **form):
    return ctx["client"].post(
        f"/procurement/orders/{po_id}/attachments",
        files={"file": (name, _pdf() if content is None else content)},
        data={k: str(v) for k, v in form.items()},
    )


def _attachment_rows(po_id: int) -> list[dict]:
    return _sql(
        "SELECT attachment_id, file_name, file_path, file_blob_id"
        " FROM po_attachments WHERE po_id = :p ORDER BY 1",
        p=po_id,
    )


def _download(ctx: dict, po_id: int, attachment_id: int):
    return ctx["client"].get(f"/procurement/orders/{po_id}/attachments/{attachment_id}/download")


@pytest.mark.parametrize("uploader", ["foreign", "missing"])
def test_upload_refuses_an_uploader_who_is_not_in_this_workspace(upload_dir, uploader):
    # uploaded_by is joined to app_user.full_name, so another workspace's user id leaked that
    # name; an id that did not exist was a raw 500 after the file had been written.
    mine = _login()
    other = _login()
    po = _create_order(mine)
    uid = other["uid"] if uploader == "foreign" else 999_999_999

    r = _upload(mine, po["po_id"], uploaded_by=uid)

    assert r.status_code == 422, r.text
    assert _attachment_rows(po["po_id"]) == []
    assert _files_on_disk(upload_dir) == []


def test_an_older_row_naming_a_foreign_uploader_shows_no_name():
    mine = _login()
    other = _login()
    po = _create_order(mine)
    _sql(
        "INSERT INTO po_attachments (po_id, attachment_type, file_name, file_path, uploaded_by)"
        " VALUES (:p, 'File', 'old.pdf', '/nowhere', :u)",
        p=po["po_id"], u=other["uid"],
    )

    listed = mine["client"].get(f"/procurement/orders/{po['po_id']}/attachments").json()
    detail = mine["client"].get(f"/procurement/orders/{po['po_id']}").json()["attachments"]

    assert [a["uploaded_by_name"] for a in listed] == [None]
    assert [a["uploaded_by_name"] for a in detail] == [None]


def test_an_uploader_in_this_workspace_is_named(upload_dir):
    ctx = _login()
    po = _create_order(ctx)
    assert _upload(ctx, po["po_id"], uploaded_by=ctx["uid"]).status_code == 201
    listed = ctx["client"].get(f"/procurement/orders/{po['po_id']}/attachments").json()
    assert [a["uploaded_by_name"] for a in listed] == ["U"]


def test_an_upload_lands_in_the_shared_store_not_the_working_directory(upload_dir):
    # It used to be written to ./uploads, relative to the api process — the container's own
    # layer rather than the mounted volume — and nothing could read it back.
    ctx = _login()
    po = _create_order(ctx)
    content = _pdf(b"body")

    assert _upload(ctx, po["po_id"], content=content).status_code == 201

    (row,) = _attachment_rows(po["po_id"])
    assert row["file_blob_id"] is not None and row["file_path"] is None
    (blob,) = _sql(
        "SELECT workspace_id, mime, byte_size, storage_key FROM file_blob WHERE file_blob_id = :b",
        b=row["file_blob_id"],
    )
    assert blob["workspace_id"] == ctx["wid"] and blob["mime"] == "application/pdf"
    assert blob["byte_size"] == len(content)
    assert [p.read_bytes() for p in _files_on_disk(upload_dir)] == [content]
    assert _files_on_disk(upload_dir)[0].relative_to(upload_dir).as_posix() == blob["storage_key"]
    audits = _sql("SELECT event FROM audit_log WHERE event = 'file_blob.create' AND workspace_id = :w", w=ctx["wid"])
    assert len(audits) == 1


def test_the_same_bytes_attached_twice_share_one_blob(upload_dir):
    ctx = _login()
    po = _create_order(ctx)
    other_po = _create_order(ctx)
    assert _upload(ctx, po["po_id"], "a.pdf").status_code == 201
    assert _upload(ctx, other_po["po_id"], "b.pdf").status_code == 201

    ids = {r["file_blob_id"] for r in _attachment_rows(po["po_id"]) + _attachment_rows(other_po["po_id"])}
    assert len(ids) == 1
    assert len(_files_on_disk(upload_dir)) == 1
    assert _sql("SELECT count(*) AS n FROM file_blob")[0]["n"] == 1


def test_two_uploads_with_the_same_name_keep_their_own_content(upload_dir):
    ctx = _login()
    po = _create_order(ctx)
    assert _upload(ctx, po["po_id"], "quote.pdf", _pdf(b"first")).status_code == 201
    assert _upload(ctx, po["po_id"], "quote.pdf", _pdf(b"second")).status_code == 201
    first, second = _attachment_rows(po["po_id"])

    assert first["file_name"] == second["file_name"] == "quote.pdf"
    assert first["file_blob_id"] != second["file_blob_id"]
    assert _download(ctx, po["po_id"], first["attachment_id"]).content == _pdf(b"first")
    assert _download(ctx, po["po_id"], second["attachment_id"]).content == _pdf(b"second")

    r = ctx["client"].delete(f"/procurement/orders/{po['po_id']}/attachments/{first['attachment_id']}")
    assert r.status_code == 200, r.text
    assert _download(ctx, po["po_id"], second["attachment_id"]).content == _pdf(b"second")


def test_deleting_an_attachment_keeps_a_blob_another_row_still_uses(upload_dir):
    ctx = _login()
    po = _create_order(ctx)
    other_po = _create_order(ctx)
    assert _upload(ctx, po["po_id"], "a.pdf").status_code == 201
    assert _upload(ctx, other_po["po_id"], "b.pdf").status_code == 201
    (gone,) = _attachment_rows(po["po_id"])
    (kept,) = _attachment_rows(other_po["po_id"])

    r = ctx["client"].delete(f"/procurement/orders/{po['po_id']}/attachments/{gone['attachment_id']}")

    assert r.status_code == 200, r.text
    assert _attachment_rows(po["po_id"]) == []
    assert len(_files_on_disk(upload_dir)) == 1
    assert _download(ctx, other_po["po_id"], kept["attachment_id"]).content == _pdf()


def test_a_file_shared_by_older_rows_stays_until_the_last_row_goes(tmp_path):
    ctx = _login()
    po = _create_order(ctx)
    shared = tmp_path / "shared.pdf"
    shared.write_bytes(b"x")
    for _ in range(2):
        _sql(
            "INSERT INTO po_attachments (po_id, attachment_type, file_name, file_path)"
            " VALUES (:p, 'File', 'shared.pdf', :fp)",
            p=po["po_id"], fp=str(shared),
        )
    a, b = _attachment_rows(po["po_id"])

    assert ctx["client"].delete(f"/procurement/orders/{po['po_id']}/attachments/{a['attachment_id']}").status_code == 200
    assert shared.exists()
    assert ctx["client"].delete(f"/procurement/orders/{po['po_id']}/attachments/{b['attachment_id']}").status_code == 200
    assert not shared.exists()


def test_an_upload_over_the_cap_is_refused_and_leaves_nothing(upload_dir, monkeypatch):
    # No cap at all before: a 30 MB file was accepted (POST /files stops at 25 MB).
    monkeypatch.setattr(proc_routes, "MAX_BYTE_SIZE", 10)
    ctx = _login()
    po = _create_order(ctx)

    too_big = _upload(ctx, po["po_id"], content=b"%PDF-" + b"x" * 6)
    assert too_big.status_code == 413, too_big.text
    assert _attachment_rows(po["po_id"]) == []
    assert _files_on_disk(upload_dir) == []

    assert _upload(ctx, po["po_id"], content=b"%PDF-" + b"x" * 5).status_code == 201


@pytest.mark.parametrize(
    "name, content, status",
    [
        ("sheet.xlsx", b"PK\x03\x04 zipped office document", 415),  # not an accepted type
        ("notes.txt", b"just some text", 415),
        ("quote.png", _pdf(), 415),  # extension disagrees with the bytes
        ("empty.pdf", b"", 400),
    ],
)
def test_an_upload_that_fails_the_shared_checks_is_refused_and_leaves_nothing(upload_dir, name, content, status):
    # Any type used to be accepted unchecked; the store is shared now, so its rules apply.
    ctx = _login()
    po = _create_order(ctx)

    r = _upload(ctx, po["po_id"], name, content)

    assert r.status_code == status, r.text
    assert _attachment_rows(po["po_id"]) == []
    assert _files_on_disk(upload_dir) == []
    assert _sql("SELECT count(*) AS n FROM file_blob")[0]["n"] == 0


def test_a_failure_after_the_bytes_were_written_removes_them(upload_dir, monkeypatch):
    ctx = _login()
    po = _create_order(ctx)

    def boom(*a, **k):
        raise RuntimeError("db went away")

    monkeypatch.setattr(proc_routes.q, "insert_attachment", boom)
    with pytest.raises(RuntimeError):
        _upload(ctx, po["po_id"])

    assert _files_on_disk(upload_dir) == []
    assert _sql("SELECT count(*) AS n FROM file_blob")[0]["n"] == 0


def test_a_failure_does_not_remove_a_blob_other_rows_share(upload_dir, monkeypatch):
    ctx = _login()
    po = _create_order(ctx)
    assert _upload(ctx, po["po_id"]).status_code == 201

    def boom(*a, **k):
        raise RuntimeError("db went away")

    monkeypatch.setattr(proc_routes.q, "insert_attachment", boom)
    with pytest.raises(RuntimeError):
        _upload(ctx, po["po_id"], "again.pdf")

    assert len(_files_on_disk(upload_dir)) == 1


@pytest.mark.parametrize("frozen", ["Delivered", "Cancelled"])
def test_a_frozen_order_takes_and_loses_no_attachments(upload_dir, frozen):
    ctx = _login()
    po = _create_order(ctx)
    keep = _pdf(b"keep")
    assert _upload(ctx, po["po_id"], content=keep).status_code == 201
    kept = _attachment_rows(po["po_id"])[0]
    _set_status(po["po_id"], frozen)

    up = _upload(ctx, po["po_id"], "late.pdf", _pdf(b"late"))
    assert up.status_code == 409, up.text
    assert up.json()["detail"] == {"code": "ORDER_LOCKED", "status": frozen}
    rm = ctx["client"].delete(f"/procurement/orders/{po['po_id']}/attachments/{kept['attachment_id']}")
    assert rm.status_code == 409, rm.text

    assert len(_attachment_rows(po["po_id"])) == 1
    assert [p.read_bytes() for p in _files_on_disk(upload_dir)] == [keep]
    # Reading is not editing: a frozen order's attachment can still be downloaded.
    assert _download(ctx, po["po_id"], kept["attachment_id"]).content == keep


def test_attachment_responses_do_not_expose_the_server_path(upload_dir):
    ctx = _login()
    po = _create_order(ctx)
    assert _upload(ctx, po["po_id"]).status_code == 201

    listed = ctx["client"].get(f"/procurement/orders/{po['po_id']}/attachments").json()
    detail = ctx["client"].get(f"/procurement/orders/{po['po_id']}").json()["attachments"]

    for row in listed + detail:
        assert "file_path" not in row and "storage_key" not in row
        assert {"attachment_id", "file_name", "file_size_bytes", "uploaded_at"} <= set(row)


# ── Attachment download ───────────────────────────────────────────────────────
def test_download_streams_the_uploaded_bytes(upload_dir):
    ctx = _login()
    po = _create_order(ctx)
    content = _pdf(b"hello")
    assert _upload(ctx, po["po_id"], "Quote – v2.pdf", content).status_code == 201
    (row,) = _attachment_rows(po["po_id"])

    r = _download(ctx, po["po_id"], row["attachment_id"])

    assert r.status_code == 200, r.text
    assert r.content == content
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-length"] == str(len(content))
    disposition = r.headers["content-disposition"]
    assert disposition.startswith("inline;") and "filename*=UTF-8''Quote%20%E2%80%93%20v2.pdf" in disposition


def test_download_is_404_across_workspaces(upload_dir):
    mine = _login()
    other = _login()
    po = _create_order(other)
    assert _upload(other, po["po_id"]).status_code == 201
    (row,) = _attachment_rows(po["po_id"])

    assert _download(mine, po["po_id"], row["attachment_id"]).status_code == 404
    assert _download(other, po["po_id"], row["attachment_id"]).status_code == 200


def test_download_does_not_serve_another_workspaces_blob(upload_dir):
    # file_blob_id is a plain FK with no workspace of its own, so the join to the blob is
    # scoped: a row pointing at a foreign workspace's blob serves nothing.
    mine = _login()
    other = _login()
    other_po = _create_order(other)
    assert _upload(other, other_po["po_id"]).status_code == 201
    foreign_blob = _attachment_rows(other_po["po_id"])[0]["file_blob_id"]
    po = _create_order(mine)
    _sql(
        "INSERT INTO po_attachments (po_id, attachment_type, file_name, file_blob_id)"
        " VALUES (:p, 'PDF', 'x.pdf', :b)",
        p=po["po_id"], b=foreign_blob,
    )
    (row,) = _attachment_rows(po["po_id"])

    assert _download(mine, po["po_id"], row["attachment_id"]).status_code == 404


def test_download_unknown_attachment_or_wrong_order_is_404(upload_dir):
    ctx = _login()
    po = _create_order(ctx)
    other_po = _create_order(ctx)
    assert _upload(ctx, po["po_id"]).status_code == 201
    (row,) = _attachment_rows(po["po_id"])

    assert _download(ctx, po["po_id"], 999_999).status_code == 404
    assert _download(ctx, other_po["po_id"], row["attachment_id"]).status_code == 404
    assert _download(ctx, 999_999, row["attachment_id"]).status_code == 404


def test_download_needs_orderbook_read(upload_dir):
    ctx = _login()
    po = _create_order(ctx)
    assert _upload(ctx, po["po_id"]).status_code == 201
    (row,) = _attachment_rows(po["po_id"])
    # A group that holds nothing on orderbook: a real "no" from the RBAC engine.
    _sql("DELETE FROM user_group_membership WHERE user_id = :u", u=ctx["uid"])
    gid = _sql(
        "INSERT INTO permission_group(workspace_id, name, is_system) VALUES (:w, 'none', false) RETURNING group_id",
        w=ctx["wid"],
    )[0]["group_id"]
    _sql("INSERT INTO user_group_membership(user_id, group_id) VALUES (:u, :g)", u=ctx["uid"], g=gid)

    assert _download(ctx, po["po_id"], row["attachment_id"]).status_code == 403


def test_a_legacy_row_downloads_from_its_path_as_an_attachment_only(tmp_path):
    ctx = _login()
    po = _create_order(ctx)
    old = tmp_path / "old.html"
    old.write_bytes(b"<script>alert(1)</script>")
    _sql(
        "INSERT INTO po_attachments (po_id, attachment_type, file_name, file_path)"
        " VALUES (:p, 'File', 'old.html', :fp)",
        p=po["po_id"], fp=str(old),
    )
    (row,) = _attachment_rows(po["po_id"])

    r = _download(ctx, po["po_id"], row["attachment_id"])

    assert r.status_code == 200, r.text
    assert r.content == b"<script>alert(1)</script>"
    # Never rendered: these files were not sniffed on the way in.
    assert r.headers["content-disposition"].startswith("attachment;")
    assert r.headers["x-content-type-options"] == "nosniff"


def test_a_legacy_row_whose_file_is_gone_is_404():
    ctx = _login()
    po = _create_order(ctx)
    _sql(
        "INSERT INTO po_attachments (po_id, attachment_type, file_name, file_path)"
        " VALUES (:p, 'File', 'lost.pdf', '/nowhere/lost.pdf')",
        p=po["po_id"],
    )
    _sql(
        "INSERT INTO po_attachments (po_id, attachment_type, file_name)"
        " VALUES (:p, 'File', 'no-path.pdf')",
        p=po["po_id"],
    )

    for row in _attachment_rows(po["po_id"]):
        r = _download(ctx, po["po_id"], row["attachment_id"])
        assert r.status_code == 404, r.text


def test_a_blob_whose_bytes_are_gone_is_404(upload_dir):
    ctx = _login()
    po = _create_order(ctx)
    assert _upload(ctx, po["po_id"]).status_code == 201
    (row,) = _attachment_rows(po["po_id"])
    for f in _files_on_disk(upload_dir):
        f.unlink()

    assert _download(ctx, po["po_id"], row["attachment_id"]).status_code == 404


# ── Validation ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "path",
    ["/procurement/orders?offset=-1", "/procurement/orders?limit=-1", "/procurement/approvals/history?limit=-1"],
)
def test_negative_paging_is_a_422_not_a_500(path):
    ctx = _login()
    assert ctx["client"].get(path).status_code == 422


def test_a_zero_limit_is_still_allowed():
    ctx = _login()
    r = ctx["client"].get("/procurement/orders?limit=0")
    assert r.status_code == 200 and r.json() == []


def test_duplicate_line_numbers_are_a_422_and_create_nothing():
    ctx = _login()
    before = _sql("SELECT count(*) n FROM purchase_orders")[0]["n"]

    r = ctx["client"].post(
        "/procurement/orders",
        json={
            "vendor_id": ctx["vendor_id"], "requester_id": ctx["uid"], "cost_center_id": ctx["cc_id"],
            "description": "x", "category": "Office",
            "line_items": [
                {"line_number": 1, "item_description": "a", "quantity": 1, "unit_price": 1},
                {"line_number": 1, "item_description": "b", "quantity": 1, "unit_price": 1},
            ],
        },
    )

    assert r.status_code == 422, r.text
    assert _sql("SELECT count(*) n FROM purchase_orders")[0]["n"] == before


# ── Duplicate ─────────────────────────────────────────────────────────────────
def test_duplicate_keeps_the_project_item_attributes_and_line_provenance():
    # It dropped project_id, item_id and attributes: a copy of a v1 order lost its links and,
    # with no project, reached its workspace through the vendor instead.
    ctx = _login()
    project_id = _sql(
        "INSERT INTO projects(project_code, name, workspace_id) VALUES (:c, 'P', :w) RETURNING project_id",
        c=f"D-{uuid.uuid4().hex[:6]}", w=ctx["wid"],
    )[0]["project_id"]
    item_id = _sql(
        "INSERT INTO items(num, project_id, description, status, stage)"
        " VALUES (nextval('joinery_number_seq'), :p, 'unit', 'CLEAR', 'Block B') RETURNING item_id",
        p=project_id,
    )[0]["item_id"]
    po = _create_order(ctx, line_items=_lines((2, 50)))
    _sql(
        "UPDATE purchase_orders SET project_id = :p, item_id = :i, attributes = '{\"k\": \"v\"}'::jsonb"
        " WHERE po_id = :po",
        p=project_id, i=item_id, po=po["po_id"],
    )
    _sql(
        "UPDATE po_line_items SET attributes = '{\"finish\": \"matt\"}'::jsonb,"
        " material_table = 'board_materials', material_id = 12345 WHERE po_id = :po",
        po=po["po_id"],
    )

    dup = ctx["client"].post(f"/procurement/orders/{po['po_id']}/duplicate").json()

    head = _sql("SELECT project_id, item_id, attributes FROM purchase_orders WHERE po_id = :p", p=dup["po_id"])[0]
    assert head == {"project_id": project_id, "item_id": item_id, "attributes": {"k": "v"}}
    line = _sql(
        "SELECT attributes, material_table, material_id FROM po_line_items WHERE po_id = :p", p=dup["po_id"]
    )[0]
    assert line == {"attributes": {"finish": "matt"}, "material_table": "board_materials", "material_id": 12345}
