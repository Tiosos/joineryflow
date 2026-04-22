-- ============================================================
--  Procurement Orderbook System — MySQL Schema
--  Stack: Python (FastAPI) + HTML/JS + MySQL
--  Updated: aligned with FileMaker Orderbook layout (filemaker.md)
-- ============================================================

CREATE DATABASE IF NOT EXISTS procurement_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE procurement_db;

-- ── Vendors / Suppliers ────────────────────────────────────────────────────
CREATE TABLE vendors (
    vendor_id       INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    category        ENUM('IT','Office','Logistics','Facilities','Services','Other') NOT NULL,
    contact_name    VARCHAR(255),
    contact_email   VARCHAR(255),
    contact_phone   VARCHAR(50),
    address         TEXT,
    rating          DECIMAL(3,1) DEFAULT 0.0,
    status          ENUM('Active','Inactive','Under Review','Blacklisted') DEFAULT 'Active',
    tax_id          VARCHAR(100),
    payment_terms   VARCHAR(100),
    bank_account    VARCHAR(100),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ── Cost Centers / Budget ──────────────────────────────────────────────────
CREATE TABLE cost_centers (
    cost_center_id  INT AUTO_INCREMENT PRIMARY KEY,
    code            VARCHAR(50) UNIQUE NOT NULL,
    name            VARCHAR(255) NOT NULL,
    budget_amount   DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    fiscal_year     YEAR NOT NULL,
    manager_id      INT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Users / Staff ──────────────────────────────────────────────────────────
CREATE TABLE users (
    user_id         INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    role            ENUM('Requester','Approver','Finance','Admin') DEFAULT 'Requester',
    department      VARCHAR(100),
    extension       VARCHAR(20),                          -- phone extension (FileMaker: EXT)
    cost_center_id  INT,
    approval_limit  DECIMAL(15,2) DEFAULT 0.00,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cost_center_id) REFERENCES cost_centers(cost_center_id)
);

ALTER TABLE cost_centers
    ADD CONSTRAINT fk_cc_manager FOREIGN KEY (manager_id) REFERENCES users(user_id);

-- ── Purchase Orders ────────────────────────────────────────────────────────
--   Extended with FileMaker Orderbook fields (ref: filemaker.md §2.9)
CREATE TABLE purchase_orders (
    po_id                   INT AUTO_INCREMENT PRIMARY KEY,

    -- ── Core identifiers ──────────────────────────────────────────────────
    po_number               VARCHAR(50) UNIQUE NOT NULL,
    order_number            VARCHAR(50),                  -- internal order ref (FileMaker: ORDER NUMBER)
    cutlist_no              VARCHAR(50),                  -- linked cutlist number
    supplier_ref_no         VARCHAR(100),                 -- supplier's own ref / quote number

    -- ── Relationships ─────────────────────────────────────────────────────
    vendor_id               INT NOT NULL,
    requester_id            INT NOT NULL,
    cost_center_id          INT NOT NULL,

    -- ── Classification ────────────────────────────────────────────────────
    description             TEXT NOT NULL,
    category                ENUM('IT','Office','Logistics','Facilities','Services','Other') NOT NULL,
    order_type              VARCHAR(100),                 -- e.g. CONTRACTOR-MANUFACTURING
    project_name            VARCHAR(255),                 -- project (e.g. Alfred Level 3 Fitout)
    location                VARCHAR(255),                 -- area code (e.g. lv3 JL-SB01a)

    -- ── Status & Priority ─────────────────────────────────────────────────
    status                  ENUM('Draft','Pending','Approved','Rejected','Delivered',
                                 'Cancelled','Hold','Quote','Next') DEFAULT 'Draft',
    priority                ENUM('High','Medium','Low','Next','Hold','Quote') DEFAULT 'Medium',

    -- ── Dates ─────────────────────────────────────────────────────────────
    required_date           DATE,                         -- when item is needed on site
    requested_date          DATE,                         -- date request was lodged
    requested_time          TIME,                         -- time of request
    date_ordered            DATE,                         -- date PO was placed with supplier
    due_date                DATE,                         -- expected delivery date
    arrived_date            DATE,                         -- actual date received
    delivery_date           DATE,                         -- scheduled delivery date

    -- ── Product detail ────────────────────────────────────────────────────
    product_code            VARCHAR(100),                 -- supplier SKU / product code
    product_website         VARCHAR(500),                 -- URL to supplier product page
    product_description     TEXT,                         -- supplier's catalogue description
    product_image_path      VARCHAR(1000),                -- path/URL to product image
    stock_tracked           BOOLEAN DEFAULT FALSE,        -- whether item is tracked in inventory

    -- ── Financials ────────────────────────────────────────────────────────
    quantity                DECIMAL(10,3) DEFAULT 1,      -- total quantity ordered
    unit_of_measure         VARCHAR(50),                  -- unit (units, m², m, etc.)
    unit_cost               DECIMAL(15,4),                -- cost per unit
    total_amount            DECIMAL(15,2) DEFAULT 0.00,   -- subtotal (qty × unit cost)
    gst_applicable          BOOLEAN DEFAULT TRUE,         -- GST applies to this order
    gst_included_in_price   BOOLEAN DEFAULT FALSE,        -- price is GST-inclusive
    gst_amount              DECIMAL(15,2) GENERATED ALWAYS AS (
                                CASE WHEN gst_applicable = TRUE AND gst_included_in_price = FALSE
                                     THEN ROUND(total_amount * 0.10, 2) ELSE 0.00 END
                            ) STORED,
    grand_total             DECIMAL(15,2) GENERATED ALWAYS AS (
                                total_amount + CASE WHEN gst_applicable = TRUE AND gst_included_in_price = FALSE
                                                    THEN ROUND(total_amount * 0.10, 2) ELSE 0.00 END
                            ) STORED,
    currency                CHAR(3) DEFAULT 'AUD',

    -- ── Notes & comments ──────────────────────────────────────────────────
    notes                   TEXT,
    line_item_comments      TEXT,    -- PRINTED on Purchase Order document
    internal_comments       TEXT,    -- NOT printed; internal use only
    changelog               TEXT,    -- audit trail / change history

    -- ── Metadata ──────────────────────────────────────────────────────────
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (vendor_id)       REFERENCES vendors(vendor_id),
    FOREIGN KEY (requester_id)    REFERENCES users(user_id),
    FOREIGN KEY (cost_center_id)  REFERENCES cost_centers(cost_center_id)
);

-- ── PO Line Items ──────────────────────────────────────────────────────────
CREATE TABLE po_line_items (
    line_id             INT AUTO_INCREMENT PRIMARY KEY,
    po_id               INT NOT NULL,
    line_number         INT NOT NULL,
    item_description    VARCHAR(500) NOT NULL,
    sku                 VARCHAR(100),
    quantity            DECIMAL(10,3) NOT NULL,
    unit                VARCHAR(50),
    unit_price          DECIMAL(15,4) NOT NULL,
    tax_rate            DECIMAL(5,2) DEFAULT 10.00,
    line_total          DECIMAL(15,2) GENERATED ALWAYS AS (ROUND(quantity * unit_price, 2)) STORED,
    UNIQUE KEY uq_po_line (po_id, line_number),
    FOREIGN KEY (po_id) REFERENCES purchase_orders(po_id) ON DELETE CASCADE
);

-- ── PO Attachments ─────────────────────────────────────────────────────────
--   Stores metadata for files attached via the Details pop-up (§2.9.4 Zones B & C)
CREATE TABLE po_attachments (
    attachment_id       INT AUTO_INCREMENT PRIMARY KEY,
    po_id               INT NOT NULL,
    attachment_type     ENUM('File','PDF','Image') DEFAULT 'File',
    file_name           VARCHAR(500) NOT NULL,
    file_size_bytes     INT,
    file_path           VARCHAR(1000),                    -- server-side storage path
    uploaded_by         INT,
    uploaded_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (po_id)         REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by)   REFERENCES users(user_id)
);

