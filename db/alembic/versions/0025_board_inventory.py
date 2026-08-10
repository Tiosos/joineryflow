"""board_inventory — sheet stock on hand per board material + size

Until now the CutPlan optimiser had no idea what stock existed: sheet
dimensions were typed by hand on every run (a per-optimisation override) and
nothing capped how many sheets a nest could assume.

`board_inventory` holds a count of physical sheets per (material, size), so
the optimiser can default its sheet dimensions from real stock and flag when a
nest needs more sheets than the workspace owns. One row per distinct size a
material is stocked in — the same board is often held in more than one sheet
size.

Stock is **read-only** to the optimiser: `/optimise` stays a pure function and
never reserves or decrements. Consumption on cut-plan completion is a separate,
later decision.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-10
"""
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS board_inventory (
        inventory_id BIGSERIAL   PRIMARY KEY,
        workspace_id BIGINT      NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
        material_id  BIGINT      NOT NULL REFERENCES board_materials(material_id) ON DELETE CASCADE,
        len_mm       integer     NOT NULL CHECK (len_mm > 0),
        wid_mm       integer     NOT NULL CHECK (wid_mm > 0),
        qty_on_hand  integer     NOT NULL DEFAULT 0 CHECK (qty_on_hand >= 0),
        location     varchar(128),
        notes        text,
        created_at   timestamptz NOT NULL DEFAULT now(),
        created_by   BIGINT      REFERENCES app_user(id) ON DELETE SET NULL,
        updated_at   timestamptz NOT NULL DEFAULT now(),
        -- One row per material per stocked size; adjusting stock is an UPDATE
        -- of qty_on_hand, not a second row.
        CONSTRAINT uq_board_inventory UNIQUE (workspace_id, material_id, len_mm, wid_mm)
    );

    CREATE INDEX IF NOT EXISTS idx_board_inventory_material
        ON board_inventory (workspace_id, material_id);

    -- Partial index for the optimiser's hot path: "what can I actually cut?"
    CREATE INDEX IF NOT EXISTS idx_board_inventory_in_stock
        ON board_inventory (workspace_id, material_id)
        WHERE qty_on_hand > 0;
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS board_inventory;")
