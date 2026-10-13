"""Purchase order documents (the old system's PO screen): a PO groups orders of one supplier

Plan V1 Q505 says Create PO makes a real PO with a number, supplier, lines and status; Q553 keeps
`purchase_orders` as the *order* layer (one row per ordered item: its own requester, project,
location, cost, arrival, budget). The old PO screen groups several of those orders of one supplier
onto one document. Decision (October 2026, asked first): a **new header table over the orders**, so
the orders, their budget, decisions and filters stay exactly as they are.

- `po_document`: the PO header. Its number (`po_no`) is a plain running number from its own sequence,
  never `MAX+1` (the old screen shows 103951); the sequence starts at 100001 and is moved past the old
  system's series when the real numbers are known. `reference_no` is typed by hand, `delivery_order_id`
  points at the ordinary "Delivery Fee" order that carries the delivery charge.
- `purchase_orders.po_document_id`: the order's PO (null = on no PO). `ON DELETE SET NULL`.
- `vendor_contact`: a supplier's contacts (position, name, mobile, email) for the PO screen's list.
- `po_invoice`: invoice rows entered against the orders on a PO (the Invoice Details table).

Revision ID: 0059
Revises: 0058
Create Date: 2026-10-14
"""
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE SEQUENCE po_document_no_seq START 100001;

    CREATE TABLE po_document (
        po_document_id    BIGSERIAL PRIMARY KEY,
        workspace_id      bigint NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
        po_no             bigint NOT NULL DEFAULT nextval('po_document_no_seq'),
        vendor_id         bigint NOT NULL REFERENCES vendors(vendor_id),
        status            text NOT NULL DEFAULT 'Open' CHECK (status IN ('Open', 'Cancelled')),
        reference_no      varchar(100),
        ordered_by_id     bigint REFERENCES app_user(id) ON DELETE SET NULL,
        date_ordered      date NOT NULL DEFAULT CURRENT_DATE,
        date_required     date,
        date_due          date,
        memo              text,
        deliver_to        text,
        delivery_order_id bigint REFERENCES purchase_orders(po_id) ON DELETE SET NULL,
        created_by        bigint REFERENCES app_user(id) ON DELETE SET NULL,
        created_at        timestamptz NOT NULL DEFAULT now(),
        updated_at        timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_po_document_no UNIQUE (po_no)
    );
    CREATE INDEX idx_po_document_workspace ON po_document (workspace_id, po_document_id DESC);
    CREATE INDEX idx_po_document_vendor ON po_document (vendor_id);

    ALTER TABLE purchase_orders
        ADD COLUMN po_document_id bigint REFERENCES po_document(po_document_id) ON DELETE SET NULL;
    CREATE INDEX idx_purchase_orders_po_document ON purchase_orders (po_document_id)
        WHERE po_document_id IS NOT NULL;

    CREATE TABLE vendor_contact (
        contact_id  BIGSERIAL PRIMARY KEY,
        vendor_id   bigint NOT NULL REFERENCES vendors(vendor_id) ON DELETE CASCADE,
        position    varchar(100),
        name        varchar(255) NOT NULL,
        mobile      varchar(50),
        email       varchar(255),
        created_at  timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX idx_vendor_contact_vendor ON vendor_contact (vendor_id, contact_id);

    CREATE TABLE po_invoice (
        invoice_id     BIGSERIAL PRIMARY KEY,
        po_document_id bigint NOT NULL REFERENCES po_document(po_document_id) ON DELETE CASCADE,
        order_id       bigint NOT NULL REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
        invoice_number varchar(100) NOT NULL,
        invoiced_date  date,
        qty            numeric(10,3),
        total_inc      numeric(15,2),
        notes          text,
        delivery_doc   varchar(100),
        created_by     bigint REFERENCES app_user(id) ON DELETE SET NULL,
        created_at     timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX idx_po_invoice_document ON po_invoice (po_document_id, invoice_id);
    CREATE INDEX idx_po_invoice_order ON po_invoice (order_id);
    """)


def downgrade():
    op.execute("""
    DROP TABLE IF EXISTS po_invoice;
    DROP TABLE IF EXISTS vendor_contact;
    ALTER TABLE purchase_orders DROP COLUMN IF EXISTS po_document_id;
    DROP TABLE IF EXISTS po_document;
    DROP SEQUENCE IF EXISTS po_document_no_seq;
    """)