-- ── Approval Workflows ─────────────────────────────────────────────────────
CREATE TABLE approval_workflows (
    workflow_id     INT AUTO_INCREMENT PRIMARY KEY,
    po_id           INT NOT NULL,
    approver_id     INT NOT NULL,
    sequence_order  INT NOT NULL DEFAULT 1,
    status          ENUM('Pending','Approved','Rejected','Skipped') DEFAULT 'Pending',
    comments        TEXT,
    acted_at        TIMESTAMP NULL,
    escalated       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (po_id)         REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
    FOREIGN KEY (approver_id)   REFERENCES users(user_id)
);

-- ── Inventory ──────────────────────────────────────────────────────────────
CREATE TABLE inventory (
    item_id             INT AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    sku                 VARCHAR(100) UNIQUE NOT NULL,
    category            VARCHAR(100),
    description         TEXT,
    quantity_on_hand    DECIMAL(10,3) DEFAULT 0,
    quantity_reserved   DECIMAL(10,3) DEFAULT 0,
    reorder_point       DECIMAL(10,3) DEFAULT 0,
    reorder_quantity    DECIMAL(10,3) DEFAULT 0,
    unit                VARCHAR(50),
    unit_cost           DECIMAL(15,4),
    location            VARCHAR(100),
    last_restocked      TIMESTAMP NULL,
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ── Inventory Movements ────────────────────────────────────────────────────
CREATE TABLE inventory_movements (
    movement_id         INT AUTO_INCREMENT PRIMARY KEY,
    item_id             INT NOT NULL,
    po_id               INT,
    movement_type       ENUM('IN','OUT','ADJUSTMENT','RETURN') NOT NULL,
    quantity            DECIMAL(10,3) NOT NULL,
    unit_cost           DECIMAL(15,4),
    reference_number    VARCHAR(100),
    notes               TEXT,
    created_by          INT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id)       REFERENCES inventory(item_id),
    FOREIGN KEY (po_id)         REFERENCES purchase_orders(po_id),
    FOREIGN KEY (created_by)    REFERENCES users(user_id)
);

