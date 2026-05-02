"""projects.workspace_id direct column (workspace isolation hardening)

Adds an explicit `workspace_id` FK column to `projects`, backfilled from the
existing `pm_id -> app_user.workspace_id` chain. This eliminates the unsafe
`(p.pm_id IS NULL OR u.workspace_id = :w)` predicate that read TRUE in every
workspace whenever a project lacked a PM.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-02
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    -- 1. Nullable column first so the backfill UPDATE has somewhere to land.
    ALTER TABLE projects
        ADD COLUMN workspace_id BIGINT
        REFERENCES workspace(id) ON DELETE RESTRICT;

    -- 2. Backfill from the pm_id chain. Projects with a pm_id inherit that
    --    user's workspace; projects without a pm_id are an integrity hole
    --    this migration explicitly refuses to paper over (see step 3).
    UPDATE projects p
       SET workspace_id = au.workspace_id
       FROM app_user au
      WHERE au.id = p.pm_id;

    -- 3. Fail loudly if any project still has NULL workspace_id. Per the
    --    create_project_route invariant (pm_id defaults to caller.id) this
    --    should be impossible in practice, but a stray INSERT from an admin
    --    script or hand-rolled SQL would otherwise have created a project
    --    that any workspace could read. Refuse to migrate such a database.
    DO $$
    DECLARE
        orphan_count int;
    BEGIN
        SELECT COUNT(*) INTO orphan_count
          FROM projects WHERE workspace_id IS NULL;
        IF orphan_count > 0 THEN
            RAISE EXCEPTION
              'projects.workspace_id backfill: % project row(s) have no resolvable workspace (pm_id is NULL or points at a missing app_user). Repair these rows before re-running migration 0014.',
              orphan_count;
        END IF;
    END $$;

    -- 4. Lock the column down.
    ALTER TABLE projects ALTER COLUMN workspace_id SET NOT NULL;
    CREATE INDEX projects_workspace_id_idx ON projects(workspace_id);
    """)


def downgrade():
    op.execute(r"""
    DROP INDEX IF EXISTS projects_workspace_id_idx;
    ALTER TABLE projects DROP COLUMN IF EXISTS workspace_id;
    """)
