"""sample: material sample wall (iSample tab) — sub-project #5c

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-02
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    CREATE TABLE sample (
      sample_id          bigserial    PRIMARY KEY,
      project_id         bigint       NOT NULL REFERENCES projects(project_id),
      title              varchar(200) NOT NULL,
      room               varchar(64),
      hex_swatch         varchar(7)   NOT NULL CHECK (hex_swatch ~ '^#[0-9A-Fa-f]{6}$'),
      supplier           varchar(128),
      status             text         NOT NULL CHECK (status IN ('pending','approved','rejected'))
                                      DEFAULT 'pending',
      review_note        text,
      reviewed_by        bigint       REFERENCES app_user(id),
      reviewed_at        timestamptz,
      photo_file_blob_id bigint       REFERENCES file_blob(file_blob_id),
      archived_at        timestamptz,
      archived_by        bigint       REFERENCES app_user(id),
      created_by         bigint       NOT NULL REFERENCES app_user(id),
      created_at         timestamptz  NOT NULL DEFAULT now(),
      updated_at         timestamptz  NOT NULL DEFAULT now()
    );

    CREATE INDEX idx_sample_project ON sample (project_id);
    CREATE INDEX idx_sample_status  ON sample (project_id, status);
    CREATE INDEX idx_sample_active  ON sample (project_id) WHERE archived_at IS NULL;
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-sample schema is recoverable from migrations 0001-0015 only")
