"""estimate revision expires_at — sub-project #9a polish

Adds a nullable `expires_at` date to `estimate_revision`. Set on sent
revisions to track the quote's validity window; nullable elsewhere.

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-15
"""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE estimate_revision
      ADD COLUMN IF NOT EXISTS expires_at date;
    """)


def downgrade():
    op.execute("""
    ALTER TABLE estimate_revision DROP COLUMN IF EXISTS expires_at;
    """)
