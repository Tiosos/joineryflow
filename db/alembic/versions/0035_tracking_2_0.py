"""tracking 2.0 — workspace_counter + item enrichment columns

Adds:
- workspace_counter(workspace_id, name, next_value) — shared atomic counter
  table reused by #12 (PO #), #13 (invoice / variation #), etc.
- items.jid_code, jid_color, var_boq, contractor_id, total_amount,
  site_measure_notes — legacy-parity columns for the Tracking 2.0 grid.

items.num stays as the legacy 6-digit cutlist# (already global UNIQUE).

Revision ID: 0035
Revises: 0034
Create Date: 2026-05-27
"""
from alembic import op


revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS workspace_counter (
        workspace_id BIGINT      NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
        name         VARCHAR(32) NOT NULL,
        next_value   BIGINT      NOT NULL DEFAULT 1,
        PRIMARY KEY (workspace_id, name)
    );

    ALTER TABLE items
        ADD COLUMN IF NOT EXISTS jid_code           VARCHAR(32),
        ADD COLUMN IF NOT EXISTS jid_color          CHAR(7),
        ADD COLUMN IF NOT EXISTS var_boq            VARCHAR(8)  NOT NULL DEFAULT 'BOQ',
        ADD COLUMN IF NOT EXISTS contractor_id      BIGINT,
        ADD COLUMN IF NOT EXISTS total_amount       NUMERIC(12, 2),
        ADD COLUMN IF NOT EXISTS site_measure_notes TEXT;

    ALTER TABLE items DROP CONSTRAINT IF EXISTS items_var_boq_check;
    ALTER TABLE items
        ADD CONSTRAINT items_var_boq_check
            CHECK (var_boq IN ('BOQ', 'VAR'));

    ALTER TABLE items DROP CONSTRAINT IF EXISTS items_jid_color_check;
    ALTER TABLE items
        ADD CONSTRAINT items_jid_color_check
            CHECK (jid_color IS NULL OR jid_color ~ '^#[0-9A-Fa-f]{6}$');

    ALTER TABLE items DROP CONSTRAINT IF EXISTS items_contractor_id_fkey;
    ALTER TABLE items
        ADD CONSTRAINT items_contractor_id_fkey
            FOREIGN KEY (contractor_id) REFERENCES app_user(id) ON DELETE SET NULL;

    CREATE INDEX IF NOT EXISTS idx_items_var_boq    ON items (var_boq);
    CREATE INDEX IF NOT EXISTS idx_items_contractor ON items (contractor_id);
    """)


def downgrade():
    op.execute("""
    DROP INDEX IF EXISTS idx_items_contractor;
    DROP INDEX IF EXISTS idx_items_var_boq;

    ALTER TABLE items DROP CONSTRAINT IF EXISTS items_contractor_id_fkey;
    ALTER TABLE items DROP CONSTRAINT IF EXISTS items_jid_color_check;
    ALTER TABLE items DROP CONSTRAINT IF EXISTS items_var_boq_check;

    ALTER TABLE items
        DROP COLUMN IF EXISTS site_measure_notes,
        DROP COLUMN IF EXISTS total_amount,
        DROP COLUMN IF EXISTS contractor_id,
        DROP COLUMN IF EXISTS var_boq,
        DROP COLUMN IF EXISTS jid_color,
        DROP COLUMN IF EXISTS jid_code;

    DROP TABLE IF EXISTS workspace_counter;
    """)
