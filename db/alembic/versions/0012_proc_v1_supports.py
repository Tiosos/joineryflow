"""procurement_v1 supports: cancelled_at + supplier/allocation indexes

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-28
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    ALTER TABLE procurement_batches
      ADD COLUMN cancelled_at timestamptz;

    CREATE INDEX IF NOT EXISTS idx_batches_supplier
      ON procurement_batches (supplier);

    CREATE INDEX IF NOT EXISTS idx_alloc_batch
      ON batch_allocations (batch_id);
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-procurement-v1 schema is recoverable from migrations 0001-0011 only")
