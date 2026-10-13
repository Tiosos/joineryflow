"""Order priority has three levels: High, Medium, Low

Product-owner decision (October 2026): the old system's priority had only high, medium and low.
`Next`, `Hold` and `Quote` were carried over from the status list (0002 gave both columns the same
six values), but they are order *statuses*, and `purchase_orders.status` already allows all three,
so nothing is lost by taking them out of `priority`.

Data-preserving: an order whose priority was one of the three is set to `Medium` and keeps its
status as it is (it is not copied into the status). The check is then narrowed to the three levels.
Downgrade widens the check again; the priorities that were replaced are not recoverable.

Revision ID: 0058
Revises: 0057
Create Date: 2026-10-13
"""
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    UPDATE purchase_orders SET priority = 'Medium' WHERE priority IN ('Next', 'Hold', 'Quote');
    ALTER TABLE purchase_orders DROP CONSTRAINT purchase_orders_priority_check;
    ALTER TABLE purchase_orders ADD CONSTRAINT purchase_orders_priority_check
        CHECK (priority IN ('High', 'Medium', 'Low'));
    """)


def downgrade():
    op.execute("""
    ALTER TABLE purchase_orders DROP CONSTRAINT purchase_orders_priority_check;
    ALTER TABLE purchase_orders ADD CONSTRAINT purchase_orders_priority_check
        CHECK (priority IN ('High', 'Medium', 'Low', 'Next', 'Hold', 'Quote'));
    """)
