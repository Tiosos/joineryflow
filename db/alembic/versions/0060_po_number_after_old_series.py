"""PO numbers continue after the old system's series

The customer gave the old system's last PO number: 193970. `po_document_no_seq` (0059) started at
100001, which would reuse old numbers, so it is moved so the next PO is 193971. It never moves
backwards: if the sequence or a stored `po_no` is already past 193970, that wins.

Revision ID: 0060
Revises: 0059
Create Date: 2026-10-14
"""
from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        SELECT setval(
          'po_document_no_seq',
          GREATEST(
            193970,
            (SELECT COALESCE(MAX(po_no), 0) FROM po_document),
            (SELECT last_value FROM po_document_no_seq WHERE is_called)
          )
        )
        """
    )


def downgrade() -> None:
    # A sequence cannot safely be moved back: numbers may already have been issued.
    pass
