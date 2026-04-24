"""procurement port

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-22
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # NOTE: The legacy procurement schema (legacy/procurement_schema.sql) also
    # defines a `users` table, but 0001 already created `users` with a
    # JoineryFlow-native shape (username/full_name/role CEO|PM|DRAFTER|...).
    # The legacy procurement `users` (email PK-style, role Requester|Approver|
    # Finance|Admin, cost_center_id, approval_limit, extension) is SKIPPED here
    # to avoid a conflicting redefinition. Procurement FK references to users
    # still resolve because both shapes use `user_id BIGSERIAL PRIMARY KEY`.
    # Fields missing from 0001 users (cost_center_id, approval_limit,
    # extension, department) can be added in a later migration if procurement
    # needs them.
    #
    # Views (v_po_summary, v_budget_utilisation, v_inventory_status,
    # v_orders_due), the generate_po_number stored procedure, and the
    # po_line_items triggers are NOT ported here. Views will be rebuilt later
    # as Postgres views once app-layer shape is final; PO numbering and total
    # recomputation will live in the application (consistent with the 0001
    # decision to drop ON UPDATE CURRENT_TIMESTAMP in favor of app-layer).
    op.execute(r"""
    -- Vendors / Suppliers
    CREATE TABLE vendors (
        vendor_id       BIGSERIAL PRIMARY KEY,
        name            varchar(255) NOT NULL,
        category        text NOT NULL
                        CHECK (category IN ('IT','Office','Logistics','Facilities','Services','Other')),
        contact_name    varchar(255),
        contact_email   citext,
        contact_phone   varchar(50),
        address         text,
        rating          numeric(3,1) DEFAULT 0.0,
        status          text DEFAULT 'Active'
                        CHECK (status IN ('Active','Inactive','Under Review','Blacklisted')),
        tax_id          varchar(100),
        payment_terms   varchar(100),
        bank_account    varchar(100),
        created_at      timestamptz DEFAULT now(),
        updated_at      timestamptz DEFAULT now()
    );

    -- Cost Centers / Budget
    CREATE TABLE cost_centers (
        cost_center_id  BIGSERIAL PRIMARY KEY,
        code            varchar(50) UNIQUE NOT NULL,
        name            varchar(255) NOT NULL,
        budget_amount   numeric(15,2) NOT NULL DEFAULT 0.00,
        fiscal_year     smallint NOT NULL,
        manager_id      bigint REFERENCES users(user_id),
        is_active       boolean DEFAULT TRUE,
        created_at      timestamptz DEFAULT now()
    );

    -- Purchase Orders (aligned with FileMaker Orderbook layout, filemaker.md sec 2.9)
    CREATE TABLE purchase_orders (
        po_id                   BIGSERIAL PRIMARY KEY,

        po_number               varchar(50) UNIQUE NOT NULL,
        order_number            varchar(50),
        cutlist_no              varchar(50),
        supplier_ref_no         varchar(100),

        vendor_id               bigint NOT NULL REFERENCES vendors(vendor_id),
        requester_id            bigint NOT NULL REFERENCES users(user_id),
        cost_center_id          bigint NOT NULL REFERENCES cost_centers(cost_center_id),

        description             text NOT NULL,
        category                text NOT NULL
                                CHECK (category IN ('IT','Office','Logistics','Facilities','Services','Other')),
        order_type              varchar(100),
        project_name            varchar(255),
        location                varchar(255),

        status                  text DEFAULT 'Draft'
                                CHECK (status IN ('Draft','Pending','Approved','Rejected','Delivered',
                                                  'Cancelled','Hold','Quote','Next')),
        priority                text DEFAULT 'Medium'
                                CHECK (priority IN ('High','Medium','Low','Next','Hold','Quote')),

        required_date           date,
        requested_date          date,
        requested_time          time,
        date_ordered            date,
        due_date                date,
        arrived_date            date,
        delivery_date           date,

        product_code            varchar(100),
        product_website         varchar(500),
        product_description     text,
        product_image_path      varchar(1000),
        stock_tracked           boolean DEFAULT FALSE,

        quantity                numeric(10,3) DEFAULT 1,
        unit_of_measure         varchar(50),
        unit_cost               numeric(15,4),
        total_amount            numeric(15,2) DEFAULT 0.00,
        gst_applicable          boolean DEFAULT TRUE,
        gst_included_in_price   boolean DEFAULT FALSE,
        gst_amount              numeric(15,2) GENERATED ALWAYS AS (
                                    CASE WHEN gst_applicable = TRUE AND gst_included_in_price = FALSE
                                         THEN ROUND(total_amount * 0.10, 2) ELSE 0.00 END
                                ) STORED,
        grand_total             numeric(15,2) GENERATED ALWAYS AS (
                                    total_amount + CASE WHEN gst_applicable = TRUE AND gst_included_in_price = FALSE
                                                        THEN ROUND(total_amount * 0.10, 2) ELSE 0.00 END
                                ) STORED,
        currency                char(3) DEFAULT 'AUD',

        notes                   text,
        line_item_comments      text,
        internal_comments       text,
        changelog               text,

        created_at              timestamptz DEFAULT now(),
        updated_at              timestamptz DEFAULT now()
    );

    -- PO Line Items
    CREATE TABLE po_line_items (
        line_id             BIGSERIAL PRIMARY KEY,
        po_id               bigint NOT NULL REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
        line_number         integer NOT NULL,
        item_description    varchar(500) NOT NULL,
        sku                 varchar(100),
        quantity            numeric(10,3) NOT NULL,
        unit                varchar(50),
        unit_price          numeric(15,4) NOT NULL,
        tax_rate            numeric(5,2) DEFAULT 10.00,
        line_total          numeric(15,2) GENERATED ALWAYS AS (ROUND(quantity * unit_price, 2)) STORED,
        UNIQUE (po_id, line_number)
    );

    -- PO Attachments
    CREATE TABLE po_attachments (
        attachment_id       BIGSERIAL PRIMARY KEY,
        po_id               bigint NOT NULL REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
        attachment_type     text DEFAULT 'File'
                            CHECK (attachment_type IN ('File','PDF','Image')),
        file_name           varchar(500) NOT NULL,
        file_size_bytes     bigint,
        file_path           varchar(1000),
        uploaded_by         bigint REFERENCES users(user_id),
        uploaded_at         timestamptz DEFAULT now()
    );

    -- Approval Workflows
    CREATE TABLE approval_workflows (
        workflow_id     BIGSERIAL PRIMARY KEY,
        po_id           bigint NOT NULL REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
        approver_id     bigint NOT NULL REFERENCES users(user_id),
        sequence_order  integer NOT NULL DEFAULT 1,
        status          text DEFAULT 'Pending'
                        CHECK (status IN ('Pending','Approved','Rejected','Skipped')),
        comments        text,
        acted_at        timestamptz,
        escalated       boolean DEFAULT FALSE,
        created_at      timestamptz DEFAULT now()
    );

    -- Inventory
    CREATE TABLE inventory (
        item_id             BIGSERIAL PRIMARY KEY,
        name                varchar(255) NOT NULL,
        sku                 varchar(100) UNIQUE NOT NULL,
        category            varchar(100),
        description         text,
        quantity_on_hand    numeric(10,3) DEFAULT 0,
        quantity_reserved   numeric(10,3) DEFAULT 0,
        reorder_point       numeric(10,3) DEFAULT 0,
        reorder_quantity    numeric(10,3) DEFAULT 0,
        unit                varchar(50),
        unit_cost           numeric(15,4),
        location            varchar(100),
        last_restocked      timestamptz,
        is_active           boolean DEFAULT TRUE,
        created_at          timestamptz DEFAULT now(),
        updated_at          timestamptz DEFAULT now()
    );

    -- Inventory Movements
    CREATE TABLE inventory_movements (
        movement_id         BIGSERIAL PRIMARY KEY,
        item_id             bigint NOT NULL REFERENCES inventory(item_id),
        po_id               bigint REFERENCES purchase_orders(po_id),
        movement_type       text NOT NULL
                            CHECK (movement_type IN ('IN','OUT','ADJUSTMENT','RETURN')),
        quantity            numeric(10,3) NOT NULL,
        unit_cost           numeric(15,4),
        reference_number    varchar(100),
        notes               text,
        created_by          bigint REFERENCES users(user_id),
        created_at          timestamptz DEFAULT now()
    );

    -- Budget Transactions
    CREATE TABLE budget_transactions (
        transaction_id      BIGSERIAL PRIMARY KEY,
        cost_center_id      bigint NOT NULL REFERENCES cost_centers(cost_center_id),
        po_id               bigint REFERENCES purchase_orders(po_id),
        amount              numeric(15,2) NOT NULL,
        transaction_type    text NOT NULL
                            CHECK (transaction_type IN ('Commitment','Expenditure','Release','Adjustment')),
        description         text,
        transaction_date    date NOT NULL,
        created_by          bigint REFERENCES users(user_id),
        created_at          timestamptz DEFAULT now()
    );

    -- Performance Indexes
    CREATE INDEX idx_po_status          ON purchase_orders(status);
    CREATE INDEX idx_po_priority        ON purchase_orders(priority);
    CREATE INDEX idx_po_vendor          ON purchase_orders(vendor_id);
    CREATE INDEX idx_po_requester       ON purchase_orders(requester_id);
    CREATE INDEX idx_po_cost_center     ON purchase_orders(cost_center_id);
    CREATE INDEX idx_po_required_date   ON purchase_orders(required_date);
    CREATE INDEX idx_po_cutlist         ON purchase_orders(cutlist_no);
    CREATE INDEX idx_po_project         ON purchase_orders(project_name);
    CREATE INDEX idx_po_created         ON purchase_orders(created_at DESC);
    CREATE INDEX idx_workflow_po        ON approval_workflows(po_id);
    CREATE INDEX idx_workflow_appr      ON approval_workflows(approver_id, status);
    CREATE INDEX idx_inv_sku            ON inventory(sku);
    CREATE INDEX idx_invmov_item        ON inventory_movements(item_id);
    CREATE INDEX idx_budget_cc          ON budget_transactions(cost_center_id, transaction_date);
    CREATE INDEX idx_attach_po          ON po_attachments(po_id);
    """)


def downgrade():
    op.execute("-- intentionally no granular down; see 0001")
