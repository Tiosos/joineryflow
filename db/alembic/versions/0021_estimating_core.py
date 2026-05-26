"""estimating core — sub-project #9a

Adds:
  - widen app_user.auth_role CHECK to include 'estimator'
  - customer (workspace-scoped registry)
  - estimate + estimate_revision (revisioned quotes)
  - estimate_line + estimate_line_part / _hardware / _labour
    (snapshotted cost columns; live material_id refs retained)
  - workspace_labour_rate (per-stage hourly rate config)
  - projects.customer_id (nullable FK)
  - projects.estimate_revision_id (nullable FK; set on Convert)

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-13
"""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    -- 1. Widen app_user.auth_role to allow 'estimator'
    ALTER TABLE app_user DROP CONSTRAINT IF EXISTS app_user_auth_role_check;
    ALTER TABLE app_user ADD CONSTRAINT app_user_auth_role_check
      CHECK (auth_role IN
        ('admin','manager','editor','drafter','estimator','purchase_officer','viewer'));

    -- 2. customer registry (workspace-scoped, case-insensitive UNIQUE on name)
    CREATE TABLE customer (
        customer_id      BIGSERIAL    PRIMARY KEY,
        workspace_id     BIGINT       NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
        name             text         NOT NULL,
        email            citext,
        phone            varchar(64),
        billing_address  text,
        abn              varchar(32),
        notes            text,
        archived_at      timestamptz,
        archived_by      BIGINT       REFERENCES app_user(id) ON DELETE SET NULL,
        created_at       timestamptz  NOT NULL DEFAULT now(),
        created_by       BIGINT       REFERENCES app_user(id) ON DELETE SET NULL,
        updated_at       timestamptz  NOT NULL DEFAULT now(),
        CONSTRAINT uq_customer_name UNIQUE (workspace_id, name)
    );
    CREATE INDEX idx_customer_workspace_active
        ON customer (workspace_id)
        WHERE archived_at IS NULL;

    -- 3. estimate root row (one row per quoted job). current_revision_id is
    --    set after the first revision row inserts.
    CREATE TABLE estimate (
        estimate_id           BIGSERIAL    PRIMARY KEY,
        workspace_id          BIGINT       NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
        customer_id           BIGINT       NOT NULL REFERENCES customer(customer_id) ON DELETE RESTRICT,
        estimate_no           text         NOT NULL,
        title                 varchar(255) NOT NULL,
        site_address          text,
        current_revision_id   BIGINT,   -- FK added after estimate_revision exists
        created_at            timestamptz  NOT NULL DEFAULT now(),
        created_by            BIGINT       REFERENCES app_user(id) ON DELETE SET NULL,
        updated_at            timestamptz  NOT NULL DEFAULT now(),
        CONSTRAINT uq_estimate_no UNIQUE (workspace_id, estimate_no)
    );
    CREATE INDEX idx_estimate_workspace_customer
        ON estimate (workspace_id, customer_id);

    -- 4. estimate_revision — immutable once status leaves 'draft'.
    --    Snapshots of workspace labour rates + terms text are frozen on lock.
    CREATE TABLE estimate_revision (
        revision_id                       BIGSERIAL    PRIMARY KEY,
        estimate_id                       BIGINT       NOT NULL REFERENCES estimate(estimate_id) ON DELETE CASCADE,
        rev_no                            integer      NOT NULL,
        status                            text         NOT NULL DEFAULT 'draft'
                                                       CHECK (status IN ('draft','sent','accepted','rejected','expired','withdrawn')),
        markup_pct                        numeric(5,2) NOT NULL DEFAULT 0,
        gst_pct                           numeric(5,2) NOT NULL DEFAULT 10.00,
        workspace_stage_rates_snapshot    jsonb,
        terms_text                        text,
        subtotal_cost                     numeric(14,2),
        subtotal_sell                     numeric(14,2),
        total_inc_gst                     numeric(14,2),
        sent_at                           timestamptz,
        sent_by                           BIGINT REFERENCES app_user(id) ON DELETE SET NULL,
        locked_at                         timestamptz,
        locked_by                         BIGINT REFERENCES app_user(id) ON DELETE SET NULL,
        accepted_at                       timestamptz,
        rejected_at                       timestamptz,
        lost_reason                       text,
        converted_project_id              BIGINT REFERENCES projects(project_id) ON DELETE SET NULL,
        created_at                        timestamptz  NOT NULL DEFAULT now(),
        created_by                        BIGINT REFERENCES app_user(id) ON DELETE SET NULL,
        CONSTRAINT uq_revision_no UNIQUE (estimate_id, rev_no)
    );
    CREATE UNIQUE INDEX uniq_estimate_draft
        ON estimate_revision (estimate_id)
        WHERE status = 'draft';
    CREATE INDEX idx_revision_estimate_status
        ON estimate_revision (estimate_id, status);
    CREATE INDEX idx_revision_converted
        ON estimate_revision (converted_project_id)
        WHERE converted_project_id IS NOT NULL;

    -- estimate.current_revision_id FK (now that the table exists)
    ALTER TABLE estimate
        ADD CONSTRAINT fk_estimate_current_revision
        FOREIGN KEY (current_revision_id)
        REFERENCES estimate_revision(revision_id) ON DELETE SET NULL;

    -- 5. estimate_line — one row per priced item on the quote
    CREATE TABLE estimate_line (
        line_id              BIGSERIAL    PRIMARY KEY,
        revision_id          BIGINT       NOT NULL REFERENCES estimate_revision(revision_id) ON DELETE CASCADE,
        seq                  integer      NOT NULL DEFAULT 1,
        description          varchar(255) NOT NULL,
        qty                  numeric(10,2) NOT NULL DEFAULT 1,
        unit                 varchar(16)  NOT NULL DEFAULT 'EA',
        has_breakdown        boolean      NOT NULL DEFAULT false,
        material_cost        numeric(12,2) NOT NULL DEFAULT 0,
        labour_cost          numeric(12,2) NOT NULL DEFAULT 0,
        total_cost           numeric(14,2) GENERATED ALWAYS AS (material_cost + labour_cost) STORED,
        unit_sell_override   numeric(12,2),
        notes                text,
        created_at           timestamptz  NOT NULL DEFAULT now(),
        updated_at           timestamptz  NOT NULL DEFAULT now()
    );
    CREATE INDEX idx_line_revision ON estimate_line (revision_id, seq);

    -- 6. estimate_line_part — board/custom/benchtop drill-down, snapshotted
    CREATE TABLE estimate_line_part (
        part_id                   BIGSERIAL    PRIMARY KEY,
        line_id                   BIGINT       NOT NULL REFERENCES estimate_line(line_id) ON DELETE CASCADE,
        material_type             text         NOT NULL
                                               CHECK (material_type IN ('BOARD','CUSTOM','BENCHTOP')),
        material_id               BIGINT,
        sku_snapshot              varchar(64),
        description_snapshot      varchar(255),
        supplier_snapshot         varchar(128),
        qty                       numeric(10,2) NOT NULL DEFAULT 1,
        len_mm                    integer,
        wid_mm                    integer,
        cost_per_unit_snapshot    numeric(12,4) NOT NULL DEFAULT 0,
        cost_extended             numeric(14,4) GENERATED ALWAYS AS (qty * cost_per_unit_snapshot) STORED,
        paint_instruction         text         NOT NULL DEFAULT 'NONE'
                                               CHECK (paint_instruction IN ('NONE','DOUBLE_SIDE','SINGLE_SIDE','EDGE_ONLY')),
        comment                   text,
        created_at                timestamptz  NOT NULL DEFAULT now()
    );
    CREATE INDEX idx_line_part_line ON estimate_line_part (line_id);

    -- 7. estimate_line_hardware — hardware/appliance drill-down, snapshotted.
    --    Equipment hire is excluded because it's project-scoped (project_id FK
    --    on the catalog row itself) and cannot be referenced from a pre-project
    --    quote. Hire is handled post-conversion by the existing equipment_hire
    --    table.
    CREATE TABLE estimate_line_hardware (
        hw_id                     BIGSERIAL    PRIMARY KEY,
        line_id                   BIGINT       NOT NULL REFERENCES estimate_line(line_id) ON DELETE CASCADE,
        material_type             text         NOT NULL
                                               CHECK (material_type IN ('HARDWARE','APPLIANCE')),
        material_id               BIGINT,
        sku_snapshot              varchar(64),
        description_snapshot      varchar(255),
        supplier_snapshot         varchar(128),
        qty                       numeric(10,2) NOT NULL DEFAULT 1,
        cost_per_unit_snapshot    numeric(12,4) NOT NULL DEFAULT 0,
        cost_extended             numeric(14,4) GENERATED ALWAYS AS (qty * cost_per_unit_snapshot) STORED,
        comment                   text,
        created_at                timestamptz  NOT NULL DEFAULT now()
    );
    CREATE INDEX idx_line_hardware_line ON estimate_line_hardware (line_id);

    -- 8. estimate_line_labour — hours per stage, rate snapshotted on insert
    CREATE TABLE estimate_line_labour (
        labour_id        BIGSERIAL    PRIMARY KEY,
        line_id          BIGINT       NOT NULL REFERENCES estimate_line(line_id) ON DELETE CASCADE,
        stage_key        varchar(16)  NOT NULL REFERENCES stages(stage_key),
        hours            numeric(6,2) NOT NULL DEFAULT 0,
        rate_snapshot    numeric(8,2) NOT NULL DEFAULT 0,
        cost_extended    numeric(12,2) GENERATED ALWAYS AS (hours * rate_snapshot) STORED,
        created_at       timestamptz  NOT NULL DEFAULT now(),
        CONSTRAINT uq_line_labour UNIQUE (line_id, stage_key)
    );

    -- 9. workspace_labour_rate — per-stage hourly rate (admin-managed)
    CREATE TABLE workspace_labour_rate (
        workspace_id     BIGINT       NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
        stage_key        varchar(16)  NOT NULL REFERENCES stages(stage_key),
        hourly_rate      numeric(8,2) NOT NULL DEFAULT 0,
        effective_from   date         NOT NULL DEFAULT CURRENT_DATE,
        updated_at       timestamptz  NOT NULL DEFAULT now(),
        updated_by       BIGINT       REFERENCES app_user(id) ON DELETE SET NULL,
        PRIMARY KEY (workspace_id, stage_key)
    );

    -- 10. projects FKs back into the estimating layer
    ALTER TABLE projects
        ADD COLUMN customer_id BIGINT
            REFERENCES customer(customer_id) ON DELETE SET NULL,
        ADD COLUMN estimate_revision_id BIGINT
            REFERENCES estimate_revision(revision_id) ON DELETE SET NULL;

    CREATE INDEX idx_projects_customer
        ON projects (customer_id)
        WHERE customer_id IS NOT NULL;
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-Estimating schema is recoverable from migrations 0001-0020 only")
