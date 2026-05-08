"""cut_floor — CutPlan / CutSchedule enrichment for sub-project #7c

Adds:
  - part_slot.part_id FK -> parts(part_id) ON DELETE SET NULL
  - cut_schedule.priority, assigned_to, created_at, created_by, updated_at
  - cut_plan.created_by, cut_plan.notes
  - idx_part_slot_part, idx_cut_schedule_date_priority

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-08
"""
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    -- 1. part_slot.part_id (nullable; v1 had no real cut plans)
    ALTER TABLE part_slot
      ADD COLUMN part_id bigint REFERENCES parts(part_id) ON DELETE SET NULL;
    CREATE INDEX idx_part_slot_part ON part_slot (part_id);

    -- 2. cut_schedule enrichment
    ALTER TABLE cut_schedule
      ADD COLUMN priority    int    NOT NULL DEFAULT 0,
      ADD COLUMN assigned_to bigint REFERENCES app_user(id) ON DELETE SET NULL,
      ADD COLUMN created_at  timestamptz NOT NULL DEFAULT now(),
      ADD COLUMN created_by  bigint REFERENCES app_user(id),
      ADD COLUMN updated_at  timestamptz NOT NULL DEFAULT now();
    CREATE INDEX idx_cut_schedule_date_priority
      ON cut_schedule (scheduled_for, priority);

    -- 3. cut_plan metadata
    ALTER TABLE cut_plan
      ADD COLUMN created_by bigint REFERENCES app_user(id),
      ADD COLUMN notes      text;
    """)


def downgrade():
    op.execute("-- intentionally not reversible; recover via 0001-0018 only")
