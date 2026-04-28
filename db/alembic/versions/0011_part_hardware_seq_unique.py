"""unique constraints on parts(module_id, seq) and item_hardware_lines(item_id, seq)

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-27
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    -- Enforce uniqueness of seq within a parent so seed/UI can rely on
    -- INSERT ... ON CONFLICT (module_id, seq) / (item_id, seq) DO NOTHING.
    -- seq remains nullable; PostgreSQL's default NULLS DISTINCT semantics
    -- mean rows with NULL seq do not conflict with each other.
    ALTER TABLE parts
      ADD CONSTRAINT uq_parts_module_seq UNIQUE (module_id, seq);

    ALTER TABLE item_hardware_lines
      ADD CONSTRAINT uq_ihl_item_seq UNIQUE (item_id, seq);
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-PM-Workbench schema is recoverable from migrations 0001-0007 only")
