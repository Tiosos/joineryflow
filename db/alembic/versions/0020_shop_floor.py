"""shop_floor — Foreman + Machine team Shop Floor Ops (sub-project #8)

Adds:
  - app_user.is_shop_worker (bool, default false)
  - items.paint_after_assembly (bool, default false; reorders PAINTED
    after MADE in the lifecycle when true)
  - worker_assignment register
  - stage_completion_log (immutable history)
  - 4 supporting indexes incl. partial unique idx for active assignment

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-08
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    -- 1. Worker flag on existing app_user
    ALTER TABLE app_user
        ADD COLUMN is_shop_worker boolean NOT NULL DEFAULT false;

    CREATE INDEX idx_app_user_workers
        ON app_user (workspace_id)
        WHERE is_shop_worker = true;

    -- 2. Per-item ordering hint for the PAINTED stage
    ALTER TABLE items
        ADD COLUMN paint_after_assembly boolean NOT NULL DEFAULT false;

    -- 3. Worker assignment register (mutable assignment state)
    CREATE TABLE worker_assignment (
        assignment_id  bigserial    PRIMARY KEY,
        item_id        bigint       NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
        stage_key      varchar(16)  NOT NULL REFERENCES stages(stage_key),
        worker_id      bigint       NOT NULL REFERENCES app_user(id),
        status         text         NOT NULL CHECK (status IN
                                      ('assigned','in_progress','done','cancelled'))
                                    DEFAULT 'assigned',
        note           text,
        assigned_by    bigint       NOT NULL REFERENCES app_user(id),
        assigned_at    timestamptz  NOT NULL DEFAULT now(),
        started_at     timestamptz,
        ended_at       timestamptz,
        cancelled_at   timestamptz,
        cancelled_by   bigint       REFERENCES app_user(id),
        created_at     timestamptz  NOT NULL DEFAULT now(),
        updated_at     timestamptz  NOT NULL DEFAULT now(),
        CHECK (stage_key IN ('DOWN','CNC','EDGED','PAINTED','MADE'))
    );

    -- At most one ACTIVE assignment per (item, stage). Cancelled/done
    -- rows are kept for history.
    CREATE UNIQUE INDEX uniq_active_assignment
        ON worker_assignment (item_id, stage_key)
        WHERE status IN ('assigned', 'in_progress');

    CREATE INDEX idx_assignment_worker
        ON worker_assignment (worker_id, status)
        WHERE status IN ('assigned', 'in_progress');

    CREATE INDEX idx_assignment_item
        ON worker_assignment (item_id);

    -- 4. Stage completion log (append-only, immutable)
    CREATE TABLE stage_completion_log (
        log_id         bigserial    PRIMARY KEY,
        item_id        bigint       NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
        stage_key      varchar(16)  NOT NULL REFERENCES stages(stage_key),
        assignment_id  bigint       REFERENCES worker_assignment(assignment_id),
        worker_id      bigint       NOT NULL REFERENCES app_user(id),
        completed_at   timestamptz  NOT NULL DEFAULT now(),
        note           text,
        undone_at      timestamptz,
        undone_by      bigint       REFERENCES app_user(id),
        CHECK (stage_key IN ('DOWN','CNC','EDGED','PAINTED','MADE'))
    );

    CREATE INDEX idx_completion_item
        ON stage_completion_log (item_id, stage_key);

    CREATE INDEX idx_completion_worker
        ON stage_completion_log (worker_id, completed_at DESC)
        WHERE undone_at IS NULL;
    """)


def downgrade():
    op.execute("-- intentionally not reversible; recover via 0001-0019 only")
