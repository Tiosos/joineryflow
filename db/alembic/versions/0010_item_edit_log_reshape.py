"""item_edit_log reshape

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-27
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    -- Reshape legacy FileMaker-era columns to match the PM Workbench spec §6.5.
    ALTER TABLE item_edit_log ADD COLUMN actor_id BIGINT
      REFERENCES app_user(id) ON DELETE SET NULL;
    ALTER TABLE item_edit_log RENAME COLUMN field_label TO field;
    ALTER TABLE item_edit_log RENAME COLUMN changed_at TO ts;
    ALTER TABLE item_edit_log DROP COLUMN changed_by;
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-PM-Workbench schema is recoverable from migrations 0001-0007 only")
