"""material catalog reconciliation (hybrid)

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-25

Resolves the T11 Foundation concern: the six catalog tables
(`board_materials`, `hardware_materials`, `custom_made`, `benchtop_materials`,
`appliances`, `equipment_hire`) were ported in 0001 with their full legacy
shape (15+ columns each), while the Foundation design spec called for a
simpler shape `(id, workspace_id, sku, name, spec jsonb, unit_cost)`.

Per Q4-B (hybrid): keep all legacy columns AND add the spec-target columns
`workspace_id`, `sku`, `unit_cost`. Future PM Workbench / Cabinet Vision
Integration work can write to either shape; reconciliation/dropping legacy
cols is deferred until those consumers settle.

Per-table notes:
- `hardware_materials` already has `sku` natively (legacy column name); we
  only add `workspace_id` + `unit_cost`. The pre-existing global UNIQUE(sku)
  is left intact - it's stricter than UNIQUE(workspace_id, sku) so the
  Foundation invariant is satisfied without a duplicate constraint.
- `equipment_hire` is more transactional than catalog (per-rental contracts),
  but the Foundation spec listed it among the six. Columns added for
  consistency; semantics are looser there.

All new columns are NULL-able for now since the tables are empty. A future
migration can `SET NOT NULL` once there is real data.
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    -- board_materials: add workspace_id, sku, unit_cost
    ALTER TABLE board_materials
      ADD COLUMN workspace_id BIGINT REFERENCES workspace(id) ON DELETE CASCADE,
      ADD COLUMN sku          varchar(255),
      ADD COLUMN unit_cost    numeric(12,2);
    CREATE INDEX idx_board_materials_workspace ON board_materials(workspace_id);
    ALTER TABLE board_materials
      ADD CONSTRAINT board_materials_workspace_sku_key UNIQUE (workspace_id, sku);

    -- hardware_materials: add workspace_id, unit_cost (sku already exists)
    ALTER TABLE hardware_materials
      ADD COLUMN workspace_id BIGINT REFERENCES workspace(id) ON DELETE CASCADE,
      ADD COLUMN unit_cost    numeric(12,2);
    CREATE INDEX idx_hardware_materials_workspace ON hardware_materials(workspace_id);

    -- custom_made: add workspace_id, sku, unit_cost
    ALTER TABLE custom_made
      ADD COLUMN workspace_id BIGINT REFERENCES workspace(id) ON DELETE CASCADE,
      ADD COLUMN sku          varchar(255),
      ADD COLUMN unit_cost    numeric(12,2);
    CREATE INDEX idx_custom_made_workspace ON custom_made(workspace_id);
    ALTER TABLE custom_made
      ADD CONSTRAINT custom_made_workspace_sku_key UNIQUE (workspace_id, sku);

    -- benchtop_materials: add workspace_id, sku, unit_cost
    ALTER TABLE benchtop_materials
      ADD COLUMN workspace_id BIGINT REFERENCES workspace(id) ON DELETE CASCADE,
      ADD COLUMN sku          varchar(255),
      ADD COLUMN unit_cost    numeric(12,2);
    CREATE INDEX idx_benchtop_materials_workspace ON benchtop_materials(workspace_id);
    ALTER TABLE benchtop_materials
      ADD CONSTRAINT benchtop_materials_workspace_sku_key UNIQUE (workspace_id, sku);

    -- appliances: add workspace_id, sku, unit_cost
    ALTER TABLE appliances
      ADD COLUMN workspace_id BIGINT REFERENCES workspace(id) ON DELETE CASCADE,
      ADD COLUMN sku          varchar(255),
      ADD COLUMN unit_cost    numeric(12,2);
    CREATE INDEX idx_appliances_workspace ON appliances(workspace_id);
    ALTER TABLE appliances
      ADD CONSTRAINT appliances_workspace_sku_key UNIQUE (workspace_id, sku);

    -- equipment_hire: add workspace_id, sku, unit_cost
    ALTER TABLE equipment_hire
      ADD COLUMN workspace_id BIGINT REFERENCES workspace(id) ON DELETE CASCADE,
      ADD COLUMN sku          varchar(255),
      ADD COLUMN unit_cost    numeric(12,2);
    CREATE INDEX idx_equipment_hire_workspace ON equipment_hire(workspace_id);
    ALTER TABLE equipment_hire
      ADD CONSTRAINT equipment_hire_workspace_sku_key UNIQUE (workspace_id, sku);
    """)


def downgrade():
    op.execute(r"""
    ALTER TABLE equipment_hire
      DROP CONSTRAINT IF EXISTS equipment_hire_workspace_sku_key,
      DROP COLUMN IF EXISTS unit_cost,
      DROP COLUMN IF EXISTS sku,
      DROP COLUMN IF EXISTS workspace_id;
    DROP INDEX IF EXISTS idx_equipment_hire_workspace;

    ALTER TABLE appliances
      DROP CONSTRAINT IF EXISTS appliances_workspace_sku_key,
      DROP COLUMN IF EXISTS unit_cost,
      DROP COLUMN IF EXISTS sku,
      DROP COLUMN IF EXISTS workspace_id;
    DROP INDEX IF EXISTS idx_appliances_workspace;

    ALTER TABLE benchtop_materials
      DROP CONSTRAINT IF EXISTS benchtop_materials_workspace_sku_key,
      DROP COLUMN IF EXISTS unit_cost,
      DROP COLUMN IF EXISTS sku,
      DROP COLUMN IF EXISTS workspace_id;
    DROP INDEX IF EXISTS idx_benchtop_materials_workspace;

    ALTER TABLE custom_made
      DROP CONSTRAINT IF EXISTS custom_made_workspace_sku_key,
      DROP COLUMN IF EXISTS unit_cost,
      DROP COLUMN IF EXISTS sku,
      DROP COLUMN IF EXISTS workspace_id;
    DROP INDEX IF EXISTS idx_custom_made_workspace;

    ALTER TABLE hardware_materials
      DROP COLUMN IF EXISTS unit_cost,
      DROP COLUMN IF EXISTS workspace_id;
    DROP INDEX IF EXISTS idx_hardware_materials_workspace;

    ALTER TABLE board_materials
      DROP CONSTRAINT IF EXISTS board_materials_workspace_sku_key,
      DROP COLUMN IF EXISTS unit_cost,
      DROP COLUMN IF EXISTS sku,
      DROP COLUMN IF EXISTS workspace_id;
    DROP INDEX IF EXISTS idx_board_materials_workspace;
    """)