-- ── Budget Transactions ────────────────────────────────────────────────────
CREATE TABLE budget_transactions (
    transaction_id      INT AUTO_INCREMENT PRIMARY KEY,
    cost_center_id      INT NOT NULL,
    po_id               INT,
    amount              DECIMAL(15,2) NOT NULL,
    transaction_type    ENUM('Commitment','Expenditure','Release','Adjustment') NOT NULL,
    description         TEXT,
    transaction_date    DATE NOT NULL,
    created_by          INT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cost_center_id)    REFERENCES cost_centers(cost_center_id),
    FOREIGN KEY (po_id)             REFERENCES purchase_orders(po_id),
    FOREIGN KEY (created_by)        REFERENCES users(user_id)
);

-- ── Performance Indexes ────────────────────────────────────────────────────
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

-- ── Stored Procedure: Auto-generate PO number ─────────────────────────────
DELIMITER //
CREATE PROCEDURE generate_po_number(OUT new_po_number VARCHAR(50))
BEGIN
    DECLARE yr CHAR(4);
    DECLARE seq INT;
    SET yr = YEAR(CURDATE());
    SELECT COALESCE(MAX(CAST(SUBSTRING_INDEX(po_number, '-', -1) AS UNSIGNED)), 0) + 1
        INTO seq
        FROM purchase_orders
        WHERE YEAR(created_at) = yr;
    SET new_po_number = CONCAT('PO-', yr, '-', LPAD(seq, 4, '0'));
END //
DELIMITER ;

-- ── Trigger: Recalculate PO total on line item change ─────────────────────
DELIMITER //
CREATE TRIGGER trg_update_po_total_insert
AFTER INSERT ON po_line_items
FOR EACH ROW BEGIN
    UPDATE purchase_orders
        SET total_amount = (SELECT COALESCE(SUM(line_total), 0) FROM po_line_items WHERE po_id = NEW.po_id)
        WHERE po_id = NEW.po_id;
END //

CREATE TRIGGER trg_update_po_total_update
AFTER UPDATE ON po_line_items
FOR EACH ROW BEGIN
    UPDATE purchase_orders
        SET total_amount = (SELECT COALESCE(SUM(line_total), 0) FROM po_line_items WHERE po_id = NEW.po_id)
        WHERE po_id = NEW.po_id;
