"""The PO screen's Invoice Details window, Authorisation Form details and staff photos

Built from the old system's screens (screenshots supplied by the customer):

- `payment_method`: a per-workspace list the purchase officer can add to (Account, Credit card,
  Deposit, COD / Pay on delivery to start; "John's credit card" is the kind of entry they add).
  Shared by the invoice's Payment Method and the authorisation form's Payment Type.
- `po_invoice`: payment method, Total Cost (Ex), GST (auto 10% of Ex while `gst_auto`, else typed)
  and the three file boxes (Delivery Doc, Invoice Doc, Non Delivery). `total_inc` stays as it was.
  The old free-text `delivery_doc` column is kept (data-preserving) but is no longer written.
- `po_authorisation`: one row per PO, the Authorisation Form Details window: payment type, a deposit
  % OR an amount, date required by, on behalf of, the created PDF form and the signed copy.
- `app_user.photo_file_blob_id`: the small photo shown in front of a name in the PO staff list.

Revision ID: 0063
Revises: 0062
Create Date: 2026-10-15
"""
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE payment_method (
            payment_method_id bigserial PRIMARY KEY,
            workspace_id      bigint NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
            name              varchar(100) NOT NULL,
            is_active         boolean NOT NULL DEFAULT true,
            created_at        timestamptz NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX uq_payment_method_name ON payment_method (workspace_id, lower(name));

        INSERT INTO payment_method (workspace_id, name)
        SELECT w.id, n.name
          FROM workspace w
         CROSS JOIN (VALUES ('Account'), ('Credit card'), ('Deposit'), ('COD / Pay on delivery')) AS n(name);

        ALTER TABLE po_invoice
            ADD COLUMN payment_method_id   bigint REFERENCES payment_method(payment_method_id),
            ADD COLUMN total_ex            numeric(15,2),
            ADD COLUMN gst                 numeric(15,2),
            ADD COLUMN gst_auto            boolean NOT NULL DEFAULT true,
            ADD COLUMN delivery_doc_blob   bigint REFERENCES file_blob(file_blob_id),
            ADD COLUMN invoice_doc_blob    bigint REFERENCES file_blob(file_blob_id),
            ADD COLUMN non_delivery_blob   bigint REFERENCES file_blob(file_blob_id),
            ADD COLUMN updated_at          timestamptz NOT NULL DEFAULT now();

        CREATE TABLE po_authorisation (
            po_document_id    bigint PRIMARY KEY REFERENCES po_document(po_document_id) ON DELETE CASCADE,
            payment_method_id bigint REFERENCES payment_method(payment_method_id),
            deposit_pct       numeric(5,2) CHECK (deposit_pct IS NULL OR (deposit_pct >= 0 AND deposit_pct <= 100)),
            amount_required   numeric(15,2) CHECK (amount_required IS NULL OR amount_required >= 0),
            date_required     date,
            on_behalf_of_id   bigint REFERENCES app_user(id) ON DELETE SET NULL,
            form_blob         bigint REFERENCES file_blob(file_blob_id),
            signed_blob       bigint REFERENCES file_blob(file_blob_id),
            form_created_at   timestamptz,
            updated_at        timestamptz NOT NULL DEFAULT now(),
            CHECK (deposit_pct IS NULL OR amount_required IS NULL)
        );

        ALTER TABLE app_user ADD COLUMN photo_file_blob_id bigint REFERENCES file_blob(file_blob_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE app_user DROP COLUMN photo_file_blob_id;
        DROP TABLE po_authorisation;
        ALTER TABLE po_invoice
            DROP COLUMN updated_at, DROP COLUMN non_delivery_blob, DROP COLUMN invoice_doc_blob,
            DROP COLUMN delivery_doc_blob, DROP COLUMN gst_auto, DROP COLUMN gst,
            DROP COLUMN total_ex, DROP COLUMN payment_method_id;
        DROP TABLE payment_method;
        """
    )
