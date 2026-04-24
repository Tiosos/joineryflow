"""tracking port

Revision ID: 0001
Revises:
Create Date: 2026-04-22
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(r"""
    -- Users
    CREATE TABLE users (
        user_id    BIGSERIAL PRIMARY KEY,
        username   varchar(64) UNIQUE NOT NULL,
        full_name  varchar(255),
        email      citext,
        role       text DEFAULT 'DRAFTER'
                   CHECK (role IN ('CEO','PM','DRAFTER','FOREMAN','MACHINE','PROCUREMENT')),
        is_active  boolean DEFAULT TRUE,
        created_at timestamptz DEFAULT now()
    );

    -- Projects
    CREATE TABLE projects (
        project_id              BIGSERIAL PRIMARY KEY,
        name                    varchar(255) UNIQUE NOT NULL,
        project_code            varchar(32)  NOT NULL,
        carell_pid              varchar(32),
        builder                 varchar(128),
        classification          varchar(128),
        site_street             varchar(255),
        site_suburb             varchar(128),
        site_postcode           varchar(16),
        site_state              varchar(8),
        tg_project_manager      varchar(128),
        tg_coordinator          varchar(128),
        status                  text DEFAULT 'Current'
                                CHECK (status IN ('Current','Closed','Hold')),
        installation_start      date,
        total_value             numeric(15,2),
        total_line_items        integer,
        tg_solid                boolean DEFAULT FALSE,
        optimisation_drafter_id bigint DEFAULT NULL,
        created_by              varchar(64),
        created_at              timestamptz DEFAULT now(),
        -- NOTE: legacy had ON UPDATE CURRENT_TIMESTAMP; handle via trigger/app layer
        updated_at              timestamptz DEFAULT now(),
        FOREIGN KEY (optimisation_drafter_id) REFERENCES users(user_id)
    );

    -- User-project favourites
    CREATE TABLE project_favourites (
        user_id    bigint NOT NULL,
        project_id bigint NOT NULL,
        created_at timestamptz DEFAULT now(),
        PRIMARY KEY (user_id, project_id),
        FOREIGN KEY (user_id)    REFERENCES users(user_id)       ON DELETE CASCADE,
        FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
    );

    -- Lookups
    CREATE TABLE stages (
        stage_key  varchar(16) PRIMARY KEY,
        label      varchar(32) NOT NULL,
        sort_order smallint    NOT NULL
    );

    CREATE TABLE status_options (
        status_key varchar(16) PRIMARY KEY,
        sort_order smallint    NOT NULL
    );

    CREATE TABLE status_symbols (
        symbol_key varchar(16) PRIMARY KEY,
        glyph      varchar(8)  NOT NULL,
        colour     varchar(16) NOT NULL,
        label      varchar(64) NOT NULL,
        sort_order smallint    NOT NULL
    );

    -- Material catalog: board
    CREATE TABLE board_materials (
        material_id    BIGSERIAL PRIMARY KEY,
        code           varchar(64) UNIQUE NOT NULL,
        description    varchar(255),
        thickness_mm   numeric(6,2),
        sheet_len_mm   integer,
        sheet_wid_mm   integer,
        supplier       varchar(128),
        cost_per_sheet numeric(12,2),
        lead_time_days integer DEFAULT 0,
        notes          text,
        is_active      boolean DEFAULT TRUE,
        created_at     timestamptz DEFAULT now(),
        updated_at     timestamptz DEFAULT now()
    );

    -- Material catalog: hardware
    CREATE TABLE hardware_materials (
        material_id    BIGSERIAL PRIMARY KEY,
        sku            varchar(64) UNIQUE NOT NULL,
        description    varchar(255),
        hardware_type  varchar(64),
        supplier       varchar(128),
        brand          varchar(128),
        cost_per_unit  numeric(12,2),
        lead_time_days integer DEFAULT 0,
        notes          text,
        is_active      boolean DEFAULT TRUE,
        created_at     timestamptz DEFAULT now(),
        updated_at     timestamptz DEFAULT now()
    );

    -- Material catalog: custom_made
    CREATE TABLE custom_made (
        material_id      BIGSERIAL PRIMARY KEY,
        internal_ref     varchar(64) UNIQUE NOT NULL,
        description      varchar(255),
        vendor           varchar(128),
        vendor_quote_ref varchar(64),
        cost             numeric(12,2),
        lead_time_days   integer DEFAULT 0,
        notes            text,
        created_at       timestamptz DEFAULT now(),
        updated_at       timestamptz DEFAULT now()
    );

    -- Material catalog: benchtop
    CREATE TABLE benchtop_materials (
        material_id    BIGSERIAL PRIMARY KEY,
        slab_id        varchar(64) UNIQUE NOT NULL,
        description    varchar(255),
        material_type  varchar(64),
        thickness_mm   numeric(6,2),
        slab_len_mm    integer,
        slab_wid_mm    integer,
        supplier       varchar(128),
        cost_per_slab  numeric(12,2),
        lead_time_days integer DEFAULT 0,
        notes          text,
        created_at     timestamptz DEFAULT now(),
        updated_at     timestamptz DEFAULT now()
    );

    -- Material catalog: appliances
    CREATE TABLE appliances (
        material_id    BIGSERIAL PRIMARY KEY,
        model_number   varchar(64) UNIQUE NOT NULL,
        description    varchar(255),
        manufacturer   varchar(128),
        supplier       varchar(128),
        cost_per_unit  numeric(12,2),
        lead_time_days integer DEFAULT 0,
        notes          text,
        created_at     timestamptz DEFAULT now(),
        updated_at     timestamptz DEFAULT now()
    );

    -- Equipment hire
    CREATE TABLE equipment_hire (
        hire_id      BIGSERIAL PRIMARY KEY,
        contract_ref varchar(64) UNIQUE NOT NULL,
        project_id   bigint NOT NULL,
        description  varchar(255),
        supplier     varchar(128),
        rate         numeric(12,2),
        rate_unit    text DEFAULT 'DAY'
                     CHECK (rate_unit IN ('HOUR','DAY','WEEK','MONTH')),
        hire_start   date,
        hire_end     date,
        total_cost   numeric(12,2),
        notes        text,
        created_at   timestamptz DEFAULT now(),
        updated_at   timestamptz DEFAULT now(),
        FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
    );
    CREATE INDEX idx_hire_project ON equipment_hire (project_id);

    -- Project hardware catalog
    CREATE TABLE project_hardware_catalog (
        catalog_id    BIGSERIAL PRIMARY KEY,
        project_id    bigint NOT NULL,
        material_type text NOT NULL
                      CHECK (material_type IN ('BOARD','HARDWARE','CUSTOM','BENCHTOP','APPLIANCE','HIRE')),
        material_id   bigint NOT NULL,
        added_by      bigint NOT NULL,
        added_at      timestamptz DEFAULT now(),
        is_active     boolean DEFAULT TRUE,
        notes         text,
        FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
        FOREIGN KEY (added_by)   REFERENCES users(user_id),
        CONSTRAINT uq_proj_mat UNIQUE (project_id, material_type, material_id)
    );
    CREATE INDEX idx_phc_project ON project_hardware_catalog (project_id);

    -- Project hardware catalog log
    CREATE TABLE project_hardware_catalog_log (
        log_id        BIGSERIAL PRIMARY KEY,
        project_id    bigint NOT NULL,
        material_type text NOT NULL
                      CHECK (material_type IN ('BOARD','HARDWARE','CUSTOM','BENCHTOP','APPLIANCE','HIRE')),
        material_id   bigint NOT NULL,
        action        text NOT NULL
                      CHECK (action IN ('ADD','REMOVE','REACTIVATE')),
        changed_by    bigint NOT NULL,
        changed_at    timestamptz DEFAULT now(),
        note          text,
        FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
        FOREIGN KEY (changed_by) REFERENCES users(user_id)
    );
    CREATE INDEX idx_phc_log_project ON project_hardware_catalog_log (project_id, changed_at DESC);

    -- Items
    CREATE TABLE items (
        item_id           BIGSERIAL PRIMARY KEY,
        num               integer UNIQUE NOT NULL,
        project_id        bigint NOT NULL,
        stage             varchar(64),
        zone              varchar(16),
        level             varchar(16),
        rm_no             varchar(16),
        rm_desc           varchar(128),
        code              varchar(64),
        description       varchar(255),
        size              integer,
        qty               integer,
        assembler         varchar(128),
        lister            varchar(128),
        item_code         varchar(32),
        group_id          varchar(32),
        floor_plan        varchar(64),
        rls               varchar(64),
        joiery_details    varchar(64),
        painting_req      boolean DEFAULT FALSE,
        solid_surface_req boolean DEFAULT FALSE,
        cutlist_printed   boolean DEFAULT TRUE,
        sketchup_file     varchar(255),
        cab_vision_file   varchar(255),
        estimator_notes   text,
        cutlist_owner_id  bigint DEFAULT NULL,
        item_locked       boolean DEFAULT FALSE,
        status            varchar(16) DEFAULT 'CLEAR',
        status_symbol     varchar(16) DEFAULT NULL,
        omitted           boolean DEFAULT FALSE,
        fav               boolean DEFAULT FALSE,
        deleted           boolean DEFAULT FALSE,
        void_flag         boolean DEFAULT FALSE,
        created_at        timestamptz DEFAULT now(),
        updated_at        timestamptz DEFAULT now(),
        FOREIGN KEY (project_id)       REFERENCES projects(project_id),
        FOREIGN KEY (status)           REFERENCES status_options(status_key),
        FOREIGN KEY (status_symbol)    REFERENCES status_symbols(symbol_key),
        FOREIGN KEY (cutlist_owner_id) REFERENCES users(user_id)
    );
    CREATE INDEX idx_items_project ON items (project_id);
    CREATE INDEX idx_items_status  ON items (status);
    CREATE INDEX idx_items_symbol  ON items (status_symbol);

    -- Item x stage pivot
    CREATE TABLE item_stages (
        item_id   bigint      NOT NULL,
        stage_key varchar(16) NOT NULL,
        due_date  date DEFAULT NULL,
        done_date date DEFAULT NULL,
        PRIMARY KEY (item_id, stage_key),
        FOREIGN KEY (item_id)   REFERENCES items(item_id)    ON DELETE CASCADE,
        FOREIGN KEY (stage_key) REFERENCES stages(stage_key)
    );

    -- Item status log
    CREATE TABLE item_status_log (
        log_id     BIGSERIAL PRIMARY KEY,
        item_id    bigint      NOT NULL,
        status     varchar(16) NOT NULL,
        note       text        NOT NULL,
        changed_by varchar(64) NOT NULL,
        changed_at timestamptz DEFAULT now(),
        FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
        FOREIGN KEY (status)  REFERENCES status_options(status_key)
    );
    CREATE INDEX idx_status_log_item ON item_status_log (item_id, changed_at DESC);

    -- Item edit log
    CREATE TABLE item_edit_log (
        log_id      BIGSERIAL PRIMARY KEY,
        item_id     bigint      NOT NULL,
        field_label varchar(64) NOT NULL,
        old_value   varchar(255),
        new_value   varchar(255),
        changed_by  varchar(64) NOT NULL,
        changed_at  timestamptz DEFAULT now(),
        FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE
    );
    CREATE INDEX idx_edit_log_item ON item_edit_log (item_id, changed_at DESC);

    -- Modules
    CREATE TABLE modules (
        module_id  BIGSERIAL PRIMARY KEY,
        item_id    bigint NOT NULL,
        module_no  varchar(16) NOT NULL,
        name       varchar(255),
        notes      text,
        created_at timestamptz DEFAULT now(),
        FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
        CONSTRAINT uq_item_mod UNIQUE (item_id, module_no)
    );
    CREATE INDEX idx_modules_item ON modules (item_id);

    -- Parts
    CREATE TABLE parts (
        part_id           BIGSERIAL PRIMARY KEY,
        module_id         bigint NOT NULL,
        seq               integer,
        qty               integer NOT NULL DEFAULT 1,
        part_name         varchar(128),
        len_mm            integer,
        wid_mm            integer,
        board_material_id bigint,
        edge              varchar(64),
        colour            varchar(64),
        edging_spec       varchar(64),
        paint_instruction text DEFAULT 'NONE'
                          CHECK (paint_instruction IN ('NONE','DOUBLE_SIDE','SINGLE_SIDE','EDGE_ONLY')),
        comment           text,
        created_at        timestamptz DEFAULT now(),
        updated_at        timestamptz DEFAULT now(),
        FOREIGN KEY (module_id)         REFERENCES modules(module_id)           ON DELETE CASCADE,
        FOREIGN KEY (board_material_id) REFERENCES board_materials(material_id)
    );
    CREATE INDEX idx_parts_module ON parts (module_id);

    -- Item hardware lines
    CREATE TABLE item_hardware_lines (
        line_id    BIGSERIAL PRIMARY KEY,
        item_id    bigint NOT NULL,
        seq        integer,
        qty        integer NOT NULL DEFAULT 1,
        catalog_id bigint NOT NULL,
        note       text,
        created_at timestamptz DEFAULT now(),
        updated_at timestamptz DEFAULT now(),
        FOREIGN KEY (item_id)    REFERENCES items(item_id) ON DELETE CASCADE,
        FOREIGN KEY (catalog_id) REFERENCES project_hardware_catalog(catalog_id)
    );
    CREATE INDEX idx_ihl_item    ON item_hardware_lines (item_id);
    CREATE INDEX idx_ihl_catalog ON item_hardware_lines (catalog_id);

    -- Procurement batches
    CREATE TABLE procurement_batches (
        batch_id      BIGSERIAL PRIMARY KEY,
        project_id    bigint NOT NULL,
        material_type text NOT NULL
                      CHECK (material_type IN ('BOARD','HARDWARE','CUSTOM','BENCHTOP','APPLIANCE','HIRE')),
        material_id   bigint NOT NULL,
        supplier      varchar(128),
        po_ref        varchar(64),
        qty_ordered   numeric(12,2) NOT NULL DEFAULT 0,
        qty_received  numeric(12,2) NOT NULL DEFAULT 0,
        cost_per_unit numeric(12,2),
        ordered_date  date,
        eta_date      date,
        received_date date,
        notes         text,
        created_at    timestamptz DEFAULT now(),
        updated_at    timestamptz DEFAULT now(),
        FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
    );
    CREATE INDEX idx_batch_project  ON procurement_batches (project_id);
    CREATE INDEX idx_batch_material ON procurement_batches (material_type, material_id);
    CREATE INDEX idx_batch_eta      ON procurement_batches (eta_date);

    -- Batch allocations
    CREATE TABLE batch_allocations (
        allocation_id         BIGSERIAL PRIMARY KEY,
        batch_id              bigint NOT NULL,
        item_hardware_line_id bigint NOT NULL,
        qty_allocated         numeric(12,2) NOT NULL DEFAULT 0,
        created_at            timestamptz DEFAULT now(),
        FOREIGN KEY (batch_id)              REFERENCES procurement_batches(batch_id) ON DELETE CASCADE,
        FOREIGN KEY (item_hardware_line_id) REFERENCES item_hardware_lines(line_id)  ON DELETE CASCADE,
        CONSTRAINT uq_batch_line UNIQUE (batch_id, item_hardware_line_id)
    );
    CREATE INDEX idx_alloc_line ON batch_allocations (item_hardware_line_id);
    """)


def downgrade():
    op.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
