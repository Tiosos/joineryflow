"""§L close-out: Hard Lock, Approval Lock, field-level optimistic concurrency

Plan V1 §12 / §11, Q508 + Q511 + Q512 — the three items Q566 recorded as
having "no task anywhere" after B7 shipped the Controlled Lock alone:

- **Q508's Hard Lock** — items.hard_locked_at / hard_locked_by. Unlike the
  Controlled Lock (a request the owner decides), a Hard Lock blocks
  PATCH /items/{id} unconditionally for everyone, including the owner, until
  a manager/admin explicitly clears it via POST|DELETE /items/{id}/hard-lock.
- **Q508's Approval Lock** — no new column. "Information automatically locks
  when approved" binds directly to the existing Status taxonomy's `APPROVED`
  value (`items.status`); there is nothing to store that isn't already
  there. Setting status to APPROVED locks PATCH /items/{id}; moving it away
  unlocks — both audited from `items/queries.py::patch_item_status`.
- **Q511 + Q512's field-level optimistic concurrency** — a `field_versions
  jsonb` column on each of the three named surfaces (item editor, cutlist,
  orders). One integer counter per field, bumped on every write that
  actually changes it. A caller MAY submit `expected_versions` on a PATCH;
  a named field whose version has moved on is a genuine conflict (409,
  naming just that field — Q366) and nothing is silently overwritten.
  Omitting it (every existing caller, and every field not being changed)
  keeps last-write-wins, so this is additive, not a breaking change to the
  ~181 endpoints Q511 explicitly declined to touch.

Q510 remains the ceiling it always was: item and project are the only legal
granularities, and this migration does not add a project-level lock column —
same reasoning `0032`'s docstring already gave (no lock column exists on
`projects`, so a project lock would be new functionality with no owner or UI,
not a conversion of something that already exists).

Revision ID: 0040
Revises: 0039
Create Date: 2026-09-27
"""
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE items
        ADD COLUMN IF NOT EXISTS hard_locked_at timestamptz,
        ADD COLUMN IF NOT EXISTS hard_locked_by integer,
        ADD COLUMN IF NOT EXISTS field_versions jsonb NOT NULL DEFAULT '{}'::jsonb;

    ALTER TABLE items DROP CONSTRAINT IF EXISTS items_hard_locked_by_fkey;
    ALTER TABLE items
        ADD CONSTRAINT items_hard_locked_by_fkey
            FOREIGN KEY (hard_locked_by) REFERENCES app_user (id);

    ALTER TABLE cutlist
        ADD COLUMN IF NOT EXISTS field_versions jsonb NOT NULL DEFAULT '{}'::jsonb;

    ALTER TABLE purchase_orders
        ADD COLUMN IF NOT EXISTS field_versions jsonb NOT NULL DEFAULT '{}'::jsonb;

    COMMENT ON COLUMN items.hard_locked_at IS
        'Q508 Hard Lock: non-NULL blocks PATCH /items/{id} for everyone, '
        'including the owner, until a manager/admin unlocks it.';
    COMMENT ON COLUMN items.field_versions IS
        'Q511/Q512: per-field version counters for optimistic concurrency. '
        'Bumped on every write that actually changes that field.';
    """)


def downgrade():
    op.execute("""
    ALTER TABLE purchase_orders DROP COLUMN IF EXISTS field_versions;
    ALTER TABLE cutlist DROP COLUMN IF EXISTS field_versions;

    ALTER TABLE items DROP CONSTRAINT IF EXISTS items_hard_locked_by_fkey;
    ALTER TABLE items
        DROP COLUMN IF EXISTS field_versions,
        DROP COLUMN IF EXISTS hard_locked_by,
        DROP COLUMN IF EXISTS hard_locked_at;
    """)
