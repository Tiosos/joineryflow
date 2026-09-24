"""cutlist — the entity that will own the production workflow

Plan V1 Q410–Q413 makes the cutlist a thing in its own right: a six-digit
company reference that **several Joinery Items can share**, carrying one set of
production-stage completions between them. Today there is no such entity —
`items.num` *is* the cutlist number, one per item, and the Tracking screen
renders it in the CUTLIST column.

This migration creates the entity and links items to it. It does **not** move
the workflow yet: `item_stages` stays exactly as it is, and stage completions
are fanned out to linked items later (Q439), by the Shop Floor rework. Nothing
reads `items.cutlist_id` until then.

Per Q540, **every existing item gets its own cutlist carrying its current
number**, so nobody loses the number they recognise and cutlist *sharing* only
begins with new work. Per Q440 the link is nullable — an item may sit with no
cutlist indefinitely, which Q429 already assumes when it allows a related-part
order before the parent has a cutlist number.

## One number source (Q541)

Item IDs and cutlist numbers draw from **one** sequence, so a six-digit number
never means two different things. That matters more than it first appears,
because the tree currently has **two** different and mutually inconsistent ways
of allocating `items.num`:

* `apps/api/app/items/queries.py` — `nextval('items_item_id_seq') + 100000`
* `apps/api/app/estimating/queries.py` — `SELECT COALESCE(MAX(num), 0) + 1`

`items.num` is UNIQUE (`items_num_key`), and the second form is a read-then-
insert with no lock, so two concurrent estimate conversions pick the same
number and the loser fails with a unique violation. That was reproduced
directly against this schema before writing this migration. Both call sites are
repointed at `joinery_number_seq` by the backend tasks that follow; the
sequence is seeded above **both** existing watermarks so it can never collide
with a number either scheme already handed out.

## Six digits

New numbers are six digits because the sequence starts at or above 100000.
Historical numbers are carried across **verbatim** — no CHECK constrains their
width. Q540's purpose is that existing numbers survive recognisably, and a
width constraint would fail the migration on any legacy value that is shorter.

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-18
"""
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE SEQUENCE joinery_number_seq AS integer MINVALUE 100000 START WITH 100000;

    CREATE TABLE cutlist (
        cutlist_id BIGSERIAL    PRIMARY KEY,
        project_id bigint       NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
        cutlist_no integer      NOT NULL UNIQUE,
        name       varchar(255),
        created_by bigint       REFERENCES app_user(id),
        created_at timestamptz  NOT NULL DEFAULT now(),
        updated_at timestamptz  NOT NULL DEFAULT now()
    );
    CREATE INDEX idx_cutlist_project ON cutlist (project_id);

    -- Nullable, and a single column: an item may have no cutlist (Q440) and
    -- can never have two (Q411).
    ALTER TABLE items
        ADD COLUMN cutlist_id bigint REFERENCES cutlist(cutlist_id) ON DELETE SET NULL;
    CREATE INDEX idx_items_cutlist ON items (cutlist_id);
    """)

    # Seed the shared sequence above every number either existing scheme could
    # already have issued: the highest num in use, and whatever the
    # items_item_id_seq + 100000 form would next produce.
    op.execute("""
    SELECT setval('joinery_number_seq', GREATEST(
        100000,
        COALESCE((SELECT MAX(num) FROM items), 0),
        COALESCE((SELECT last_value + 100000 FROM items_item_id_seq), 0)
    ));
    """)

    # Q540: one cutlist per existing item, carrying that item's number.
    op.execute("""
    INSERT INTO cutlist (project_id, cutlist_no, name, created_at)
    SELECT i.project_id, i.num, i.code, i.created_at
    FROM items i
    ON CONFLICT (cutlist_no) DO NOTHING;
    """)

    op.execute("""
    UPDATE items i
       SET cutlist_id = c.cutlist_id
      FROM cutlist c
     WHERE c.cutlist_no = i.num;
    """)


def downgrade():
    op.execute("""
    DROP INDEX IF EXISTS idx_items_cutlist;
    ALTER TABLE items DROP COLUMN IF EXISTS cutlist_id;
    DROP TABLE IF EXISTS cutlist;
    DROP SEQUENCE IF EXISTS joinery_number_seq;
    """)
