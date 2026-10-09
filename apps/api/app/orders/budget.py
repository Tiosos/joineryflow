"""Budget ledger rows for an order that leaves the book (migration 0054 follows the legacy convention).

`budget_transactions` is a ledger and `v_budget_utilisation` sums Commitment, Expenditure and
Release together (a Release is stored negative, migration 0046). So:

- **Cancelled**: the order's outstanding Commitment is released (a negative `Release` row).
- **Delivered**: the real cost is posted as an `Expenditure` (the order's total at delivery) and
  the outstanding Commitment is released, so the same money is not counted twice.

Both need the order to have a cost centre and are no-ops without one (Q563). Outstanding is
read from the ledger (commitments less earlier releases), not from the order's total, which may
have moved since approval. Nothing is posted twice: a second cancel/delivery finds nothing
outstanding, and an order that already has an Expenditure gets no second one.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit


def settle_on_close(
    db: Session, *, order: dict, workspace_id: int, actor_id: int, delivered: bool
) -> dict:
    """`order` is the order as it stands after the status change (needs po_id, po_number,
    cost_center_id, total_amount). Returns what was posted: {"expenditure", "released"}."""
    posted = {"expenditure": Decimal(0), "released": Decimal(0)}
    cc = order["cost_center_id"]
    if cc is None:
        return posted
    if not db.execute(
        text("SELECT 1 FROM cost_centers WHERE cost_center_id = :c AND workspace_id = :w"),
        {"c": cc, "w": workspace_id},
    ).first():
        return posted

    def post(amount: Decimal, kind: str, note: str) -> None:
        db.execute(
            text(
                """
                INSERT INTO budget_transactions
                    (cost_center_id, po_id, amount, transaction_type, description,
                     transaction_date, created_by)
                VALUES (:c, :o, :a, :t, :d, CURRENT_DATE, :u)
                """
            ),
            {"c": cc, "o": order["po_id"], "a": amount, "t": kind, "d": note, "u": actor_id},
        )

    total = order["total_amount"]
    if delivered and total is not None and total > 0 and not db.execute(
        text("SELECT 1 FROM budget_transactions WHERE po_id = :o AND transaction_type = 'Expenditure'"),
        {"o": order["po_id"]},
    ).first():
        post(total, "Expenditure", "PO delivered")
        posted["expenditure"] = total

    outstanding = db.execute(
        text(
            "SELECT COALESCE(SUM(amount), 0) FROM budget_transactions"
            " WHERE po_id = :o AND transaction_type IN ('Commitment', 'Release')"
        ),
        {"o": order["po_id"]},
    ).scalar()
    if outstanding and outstanding > 0:
        post(-Decimal(outstanding), "Release", "PO delivered" if delivered else "PO cancelled")
        posted["released"] = Decimal(outstanding)

    if posted["expenditure"] or posted["released"]:
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id,
            event="order.budget.delivered" if delivered else "order.budget.cancelled",
            target=str(order["po_id"]),
            payload={"po_number": order["po_number"],
                     "expenditure": str(posted["expenditure"]), "released": str(posted["released"])},
        )
    return posted
