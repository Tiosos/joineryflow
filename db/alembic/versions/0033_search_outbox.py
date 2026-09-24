"""Global Search outbox, fed by triggers (sub-project #11)

`search_outbox` is the transactional outbox **Q575** chose: every write to an
indexed table records *which* row changed, in the writer's own transaction,
and the `search-worker` later reads the row's current state and pushes it to
Meilisearch. The outbox holds identity only — never a payload — so processing
is idempotent and order-independent.

**These are the repo's first triggers** (Q578). Nothing in `0001`–`0032`
creates one, so they are invisible to anyone reading only the Python. They
were chosen over an `enqueue()` call beside each write because 13 modules
write these tables — `catalog` and `cv` through dynamic SQL a grep misses —
and because triggers also catch seed and migration data (CLAUDE.md's
*recurring trap*: backfills only touch rows that exist when they run).

Two functions:

- `search_enqueue(kind, id_column)` — the per-row trigger on every indexed
  table. It also sits on `estimate_revision` with `('estimate', 'estimate_id')`,
  because an estimate's document shows its current revision's status.
- `search_fanout()` — on parent tables whose values are *embedded* in child
  documents (project code, area / room names, cutlist number, supplier and
  customer names). It fires only when one of those columns actually changed
  (the `WHEN` clauses below), so an ordinary save never fans out.

Deletes need no special case: `ON DELETE CASCADE` / `SET NULL` fire the
children's own row triggers, and the worker turns "row not found" into a
document delete.

The upgrade backfills every existing row into the outbox, so the first worker
run indexes the whole tree with no manual step.

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-24
"""
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

# (outbox kind, table, primary key). The six catalog tables keep their own
# kind because their primary keys overlap.
SOURCES = [
    ("project", "projects", "project_id"),
    ("item", "items", "item_id"),
    ("cutlist", "cutlist", "cutlist_id"),
    ("order", "purchase_orders", "po_id"),
    ("supplier", "vendors", "vendor_id"),
    ("drawing", "shop_drawing", "drawing_id"),
    ("sample", "sample", "sample_id"),
    ("customer", "customer", "customer_id"),
    ("estimate", "estimate", "estimate_id"),
    ("board_materials", "board_materials", "material_id"),
    ("hardware_materials", "hardware_materials", "material_id"),
    ("custom_made", "custom_made", "material_id"),
    ("benchtop_materials", "benchtop_materials", "material_id"),
    ("appliances", "appliances", "material_id"),
    ("equipment_hire", "equipment_hire", "hire_id"),
]

# (parent table, embedded columns, [(child kind, child table, child pk, fk)])
FANOUTS = [
    ("projects", ["project_code", "name"], [
        ("item", "items", "item_id", "project_id"),
        ("cutlist", "cutlist", "cutlist_id", "project_id"),
        ("order", "purchase_orders", "po_id", "project_id"),
        ("drawing", "shop_drawing", "drawing_id", "project_id"),
        ("sample", "sample", "sample_id", "project_id"),
    ]),
    ("area", ["name"], [("item", "items", "item_id", "area_id")]),
    ("room", ["rm_no", "rm_desc"], [("item", "items", "item_id", "room_id")]),
    ("cutlist", ["cutlist_no"], [("item", "items", "item_id", "cutlist_id")]),
    ("vendors", ["name"], [("order", "purchase_orders", "po_id", "vendor_id")]),
    ("customer", ["name"], [("estimate", "estimate", "estimate_id", "customer_id")]),
]

KINDS = [k for k, _, _ in SOURCES]


def upgrade():
    kinds = ", ".join(f"'{k}'" for k in KINDS)
    op.execute(f"""
    CREATE TABLE search_outbox (
        outbox_id   bigserial   PRIMARY KEY,
        entity_type text        NOT NULL CHECK (entity_type IN ({kinds})),
        entity_id   bigint      NOT NULL,
        enqueued_at timestamptz NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE FUNCTION search_enqueue() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE
        r jsonb;
    BEGIN
        IF TG_OP = 'DELETE' THEN r := to_jsonb(OLD); ELSE r := to_jsonb(NEW); END IF;
        IF r ->> TG_ARGV[1] IS NOT NULL THEN
            INSERT INTO search_outbox (entity_type, entity_id)
            VALUES (TG_ARGV[0], (r ->> TG_ARGV[1])::bigint);
        END IF;
        RETURN NULL;
    END $$;
    """)

    # search_fanout(parent_pk, kind, table, pk, fk [, kind, table, pk, fk ...])
    op.execute("""
    CREATE FUNCTION search_fanout() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE
        parent_id bigint := (to_jsonb(NEW) ->> TG_ARGV[0])::bigint;
        i int := 1;
    BEGIN
        WHILE i < TG_NARGS LOOP
            EXECUTE format(
                'INSERT INTO search_outbox (entity_type, entity_id) '
                'SELECT %L, %I FROM %I WHERE %I = $1',
                TG_ARGV[i], TG_ARGV[i + 2], TG_ARGV[i + 1], TG_ARGV[i + 3])
            USING parent_id;
            i := i + 4;
        END LOOP;
        RETURN NULL;
    END $$;
    """)

    for kind, table, pk in SOURCES:
        op.execute(f"""
        CREATE TRIGGER search_enqueue_{table}
        AFTER INSERT OR UPDATE OR DELETE ON {table}
        FOR EACH ROW EXECUTE FUNCTION search_enqueue('{kind}', '{pk}');
        """)
    op.execute("""
    CREATE TRIGGER search_enqueue_estimate_revision
    AFTER INSERT OR UPDATE OR DELETE ON estimate_revision
    FOR EACH ROW EXECUTE FUNCTION search_enqueue('estimate', 'estimate_id');
    """)

    parent_pk = {"projects": "project_id", "area": "area_id", "room": "room_id",
                 "cutlist": "cutlist_id", "vendors": "vendor_id",
                 "customer": "customer_id"}
    for parent, cols, children in FANOUTS:
        when = " OR ".join(f"OLD.{c} IS DISTINCT FROM NEW.{c}" for c in cols)
        args = [parent_pk[parent]]
        for c_kind, c_table, c_pk, c_fk in children:
            args += [c_kind, c_table, c_pk, c_fk]
        op.execute(f"""
        CREATE TRIGGER search_fanout_{parent}
        AFTER UPDATE ON {parent}
        FOR EACH ROW WHEN ({when})
        EXECUTE FUNCTION search_fanout({", ".join(f"'{a}'" for a in args)});
        """)

    for kind, table, pk in SOURCES:
        op.execute(f"""
        INSERT INTO search_outbox (entity_type, entity_id)
        SELECT '{kind}', {pk} FROM {table} ORDER BY {pk};
        """)


def downgrade():
    for parent, _, _ in FANOUTS:
        op.execute(f"DROP TRIGGER IF EXISTS search_fanout_{parent} ON {parent};")
    op.execute("DROP TRIGGER IF EXISTS search_enqueue_estimate_revision ON estimate_revision;")
    for _, table, _ in SOURCES:
        op.execute(f"DROP TRIGGER IF EXISTS search_enqueue_{table} ON {table};")
    op.execute("DROP FUNCTION IF EXISTS search_fanout();")
    op.execute("DROP FUNCTION IF EXISTS search_enqueue();")
    op.execute("DROP TABLE IF EXISTS search_outbox;")
