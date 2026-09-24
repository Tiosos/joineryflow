"""area + room — Plan V1's Project -> Area -> Room -> Joinery Item hierarchy

Plan V1 §2 drills down Company -> Project -> Area -> Room -> Joinery Item.
Both middle levels already existed in this schema under other names, as free
text on `items`: the site location in `items.stage`, and the room in
`items.rm_no` + `items.rm_desc` (the API already aliases those two as
`room_no` / `room_desc`). So this is a rename and normalisation, not new
structure — see `docs/plan-v1/OPEN-QUESTIONS.md` Q454/Q455.

Room is **nested under Area**, not a sibling of it, so the hierarchy in §2 is
real containment rather than a UI grouping. A composite foreign key from
`items (area_id, room_id)` enforces that an item's room always belongs to that
item's area; without it the two columns could drift apart.

That nesting means a room number used in more than one area becomes more than
one room. In the demo data `K1 Kitchen` appears under both `Stage 1` and
`Stage 2`, so 6 distinct (project, room) pairs migrate to 8 room rows. That is
intended: under §2 a room lives in exactly one area.

Because a room must sit inside an area, an item with a room number but **no**
area gets `area_id` and `room_id` both NULL — its room cannot be modelled until
it has an area. No information is lost: `rm_no` / `rm_desc` stay on the row, and
assigning an area later lets the room be created then.

`items.stage`, `rm_no` and `rm_desc` are **left in place and still populated**.
Nothing reads the new columns yet, and Q435 requires migrations to preserve
data; the old columns are dropped in a later migration once every query has
been repointed. `items.level` and `items.zone` stay ordinary columns and do
**not** become levels of the hierarchy (Q546).

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-18
"""
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE area (
        area_id    BIGSERIAL PRIMARY KEY,
        project_id bigint      NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
        name       varchar(64) NOT NULL,
        sort_order smallint    NOT NULL DEFAULT 0,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_area_project_name UNIQUE (project_id, name)
    );
    CREATE INDEX idx_area_project ON area (project_id);

    CREATE TABLE room (
        room_id    BIGSERIAL   PRIMARY KEY,
        area_id    bigint      NOT NULL REFERENCES area(area_id) ON DELETE CASCADE,
        rm_no      varchar(16) NOT NULL,
        rm_desc    varchar(128),
        sort_order smallint    NOT NULL DEFAULT 0,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_room_area_no UNIQUE (area_id, rm_no),
        -- target for the composite FK from items; keeps a room's area and the
        -- item's area provably the same row rather than merely equal-looking.
        CONSTRAINT uq_room_area_room UNIQUE (area_id, room_id)
    );
    CREATE INDEX idx_room_area ON room (area_id);

    ALTER TABLE items
        ADD COLUMN area_id bigint REFERENCES area(area_id),
        ADD COLUMN room_id bigint;

    -- MATCH SIMPLE (the default): not enforced while either column is NULL,
    -- which is what we want for an item with no area or no room yet (Q440's
    -- "assigned later" shape applies here too).
    ALTER TABLE items
        ADD CONSTRAINT fk_items_room_within_area
        FOREIGN KEY (area_id, room_id) REFERENCES room (area_id, room_id);

    CREATE INDEX idx_items_area ON items (area_id);
    CREATE INDEX idx_items_room ON items (room_id);
    """)

    # ---- data migration -------------------------------------------------
    # One area per distinct (project, stage). Blank and NULL stages are not
    # areas; those items simply keep a NULL area_id.
    op.execute("""
    INSERT INTO area (project_id, name)
    SELECT DISTINCT i.project_id, btrim(i.stage)
    FROM items i
    WHERE i.stage IS NOT NULL AND btrim(i.stage) <> ''
    ON CONFLICT (project_id, name) DO NOTHING;
    """)

    # One room per distinct (area, rm_no). DISTINCT ON picks a single
    # description where the same room number carries more than one spelling,
    # which would otherwise violate uq_room_area_no.
    op.execute("""
    INSERT INTO room (area_id, rm_no, rm_desc)
    SELECT DISTINCT ON (a.area_id, btrim(i.rm_no))
           a.area_id, btrim(i.rm_no), i.rm_desc
    FROM items i
    JOIN area a ON a.project_id = i.project_id AND a.name = btrim(i.stage)
    WHERE i.rm_no IS NOT NULL AND btrim(i.rm_no) <> ''
    ORDER BY a.area_id, btrim(i.rm_no), i.rm_desc NULLS LAST
    ON CONFLICT (area_id, rm_no) DO NOTHING;
    """)

    op.execute("""
    UPDATE items i
       SET area_id = a.area_id
      FROM area a
     WHERE a.project_id = i.project_id
       AND a.name = btrim(i.stage);
    """)

    op.execute("""
    UPDATE items i
       SET room_id = r.room_id
      FROM room r
     WHERE r.area_id = i.area_id
       AND r.rm_no = btrim(i.rm_no);
    """)


def downgrade():
    op.execute("""
    ALTER TABLE items DROP CONSTRAINT IF EXISTS fk_items_room_within_area;
    DROP INDEX IF EXISTS idx_items_area;
    DROP INDEX IF EXISTS idx_items_room;
    ALTER TABLE items DROP COLUMN IF EXISTS room_id;
    ALTER TABLE items DROP COLUMN IF EXISTS area_id;
    DROP TABLE IF EXISTS room;
    DROP TABLE IF EXISTS area;
    """)
