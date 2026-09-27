"""rbac groups — dynamic, project-scoped permission engine (Plan V1 §3.4, Q466-473)

Adds the DB-backed layer that Q466 confirms: groups replace the static
`app.auth.permissions.MATRIX` as the live source of truth, and a group's
grants can be scoped to a single project rather than the whole workspace.

- `permission_group` (workspace_id, name, is_system) — 7 system groups seeded
  per workspace, named after today's 7 auth roles.
- `group_module_grant` (group_id, module, action) — what a group can do.
- `user_group_membership` (user_id, group_id, project_id NULL) — who holds a
  group's grants where. `project_id IS NULL` means workspace-wide, which is
  what every existing role check becomes under this migration — union across
  a user's memberships, most-permissive-wins, is `app.auth.rbac_engine`.

Backfill (Q435 data-preserving, Q436 pilot data): every existing workspace
gets its 7 system groups with grants copied verbatim from `MATRIX` at
authoring time (188 rows, machine-generated from the live dict so this
migration cannot drift from it by transcription), and every existing
`app_user` gets a workspace-wide membership in the system group matching
their current `auth_role`. Day one is bit-for-bit behaviour-preserving
(Q468) — `permissions.py` stays only as the fallback in
`rbac_engine.effective_actions` for a user who holds zero memberships
(covers rows created outside this backfill, e.g. in tests).

Q472 (moving hand-written per-object rules — require_drafter(), the
not-uploader approve rule, creator-or-manager, the 5-minute undo window —
into the engine) and Q470's critical actions (Lock/Unlock/Override/Configure,
deliberately kept out of this matrix) are NOT built here; see CLAUDE.md.

Revision ID: 0037
Revises: 0036
Create Date: 2026-09-27
"""
from alembic import op


revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS permission_group (
      group_id     BIGSERIAL PRIMARY KEY,
      workspace_id BIGINT NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
      name         VARCHAR(64) NOT NULL,
      is_system    BOOLEAN NOT NULL DEFAULT false,
      created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (workspace_id, name)
    );

    CREATE TABLE IF NOT EXISTS group_module_grant (
      group_id BIGINT NOT NULL REFERENCES permission_group(group_id) ON DELETE CASCADE,
      module   VARCHAR(32) NOT NULL,
      action   VARCHAR(16) NOT NULL,
      PRIMARY KEY (group_id, module, action)
    );
    CREATE INDEX IF NOT EXISTS idx_group_module_grant_module
        ON group_module_grant (module);

    CREATE TABLE IF NOT EXISTS user_group_membership (
      membership_id BIGSERIAL PRIMARY KEY,
      user_id    BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
      group_id   BIGINT NOT NULL REFERENCES permission_group(group_id) ON DELETE CASCADE,
      project_id BIGINT REFERENCES projects(project_id) ON DELETE CASCADE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      created_by BIGINT REFERENCES app_user(id) ON DELETE SET NULL
    );
    -- COALESCE(project_id, 0) so a NULL (workspace-wide) membership in a
    -- group can only exist once per user — plain UNIQUE would let NULLs
    -- repeat, since Postgres treats NULL <> NULL in a unique constraint.
    CREATE UNIQUE INDEX IF NOT EXISTS uniq_user_group_membership
        ON user_group_membership (user_id, group_id, COALESCE(project_id, 0));
    CREATE INDEX IF NOT EXISTS idx_user_group_membership_user
        ON user_group_membership (user_id);

    -- Seed the 7 system groups for every existing workspace.
    INSERT INTO permission_group (workspace_id, name, is_system)
    SELECT w.id, r.role, true
    FROM workspace w
    CROSS JOIN (VALUES ('admin'),('manager'),('editor'),('drafter'),
                       ('estimator'),('purchase_officer'),('viewer')) AS r(role)
    ON CONFLICT (workspace_id, name) DO NOTHING;

    -- Grants copied verbatim from app.auth.permissions.MATRIX (188 rows).
    INSERT INTO group_module_grant (group_id, module, action)
    SELECT g.group_id, m.module, m.action
    FROM permission_group g
    JOIN (VALUES
        ('admin','dashboard','approve'),
        ('admin','dashboard','comment'),
        ('admin','dashboard','read'),
        ('admin','dashboard','write'),
        ('admin','tracking','approve'),
        ('admin','tracking','comment'),
        ('admin','tracking','read'),
        ('admin','tracking','write'),
        ('admin','list','approve'),
        ('admin','list','comment'),
        ('admin','list','read'),
        ('admin','list','write'),
        ('admin','shop_dwgs','approve'),
        ('admin','shop_dwgs','comment'),
        ('admin','shop_dwgs','read'),
        ('admin','shop_dwgs','write'),
        ('admin','isample','approve'),
        ('admin','isample','comment'),
        ('admin','isample','read'),
        ('admin','isample','write'),
        ('admin','orderbook','approve'),
        ('admin','orderbook','comment'),
        ('admin','orderbook','read'),
        ('admin','orderbook','write'),
        ('admin','catalog','approve'),
        ('admin','catalog','comment'),
        ('admin','catalog','read'),
        ('admin','catalog','write'),
        ('admin','cut_floor','approve'),
        ('admin','cut_floor','comment'),
        ('admin','cut_floor','read'),
        ('admin','cut_floor','write'),
        ('admin','shop_floor','approve'),
        ('admin','shop_floor','comment'),
        ('admin','shop_floor','read'),
        ('admin','shop_floor','write'),
        ('admin','estimating','approve'),
        ('admin','estimating','comment'),
        ('admin','estimating','read'),
        ('admin','estimating','write'),
        ('admin','it_management','approve'),
        ('admin','it_management','comment'),
        ('admin','it_management','read'),
        ('admin','it_management','write'),
        ('manager','dashboard','approve'),
        ('manager','dashboard','comment'),
        ('manager','dashboard','read'),
        ('manager','dashboard','write'),
        ('manager','tracking','approve'),
        ('manager','tracking','comment'),
        ('manager','tracking','read'),
        ('manager','tracking','write'),
        ('manager','list','approve'),
        ('manager','list','comment'),
        ('manager','list','read'),
        ('manager','list','write'),
        ('manager','shop_dwgs','approve'),
        ('manager','shop_dwgs','comment'),
        ('manager','shop_dwgs','read'),
        ('manager','shop_dwgs','write'),
        ('manager','isample','approve'),
        ('manager','isample','comment'),
        ('manager','isample','read'),
        ('manager','isample','write'),
        ('manager','orderbook','approve'),
        ('manager','orderbook','comment'),
        ('manager','orderbook','read'),
        ('manager','orderbook','write'),
        ('manager','catalog','approve'),
        ('manager','catalog','comment'),
        ('manager','catalog','read'),
        ('manager','catalog','write'),
        ('manager','cut_floor','approve'),
        ('manager','cut_floor','comment'),
        ('manager','cut_floor','read'),
        ('manager','cut_floor','write'),
        ('manager','shop_floor','approve'),
        ('manager','shop_floor','comment'),
        ('manager','shop_floor','read'),
        ('manager','shop_floor','write'),
        ('manager','estimating','approve'),
        ('manager','estimating','comment'),
        ('manager','estimating','read'),
        ('manager','estimating','write'),
        ('manager','it_management','read'),
        ('editor','dashboard','comment'),
        ('editor','dashboard','read'),
        ('editor','dashboard','write'),
        ('editor','tracking','comment'),
        ('editor','tracking','read'),
        ('editor','tracking','write'),
        ('editor','list','comment'),
        ('editor','list','read'),
        ('editor','list','write'),
        ('editor','shop_dwgs','comment'),
        ('editor','shop_dwgs','read'),
        ('editor','shop_dwgs','write'),
        ('editor','isample','comment'),
        ('editor','isample','read'),
        ('editor','isample','write'),
        ('editor','orderbook','comment'),
        ('editor','orderbook','read'),
        ('editor','catalog','comment'),
        ('editor','catalog','read'),
        ('editor','catalog','write'),
        ('editor','cut_floor','comment'),
        ('editor','cut_floor','read'),
        ('editor','cut_floor','write'),
        ('editor','shop_floor','comment'),
        ('editor','shop_floor','read'),
        ('editor','shop_floor','write'),
        ('editor','estimating','read'),
        ('drafter','dashboard','read'),
        ('drafter','tracking','approve'),
        ('drafter','tracking','comment'),
        ('drafter','tracking','read'),
        ('drafter','tracking','write'),
        ('drafter','list','approve'),
        ('drafter','list','comment'),
        ('drafter','list','read'),
        ('drafter','list','write'),
        ('drafter','shop_dwgs','approve'),
        ('drafter','shop_dwgs','comment'),
        ('drafter','shop_dwgs','read'),
        ('drafter','shop_dwgs','write'),
        ('drafter','isample','approve'),
        ('drafter','isample','comment'),
        ('drafter','isample','read'),
        ('drafter','isample','write'),
        ('drafter','orderbook','approve'),
        ('drafter','orderbook','comment'),
        ('drafter','orderbook','read'),
        ('drafter','orderbook','write'),
        ('drafter','catalog','approve'),
        ('drafter','catalog','comment'),
        ('drafter','catalog','read'),
        ('drafter','catalog','write'),
        ('drafter','cut_floor','approve'),
        ('drafter','cut_floor','comment'),
        ('drafter','cut_floor','read'),
        ('drafter','cut_floor','write'),
        ('drafter','shop_floor','comment'),
        ('drafter','shop_floor','read'),
        ('drafter','estimating','comment'),
        ('drafter','estimating','read'),
        ('estimator','dashboard','read'),
        ('estimator','tracking','comment'),
        ('estimator','tracking','read'),
        ('estimator','list','comment'),
        ('estimator','list','read'),
        ('estimator','shop_dwgs','comment'),
        ('estimator','shop_dwgs','read'),
        ('estimator','isample','comment'),
        ('estimator','isample','read'),
        ('estimator','orderbook','read'),
        ('estimator','catalog','comment'),
        ('estimator','catalog','read'),
        ('estimator','cut_floor','read'),
        ('estimator','shop_floor','read'),
        ('estimator','estimating','approve'),
        ('estimator','estimating','comment'),
        ('estimator','estimating','read'),
        ('estimator','estimating','write'),
        ('purchase_officer','dashboard','read'),
        ('purchase_officer','tracking','comment'),
        ('purchase_officer','tracking','read'),
        ('purchase_officer','list','read'),
        ('purchase_officer','shop_dwgs','read'),
        ('purchase_officer','isample','read'),
        ('purchase_officer','orderbook','approve'),
        ('purchase_officer','orderbook','comment'),
        ('purchase_officer','orderbook','read'),
        ('purchase_officer','orderbook','write'),
        ('purchase_officer','catalog','comment'),
        ('purchase_officer','catalog','read'),
        ('purchase_officer','cut_floor','read'),
        ('purchase_officer','shop_floor','read'),
        ('purchase_officer','estimating','read'),
        ('viewer','dashboard','read'),
        ('viewer','tracking','read'),
        ('viewer','list','read'),
        ('viewer','shop_dwgs','read'),
        ('viewer','isample','read'),
        ('viewer','orderbook','read'),
        ('viewer','catalog','read'),
        ('viewer','cut_floor','read'),
        ('viewer','shop_floor','read'),
        ('viewer','estimating','read')
    ) AS m(role, module, action) ON m.role = g.name
    WHERE g.is_system
    ON CONFLICT DO NOTHING;

    -- Backfill: every existing user gets a workspace-wide membership in the
    -- system group matching their current auth_role.
    INSERT INTO user_group_membership (user_id, group_id, project_id)
    SELECT u.id, g.group_id, NULL
    FROM app_user u
    JOIN permission_group g
      ON g.workspace_id = u.workspace_id AND g.name = u.auth_role AND g.is_system
    ON CONFLICT (user_id, group_id, COALESCE(project_id, 0)) DO NOTHING;
    """)


def downgrade():
    op.execute("""
    DROP TABLE IF EXISTS user_group_membership;
    DROP TABLE IF EXISTS group_module_grant;
    DROP TABLE IF EXISTS permission_group;
    """)
