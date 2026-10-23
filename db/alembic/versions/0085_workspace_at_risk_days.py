"""How many days ahead a stage counts as At risk (Q591).

A stage that is not done is At risk when it falls due within this many days and an earlier stage
of the item is not done. One number per workspace, set by an admin on /it; three days until then.

Revision ID: 0085
Revises: 0084
"""
from alembic import op

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE workspace
        ADD COLUMN at_risk_days integer NOT NULL DEFAULT 3
        CONSTRAINT ck_workspace_at_risk_days CHECK (at_risk_days BETWEEN 0 AND 90);
    """)


def downgrade():
    op.execute("ALTER TABLE workspace DROP COLUMN at_risk_days;")
