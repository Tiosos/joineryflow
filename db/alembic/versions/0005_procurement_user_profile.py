"""procurement user profile

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-25

Side-table that attaches procurement-specific attributes to an app_user
without bloating the main `app_user` shape. Created in response to the T10
Foundation concern: the legacy procurement schema's `users` table had
cost_center_id, approval_limit, extension, and department, which the
JoineryFlow `app_user` table does not carry.

A row here is OPTIONAL - only users who actually participate in procurement
(typically auth_role=purchase_officer or admin) need one. View v_po_summary
(migration 0006) LEFT JOINs this table to surface `requester_ext`.
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    CREATE TABLE procurement_user_profile (
      user_id        BIGINT PRIMARY KEY
                       REFERENCES app_user(id) ON DELETE CASCADE,
      cost_center_id BIGINT
                       REFERENCES cost_centers(cost_center_id) ON DELETE SET NULL,
      approval_limit numeric(12,2),
      extension      varchar(20),
      department     varchar(100),
      created_at     timestamptz NOT NULL DEFAULT now()
    );

    CREATE INDEX procurement_user_profile_cc_idx
      ON procurement_user_profile(cost_center_id);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS procurement_user_profile CASCADE;")
