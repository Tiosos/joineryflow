"""Shop Floor re-keys from the item to the cutlist

Plan V1 Q412 makes the production workflow the **cutlist's**, not the item's:
items sharing a cutlist share one set of production-stage completions and one
completion time each. Migration `0020` keyed `worker_assignment` and
`stage_completion_log` on `(item_id, stage_key)`, so both must move to
`(cutlist_id, stage_key)`.

## Scope — the five production stages only (Q561)

Q445 reads "(cutlist_id, stage_key) for production, (item_id, 'INST') for
install", but **Shop Floor has never been able to hold DEL or INST**: both
tables carry `CHECK (stage_key IN ('DOWN','CNC','EDGED','PAINTED','MADE'))`
from `0020`, and neither stage appears in `app/shop_floor/` or on the
five-column board. Q561 confirmed the install half is unbuilt functionality
rather than a re-key, so this migration does **not** widen either CHECK.
Delivery (shared per Q413) and installation (per item per Q415) stay out of
Shop Floor and remain recordable through the item editor's lifecycle PATCH.

## Why the backfill cannot collide

`0027` minted **one cutlist per existing item** (Q540), so every pre-existing
item maps to a distinct cutlist. Copying `items.cutlist_id` onto each
assignment therefore turns each unique `(item_id, stage_key)` into a unique
`(cutlist_id, stage_key)`, and the rebuilt partial unique index applies
without a single conflict. Sharing only begins for cutlists created after
`0027`.

## The two tables are treated differently, on purpose

* `worker_assignment` is **mutable current state**. It is fully re-keyed:
  `item_id` is dropped, because an active assignment belongs to the cutlist
  and nothing is lost by saying so.
* `stage_completion_log` is **append-only history**, and Q435 requires
  data-preserving migrations. Its `item_id` is kept (made nullable) as the
  provenance of every pre-`0030` completion — which item the row was
  originally recorded against. New rows write `cutlist_id` and leave it NULL.

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-19
"""
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------
    # 1. Add the new key, nullable while we backfill.
    # ------------------------------------------------------------------
    op.execute("""
    ALTER TABLE worker_assignment
        ADD COLUMN cutlist_id bigint REFERENCES cutlist(cutlist_id) ON DELETE CASCADE;
    ALTER TABLE stage_completion_log
        ADD COLUMN cutlist_id bigint REFERENCES cutlist(cutlist_id) ON DELETE CASCADE;
    """)

    op.execute("""
    UPDATE worker_assignment wa
       SET cutlist_id = i.cutlist_id
      FROM items i
     WHERE i.item_id = wa.item_id;

    UPDATE stage_completion_log scl
       SET cutlist_id = i.cutlist_id
      FROM items i
     WHERE i.item_id = scl.item_id;
    """)

    # An assignment whose item somehow has no cutlist cannot be re-keyed.
    # 0027 gave every existing item one, so this deletes nothing in practice —
    # it is here so the NOT NULL below cannot fail on a surprise row.
    op.execute("""
    DELETE FROM stage_completion_log WHERE cutlist_id IS NULL;
    DELETE FROM worker_assignment    WHERE cutlist_id IS NULL;
    """)

    # ------------------------------------------------------------------
    # 2. Re-key worker_assignment: the cutlist replaces the item outright.
    # ------------------------------------------------------------------
    op.execute("""
    DROP INDEX IF EXISTS uniq_active_assignment;
    DROP INDEX IF EXISTS idx_assignment_item;

    ALTER TABLE worker_assignment
        ALTER COLUMN cutlist_id SET NOT NULL;
    ALTER TABLE worker_assignment
        DROP COLUMN item_id;

    -- At most one ACTIVE assignment per (cutlist, stage) — the 0020 rule with
    -- the new key. Cancelled/done rows are still kept for history.
    CREATE UNIQUE INDEX uniq_active_assignment
        ON worker_assignment (cutlist_id, stage_key)
        WHERE status IN ('assigned', 'in_progress');

    CREATE INDEX idx_assignment_cutlist
        ON worker_assignment (cutlist_id);
    """)

    # ------------------------------------------------------------------
    # 3. stage_completion_log keeps item_id as provenance (Q435).
    # ------------------------------------------------------------------
    op.execute("""
    DROP INDEX IF EXISTS idx_completion_item;

    ALTER TABLE stage_completion_log
        ALTER COLUMN cutlist_id SET NOT NULL;
    ALTER TABLE stage_completion_log
        ALTER COLUMN item_id DROP NOT NULL;

    CREATE INDEX idx_completion_cutlist
        ON stage_completion_log (cutlist_id, stage_key);

    COMMENT ON COLUMN stage_completion_log.item_id IS
        'Provenance only: the item a pre-0030 completion was recorded against, '
        'when Shop Floor keyed on the item. NULL on every row written since. '
        'Read cutlist_id for the completion itself.';
    """)


def downgrade():
    # worker_assignment.item_id cannot be restored for a SHARED cutlist — one
    # assignment would map to several items and there is no way to choose. The
    # lowest linked item_id is used, which is exact for every row this
    # migration converted (0027 made those cutlists 1:1 with items) and
    # arbitrary only for assignments created after it.
    op.execute("""
    ALTER TABLE worker_assignment
        ADD COLUMN item_id bigint REFERENCES items(item_id) ON DELETE CASCADE;

    UPDATE worker_assignment wa
       SET item_id = (
           SELECT MIN(i.item_id) FROM items i WHERE i.cutlist_id = wa.cutlist_id
       );

    DELETE FROM worker_assignment WHERE item_id IS NULL;
    ALTER TABLE worker_assignment ALTER COLUMN item_id SET NOT NULL;

    DROP INDEX IF EXISTS uniq_active_assignment;
    DROP INDEX IF EXISTS idx_assignment_cutlist;
    ALTER TABLE worker_assignment DROP COLUMN cutlist_id;

    CREATE UNIQUE INDEX uniq_active_assignment
        ON worker_assignment (item_id, stage_key)
        WHERE status IN ('assigned', 'in_progress');
    CREATE INDEX idx_assignment_item ON worker_assignment (item_id);
    """)

    op.execute("""
    UPDATE stage_completion_log scl
       SET item_id = (
           SELECT MIN(i.item_id) FROM items i WHERE i.cutlist_id = scl.cutlist_id
       )
     WHERE scl.item_id IS NULL;

    DELETE FROM stage_completion_log WHERE item_id IS NULL;
    ALTER TABLE stage_completion_log ALTER COLUMN item_id SET NOT NULL;

    DROP INDEX IF EXISTS idx_completion_cutlist;
    ALTER TABLE stage_completion_log DROP COLUMN cutlist_id;

    CREATE INDEX idx_completion_item ON stage_completion_log (item_id, stage_key);
    """)
