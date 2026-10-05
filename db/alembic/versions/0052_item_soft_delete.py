"""Soft delete for items: `items.deleted` becomes NOT NULL and `cutlist.deleted` is added

`DELETE /items/{id}` used to remove the row. It now flags the item, its related parts
and (when no live item is left in it) its cutlist, so production history, QC records
and audit stay intact and a restore brings everything back.

`items.deleted` has existed since 0001 as a nullable `boolean DEFAULT false` that
nothing wrote. Every reader now says `NOT i.deleted`, and `NOT NULL` is what makes that
safe (a NULL would hide the row). Existing rows are all false, so nothing changes.

Revision ID: 0052
Revises: 0051
Create Date: 2026-10-05
"""
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    UPDATE items SET deleted = false WHERE deleted IS NULL;
    ALTER TABLE items
      ALTER COLUMN deleted SET DEFAULT false,
      ALTER COLUMN deleted SET NOT NULL;
    ALTER TABLE cutlist ADD COLUMN IF NOT EXISTS deleted boolean NOT NULL DEFAULT false;
    CREATE INDEX IF NOT EXISTS idx_items_project_deleted ON items (project_id) WHERE deleted;
    """)


def downgrade():
    op.execute("""
    DROP INDEX IF EXISTS idx_items_project_deleted;
    ALTER TABLE cutlist DROP COLUMN IF EXISTS deleted;
    ALTER TABLE items ALTER COLUMN deleted DROP NOT NULL;
    """)
