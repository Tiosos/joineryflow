"""item & project detail 2.0 — close-out + contacts + lift access + queries + documents

Adds:
- projects.closed_at, closed_by
- project_contact (office + site)
- project_lift_access
- item_query (Q&A per item)
- item_document (open Document Register beyond the 4 named attachment slots)
- item_attachment kind CHECK widened to (cv_drawing, sketchup, cabvision, floor_plan, site_measure)
- project_labour_hours_view (returns zero; #14 populates)

Revision ID: 0036
Revises: 0035
Create Date: 2026-05-27
"""
from alembic import op


revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE projects
        ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS closed_by BIGINT REFERENCES app_user(id) ON DELETE SET NULL;

    CREATE TABLE IF NOT EXISTS project_contact (
      contact_id BIGSERIAL PRIMARY KEY,
      project_id BIGINT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
      kind       VARCHAR(8) NOT NULL CHECK (kind IN ('office','site')),
      position   VARCHAR(64),
      name       VARCHAR(128) NOT NULL,
      email      VARCHAR(255),
      mobile     VARCHAR(32),
      notes      TEXT,
      sort_order INT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      created_by BIGINT REFERENCES app_user(id) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS idx_project_contact_project
        ON project_contact (project_id, kind, sort_order);

    CREATE TABLE IF NOT EXISTS project_lift_access (
      project_id           BIGINT PRIMARY KEY REFERENCES projects(project_id) ON DELETE CASCADE,
      notes                TEXT,
      sketch_file_blob_id  BIGINT REFERENCES file_blob(file_blob_id) ON DELETE SET NULL,
      updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_by           BIGINT REFERENCES app_user(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS item_query (
      query_id      BIGSERIAL PRIMARY KEY,
      item_id       BIGINT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
      asked_by      BIGINT REFERENCES app_user(id) ON DELETE SET NULL,
      asked_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
      question      TEXT NOT NULL,
      answered_by   BIGINT REFERENCES app_user(id) ON DELETE SET NULL,
      answered_at   TIMESTAMPTZ,
      answer        TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_item_query_item
        ON item_query (item_id, asked_at DESC);

    CREATE TABLE IF NOT EXISTS item_document (
      document_id   BIGSERIAL PRIMARY KEY,
      item_id       BIGINT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
      file_blob_id  BIGINT NOT NULL REFERENCES file_blob(file_blob_id),
      label         VARCHAR(128),
      sort_order    INT NOT NULL DEFAULT 0,
      uploaded_by   BIGINT REFERENCES app_user(id) ON DELETE SET NULL,
      uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_item_document_item
        ON item_document (item_id, sort_order);

    -- Widen attachment kind CHECK; keep 'cv_drawing' as a legacy synonym so
    -- existing #5b tests + production rows don't break.
    ALTER TABLE item_attachment DROP CONSTRAINT IF EXISTS item_attachment_kind_check;
    ALTER TABLE item_attachment
        ADD CONSTRAINT item_attachment_kind_check
        CHECK (kind IN ('cv_drawing','sketchup','cabvision','floor_plan','site_measure'));

    -- Labour hours placeholder (zero per project). #14 (MyHours) replaces this view.
    CREATE OR REPLACE VIEW project_labour_hours_view AS
    SELECT
        p.project_id,
        0::numeric AS site_install,
        0::numeric AS assembly,
        0::numeric AS administration
    FROM projects p;
    """)


def downgrade():
    op.execute("""
    DROP VIEW IF EXISTS project_labour_hours_view;

    ALTER TABLE item_attachment DROP CONSTRAINT IF EXISTS item_attachment_kind_check;
    ALTER TABLE item_attachment
        ADD CONSTRAINT item_attachment_kind_check
        CHECK (kind IN ('cv_drawing','floor_plan','site_measure'));

    DROP TABLE IF EXISTS item_document;
    DROP TABLE IF EXISTS item_query;
    DROP TABLE IF EXISTS project_lift_access;
    DROP TABLE IF EXISTS project_contact;

    ALTER TABLE projects
        DROP COLUMN IF EXISTS closed_by,
        DROP COLUMN IF EXISTS closed_at;
    """)
