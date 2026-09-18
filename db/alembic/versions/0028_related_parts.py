"""related-part rows — metal / benchtop / cushion beneath a Joinery Item

Plan V1 Q416–Q424 adds a second kind of row to Tracking. A **related part** is
a metal, benchtop or cushion item that belongs to one Joinery Item: it has its
own Item ID, shares its parent's Group ID, carries its own status (Q450), gets
**no cutlist number** (Q417) and shows **no workflow stages at all** (Q419).
Its leftmost Tracking column shows the issued supplier-order number instead of
a cutlist number, linking into Orderbook (Q418).

Per Q447 these are rows in `items`, distinguished by `row_type`, rather than a
separate table — so a related part gets its own Item ID for free and inherits
workspace isolation unchanged. The cost is that **every query reading `items`
must now filter on `row_type`**; that is task B1, and it is deliberately the
first backend task because a missed call site leaks related parts into surfaces
that must never see them.

## What the database enforces, and what it cannot

Structural, in this migration:

* a related part **must** have a parent, and a Joinery Item **must not** (Q449
  allows one level of nesting only);
* that parent is **itself a Joinery Item**, enforced by a composite foreign key
  against `(item_id, row_type)` — the same technique `0026` uses to keep a room
  inside its area. Without it a related part could hang off another related
  part, which Q449 forbids;
* a related part **cannot hold a cutlist** (Q417);
* a related part **must** carry a type from the `related_part_type` lookup, and
  a Joinery Item must not.

Not structural — enforced in application code:

* **no workflow stages for a related part** (Q419). `item_stages` is keyed by
  item and a CHECK cannot reach another table, so this is B1's filter plus its
  test, not a constraint.

## Group ID (Q416, Q453)

A Joinery Item's Group ID **is its own Item ID** — that is, its `num`. A
related part carries its parent's. `items.group_id` already exists as free
text, and is written by nothing today (verified: no seed path, no route, and
`ItemMetadataPanel.tsx` carries the comment "group_id is read-only in v1"), so
the backfill has nothing to preserve and simply populates it.

The type list is a lookup table rather than a CHECK so IT can add a fourth kind
without a migration (Q448), matching how `stages` and `status_options` already
work.

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-18
"""
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE related_part_type (
        type_key   varchar(16) PRIMARY KEY,
        label      varchar(64) NOT NULL,
        sort_order smallint    NOT NULL DEFAULT 0
    );
    INSERT INTO related_part_type (type_key, label, sort_order) VALUES
        ('metal',    'Metal',    10),
        ('benchtop', 'Benchtop', 20),
        ('cushion',  'Cushion',  30);

    ALTER TABLE items
        ADD COLUMN row_type varchar(16) NOT NULL DEFAULT 'joinery_item',
        ADD COLUMN parent_item_id bigint,
        ADD COLUMN related_part_type_key varchar(16) REFERENCES related_part_type(type_key);

    ALTER TABLE items
        ADD CONSTRAINT ck_items_row_type
        CHECK (row_type IN ('joinery_item', 'related_part'));

    -- Target for the composite FK below: lets a child require that its parent
    -- row is specifically a joinery_item, not merely that it exists.
    ALTER TABLE items ADD CONSTRAINT uq_items_id_row_type UNIQUE (item_id, row_type);

    -- Always 'joinery_item' when a parent is set, so the FK can only be
    -- satisfied by a parent whose own row_type is 'joinery_item' (Q449).
    ALTER TABLE items
        ADD COLUMN parent_row_type varchar(16)
        GENERATED ALWAYS AS (
            CASE WHEN parent_item_id IS NULL THEN NULL ELSE 'joinery_item' END
        ) STORED;

    ALTER TABLE items
        ADD CONSTRAINT fk_items_parent_is_joinery_item
        FOREIGN KEY (parent_item_id, parent_row_type)
        REFERENCES items (item_id, row_type)
        ON DELETE CASCADE;

    -- A related part hangs off exactly one parent; a Joinery Item has none.
    ALTER TABLE items
        ADD CONSTRAINT ck_items_parent_matches_row_type
        CHECK (
            (row_type = 'related_part'  AND parent_item_id IS NOT NULL)
         OR (row_type = 'joinery_item'  AND parent_item_id IS NULL)
        );

    -- Q417: related parts never carry a cutlist number.
    ALTER TABLE items
        ADD CONSTRAINT ck_items_related_part_has_no_cutlist
        CHECK (row_type = 'joinery_item' OR cutlist_id IS NULL);

    -- A related part is always one of the configured kinds; a Joinery Item
    -- is never one of them.
    ALTER TABLE items
        ADD CONSTRAINT ck_items_part_type_matches_row_type
        CHECK (
            (row_type = 'related_part'  AND related_part_type_key IS NOT NULL)
         OR (row_type = 'joinery_item'  AND related_part_type_key IS NULL)
        );

    CREATE INDEX idx_items_row_type ON items (row_type);
    CREATE INDEX idx_items_parent   ON items (parent_item_id);
    CREATE INDEX idx_items_group    ON items (group_id);
    """)

    # Q416/Q453: a Joinery Item's Group ID is its own Item ID.
    op.execute("""
    UPDATE items
       SET group_id = num::text
     WHERE row_type = 'joinery_item';
    """)


def downgrade():
    op.execute("""
    DROP INDEX IF EXISTS idx_items_group;
    DROP INDEX IF EXISTS idx_items_parent;
    DROP INDEX IF EXISTS idx_items_row_type;
    ALTER TABLE items DROP CONSTRAINT IF EXISTS ck_items_part_type_matches_row_type;
    ALTER TABLE items DROP CONSTRAINT IF EXISTS ck_items_related_part_has_no_cutlist;
    ALTER TABLE items DROP CONSTRAINT IF EXISTS ck_items_parent_matches_row_type;
    ALTER TABLE items DROP CONSTRAINT IF EXISTS fk_items_parent_is_joinery_item;
    ALTER TABLE items DROP COLUMN IF EXISTS parent_row_type;
    ALTER TABLE items DROP CONSTRAINT IF EXISTS uq_items_id_row_type;
    ALTER TABLE items DROP CONSTRAINT IF EXISTS ck_items_row_type;
    ALTER TABLE items DROP COLUMN IF EXISTS related_part_type_key;
    ALTER TABLE items DROP COLUMN IF EXISTS parent_item_id;
    ALTER TABLE items DROP COLUMN IF EXISTS row_type;
    DROP TABLE IF EXISTS related_part_type;
    """)
