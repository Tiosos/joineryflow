-- ============================================================
--  Trendgosa Production System — v2 Schema
--  Backing store for the v1 build described in trackingv2.md
--  + product_spec.md §5.
--
--  Supersedes tracking_schema.sql. Adds:
--   • 6 Material Catalog tables (board / hardware / custom_made /
--     benchtop / appliances / equipment_hire)
--   • Project Hardware Catalog + audit log
--   • Item → Module → Part hierarchy (CV import target)
--   • item_hardware_lines (Drafter's per-item hardware picks)
--   • procurement_batches + batch_allocations
--   • projects.optimisation_drafter_id (FK → users)
--   • parts.edging_spec + parts.paint_instruction
--     (fields missing from CV export, filled in by Drafter)
--
--  Stack: Python (FastAPI) + HTML/JS + MySQL
-- ============================================================

CREATE DATABASE IF NOT EXISTS tracking_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE tracking_db;

-- Drop child-first for re-apply
DROP TABLE IF EXISTS batch_allocations;
DROP TABLE IF EXISTS procurement_batches;
DROP TABLE IF EXISTS item_hardware_lines;
DROP TABLE IF EXISTS parts;
DROP TABLE IF EXISTS modules;
DROP TABLE IF EXISTS project_hardware_catalog_log;
DROP TABLE IF EXISTS project_hardware_catalog;
DROP TABLE IF EXISTS equipment_hire;
DROP TABLE IF EXISTS appliances;
DROP TABLE IF EXISTS benchtop_materials;
DROP TABLE IF EXISTS custom_made;
DROP TABLE IF EXISTS hardware_materials;
DROP TABLE IF EXISTS board_materials;
DROP TABLE IF EXISTS item_edit_log;
DROP TABLE IF EXISTS item_status_log;
DROP TABLE IF EXISTS item_stages;
DROP TABLE IF EXISTS project_favourites;
DROP TABLE IF EXISTS items;
DROP TABLE IF EXISTS stages;
DROP TABLE IF EXISTS status_symbols;
DROP TABLE IF EXISTS status_options;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS users;

-- ── Users ──────────────────────────────────────────────────────────────────
CREATE TABLE users (
    user_id       INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(64)  UNIQUE NOT NULL,   -- e.g. 'DAVIDM'
    full_name     VARCHAR(255),
    email         VARCHAR(255),
    role          ENUM('CEO','PM','DRAFTER','FOREMAN','MACHINE','PROCUREMENT') DEFAULT 'DRAFTER',
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Projects ───────────────────────────────────────────────────────────────
CREATE TABLE projects (
    project_id              INT AUTO_INCREMENT PRIMARY KEY,
    name                    VARCHAR(255) UNIQUE NOT NULL,
    project_code            VARCHAR(32)  NOT NULL,
    carell_pid              VARCHAR(32),
    builder                 VARCHAR(128),
    classification          VARCHAR(128),
    site_street             VARCHAR(255),
    site_suburb             VARCHAR(128),
    site_postcode           VARCHAR(16),
    site_state              VARCHAR(8),
    tg_project_manager      VARCHAR(128),
    tg_coordinator          VARCHAR(128),
    status                  ENUM('Current','Closed','Hold') DEFAULT 'Current',
    installation_start      DATE,
    total_value             DECIMAL(15,2),
    total_line_items        INT,
    tg_solid                BOOLEAN DEFAULT FALSE,
    -- Optimisation Drafter: one Drafter per project runs board optimisation
    -- (trackingv2.md §11, resolved). Editable by PM.
    optimisation_drafter_id INT DEFAULT NULL,
    created_by              VARCHAR(64),
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (optimisation_drafter_id) REFERENCES users(user_id)
);

-- User → Project favourites (★ toggle in project dropdown)
CREATE TABLE project_favourites (
    user_id     INT NOT NULL,
    project_id  INT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, project_id),
    FOREIGN KEY (user_id)    REFERENCES users(user_id)    ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

-- ── Lookup: Stages (10 lifecycle columns) ──────────────────────────────────
CREATE TABLE stages (
    stage_key    VARCHAR(16)  PRIMARY KEY,
    label        VARCHAR(32)  NOT NULL,
    sort_order   TINYINT      NOT NULL
);

-- ── Lookup: Status options (STATUS column) ─────────────────────────────────
CREATE TABLE status_options (
    status_key   VARCHAR(16) PRIMARY KEY,
    sort_order   TINYINT     NOT NULL
);

-- ── Lookup: Status symbols (sym-col, DATE sub-panel) ───────────────────────
CREATE TABLE status_symbols (
    symbol_key   VARCHAR(16) PRIMARY KEY,
    glyph        VARCHAR(8)  NOT NULL,
    colour       VARCHAR(16) NOT NULL,
    label        VARCHAR(64) NOT NULL,
    sort_order   TINYINT     NOT NULL
);

-- ============================================================
--  Material Catalog — SIX tables (product_spec.md §5.2)
--  Kept separate because lifecycles differ fundamentally.
--  Shared abstract shape: (id, description, supplier, cost_unit,
--  lead_time_days, notes). Discriminator is the table itself.
-- ============================================================

-- ── Board materials (sheet stock, company-internal codes) ──────────────────
CREATE TABLE board_materials (
    material_id      INT AUTO_INCREMENT PRIMARY KEY,
    code             VARCHAR(64) UNIQUE NOT NULL,   -- '18-PB', '32-MDF', '19-A/WALNUT/BAM X'
    description      VARCHAR(255),
    thickness_mm     DECIMAL(6,2),
    sheet_len_mm     INT,
    sheet_wid_mm     INT,
    supplier         VARCHAR(128),
    cost_per_sheet   DECIMAL(12,2),
    lead_time_days   INT DEFAULT 0,
    notes            TEXT,
    is_active        BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ── Hardware materials (per-piece supplier SKUs) ───────────────────────────
CREATE TABLE hardware_materials (
    material_id      INT AUTO_INCREMENT PRIMARY KEY,
    sku              VARCHAR(64) UNIQUE NOT NULL,   -- '700.0KC2.054.00'
    description      VARCHAR(255),
    hardware_type    VARCHAR(64),                   -- 'hinge' | 'runner' | 'handle' | ...
    supplier         VARCHAR(128),
    brand            VARCHAR(128),
    cost_per_unit    DECIMAL(12,2),
    lead_time_days   INT DEFAULT 0,
    notes            TEXT,
    is_active        BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ── Custom-made (bespoke items commissioned from external fabricators) ─────
CREATE TABLE custom_made (
    material_id      INT AUTO_INCREMENT PRIMARY KEY,
    internal_ref     VARCHAR(64) UNIQUE NOT NULL,
    description      VARCHAR(255),
    vendor           VARCHAR(128),
    vendor_quote_ref VARCHAR(64),
    cost             DECIMAL(12,2),
    lead_time_days   INT DEFAULT 0,
    notes            TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ── Benchtop materials (stone slabs, solid-surface sheets) ─────────────────
CREATE TABLE benchtop_materials (
    material_id      INT AUTO_INCREMENT PRIMARY KEY,
    slab_id          VARCHAR(64) UNIQUE NOT NULL,   -- slab / lot number
    description      VARCHAR(255),
    material_type    VARCHAR(64),                   -- 'stone' | 'solid-surface'
    thickness_mm     DECIMAL(6,2),
    slab_len_mm      INT,
    slab_wid_mm      INT,
    supplier         VARCHAR(128),
    cost_per_slab    DECIMAL(12,2),
    lead_time_days   INT DEFAULT 0,
    notes            TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ── Appliances (integrated ovens, fridges, dishwashers) ────────────────────
CREATE TABLE appliances (
    material_id      INT AUTO_INCREMENT PRIMARY KEY,
    model_number     VARCHAR(64) UNIQUE NOT NULL,
    description      VARCHAR(255),
    manufacturer     VARCHAR(128),
    supplier         VARCHAR(128),
    cost_per_unit    DECIMAL(12,2),
    lead_time_days   INT DEFAULT 0,
    notes            TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ── Equipment hire ─────────────────────────────────────────────────────────
-- Resolved: one contract = one project (product_spec.md §7, resolved).
-- `project_id` is a single FK, no allocation join table.
CREATE TABLE equipment_hire (
    hire_id          INT AUTO_INCREMENT PRIMARY KEY,
    contract_ref     VARCHAR(64) UNIQUE NOT NULL,
    project_id       INT NOT NULL,
    description      VARCHAR(255),
    supplier         VARCHAR(128),
    rate             DECIMAL(12,2),
    rate_unit        ENUM('HOUR','DAY','WEEK','MONTH') DEFAULT 'DAY',
    hire_start       DATE,
    hire_end         DATE,
    total_cost       DECIMAL(12,2),
    notes            TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    INDEX idx_hire_project (project_id)
);

-- ============================================================
--  Project Hardware Catalog (product_spec.md §5.3)
--  Project-scoped approved materials list. Item hardware lines
--  reference a material *via* this table, not directly to globals.
--
--  Governance (resolved, product_spec.md §7): log-only, no approval
--  step. Every add/remove writes to project_hardware_catalog_log.
-- ============================================================
CREATE TABLE project_hardware_catalog (
    catalog_id     INT AUTO_INCREMENT PRIMARY KEY,
    project_id     INT NOT NULL,
    -- Material discriminator: which of the 6 catalogs the row points to.
    material_type  ENUM('BOARD','HARDWARE','CUSTOM','BENCHTOP','APPLIANCE','HIRE') NOT NULL,
    material_id    INT NOT NULL,
    added_by       INT NOT NULL,
    added_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active      BOOLEAN DEFAULT TRUE,
    notes          TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (added_by)   REFERENCES users(user_id),
    UNIQUE KEY uq_proj_mat (project_id, material_type, material_id),
    INDEX idx_phc_project (project_id)
);

-- Audit log: every add / remove / reactivate
CREATE TABLE project_hardware_catalog_log (
    log_id        INT AUTO_INCREMENT PRIMARY KEY,
    project_id    INT NOT NULL,
    material_type ENUM('BOARD','HARDWARE','CUSTOM','BENCHTOP','APPLIANCE','HIRE') NOT NULL,
    material_id   INT NOT NULL,
    action        ENUM('ADD','REMOVE','REACTIVATE') NOT NULL,
    changed_by    INT NOT NULL,
    changed_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    note          TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (changed_by) REFERENCES users(user_id),
    INDEX idx_phc_log_project (project_id, changed_at DESC)
);

-- ============================================================
--  Items (one row per manufactured cabinet / bench)
-- ============================================================
CREATE TABLE items (
    item_id              INT AUTO_INCREMENT PRIMARY KEY,
    num                  INT UNIQUE NOT NULL,              -- Cutlist #
    project_id           INT NOT NULL,
    stage                VARCHAR(64),                      -- site block
    zone                 VARCHAR(16),
    level                VARCHAR(16),
    rm_no                VARCHAR(16),
    rm_desc              VARCHAR(128),
    code                 VARCHAR(64),
    description          VARCHAR(255),
    size                 INT,
    qty                  INT,
    assembler            VARCHAR(128),
    lister               VARCHAR(128),

    -- Display / external IDs
    item_code            VARCHAR(32),
    group_id             VARCHAR(32),

    -- Item Details modal fields
    floor_plan           VARCHAR(64),
    rls                  VARCHAR(64),
    joiery_details       VARCHAR(64),
    painting_req         BOOLEAN DEFAULT FALSE,
    solid_surface_req    BOOLEAN DEFAULT FALSE,
    cutlist_printed      BOOLEAN DEFAULT TRUE,
    sketchup_file        VARCHAR(255),
    cab_vision_file      VARCHAR(255),
    estimator_notes      TEXT,

    -- Item-Editor ownership: Drafter who created the cutlist has edit rights
    cutlist_owner_id     INT DEFAULT NULL,
    item_locked          BOOLEAN DEFAULT FALSE,

    -- STATUS column
    status               VARCHAR(16) DEFAULT 'CLEAR',

    -- Status-symbol column
    status_symbol        VARCHAR(16) DEFAULT NULL,

    -- Row state flags
    omitted              BOOLEAN DEFAULT FALSE,
    fav                  BOOLEAN DEFAULT FALSE,
    deleted              BOOLEAN DEFAULT FALSE,
    void_flag            BOOLEAN DEFAULT FALSE,

    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (project_id)       REFERENCES projects(project_id),
    FOREIGN KEY (status)           REFERENCES status_options(status_key),
    FOREIGN KEY (status_symbol)    REFERENCES status_symbols(symbol_key),
    FOREIGN KEY (cutlist_owner_id) REFERENCES users(user_id),
    INDEX idx_items_project (project_id),
    INDEX idx_items_status  (status),
    INDEX idx_items_symbol  (status_symbol)
);

-- ── Item × Stage pivot (per-stage due / done dates) ────────────────────────
CREATE TABLE item_stages (
    item_id      INT         NOT NULL,
    stage_key    VARCHAR(16) NOT NULL,
    due_date     DATE        DEFAULT NULL,
    done_date    DATE        DEFAULT NULL,
    PRIMARY KEY (item_id, stage_key),
    FOREIGN KEY (item_id)   REFERENCES items(item_id)    ON DELETE CASCADE,
    FOREIGN KEY (stage_key) REFERENCES stages(stage_key)
);

-- ── Per-item status history (statusLog) ────────────────────────────────────
CREATE TABLE item_status_log (
    log_id       INT AUTO_INCREMENT PRIMARY KEY,
    item_id      INT         NOT NULL,
    status       VARCHAR(16) NOT NULL,
    note         TEXT        NOT NULL,
    changed_by   VARCHAR(64) NOT NULL,
    changed_at   TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
    FOREIGN KEY (status)  REFERENCES status_options(status_key),
    INDEX idx_status_log_item (item_id, changed_at DESC)
);

-- ── Per-item edit history (editLog) ────────────────────────────────────────
CREATE TABLE item_edit_log (
    log_id       INT AUTO_INCREMENT PRIMARY KEY,
    item_id      INT         NOT NULL,
    field_label  VARCHAR(64) NOT NULL,
    old_value    VARCHAR(255),
    new_value    VARCHAR(255),
    changed_by   VARCHAR(64) NOT NULL,
    changed_at   TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
    INDEX idx_edit_log_item (item_id, changed_at DESC)
);

-- ============================================================
--  Item → Module → Part hierarchy (product_spec.md §5.1)
--  Populated by CV import in v2; manually editable in v1.
-- ============================================================
CREATE TABLE modules (
    module_id     INT AUTO_INCREMENT PRIMARY KEY,
    item_id       INT NOT NULL,
    module_no     VARCHAR(16) NOT NULL,        -- 'MOD 1', 'MOD 2', ... from CV
    name          VARCHAR(255),
    notes         TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
    UNIQUE KEY uq_item_mod (item_id, module_no),
    INDEX idx_modules_item (item_id)
);

CREATE TABLE parts (
    part_id             INT AUTO_INCREMENT PRIMARY KEY,
    module_id           INT NOT NULL,
    seq                 INT,                          -- order within module
    qty                 INT NOT NULL DEFAULT 1,
    part_name           VARCHAR(128),
    len_mm              INT,
    wid_mm              INT,
    board_material_id   INT,                          -- FK → board_materials (nullable for non-board parts)
    edge                VARCHAR(64),
    colour              VARCHAR(64),
    -- Fields missing from CV export (resolved, product_spec.md §7):
    -- Drafter fills these manually post-import.
    edging_spec         VARCHAR(64),                  -- 'ABS 1mm', 'PVC 2mm', 'veneer', ...
    paint_instruction   ENUM('NONE','DOUBLE_SIDE','SINGLE_SIDE','EDGE_ONLY') DEFAULT 'NONE',
    comment             TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (module_id)         REFERENCES modules(module_id)           ON DELETE CASCADE,
    FOREIGN KEY (board_material_id) REFERENCES board_materials(material_id),
    INDEX idx_parts_module (module_id)
);

-- ============================================================
--  Item hardware lines (Drafter's Hardware List, trackingv2.md §5.3)
--  Resolves material via project_hardware_catalog.
-- ============================================================
CREATE TABLE item_hardware_lines (
    line_id            INT AUTO_INCREMENT PRIMARY KEY,
    item_id            INT NOT NULL,
    seq                INT,
    qty                INT NOT NULL DEFAULT 1,
    catalog_id         INT NOT NULL,          -- FK → project_hardware_catalog
    note               TEXT,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id)    REFERENCES items(item_id)                     ON DELETE CASCADE,
    FOREIGN KEY (catalog_id) REFERENCES project_hardware_catalog(catalog_id),
    INDEX idx_ihl_item (item_id),
    INDEX idx_ihl_catalog (catalog_id)
);

-- ============================================================
--  Procurement (product_spec.md §5.4)
-- ============================================================
CREATE TABLE procurement_batches (
    batch_id         INT AUTO_INCREMENT PRIMARY KEY,
    project_id       INT NOT NULL,
    material_type    ENUM('BOARD','HARDWARE','CUSTOM','BENCHTOP','APPLIANCE','HIRE') NOT NULL,
    material_id      INT NOT NULL,
    supplier         VARCHAR(128),
    po_ref           VARCHAR(64),
    qty_ordered      DECIMAL(12,2) NOT NULL DEFAULT 0,
    qty_received     DECIMAL(12,2) NOT NULL DEFAULT 0,
    cost_per_unit    DECIMAL(12,2),
    ordered_date     DATE,
    eta_date         DATE,
    received_date    DATE,
    notes            TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    INDEX idx_batch_project (project_id),
    INDEX idx_batch_material (material_type, material_id),
    INDEX idx_batch_eta (eta_date)
);

CREATE TABLE batch_allocations (
    allocation_id        INT AUTO_INCREMENT PRIMARY KEY,
    batch_id             INT NOT NULL,
    item_hardware_line_id INT NOT NULL,
    qty_allocated        DECIMAL(12,2) NOT NULL DEFAULT 0,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (batch_id)              REFERENCES procurement_batches(batch_id)     ON DELETE CASCADE,
    FOREIGN KEY (item_hardware_line_id) REFERENCES item_hardware_lines(line_id)      ON DELETE CASCADE,
    UNIQUE KEY uq_batch_line (batch_id, item_hardware_line_id),
    INDEX idx_alloc_line (item_hardware_line_id)
);

-- ============================================================
--  Seed data (mirrors tracking_schema.sql seed)
-- ============================================================

INSERT INTO users (username, full_name, role) VALUES
  ('DAVIDM', 'David M', 'DRAFTER');

INSERT INTO projects (name, project_code, carell_pid, builder, classification, status) VALUES
  ('Alfred Level 3 Fitout', '2273', '808', 'arete', 'Major Project', 'Current'),
  ('The Trentham',          '2301', '812', NULL,    NULL,            'Current'),
  ('7ss Flinder West',      '2318', '825', NULL,    NULL,            'Current');

INSERT INTO project_favourites (user_id, project_id)
SELECT u.user_id, p.project_id FROM users u, projects p
WHERE u.username = 'DAVIDM' AND p.name = 'Alfred Level 3 Fitout';

INSERT INTO stages (stage_key, label, sort_order) VALUES
  ('REQ','REQ',1),('SM','SM',2),('LISTED','LISTED',3),('DOWN','DOWN',4),
  ('CNC','CNC',5),('EDGED','EDGED',6),('PAINTED','PAINTED',7),('MADE','MADE',8),
  ('DEL','DEL',9),('INST','INST',10);

INSERT INTO status_options (status_key, sort_order) VALUES
  ('CLEAR',1),('VOID',2),('NOTE!',3),('LIVE',4),('APPROVED',5),('HOLD',6);

INSERT INTO status_symbols (symbol_key, glyph, colour, label, sort_order) VALUES
  ('question','?','red',   'Query',   1),
  ('warning', '!','yellow','Warning', 2),
  ('ok',      '✓','green', 'OK',      3),
  ('blocked', '⊘','black', 'Blocked', 4);

-- Items (12 rows under Alfred Level 3 Fitout)
SET @pid := (SELECT project_id FROM projects WHERE name = 'Alfred Level 3 Fitout');

INSERT INTO items (num, project_id, stage, zone, level, rm_no, rm_desc, code, description, size, qty, assembler, lister, item_code, group_id, floor_plan, rls, joiery_details, sketchup_file) VALUES
  (297830, @pid, 'Joinery General', '03', '03', '057', 'Dirty Utilities', 'JO-SS01',   'SS Bench',               1200, 1, '',               'John', '598200', '598200', '3101-T1', '6328-T1', '6328-T1', '297830.skp'),
  (297871, @pid, 'Joinery General', '03', '03', '057', 'Dirty Utilities', 'JO-SS02',   'SS Bench + OH Cupboard', 1500, 1, '',               'Bill', '598241', '598241', '3101-T1', '6328-T1', '6328-T1', '297871.skp'),
  (297910, @pid, 'Joinery Lab',     '03', '03', '068', 'Bacterial Room',  'JL-BE01a',  'Lab Bench',              1500, 1, '',               '',     '598280', '598280', '3101-T1', '6328-T1', '6328-T1', '297910.skp'),
  (297911, @pid, 'Joinery Lab',     '03', '03', '068', 'Bacterial Room',  'JL-BE01a',  'Lab Bench',              1500, 1, '',               '',     '598281', '598281', '3101-T1', '6328-T1', '6328-T1', '297911.skp'),
  (297912, @pid, 'Joinery Lab',     '03', '03', '068', 'Bacterial Room',  'JL-BE01r',  'Lab Bench',              1500, 1, '',               '',     '598282', '598282', '3101-T1', '6328-T1', '6328-T1', '297912.skp'),
  (297913, @pid, 'Joinery Lab',     '03', '03', '068', 'Bacterial Room',  'JL-BE01r',  'Lab Bench',              1650, 1, '',               '',     '598283', '598283', '3101-T1', '6328-T1', '6328-T1', '297913.skp'),
  (297914, @pid, 'Joinery Lab',     '03', '03', '068', 'Bacterial Room',  'JL-BE01r',  'Lab Bench',              1650, 1, '',               '',     '598284', '598284', '3101-T1', '6328-T1', '6328-T1', '297914.skp'),
  (297956, @pid, 'Joinery Lab',     '03', '03', '068', 'Bacterial Room',  'JL-SB01a',  'SS Lab Bench',           1200, 1, 'Chris Anastasi', 'Bill', '598326', '598326', '3101-T1', '6328-T1', '6328-T1', '297956.skp'),
  (297960, @pid, 'Joinery Lab',     '03', '03', '069', 'Clean Lab',       'JL-BE02',   'Lab Bench + OH',         1800, 2, 'Chris Anastasi', 'Bill', '598330', '598330', '3101-T1', '6328-T1', '6328-T1', '297960.skp'),
  (297961, @pid, 'PC2',             '04', '03', '102', 'PC2 Holding',     'JL-PC201',  'PC2 Containment Bench',  2000, 1, 'Anna Wu',        'Bill', '598331', '598331', '3101-T1', '6328-T1', '6328-T1', '297961.skp'),
  (297975, @pid, 'Stone',           '04', '03', '104', 'Reception',       'ST-CT01',   'Reception Counter Top',  3200, 1, '—',              'Bill', '598345', '598345', '3101-T1', '6328-T1', '6328-T1', '297975.skp'),
  (297988, @pid, 'Joinery General', '05', '03', '201', 'Tea Point',       'JO-TP01',   'Tea Point Joinery',      2400, 1, 'John',           'Bill', '598358', '598358', '3101-T1', '6328-T1', '6328-T1', '297988.skp');

-- Per-item stage dues / dones (same as tracking_schema.sql)
-- 297830 — SS Bench
INSERT INTO item_stages (item_id, stage_key, due_date, done_date)
SELECT item_id,'REQ',    '2026-04-01','2026-04-01' FROM items WHERE num=297830 UNION ALL
SELECT item_id,'SM',     '2026-03-28','2026-03-28' FROM items WHERE num=297830 UNION ALL
SELECT item_id,'LISTED', '2026-03-28','2026-03-28' FROM items WHERE num=297830 UNION ALL
SELECT item_id,'DOWN',   '2026-04-02','2026-04-02' FROM items WHERE num=297830 UNION ALL
SELECT item_id,'CNC',    '2026-04-05','2026-04-05' FROM items WHERE num=297830 UNION ALL
SELECT item_id,'EDGED',  '2026-04-06','2026-04-06' FROM items WHERE num=297830 UNION ALL
SELECT item_id,'PAINTED', NULL,        NULL        FROM items WHERE num=297830 UNION ALL
SELECT item_id,'MADE',   '2026-04-10','2026-04-10' FROM items WHERE num=297830 UNION ALL
SELECT item_id,'DEL',    '2026-04-14', NULL        FROM items WHERE num=297830 UNION ALL
SELECT item_id,'INST',   '2026-04-17', NULL        FROM items WHERE num=297830;

-- 297871 — SS Bench + OH Cupboard
INSERT INTO item_stages (item_id, stage_key, due_date, done_date)
SELECT item_id,'REQ',    '2026-04-01','2026-03-04' FROM items WHERE num=297871 UNION ALL
SELECT item_id,'SM',     '2026-03-18','2026-03-18' FROM items WHERE num=297871 UNION ALL
SELECT item_id,'LISTED', '2026-03-23','2026-03-23' FROM items WHERE num=297871 UNION ALL
SELECT item_id,'DOWN',   '2026-03-23','2026-03-23' FROM items WHERE num=297871 UNION ALL
SELECT item_id,'CNC',     NULL,        NULL        FROM items WHERE num=297871 UNION ALL
SELECT item_id,'EDGED',   NULL,        NULL        FROM items WHERE num=297871 UNION ALL
SELECT item_id,'PAINTED', NULL,        NULL        FROM items WHERE num=297871 UNION ALL
SELECT item_id,'MADE',    NULL,        NULL        FROM items WHERE num=297871 UNION ALL
SELECT item_id,'DEL',     NULL,        NULL        FROM items WHERE num=297871 UNION ALL
SELECT item_id,'INST',    NULL,        NULL        FROM items WHERE num=297871;

-- 297910..297914 — Lab Benches
INSERT INTO item_stages (item_id, stage_key, due_date, done_date)
SELECT it.item_id, s.stage_key, s.due_date, s.done_date
FROM items it
JOIN (
  SELECT 'REQ'    AS stage_key, DATE '2026-04-01' AS due_date, DATE '2026-04-01' AS done_date UNION ALL
  SELECT 'SM',     '2026-03-05','2026-03-05' UNION ALL
  SELECT 'LISTED', '2026-03-20', NULL        UNION ALL
  SELECT 'DOWN',    NULL,        NULL        UNION ALL
  SELECT 'CNC',     NULL,        NULL        UNION ALL
  SELECT 'EDGED',   NULL,        NULL        UNION ALL
  SELECT 'PAINTED', NULL,        NULL        UNION ALL
  SELECT 'MADE',    NULL,        NULL        UNION ALL
  SELECT 'DEL',     NULL,        NULL        UNION ALL
  SELECT 'INST',    NULL,        NULL
) s
WHERE it.num IN (297910, 297911, 297912, 297913, 297914);

-- 297956 — SS Lab Bench
INSERT INTO item_stages (item_id, stage_key, due_date, done_date)
SELECT item_id,'REQ',    '2026-04-01','2026-03-17' FROM items WHERE num=297956 UNION ALL
SELECT item_id,'SM',     '2026-03-23','2026-03-23' FROM items WHERE num=297956 UNION ALL
SELECT item_id,'LISTED', '2026-03-25','2026-03-25' FROM items WHERE num=297956 UNION ALL
SELECT item_id,'DOWN',    NULL,        NULL        FROM items WHERE num=297956 UNION ALL
SELECT item_id,'CNC',     NULL,        NULL        FROM items WHERE num=297956 UNION ALL
SELECT item_id,'EDGED',   NULL,        NULL        FROM items WHERE num=297956 UNION ALL
SELECT item_id,'PAINTED', NULL,        NULL        FROM items WHERE num=297956 UNION ALL
SELECT item_id,'MADE',    NULL,        NULL        FROM items WHERE num=297956 UNION ALL
SELECT item_id,'DEL',     NULL,        NULL        FROM items WHERE num=297956 UNION ALL
SELECT item_id,'INST',    NULL,        NULL        FROM items WHERE num=297956;

-- 297960 — Lab Bench + OH
INSERT INTO item_stages (item_id, stage_key, due_date, done_date)
SELECT item_id,'REQ',    '2026-04-20','2026-04-10' FROM items WHERE num=297960 UNION ALL
SELECT item_id,'SM',     '2026-03-30','2026-03-30' FROM items WHERE num=297960 UNION ALL
SELECT item_id,'LISTED', '2026-04-02','2026-04-02' FROM items WHERE num=297960 UNION ALL
SELECT item_id,'DOWN',   '2026-04-08','2026-04-08' FROM items WHERE num=297960 UNION ALL
SELECT item_id,'CNC',    '2026-04-15', NULL        FROM items WHERE num=297960 UNION ALL
SELECT item_id,'EDGED',   NULL,        NULL        FROM items WHERE num=297960 UNION ALL
SELECT item_id,'PAINTED', NULL,        NULL        FROM items WHERE num=297960 UNION ALL
SELECT item_id,'MADE',    NULL,        NULL        FROM items WHERE num=297960 UNION ALL
SELECT item_id,'DEL',     NULL,        NULL        FROM items WHERE num=297960 UNION ALL
SELECT item_id,'INST',    NULL,        NULL        FROM items WHERE num=297960;

-- 297961 — PC2 Containment Bench
INSERT INTO item_stages (item_id, stage_key, due_date, done_date)
SELECT item_id,'REQ',    '2026-05-01', NULL        FROM items WHERE num=297961 UNION ALL
SELECT item_id,'SM',     '2026-04-12','2026-04-12' FROM items WHERE num=297961 UNION ALL
SELECT item_id,'LISTED',  NULL,        NULL        FROM items WHERE num=297961 UNION ALL
SELECT item_id,'DOWN',    NULL,        NULL        FROM items WHERE num=297961 UNION ALL
SELECT item_id,'CNC',     NULL,        NULL        FROM items WHERE num=297961 UNION ALL
SELECT item_id,'EDGED',   NULL,        NULL        FROM items WHERE num=297961 UNION ALL
SELECT item_id,'PAINTED', NULL,        NULL        FROM items WHERE num=297961 UNION ALL
SELECT item_id,'MADE',    NULL,        NULL        FROM items WHERE num=297961 UNION ALL
SELECT item_id,'DEL',     NULL,        NULL        FROM items WHERE num=297961 UNION ALL
SELECT item_id,'INST',    NULL,        NULL        FROM items WHERE num=297961;

-- 297975 — Reception Counter Top
INSERT INTO item_stages (item_id, stage_key, due_date, done_date)
SELECT item_id,'REQ',    '2026-04-25','2026-04-10' FROM items WHERE num=297975 UNION ALL
SELECT item_id,'SM',     '2026-03-30','2026-03-30' FROM items WHERE num=297975 UNION ALL
SELECT item_id,'LISTED', '2026-04-05','2026-04-05' FROM items WHERE num=297975 UNION ALL
SELECT item_id,'DOWN',   '2026-04-12','2026-04-12' FROM items WHERE num=297975 UNION ALL
SELECT item_id,'CNC',    '2026-04-14','2026-04-14' FROM items WHERE num=297975 UNION ALL
SELECT item_id,'EDGED',  '2026-04-15','2026-04-15' FROM items WHERE num=297975 UNION ALL
SELECT item_id,'PAINTED', NULL,        NULL        FROM items WHERE num=297975 UNION ALL
SELECT item_id,'MADE',   '2026-04-16','2026-04-16' FROM items WHERE num=297975 UNION ALL
SELECT item_id,'DEL',    '2026-04-22', NULL        FROM items WHERE num=297975 UNION ALL
SELECT item_id,'INST',   '2026-04-24', NULL        FROM items WHERE num=297975;

-- 297988 — Tea Point Joinery
INSERT INTO item_stages (item_id, stage_key, due_date, done_date)
SELECT item_id,'REQ',    '2026-05-15', NULL        FROM items WHERE num=297988 UNION ALL
SELECT item_id,'SM',     '2026-04-10','2026-04-10' FROM items WHERE num=297988 UNION ALL
SELECT item_id,'LISTED',  NULL,        NULL        FROM items WHERE num=297988 UNION ALL
SELECT item_id,'DOWN',    NULL,        NULL        FROM items WHERE num=297988 UNION ALL
SELECT item_id,'CNC',     NULL,        NULL        FROM items WHERE num=297988 UNION ALL
SELECT item_id,'EDGED',   NULL,        NULL        FROM items WHERE num=297988 UNION ALL
SELECT item_id,'PAINTED', NULL,        NULL        FROM items WHERE num=297988 UNION ALL
SELECT item_id,'MADE',    NULL,        NULL        FROM items WHERE num=297988 UNION ALL
SELECT item_id,'DEL',     NULL,        NULL        FROM items WHERE num=297988 UNION ALL
SELECT item_id,'INST',    NULL,        NULL        FROM items WHERE num=297988;

-- ============================================================
--  Sample queries
-- ============================================================
-- Reconstruct tracking dashboard grid:
--   (same as tracking_schema.sql sample query)
--
-- "Is this item blocked on a material?" (product_spec.md §3 JTBD 3):
--   SELECT i.num, hm.sku, hm.description,
--          SUM(ba.qty_allocated)            AS allocated_qty,
--          MIN(pb.eta_date)                 AS earliest_eta,
--          MAX(pb.received_date IS NOT NULL) AS any_received
--   FROM items i
--   JOIN item_hardware_lines ihl ON ihl.item_id = i.item_id
--   JOIN project_hardware_catalog phc ON phc.catalog_id = ihl.catalog_id
--   JOIN hardware_materials hm ON hm.material_id = phc.material_id
--                              AND phc.material_type = 'HARDWARE'
--   LEFT JOIN batch_allocations  ba ON ba.item_hardware_line_id = ihl.line_id
--   LEFT JOIN procurement_batches pb ON pb.batch_id = ba.batch_id
--   WHERE i.item_id = ?
--   GROUP BY i.num, hm.sku, hm.description;
