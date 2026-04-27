"""drafter role

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-25
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    ALTER TABLE app_user DROP CONSTRAINT IF EXISTS app_user_auth_role_check;
    ALTER TABLE app_user ADD CONSTRAINT app_user_auth_role_check
      CHECK (auth_role IN ('admin','manager','editor','drafter','purchase_officer','viewer'));
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-PM-Workbench schema is recoverable from migrations 0001-0007 only")
