"""tasks in Global Search (Q576's list grows by one; spec docs/archive/2026-10-21-tasks.md)

A task joins the search outbox like every other indexed table (`0033`'s pattern): a row trigger
on `task`, and the outbox `entity_type` check widened by `'task'`. A task's document embeds
values that live elsewhere, so four more fan-out triggers (additive: the existing
`search_fanout_projects` / `search_fanout_cutlist` triggers are left as they are, because their
children and `WHEN` clauses are right for the documents they feed):

- `projects` (`project_code`) -> tasks on that project (the document's label);
- `items` (`code`, `num`, `deleted`) -> tasks on that item: the label, and a soft-deleted item
  drops its tasks from the index (the loader returns nothing, so the worker deletes the document);
- `cutlist` (`name`, `deleted`) -> tasks on that cutlist, likewise (`cutlist_no` is already
  covered by nothing for tasks, so the `WHEN` names it too);
- `app_user` (`full_name`) -> tasks assigned to that user (the assignee's name is in the body).

The upgrade queues every existing task so the next worker run indexes them.

Revision ID: 0081
Revises: 0080
Create Date: 2026-10-21
"""
from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None

_ENTITIES = ("project", "item", "cutlist", "order", "supplier", "drawing", "sample", "customer", "estimate")
_TABLES = ("board_materials", "hardware_materials", "custom_made", "benchtop_materials", "appliances",
           "equipment_hire", "edging_materials", "glass_materials", "timber_materials")

# (trigger, parent table, parent pk column, WHEN, child fk)
_FANOUTS = (
    ("search_fanout_projects_task", "projects", "project_id",
     "OLD.project_code IS DISTINCT FROM NEW.project_code", "project_id"),
    ("search_fanout_items_task", "items", "item_id",
     "OLD.code IS DISTINCT FROM NEW.code OR OLD.num IS DISTINCT FROM NEW.num"
     " OR OLD.deleted IS DISTINCT FROM NEW.deleted", "item_id"),
    ("search_fanout_cutlist_task", "cutlist", "cutlist_id",
     "OLD.cutlist_no IS DISTINCT FROM NEW.cutlist_no OR OLD.name IS DISTINCT FROM NEW.name"
     " OR OLD.deleted IS DISTINCT FROM NEW.deleted", "cutlist_id"),
    ("search_fanout_app_user_task", "app_user", "id",
     "OLD.full_name IS DISTINCT FROM NEW.full_name", "assignee_id"),
)


def _in(values):
    return ", ".join(f"'{v}'" for v in values)


def _recheck(values):
    op.execute("ALTER TABLE search_outbox DROP CONSTRAINT IF EXISTS search_outbox_entity_type_check;")
    op.execute("ALTER TABLE search_outbox ADD CONSTRAINT search_outbox_entity_type_check"
               f" CHECK (entity_type IN ({_in(values)}));")


def upgrade():
    _recheck(_ENTITIES + _TABLES + ("task",))
    op.execute("""
    CREATE TRIGGER search_enqueue_task
    AFTER INSERT OR UPDATE OR DELETE ON task
    FOR EACH ROW EXECUTE FUNCTION search_enqueue('task', 'task_id');
    """)
    for name, parent, pk, when, fk in _FANOUTS:
        op.execute(f"""
        CREATE TRIGGER {name}
        AFTER UPDATE ON {parent}
        FOR EACH ROW WHEN ({when})
        EXECUTE FUNCTION search_fanout('{pk}', 'task', 'task', 'task_id', '{fk}');
        """)
    op.execute("INSERT INTO search_outbox (entity_type, entity_id) SELECT 'task', task_id FROM task ORDER BY task_id;")


def downgrade():
    for name, parent, _, _, _ in _FANOUTS:
        op.execute(f"DROP TRIGGER IF EXISTS {name} ON {parent};")
    op.execute("DROP TRIGGER IF EXISTS search_enqueue_task ON task;")
    op.execute("DELETE FROM search_outbox WHERE entity_type = 'task';")
    _recheck(_ENTITIES + _TABLES)
