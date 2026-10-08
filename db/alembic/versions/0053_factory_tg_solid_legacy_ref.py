"""Factories, the item-level Tg Solid tag and a legacy reference, for the FileMaker import (E3)

The pilot export (FileMaker "Tracking 2.0") carries three things the item table had no home for:

- `_Contractor` = `TG`: the **factory** the work is made in. There are others (`SI` so far, more to come),
  so it is a per-workspace lookup, not free text and not a user. `items.factory_id` is nullable; an item
  with no factory is simply not assigned to one yet.
- `Tag_TgSolidItem`: a per-item tag, separate from `solid_surface_req` (the user said so). It mirrors the
  project-level `projects.tg_solid` that has existed since `0001`. `items.tg_solid` is the data behind
  Tracking's Tg Solid chip.
- `ItemId_Old`: FileMaker's 22-digit record id, kept as `items.legacy_item_ref` so an imported row can
  always be traced back (and a re-import can recognise it). Nullable, no uniqueness.

Existing rows: no factory, `tg_solid` false, no legacy ref.

Revision ID: 0053
Revises: 0052
Create Date: 2026-10-08
"""
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS factory (
        factory_id   bigserial PRIMARY KEY,
        workspace_id bigint NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
        code         varchar(16)  NOT NULL,
        name         varchar(255),
        is_active    boolean NOT NULL DEFAULT true,
        created_at   timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_factory_workspace_code UNIQUE (workspace_id, code)
    );
    ALTER TABLE items
      ADD COLUMN IF NOT EXISTS factory_id bigint REFERENCES factory(factory_id) ON DELETE SET NULL,
      ADD COLUMN IF NOT EXISTS tg_solid boolean NOT NULL DEFAULT false,
      ADD COLUMN IF NOT EXISTS legacy_item_ref varchar(64);
    CREATE INDEX IF NOT EXISTS idx_items_factory ON items (factory_id) WHERE factory_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_items_legacy_ref ON items (legacy_item_ref) WHERE legacy_item_ref IS NOT NULL;
    """)


def downgrade():
    op.execute("""
    DROP INDEX IF EXISTS idx_items_legacy_ref;
    DROP INDEX IF EXISTS idx_items_factory;
    ALTER TABLE items DROP COLUMN IF EXISTS legacy_item_ref, DROP COLUMN IF EXISTS tg_solid,
                      DROP COLUMN IF EXISTS factory_id;
    DROP TABLE IF EXISTS factory;
    """)
