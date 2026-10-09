"""PO approval: a flag and decision columns on purchase_orders, a per-workspace approval limit

Product-owner decisions (docs/sub-projects/06-orders-procurement.md): an order needs approval when it
is above an amount (default 2000, one value for the whole workspace, set by a purchase officer) or the
project manager flagged it. One approval is enough. Purchase officer, manager and admin approve, so the
drafter's `orderbook:approve` grant (copied from MATRIX by 0037, never checked by any order route) is
removed from the existing workspaces' drafter system groups; `permissions.MATRIX` changes with it.

- `purchase_orders.requires_approval`: the PM flag. Existing orders: false.
- `approval_requested_by/at`, `approval_decided_by/at`, `approval_note`: the single approval's trail.
  History across re-requests lives in `audit_log`.
- `workspace_order_setting.approval_threshold`: no row means the default of 2000.

Revision ID: 0054
Revises: 0053
Create Date: 2026-10-09
"""
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE purchase_orders
        ADD COLUMN IF NOT EXISTS requires_approval boolean NOT NULL DEFAULT false,
        ADD COLUMN IF NOT EXISTS approval_requested_by bigint REFERENCES app_user(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS approval_requested_at timestamptz,
        ADD COLUMN IF NOT EXISTS approval_decided_by bigint REFERENCES app_user(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS approval_decided_at timestamptz,
        ADD COLUMN IF NOT EXISTS approval_note text;

    CREATE TABLE IF NOT EXISTS workspace_order_setting (
        workspace_id       bigint PRIMARY KEY REFERENCES workspace(id) ON DELETE CASCADE,
        approval_threshold numeric(12,2) NOT NULL DEFAULT 2000 CHECK (approval_threshold >= 0),
        updated_by         bigint REFERENCES app_user(id) ON DELETE SET NULL,
        updated_at         timestamptz NOT NULL DEFAULT now()
    );

    DELETE FROM group_module_grant
     WHERE module = 'orderbook' AND action = 'approve'
       AND group_id IN (SELECT group_id FROM permission_group WHERE name = 'drafter' AND is_system);
    """)


def downgrade():
    op.execute("""
    INSERT INTO group_module_grant (group_id, module, action)
    SELECT group_id, 'orderbook', 'approve' FROM permission_group
     WHERE name = 'drafter' AND is_system
    ON CONFLICT DO NOTHING;

    DROP TABLE IF EXISTS workspace_order_setting;
    ALTER TABLE purchase_orders
        DROP COLUMN IF EXISTS approval_note,
        DROP COLUMN IF EXISTS approval_decided_at,
        DROP COLUMN IF EXISTS approval_decided_by,
        DROP COLUMN IF EXISTS approval_requested_at,
        DROP COLUMN IF EXISTS approval_requested_by,
        DROP COLUMN IF EXISTS requires_approval;
    """)