END //

CREATE TRIGGER trg_update_po_total_delete
AFTER DELETE ON po_line_items
FOR EACH ROW BEGIN
    UPDATE purchase_orders
        SET total_amount = (SELECT COALESCE(SUM(line_total), 0) FROM po_line_items WHERE po_id = OLD.po_id)
        WHERE po_id = OLD.po_id;
END //
DELIMITER ;

-- ── View: PO Summary ───────────────────────────────────────────────────────
CREATE VIEW v_po_summary AS
SELECT
    po.po_id,
    po.po_number,
    po.order_number,
    po.cutlist_no,
    po.supplier_ref_no,
    po.status,
    po.priority,
    po.category,
    po.order_type,
    po.project_name,
    po.location,
    po.description,
    po.product_code,
    po.quantity,
    po.unit_of_measure,
    po.total_amount,
    po.gst_amount,
    po.grand_total,
    po.currency,
    po.required_date,
    po.requested_date,
    po.date_ordered,
    po.due_date,
    po.arrived_date,
    po.stock_tracked,
    po.line_item_comments,
    po.created_at,
    v.vendor_id,
    v.name          AS vendor_name,
    v.rating        AS vendor_rating,
    u.user_id       AS requester_id,
    u.name          AS requester_name,
    u.extension     AS requester_ext,
    cc.cost_center_id,
    cc.name         AS cost_center,
    cc.code         AS cost_center_code
FROM purchase_orders po
JOIN vendors      v  ON po.vendor_id      = v.vendor_id
JOIN users        u  ON po.requester_id   = u.user_id
JOIN cost_centers cc ON po.cost_center_id = cc.cost_center_id;

-- ── View: Budget Utilisation ───────────────────────────────────────────────
CREATE VIEW v_budget_utilisation AS
SELECT
    cc.cost_center_id,
    cc.code,
    cc.name,
    cc.fiscal_year,
    cc.budget_amount,
    COALESCE(SUM(CASE WHEN bt.transaction_type IN ('Commitment','Expenditure') THEN bt.amount ELSE 0 END), 0)
        AS total_committed,
    cc.budget_amount - COALESCE(SUM(CASE WHEN bt.transaction_type IN ('Commitment','Expenditure') THEN bt.amount ELSE 0 END), 0)
        AS remaining,
    ROUND(
        COALESCE(SUM(CASE WHEN bt.transaction_type IN ('Commitment','Expenditure') THEN bt.amount ELSE 0 END), 0)
        / cc.budget_amount * 100, 1
    ) AS utilisation_pct
FROM cost_centers cc
LEFT JOIN budget_transactions bt ON cc.cost_center_id = bt.cost_center_id
GROUP BY cc.cost_center_id;

-- ── View: Inventory Stock Status ───────────────────────────────────────────
CREATE VIEW v_inventory_status AS
SELECT
    item_id,
    name,
    sku,
    category,
    quantity_on_hand,
    quantity_reserved,
    (quantity_on_hand - quantity_reserved) AS available_qty,
    reorder_point,
    reorder_quantity,
    unit,
    unit_cost,
    location,
    CASE
        WHEN quantity_on_hand <= 0             THEN 'Critical'
        WHEN quantity_on_hand <= reorder_point THEN 'Low'
        ELSE 'OK'
    END AS stock_level
FROM inventory
WHERE is_active = TRUE;

-- ── View: Orders Due / Overdue ─────────────────────────────────────────────
CREATE VIEW v_orders_due AS
SELECT
    po.po_id,
    po.po_number,
    po.status,
    po.priority,
    po.required_date,
    po.due_date,
    po.arrived_date,
    DATEDIFF(CURDATE(), po.required_date)   AS days_overdue,
    DATEDIFF(po.required_date, CURDATE())   AS days_until_due,
    v.name  AS vendor_name,
    u.name  AS requester_name,
    po.description,
    po.project_name
FROM purchase_orders po
JOIN vendors v ON po.vendor_id    = v.vendor_id
JOIN users   u ON po.requester_id = u.user_id
WHERE po.status NOT IN ('Delivered','Cancelled')
  AND po.required_date IS NOT NULL;
