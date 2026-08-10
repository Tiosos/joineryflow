"""grain_locked flag on board + benchtop materials — sub-project #9 (optimiser stub)

Adds a per-material `grain_locked boolean NOT NULL DEFAULT false` to
`board_materials` and `benchtop_materials`. Read only by the CutPlan
optimiser: grain-locked parts are never rotated when packing. Low-cardinality
flag — no index.

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-15
"""
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE board_materials
      ADD COLUMN IF NOT EXISTS grain_locked boolean NOT NULL DEFAULT false;
    ALTER TABLE benchtop_materials
      ADD COLUMN IF NOT EXISTS grain_locked boolean NOT NULL DEFAULT false;
    """)


def downgrade():
    op.execute("""
    ALTER TABLE board_materials    DROP COLUMN IF EXISTS grain_locked;
    ALTER TABLE benchtop_materials DROP COLUMN IF EXISTS grain_locked;
    """)
