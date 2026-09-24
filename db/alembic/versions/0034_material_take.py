"""Material Take and Material Summary (sub-project #12, Plan V1 §19-§20)

A **Material Take** is a per-Joinery-Item statement of what the item needs:
generated from its parts and hardware lines, adjusted by a person, then
approved and frozen (Q80, Q495). Changing an approved take means a new
version (Q500), so `material_take` carries `version` and `status`, and two
partial unique indexes keep at most one draft and one approved take per item.

A **Material Summary** consolidates the current approved takes of a project,
one line per material, and keeps the per-item breakdown in
`material_summary_source` together with the take version each figure came
from — that is what makes a line detectably stale when a take advances.

Nothing here is indexed for search (Q576 / Q579 fixed the type list), so no
`0033` search triggers are added.

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-24
"""
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

_MATERIAL_TYPES = "('BOARD','HARDWARE','CUSTOM','BENCHTOP','APPLIANCE','HIRE','OTHER')"
_UNITS = "('sheet','each','m','m2')"


def upgrade():
    op.execute(f"""
    CREATE TABLE material_take (
        take_id       bigserial   PRIMARY KEY,
        item_id       bigint      NOT NULL REFERENCES items (item_id) ON DELETE CASCADE,
        version       integer     NOT NULL CHECK (version >= 1),
        status        text        NOT NULL CHECK (status IN ('draft','approved','superseded')),
        generated_at  timestamptz NOT NULL,
        approved_by   bigint      REFERENCES app_user (id),
        approved_at   timestamptz,
        created_by    bigint      NOT NULL REFERENCES app_user (id),
        created_at    timestamptz NOT NULL DEFAULT now(),
        notes         text,
        UNIQUE (item_id, version),
        CHECK ((status = 'draft') = (approved_at IS NULL))
    );
    CREATE UNIQUE INDEX uniq_take_draft    ON material_take (item_id) WHERE status = 'draft';
    CREATE UNIQUE INDEX uniq_take_approved ON material_take (item_id) WHERE status = 'approved';

    CREATE TABLE material_take_line (
        line_id        bigserial PRIMARY KEY,
        take_id        bigint    NOT NULL REFERENCES material_take (take_id) ON DELETE CASCADE,
        material_type  text      NOT NULL CHECK (material_type IN {_MATERIAL_TYPES}),
        material_id    bigint,
        description    text      NOT NULL,
        unit           text      NOT NULL CHECK (unit IN {_UNITS}),
        qty_generated  numeric,
        wastage_pct    numeric   NOT NULL DEFAULT 0 CHECK (wastage_pct >= 0),
        qty            numeric   NOT NULL CHECK (qty >= 0),
        source         text      NOT NULL CHECK (source IN ('generated','manual')),
        note           text,
        CHECK (material_type <> 'OTHER' OR material_id IS NULL),
        CHECK ((source = 'generated') = (qty_generated IS NOT NULL))
    );
    CREATE INDEX idx_take_line_take ON material_take_line (take_id);

    CREATE TABLE material_take_review (
        review_id    bigserial   PRIMARY KEY,
        take_id      bigint      NOT NULL REFERENCES material_take (take_id) ON DELETE CASCADE,
        detected_at  timestamptz NOT NULL,
        outcome      text        CHECK (outcome IN ('no_impact','partial','full')),
        note         text,
        reviewed_by  bigint      REFERENCES app_user (id),
        reviewed_at  timestamptz
    );

    CREATE TABLE material_summary (
        summary_id   bigserial   PRIMARY KEY,
        project_id   bigint      NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
        status       text        NOT NULL CHECK (status IN ('draft','confirmed')),
        confirmed_by bigint      REFERENCES app_user (id),
        confirmed_at timestamptz,
        created_by   bigint      NOT NULL REFERENCES app_user (id),
        created_at   timestamptz NOT NULL DEFAULT now(),
        updated_at   timestamptz NOT NULL DEFAULT now(),
        CHECK ((status = 'confirmed') = (confirmed_at IS NOT NULL))
    );
    CREATE INDEX idx_summary_project ON material_summary (project_id, summary_id DESC);

    CREATE TABLE material_summary_line (
        line_id          bigserial PRIMARY KEY,
        summary_id       bigint    NOT NULL REFERENCES material_summary (summary_id) ON DELETE CASCADE,
        material_type    text      NOT NULL CHECK (material_type IN {_MATERIAL_TYPES}),
        material_id      bigint,
        description      text      NOT NULL,
        unit             text      NOT NULL CHECK (unit IN {_UNITS}),
        qty_consolidated numeric   NOT NULL,
        qty_confirmed    numeric   CHECK (qty_confirmed >= 0),
        note             text
    );
    CREATE INDEX idx_summary_line_summary ON material_summary_line (summary_id);

    CREATE TABLE material_summary_source (
        summary_line_id bigint  NOT NULL REFERENCES material_summary_line (line_id) ON DELETE CASCADE,
        -- CASCADE, not RESTRICT: items can be hard-deleted
        -- (items/queries.py, related_parts/queries.py). Losing a source row
        -- leaves the line's qty_consolidated intact and makes the sources no
        -- longer sum to it, which the summary reports as stale.
        take_line_id    bigint  NOT NULL REFERENCES material_take_line (line_id) ON DELETE CASCADE,
        take_id         bigint  NOT NULL REFERENCES material_take (take_id) ON DELETE CASCADE,
        take_version    integer NOT NULL,
        qty             numeric NOT NULL,
        PRIMARY KEY (summary_line_id, take_line_id)
    );
    """)


def downgrade():
    op.execute("""
    DROP TABLE IF EXISTS material_summary_source;
    DROP TABLE IF EXISTS material_summary_line;
    DROP TABLE IF EXISTS material_summary;
    DROP TABLE IF EXISTS material_take_review;
    DROP TABLE IF EXISTS material_take_line;
    DROP TABLE IF EXISTS material_take;
    """)
