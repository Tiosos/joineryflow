"""cut plan + cut schedule

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-22
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    op.execute(r"""
    CREATE TABLE cut_plan (
      id            BIGSERIAL PRIMARY KEY,
      workspace_id  BIGINT NOT NULL,
      project_id    BIGINT NOT NULL,
      name          text NOT NULL,
      created_at    timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE cut_sheet (
      id            BIGSERIAL PRIMARY KEY,
      cut_plan_id   BIGINT NOT NULL REFERENCES cut_plan(id) ON DELETE CASCADE,
      sheet_no      int NOT NULL,
      material_sku  text NOT NULL,
      UNIQUE (cut_plan_id, sheet_no)
    );

    CREATE TABLE part_slot (
      id            BIGSERIAL PRIMARY KEY,
      cut_sheet_id  BIGINT NOT NULL REFERENCES cut_sheet(id) ON DELETE CASCADE,
      x             numeric(10,2) NOT NULL,
      y             numeric(10,2) NOT NULL,
      w             numeric(10,2) NOT NULL,
      h             numeric(10,2) NOT NULL,
      label         text
    );

    CREATE TABLE cut_schedule (
      id            BIGSERIAL PRIMARY KEY,
      cut_plan_id   BIGINT NOT NULL REFERENCES cut_plan(id) ON DELETE CASCADE,
      scheduled_for date,
      status        text NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned','running','done','cancelled'))
    );
    """)

def downgrade():
    op.execute("""
    DROP TABLE IF EXISTS cut_schedule, part_slot, cut_sheet, cut_plan CASCADE;
    """)
