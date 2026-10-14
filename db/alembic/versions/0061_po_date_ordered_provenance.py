"""Remember which Date ordered a PO set, so leaving the PO clears only that one

0059's detach guessed: it cleared an order's Date ordered when it equalled the PO's current date.
That erased a hand-typed date that happened to match, and kept a PO-set date after the PO's own date
was edited. `purchase_orders.date_ordered_from_po` is true only when putting the order on a PO is
what gave it its Date ordered; editing the date by hand on the order turns it off.

Existing rows keep the old rule once: an order on a PO whose Date ordered equals the PO's is flagged.

Revision ID: 0061
Revises: 0060
Create Date: 2026-10-14
"""
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE purchase_orders ADD COLUMN date_ordered_from_po boolean NOT NULL DEFAULT false")
    op.execute(
        """
        UPDATE purchase_orders po SET date_ordered_from_po = true
          FROM po_document pd
         WHERE po.po_document_id = pd.po_document_id AND po.date_ordered = pd.date_ordered
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE purchase_orders DROP COLUMN date_ordered_from_po")
