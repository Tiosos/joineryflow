"""Orders: drop the in-software approval flow (0054/0055); keep one rejection note

Product-owner decision (October 2026): the software no longer runs an approval process. An order
added in the Orderbook starts `Pending`; a purchase officer (or a manager / admin) reviews it and
sets `Approved` or `Rejected` by hand, getting any sign-off from a manager or admin outside the
software. So the machinery 0054/0055 added goes:

- `purchase_orders.requires_approval`, `approval_requested_by/at`, `approval_decided_by/at`,
  `approved_total`: dropped (the audit log keeps who changed a status and when).
- `workspace_order_setting` (the per-workspace approval limit): dropped.
- `approval_note` is renamed `rejection_note`: a rejection still needs a reason, kept on the order.
  It is cleared on every order that is not `Rejected` (the old column also held "total raised"
  notes and approvers' comments, which no longer mean anything).

Nothing else changes: statuses stay as they are, and the drafter keeps no `orderbook:approve`
grant (purchase officer, manager and admin decide).

Revision ID: 0056
Revises: 0055
Create Date: 2026-10-09
"""
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE purchase_orders RENAME COLUMN approval_note TO rejection_note;
    UPDATE purchase_orders SET rejection_note = NULL WHERE status <> 'Rejected';

    ALTER TABLE purchase_orders
        DROP COLUMN IF EXISTS approved_total,
        DROP COLUMN IF EXISTS approval_decided_at,
        DROP COLUMN IF EXISTS approval_decided_by,
        DROP COLUMN IF EXISTS approval_requested_at,
        DROP COLUMN IF EXISTS approval_requested_by,
        DROP COLUMN IF EXISTS requires_approval;

    DROP TABLE IF EXISTS workspace_order_setting;
    """)


def downgrade():
    # The dropped columns come back empty: what they held is not recoverable.
    op.execute("""
    CREATE TABLE IF NOT EXISTS workspace_order_setting (
        workspace_id       bigint PRIMARY KEY REFERENCES workspace(id) ON DELETE CASCADE,
        approval_threshold numeric(12,2) NOT NULL DEFAULT 2000 CHECK (approval_threshold >= 0),
        updated_by         bigint REFERENCES app_user(id) ON DELETE SET NULL,
        updated_at         timestamptz NOT NULL DEFAULT now()
    );

    ALTER TABLE purchase_orders
        ADD COLUMN IF NOT EXISTS requires_approval boolean NOT NULL DEFAULT false,
        ADD COLUMN IF NOT EXISTS approval_requested_by bigint REFERENCES app_user(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS approval_requested_at timestamptz,
        ADD COLUMN IF NOT EXISTS approval_decided_by bigint REFERENCES app_user(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS approval_decided_at timestamptz,
        ADD COLUMN IF NOT EXISTS approved_total numeric;

    ALTER TABLE purchase_orders RENAME COLUMN rejection_note TO approval_note;
    """)
