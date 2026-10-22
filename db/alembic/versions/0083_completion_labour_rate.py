"""Retain the labour rate applied to each production completion.

Existing completions intentionally remain NULL: their historical rate is not
known and must not be guessed from today's workspace rate.

Revision ID: 0083
Revises: 0082
"""
from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE stage_completion_log
        ADD COLUMN hourly_rate_snapshot numeric(12,2)
        CHECK (hourly_rate_snapshot >= 0);
    """)


def downgrade():
    op.execute("ALTER TABLE stage_completion_log DROP COLUMN hourly_rate_snapshot")
