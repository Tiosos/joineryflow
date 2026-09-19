"""Make the legacy order schema usable for joinery orders

`0029` revived `purchase_orders` as the v1 order layer (Q502/Q553). Building
the routes on top of it (B6) hit three inherited office-procurement
requirements that block *creating* a joinery order at all:

* **`cost_center_id NOT NULL`** — budget-holder accounting. Plan V1's financial
  model (§16) is unscoped and **Q543** deferred item cost entirely; nothing in
  Q425–Q432 mentions a cost centre. **Q563** makes it nullable. The column,
  `cost_centers` and `budget_transactions` all stay, ready for §16.
* **`category` CHECKed to `IT / Office / Logistics / Facilities / Services /
  Other`** — a board supplier is none of those, so every joinery order would
  land in `Other` and §21's supplier comparison would have nothing to group on.
  **Q557**, raised in A4 and deferred to the C-series, is resolved here instead:
  deferring it was wrong, because a NOT NULL column blocks creation, not just
  rendering. The CHECK becomes an `order_category` lookup seeded with the six
  legacy values plus joinery ones.
* **no PO-number allocator** — `legacy/procurement_api.py:274` formats
  `PO-{year}-{seq:04d}`, which is kept (**Q564**). Its generator is not:
  `SELECT MAX(...) + 1` then insert is the same read-then-insert race **B2a**
  removed from `items.num`. A real sequence replaces it.

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-19
"""
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

# The six legacy values keep working; the joinery ones are what §21 needs.
_CATEGORIES = [
    ("IT", "IT", 10), ("Office", "Office", 20), ("Logistics", "Logistics", 30),
    ("Facilities", "Facilities", 40), ("Services", "Services", 50),
    ("Other", "Other", 60),
    ("Board", "Board", 100), ("Hardware", "Hardware", 110),
    ("Benchtop", "Benchtop", 120), ("Appliance", "Appliance", 130),
    ("Custom", "Custom-made", 140), ("Hire", "Equipment hire", 150),
    ("Metal", "Metal", 160), ("Cushion", "Cushion", 170),
]


def upgrade():
    # ---- Q563: a joinery order has no cost centre ----
    op.execute("""
    ALTER TABLE purchase_orders ALTER COLUMN cost_center_id DROP NOT NULL;

    COMMENT ON COLUMN purchase_orders.cost_center_id IS
        'Nullable since 0031 (Q563): joinery orders carry no cost centre. '
        'Kept for the office-procurement flow and for §16 if it is ever scoped.';
    """)

    # ---- Q557: category becomes a lookup, not a frozen CHECK ----
    op.execute("""
    CREATE TABLE order_category (
        category_key varchar(32) PRIMARY KEY,
        label        varchar(64) NOT NULL,
        sort_order   integer     NOT NULL DEFAULT 100,
        archived_at  timestamptz
    );
    """)
    for key, label, order in _CATEGORIES:
        op.execute(
            "INSERT INTO order_category (category_key, label, sort_order) "
            f"VALUES ('{key}', '{label}', {order}) ON CONFLICT DO NOTHING;"
        )

    # Both tables carried the same frozen list. The constraint names come from
    # 0002's inline CHECKs, so drop by the generated name.
    op.execute("""
    ALTER TABLE purchase_orders DROP CONSTRAINT IF EXISTS purchase_orders_category_check;
    ALTER TABLE vendors         DROP CONSTRAINT IF EXISTS vendors_category_check;

    ALTER TABLE purchase_orders
        ADD CONSTRAINT purchase_orders_category_fkey
        FOREIGN KEY (category) REFERENCES order_category (category_key);
    ALTER TABLE vendors
        ADD CONSTRAINT vendors_category_fkey
        FOREIGN KEY (category) REFERENCES order_category (category_key);
    """)

    # ---- Q564: a real allocator, not MAX(...) + 1 ----
    #
    # Seeded above whatever the legacy format already issued, so a revived
    # database cannot reissue a number. The scan is over an empty table today.
    op.execute("""
    CREATE SEQUENCE po_number_seq AS bigint MINVALUE 1 START WITH 1;

    -- The third argument is `is_called`: false on an empty table so the FIRST
    -- allocation is PO-<year>-0001, true when rows exist so the next one is
    -- max + 1. Passing plain setval(seq, 1) would start at 0002.
    SELECT setval('po_number_seq', GREATEST(1, existing), existing > 0)
      FROM (
        SELECT COALESCE(MAX(CAST(split_part(po_number, '-', 3) AS bigint)), 0)
                 AS existing
          FROM purchase_orders
         WHERE po_number ~ '^PO-[0-9]{4}-[0-9]+$'
      ) s;
    """)


def downgrade():
    op.execute("DROP SEQUENCE IF EXISTS po_number_seq;")

    # Rows carrying a joinery category cannot satisfy the legacy CHECK; they
    # fall back to 'Other', which is where they would have been without 0031.
    op.execute("""
    ALTER TABLE purchase_orders DROP CONSTRAINT IF EXISTS purchase_orders_category_fkey;
    ALTER TABLE vendors         DROP CONSTRAINT IF EXISTS vendors_category_fkey;

    UPDATE purchase_orders SET category = 'Other'
     WHERE category NOT IN ('IT','Office','Logistics','Facilities','Services','Other');
    UPDATE vendors SET category = 'Other'
     WHERE category NOT IN ('IT','Office','Logistics','Facilities','Services','Other');

    ALTER TABLE purchase_orders
        ADD CONSTRAINT purchase_orders_category_check
        CHECK (category IN ('IT','Office','Logistics','Facilities','Services','Other'));
    ALTER TABLE vendors
        ADD CONSTRAINT vendors_category_check
        CHECK (category IN ('IT','Office','Logistics','Facilities','Services','Other'));

    DROP TABLE IF EXISTS order_category;
    """)

    # Orders created without a cost centre cannot satisfy the restored NOT NULL.
    op.execute("""
    DELETE FROM purchase_orders WHERE cost_center_id IS NULL;
    ALTER TABLE purchase_orders ALTER COLUMN cost_center_id SET NOT NULL;
    """)
