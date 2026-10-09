"""PO approval: remember the total that was approved

An order that is approved and then has its total raised goes back for approval. To know it was
*raised*, the approval has to remember the amount it approved: `purchase_orders.approved_total`,
set when an approver approves. Existing approved orders (only those approved through the flow, which
records an approver) get their current total.

Revision ID: 0055
Revises: 0054
Create Date: 2026-10-09
"""
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS approved_total numeric;
    UPDATE purchase_orders SET approved_total = total_amount
     WHERE status = 'Approved' AND approval_decided_by IS NOT NULL;
    """)


def downgrade():
    op.execute("ALTER TABLE purchase_orders DROP COLUMN IF EXISTS approved_total;")
