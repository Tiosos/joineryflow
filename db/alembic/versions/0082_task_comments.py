"""comment threads on a Task (Plan V1 §29; spec docs/archive/2026-10-21-tasks.md)

§29 names Task among the things a thread attaches to, and `0042` / `0043` held it back because no
task entity existed. It does now (`0080`), so `comment` gains a seventh real FK, `task_id`, with the
same shape as `0043`'s module / revision: the exactly-one CHECK widened to seven, `object_type`
regenerated (a STORED generated column cannot be altered, so it is dropped and re-added; `'task'`
fits the existing `varchar(8)`), and an index. A task never hard-deletes, but the FK cascades like
its siblings.

Who may read or write a task's thread is **not** in the schema: it follows the task's own rules
(`tasks/queries.py`), which a CHECK cannot say.

Downgrade deletes task threads (they have no home in the `0043` shape), as `0043`'s did for its types.

Revision ID: 0082
Revises: 0081
Create Date: 2026-10-22
"""
from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE comment
        ADD COLUMN task_id bigint REFERENCES task(task_id) ON DELETE CASCADE;

    ALTER TABLE comment DROP CONSTRAINT ck_comment_one_object;
    ALTER TABLE comment DROP COLUMN object_type;
    ALTER TABLE comment ADD COLUMN object_type varchar(8) GENERATED ALWAYS AS (
        CASE WHEN project_id  IS NOT NULL THEN 'project'
             WHEN area_id     IS NOT NULL THEN 'area'
             WHEN room_id     IS NOT NULL THEN 'room'
             WHEN module_id   IS NOT NULL THEN 'module'
             WHEN revision_id IS NOT NULL THEN 'revision'
             WHEN task_id     IS NOT NULL THEN 'task'
             ELSE 'item' END
    ) STORED;
    ALTER TABLE comment ADD CONSTRAINT ck_comment_one_object
        CHECK (num_nonnulls(project_id, area_id, room_id, item_id, module_id, revision_id, task_id) = 1);

    CREATE INDEX idx_comment_task ON comment (task_id, created_at) WHERE task_id IS NOT NULL;
    """)


def downgrade():
    op.execute("""
    DELETE FROM comment WHERE task_id IS NOT NULL;
    ALTER TABLE comment DROP CONSTRAINT ck_comment_one_object;
    ALTER TABLE comment DROP COLUMN object_type;
    ALTER TABLE comment DROP COLUMN task_id;
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
    """)
