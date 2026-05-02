"""item_attachment: three named slots per item for Combined PDF assembly

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-02
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    CREATE TABLE item_attachment (
      item_attachment_id  bigserial   PRIMARY KEY,
      item_id             bigint      NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
      kind                text        NOT NULL CHECK (kind IN ('cv_drawing','floor_plan','site_measure')),
      file_blob_id        bigint      NOT NULL REFERENCES file_blob(file_blob_id),
      uploaded_by         bigint      NOT NULL REFERENCES app_user(id),
      uploaded_at         timestamptz NOT NULL DEFAULT now(),
      UNIQUE (item_id, kind)
    );

    CREATE INDEX idx_item_attachment_item ON item_attachment (item_id);
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-item-attachment schema is recoverable from migrations 0001-0014 only")
