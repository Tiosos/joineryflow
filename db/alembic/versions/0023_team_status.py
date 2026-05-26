"""app_user.work_status + location_label — team-status feature

Adds two nullable text columns to `app_user` so each workspace member can
publish a current working status + location. Backs the dashboard's "Team"
card (per legacy/home.html — TEAM array with st/loc fields).

work_status values follow the legacy mock: IN, ON_SITE, SHOP, WFH, OFF.
NULL = unknown / hasn't set a status yet.

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-17
"""
from alembic import op


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE app_user
      ADD COLUMN IF NOT EXISTS work_status    text,
      ADD COLUMN IF NOT EXISTS location_label text;

    ALTER TABLE app_user
      DROP CONSTRAINT IF EXISTS app_user_work_status_check;

    ALTER TABLE app_user
      ADD CONSTRAINT app_user_work_status_check
        CHECK (work_status IS NULL
               OR work_status IN ('IN', 'ON_SITE', 'SHOP', 'WFH', 'OFF'));
    """)


def downgrade():
    op.execute("""
    ALTER TABLE app_user DROP CONSTRAINT IF EXISTS app_user_work_status_check;
    ALTER TABLE app_user DROP COLUMN IF EXISTS work_status;
    ALTER TABLE app_user DROP COLUMN IF EXISTS location_label;
    """)
