"""auth

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-22
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    CREATE TABLE workspace (
      id          BIGSERIAL PRIMARY KEY,
      slug        citext NOT NULL UNIQUE,
      name        text NOT NULL,
      created_at  timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE app_user (
      id            BIGSERIAL PRIMARY KEY,
      workspace_id  BIGINT NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
      email         citext NOT NULL,
      full_name     text NOT NULL,
      password_hash text NOT NULL,
      auth_role     text NOT NULL CHECK (auth_role IN
        ('admin','manager','editor','purchase_officer','viewer')),
      jtbd_role     text,
      is_active     boolean NOT NULL DEFAULT true,
      created_at    timestamptz NOT NULL DEFAULT now(),
      UNIQUE (workspace_id, email)
    );

    CREATE TABLE session (
      token_hash      bytea PRIMARY KEY,
      user_id         BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
      created_at      timestamptz NOT NULL DEFAULT now(),
      last_seen_at    timestamptz NOT NULL DEFAULT now(),
      hard_expires_at timestamptz NOT NULL,
      revoked_at      timestamptz
    );
    CREATE INDEX session_user_idx ON session(user_id);

    CREATE TABLE audit_log (
      id            BIGSERIAL PRIMARY KEY,
      workspace_id  BIGINT NOT NULL,
      actor_id      BIGINT,
      event         text NOT NULL,
      target        text,
      payload       jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at    timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX audit_workspace_time_idx ON audit_log(workspace_id, created_at DESC);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS audit_log, session, app_user, workspace CASCADE;")
