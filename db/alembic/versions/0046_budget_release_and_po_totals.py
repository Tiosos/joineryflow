"""v_budget_utilisation counts Release rows; back-fill legacy PO totals; advance po_number_seq

Three repairs to the legacy `/procurement/*` path.

1. **`Release`.** ``v_budget_utilisation`` (`0006`) summed only ``Commitment`` and
   ``Expenditure`` rows. Approving an order posts a Commitment and delivering it an
   Expenditure, and nothing ever took the Commitment back, so a delivered order counted
   twice (a $110 order read as $220). ``budget_transactions`` already allows a
   ``Release`` type that no code used. The view now includes it in all three sums; a
   Release is stored negative, so it cancels the Commitment it replaces. Delivery posts
   one (see ``procurement.queries.release_commitment``).

2. **Totals.** ``purchase_orders.total_amount`` (and ``gst_amount`` / ``grand_total``,
   generated from it) was set from the lines by MySQL triggers that `0002` did not port,
   leaving the job "to the application". The legacy create / duplicate routes never did it,
   so every order they made with line items has ``total_amount`` 0 while its lines sum to
   a real figure, and its approval posted a $0 Commitment. The routes now recompute it;
   this back-fills the orders already in that state. Only a ``total_amount`` of 0 (or
   NULL) on an order that has lines with a non-zero sum is touched, so a figure anyone set
   on purpose is never overwritten, and ``updated_at`` is left alone (it is a correction,
   not an edit). **Budget rows already posted at $0 are not rewritten** — the ledger is
   append-only and what was posted is what was posted.

3. **PO numbers.** The legacy create / duplicate routes numbered orders ``MAX(seq) + 1``
   while the v1 module draws from ``po_number_seq`` into the same table, so they handed out
   the same number (the v1 create then failed with a unique violation). The routes now use the
   sequence too, but a database that already holds legacy-made numbers ahead of the sequence
   would keep colliding until it caught up, so the sequence is advanced past the highest
   number in use. Nothing is renumbered, and the sequence is never moved backwards.

``CREATE OR REPLACE VIEW`` is valid because the output columns, their order and their
types are identical. The downgrade restores the two-type view; the back-fill is not
reversible (the old zeros carry no information).

Revision ID: 0046
Revises: 0045
Create Date: 2026-10-01
"""
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

_VIEW_TEMPLATE = """
CREATE OR REPLACE VIEW v_budget_utilisation AS
    SELECT
        cc.cost_center_id,
        cc.code,
        cc.name,
        cc.fiscal_year,
        cc.budget_amount,
        COALESCE(SUM(CASE WHEN bt.transaction_type IN ({types})
                          THEN bt.amount ELSE 0 END), 0) AS total_committed,
        cc.budget_amount
            - COALESCE(SUM(CASE WHEN bt.transaction_type IN ({types})
                                THEN bt.amount ELSE 0 END), 0) AS remaining,
        round(
            COALESCE(SUM(CASE WHEN bt.transaction_type IN ({types})
                              THEN bt.amount ELSE 0 END), 0)
            / NULLIF(cc.budget_amount, 0) * 100, 1
        ) AS utilisation_pct
    FROM cost_centers cc
    LEFT JOIN budget_transactions bt ON cc.cost_center_id = bt.cost_center_id
    GROUP BY cc.cost_center_id
"""


def upgrade() -> None:
    op.execute(_VIEW_TEMPLATE.format(types="'Commitment','Expenditure','Release'"))
    op.execute(
        """
        UPDATE purchase_orders po
           SET total_amount = s.total
          FROM (
              SELECT po_id, SUM(line_total) AS total
                FROM po_line_items
               GROUP BY po_id
          ) s
         WHERE s.po_id = po.po_id
           AND COALESCE(po.total_amount, 0) = 0
           AND s.total <> 0
        """
    )
    op.execute(
        r"""
        DO $$
        DECLARE
            highest integer;
        BEGIN
            SELECT MAX(CAST(regexp_replace(po_number, '^.*-', '') AS integer))
              INTO highest
              FROM purchase_orders
             WHERE po_number ~ '^PO-[0-9]{4}-[0-9]+$';
            IF highest IS NOT NULL AND highest >= (SELECT last_value FROM po_number_seq) THEN
                PERFORM setval('po_number_seq', highest, true);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(_VIEW_TEMPLATE.format(types="'Commitment','Expenditure'"))
    # Not reversible: the total_amount back-fill (the old zeros carry no information) and the
    # sequence, which is never moved backwards.
