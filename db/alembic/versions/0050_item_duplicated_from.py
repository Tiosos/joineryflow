"""items.duplicated_from_item_id — the source-item link of a duplicated Joinery Item

Plan V1 §2: "Each duplicate receives a unique ID and source-item link." The new ID is
the ordinary `items.num` from `joinery_number_seq`; this column is the link.

`ON DELETE SET NULL`: deleting (hard-deleting) the source must not delete its copies,
and a copy outlives its source as an ordinary item that merely forgets where it came
from. Items are normally soft-deleted (`deleted`), which leaves the link intact.

Existing rows stay NULL — nothing in the tree was ever duplicated.

Revision ID: 0050
Revises: 0049
Create Date: 2026-10-03
"""
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE items
      ADD COLUMN IF NOT EXISTS duplicated_from_item_id bigint
        REFERENCES items(item_id) ON DELETE SET NULL;
    CREATE INDEX IF NOT EXISTS idx_items_duplicated_from
      ON items (duplicated_from_item_id) WHERE duplicated_from_item_id IS NOT NULL;
    """)


def downgrade():
    op.execute("""
    DROP INDEX IF EXISTS idx_items_duplicated_from;
    ALTER TABLE items DROP COLUMN IF EXISTS duplicated_from_item_id;
    """)
