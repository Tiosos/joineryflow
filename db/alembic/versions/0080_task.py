"""task (Plan V1 §10, Q524; spec docs/archive/2026-10-21-tasks.md)

A task is a piece of work given to a person: title, assignee, due date, status,
optionally pointing at one project, Joinery Item or cutlist (Q-T1). Only the
manual / by-request creation paths are built (`source` is `manual`; the CHECK is
widened when rule- or system-created tasks arrive, Q472).

The target is held as **three nullable real FKs** with a CHECK that at most one
is set, as `comment` does (`0042`): a hard-deleted project / item / cutlist takes
its tasks with it via ON DELETE CASCADE. A soft-deleted item or cutlist (`0052`)
is hidden by the readers, not by the schema.

`workspace_id` is the task's own scope. `field_versions` carries the per-field
counters for `PATCH ... expected_versions` (`concurrency.py`). A task is
cancelled, never hard-deleted. Nothing is added to the search outbox in v1.

Revision ID: 0080
Revises: 0079
Create Date: 2026-10-21
"""
from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE task (
        task_id        BIGSERIAL PRIMARY KEY,
        workspace_id   bigint NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
        title          varchar(200) NOT NULL,
        CONSTRAINT ck_task_title CHECK (length(btrim(title)) >= 1),
        description    text,
        CONSTRAINT ck_task_description_len CHECK (description IS NULL OR length(description) <= 5000),
        status         varchar(16) NOT NULL DEFAULT 'open',
        CONSTRAINT ck_task_status CHECK (status IN ('open', 'in_progress', 'done', 'cancelled')),
        assignee_id    bigint REFERENCES app_user(id) ON DELETE SET NULL,
        created_by     bigint NOT NULL REFERENCES app_user(id),
        due_date       date,
        source         varchar(16) NOT NULL DEFAULT 'manual',
        CONSTRAINT ck_task_source CHECK (source IN ('manual')),

        project_id     bigint REFERENCES projects(project_id) ON DELETE CASCADE,
        item_id        bigint REFERENCES items(item_id)       ON DELETE CASCADE,
        cutlist_id     bigint REFERENCES cutlist(cutlist_id)  ON DELETE CASCADE,
        CONSTRAINT ck_task_one_target
            CHECK (num_nonnulls(project_id, item_id, cutlist_id) <= 1),

        completed_at   timestamptz,
        completed_by   bigint REFERENCES app_user(id) ON DELETE SET NULL,
        cancelled_at   timestamptz,
        cancelled_by   bigint REFERENCES app_user(id) ON DELETE SET NULL,
        field_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at     timestamptz NOT NULL DEFAULT now(),
        updated_at     timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX idx_task_workspace_status ON task (workspace_id, status);
    CREATE INDEX idx_task_assignee ON task (assignee_id, status) WHERE assignee_id IS NOT NULL;
    CREATE INDEX idx_task_project ON task (project_id) WHERE project_id IS NOT NULL;
    CREATE INDEX idx_task_item    ON task (item_id)    WHERE item_id    IS NOT NULL;
    CREATE INDEX idx_task_cutlist ON task (cutlist_id) WHERE cutlist_id IS NOT NULL;
    """)


def downgrade():
    op.execute("DROP TABLE task;")
