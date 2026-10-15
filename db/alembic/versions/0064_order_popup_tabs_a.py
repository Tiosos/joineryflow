"""The order pop-up's tabs, part 1: ADMIN, Delivery log, Supplier details, Product image

Built from the old Orderbook's Details window (screenshots supplied by the customer):

- ADMIN: `purchase_orders.cancelled_at / cancelled_by / cancel_reason`, set when an order becomes Cancelled
  (cleared when it leaves Cancelled). Orders cancelled before this are filled from the audit log: the latest
  `order.cancel` / `order.update` of that order, which is the change that cancelled it unless someone edited
  a cancelled order's status afterwards.
- Delivery log: `order_delivery`, one row per delivery received (qty, date, signed by, notes, the docket),
  and `purchase_orders.received_by` (the final "Received by"; the final date is the existing `arrived_date`).
- Supplier tab: `vendors.logo_blob / website / notes / metadata` (the old screen's company card).
- Product image: `purchase_orders.image_blob`, one picture per order in the shared file store.

Revision ID: 0064
Revises: 0063
Create Date: 2026-10-15
"""
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE purchase_orders
            ADD COLUMN cancelled_at  timestamptz,
            ADD COLUMN cancelled_by  bigint REFERENCES app_user(id) ON DELETE SET NULL,
            ADD COLUMN cancel_reason text,
            ADD COLUMN received_by   varchar(100),
            ADD COLUMN image_blob    bigint REFERENCES file_blob(file_blob_id);

        UPDATE purchase_orders po
           SET cancelled_at = a.created_at, cancelled_by = a.actor_id
          FROM (SELECT DISTINCT ON (target) target, created_at, actor_id
                  FROM audit_log WHERE event IN ('order.cancel', 'order.update')
                 ORDER BY target, created_at DESC) a
         WHERE po.status = 'Cancelled' AND a.target = po.po_id::text;

        CREATE TABLE order_delivery (
            delivery_id   bigserial PRIMARY KEY,
            po_id         bigint NOT NULL REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
            qty           numeric(10,3) NOT NULL CHECK (qty > 0),
            date_received date NOT NULL,
            signed_by     varchar(100),
            notes         text,
            docket_blob   bigint REFERENCES file_blob(file_blob_id),
            created_by    bigint REFERENCES app_user(id) ON DELETE SET NULL,
            created_at    timestamptz NOT NULL DEFAULT now(),
            updated_at    timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_order_delivery_po ON order_delivery (po_id, delivery_id);

        ALTER TABLE vendors
            ADD COLUMN logo_blob bigint REFERENCES file_blob(file_blob_id),
            ADD COLUMN website   varchar(500),
            ADD COLUMN notes     text,
            ADD COLUMN metadata  text;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE vendors DROP COLUMN metadata, DROP COLUMN notes, DROP COLUMN website, DROP COLUMN logo_blob;
        DROP TABLE order_delivery;
        ALTER TABLE purchase_orders
            DROP COLUMN image_blob, DROP COLUMN received_by, DROP COLUMN cancel_reason,
            DROP COLUMN cancelled_by, DROP COLUMN cancelled_at;
        """
    )
