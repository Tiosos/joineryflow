"""comment threads on Modules and Shop-drawing revisions (Plan V1 §29)

§29 names eight object types; 0042 shipped four (Project, Area, Room, Joinery
Item) because Task and Change are not entities in this tree and Component /
Revision were ambiguous. Settled with the user: **Component = a Module**
(`modules`, one level below a Joinery Item) and **Revision = a shop-drawing
revision** (`shop_drawing_revision`). Task and Change still have nothing to
attach to and are not added.

The shape is exactly what 0042 promised — two more nullable real FKs beside the
four, the exactly-one CHECK widened to six, and `object_type` regenerated. Both
FKs cascade, so deleting a module (including a CV re-import with `mode=replace`,
which wipes every module of an item) or a revision takes its thread with it
instead of leaving dangling comments.

`object_type` is a STORED generated column and Postgres cannot alter a
generation expression, so it is dropped and re-added. Nothing depends on it (the
indexes and constraints are on the FK columns); `varchar(8)` still fits — the
longest value, `revision`, is exactly 8.

Revision ID: 0043
Revises: 0042
Create Date: 2026-09-29
"""
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE comment
        ADD COLUMN module_id   bigint REFERENCES modules(module_id) ON DELETE CASCADE,
        ADD COLUMN revision_id bigint REFERENCES shop_drawing_revision(revision_id) ON DELETE CASCADE;

    ALTER TABLE comment DROP CONSTRAINT ck_comment_one_object;
    ALTER TABLE comment DROP COLUMN object_type;
    ALTER TABLE comment ADD COLUMN object_type varchar(8) GENERATED ALWAYS AS (
        CASE WHEN project_id  IS NOT NULL THEN 'project'
             WHEN area_id     IS NOT NULL THEN 'area'
             WHEN room_id     IS NOT NULL THEN 'room'
             WHEN module_id   IS NOT NULL THEN 'module'
             WHEN revision_id IS NOT NULL THEN 'revision'
             ELSE 'item' END
    ) STORED;
    ALTER TABLE comment ADD CONSTRAINT ck_comment_one_object
        CHECK (num_nonnulls(project_id, area_id, room_id, item_id, module_id, revision_id) = 1);

    CREATE INDEX idx_comment_module   ON comment (module_id,   created_at) WHERE module_id   IS NOT NULL;
    CREATE INDEX idx_comment_revision ON comment (revision_id, created_at) WHERE revision_id IS NOT NULL;
    """)


def downgrade():
    # Threads on a module or revision have no home in the 0042 shape, so they are
    # dropped; the four original object types are untouched.
    op.execute("""
    DELETE FROM comment WHERE module_id IS NOT NULL OR revision_id IS NOT NULL;
    ALTER TABLE comment DROP CONSTRAINT ck_comment_one_object;
    ALTER TABLE comment DROP COLUMN object_type;
    ALTER TABLE comment DROP COLUMN module_id;
    ALTER TABLE comment DROP COLUMN revision_id;
    ALTER TABLE comment ADD COLUMN object_type varchar(8) GENERATED ALWAYS AS (
        CASE WHEN project_id IS NOT NULL THEN 'project'
             WHEN area_id    IS NOT NULL THEN 'area'
             WHEN room_id    IS NOT NULL THEN 'room'
             ELSE 'item' END
    ) STORED;
    ALTER TABLE comment ADD CONSTRAINT ck_comment_one_object
        CHECK (num_nonnulls(project_id, area_id, room_id, item_id) = 1);
    """)
