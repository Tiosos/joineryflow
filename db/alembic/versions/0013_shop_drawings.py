"""shop drawings: file_blob + shop_drawing + shop_drawing_revision

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-01
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    -- Generic file-upload subsystem (also reused by future #5b item attachments).
    CREATE TABLE file_blob (
      file_blob_id      bigserial PRIMARY KEY,
      workspace_id      bigint      NOT NULL REFERENCES workspace(id),
      sha256            text        NOT NULL,
      mime              text        NOT NULL,
      byte_size         bigint      NOT NULL CHECK (byte_size > 0 AND byte_size <= 26214400),
      original_filename text        NOT NULL,
      storage_key       text        NOT NULL,
      uploaded_by       bigint      NOT NULL REFERENCES app_user(id),
      uploaded_at       timestamptz NOT NULL DEFAULT now(),
      UNIQUE (workspace_id, sha256)
    );
    CREATE INDEX idx_file_blob_workspace ON file_blob (workspace_id);

    -- Shop drawings: project-scoped, room as free-text tag (matches items.room).
    CREATE TABLE shop_drawing (
      drawing_id            bigserial PRIMARY KEY,
      project_id            bigint      NOT NULL REFERENCES projects(project_id),
      title                 text        NOT NULL,
      room                  text,
      current_revision_id   bigint,
      archived_at           timestamptz,
      archived_by           bigint      REFERENCES app_user(id),
      created_by            bigint      NOT NULL REFERENCES app_user(id),
      created_at            timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX idx_shop_drawing_project ON shop_drawing (project_id);
    CREATE INDEX idx_shop_drawing_room    ON shop_drawing (project_id, room);
    CREATE INDEX idx_shop_drawing_active  ON shop_drawing (project_id) WHERE archived_at IS NULL;

    -- Revisions: one row per uploaded version.
    CREATE TABLE shop_drawing_revision (
      revision_id    bigserial   PRIMARY KEY,
      drawing_id     bigint      NOT NULL REFERENCES shop_drawing(drawing_id) ON DELETE CASCADE,
      rev_no         int         NOT NULL CHECK (rev_no >= 1),
      file_blob_id   bigint      NOT NULL REFERENCES file_blob(file_blob_id),
      status         text        NOT NULL CHECK (status IN ('draft','pending','approved','rejected')),
      uploaded_by    bigint      NOT NULL REFERENCES app_user(id),
      uploaded_at    timestamptz NOT NULL DEFAULT now(),
      reviewed_by    bigint      REFERENCES app_user(id),
      reviewed_at    timestamptz,
      review_note    text,
      UNIQUE (drawing_id, rev_no)
    );
    CREATE INDEX idx_drawing_revision_drawing ON shop_drawing_revision (drawing_id);
    CREATE INDEX idx_drawing_revision_status  ON shop_drawing_revision (status);

    -- Enforce "at most one revision in flight per drawing".
    CREATE UNIQUE INDEX uniq_drawing_inflight
      ON shop_drawing_revision (drawing_id)
      WHERE status IN ('draft','pending');

    -- Wire the back-reference (deferred so both tables exist first).
    ALTER TABLE shop_drawing
      ADD CONSTRAINT fk_shop_drawing_current_revision
        FOREIGN KEY (current_revision_id) REFERENCES shop_drawing_revision(revision_id);
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-shop-drawings schema is recoverable from migrations 0001-0012 only")
