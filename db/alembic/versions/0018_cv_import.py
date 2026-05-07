"""cv_import_run register — sub-project #7b

Adds cv_import_run with status CHECK + indexes per spec §3.1.

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-08
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    CREATE TABLE cv_import_run (
      cv_import_run_id  bigserial    PRIMARY KEY,
      project_id        bigint       NOT NULL REFERENCES projects(project_id),
      item_id           bigint       NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
      source_filename   varchar(255) NOT NULL,
      sha256            char(64)     NOT NULL,
      row_count         int          NOT NULL DEFAULT 0,
      status            text         NOT NULL CHECK (status IN ('preview','committed','failed')),
      started_at        timestamptz  NOT NULL DEFAULT now(),
      completed_at      timestamptz,
      error_log         jsonb        NOT NULL DEFAULT '[]'::jsonb,
      created_by        bigint       NOT NULL REFERENCES app_user(id)
    );
    CREATE INDEX idx_cv_import_run_item   ON cv_import_run (item_id);
    CREATE INDEX idx_cv_import_run_status ON cv_import_run (project_id, status);
    """)


def downgrade():
    op.execute("-- intentionally not reversible; recover via 0001-0017 only")
