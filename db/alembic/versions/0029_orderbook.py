"""orderbook — reviving the legacy procurement namespace as the v1 order layer

Plan V1 §21 wants a real order, a real PO and a real supplier on the v1
surface. `procurement_v1` has batches and allocations but no order entity at
all; the **legacy** `/procurement/*` namespace (migration `0002`) already has
`purchase_orders`, `po_line_items` and `vendors`, and its PO columns —
`cutlist_no`, `order_number`, `supplier_ref_no`, `product_code`,
`product_website`, `product_description`, `product_image_path`,
`stock_tracked`, the GST pair, `internal_comments`, `line_item_comments` —
match Orderbook screenshots 07–09 closely enough to be the intended shape.

**Q502 = 1** therefore revives that namespace rather than building beside it,
and **Q553** confirms there is no new `order` / `order_line`: `purchase_orders`
+ `po_line_items` *are* the order layer. **Q556** likewise confirms there is no
new `supplier` table: `vendors` is it.

All nine legacy tables are **empty** and the seed touches none of them, so the
reshaping below costs no data. Every backfill here is a no-op on a real
database today; they are written anyway because they must be correct the first
time a row exists.

## Workspace scoping (Q555)

The round-1 §K note said "add `workspace_id` to the 9 legacy procurement
tables". Tracing the FK graph showed that to be wrong, and **Q555** corrects
it: a denormalised `workspace_id` on a table that already has a join path is
the `cut_plan` pattern this codebase moved away from at `0014`/`cc7ea11`.

* `purchase_orders` reaches workspace through a new **`project_id`** FK
  (**Q554**), joining `projects.workspace_id`.
* `po_line_items`, `po_attachments`, `approval_workflows` and
  `budget_transactions` all carry `po_id` or `cost_center_id` and need nothing.
* `vendors` and `cost_centers` are referenced directly and have **no** path
  today, so they do get `workspace_id`.
* `inventory` and `inventory_movements` are dropped (**Q544**), so the question
  does not arise for them.

`purchase_orders.project_name` stays as free text (**Q435**): an order with no
project — office consumables, a stock buy — keeps its label. The consequence to
know is that such an order (`project_id IS NULL`) is invisible to every
workspace-scoped read. That is intended; every order the v1 surface creates is
project-scoped.

## Dropping legacy inventory (Q544)

`board_inventory` (`0025`) wins. `inventory` and `inventory_movements` go, and
the three columns worth keeping — `quantity_reserved`, `reorder_point`,
`reorder_quantity` — are ported onto `board_inventory`. `quantity_reserved` is
what Q541's explicit reservation action will write; `/optimise` stays the pure
function `0025` made it.

Dropping `inventory` forces dropping **`v_inventory_status`** (migration
`0006`), which selects from it. It is **not** recreated: the two endpoints that
read it (`GET /procurement/inventory`, `/inventory/low-stock`) belong to the
half of the legacy namespace this migration retires, and `board_inventory` has
its own routes from `0025`.

## What is deliberately NOT done here

The `category` CHECKs on `vendors` and `purchase_orders` still carry the
inherited office-procurement taxonomy (`IT / Office / Logistics / Facilities /
Services / Other`). A board supplier is none of those. Widening that list is
**Q557**, left open on purpose and taken with the C-series Orderbook UI where
the categories are actually rendered — not decided silently in a schema
migration.

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-18
"""
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

# The six catalog tables, mapped to the free-text supplier column each one
# actually has.
#
# CLAUDE.md states the six share an abstract interface
# `(id, type, description, supplier, cost_unit, lead_time_days, notes)`.
# **They do not.** `custom_made` calls it `vendor` (it also has
# `vendor_quote_ref`, which no other table has), and only `default_supplier`
# — added uniformly by `0017` — is genuinely common to all six. Verified
# against a real `0001`→`0028` schema; the documented interface is aspirational
# on this column.
CATALOG_SUPPLIER_COLUMN = {
    "board_materials":     "supplier",
    "hardware_materials":  "supplier",
    "custom_made":         "vendor",
    "benchtop_materials":  "supplier",
    "appliances":          "supplier",
    "equipment_hire":      "supplier",
}
CATALOG_TABLES = tuple(CATALOG_SUPPLIER_COLUMN)


def upgrade():
    # ------------------------------------------------------------------
    # 1. Q544 — legacy inventory loses to board_inventory.
    #    The view must go first: it selects from the table being dropped.
    # ------------------------------------------------------------------
    op.execute("""
    DROP VIEW IF EXISTS v_inventory_status;
    DROP TABLE IF EXISTS inventory_movements;
    DROP TABLE IF EXISTS inventory;
    """)

    # The three columns worth porting. `quantity_reserved` is what Q541's
    # explicit reservation action will write; nothing writes it yet.
    op.execute("""
    ALTER TABLE board_inventory
        ADD COLUMN qty_reserved    integer NOT NULL DEFAULT 0
                                   CHECK (qty_reserved >= 0),
        ADD COLUMN reorder_point   integer CHECK (reorder_point   >= 0),
        ADD COLUMN reorder_qty     integer CHECK (reorder_qty     >= 0);

    -- You cannot reserve stock you do not hold. This is the invariant the
    -- reservation action has to respect, so the database states it.
    ALTER TABLE board_inventory
        ADD CONSTRAINT ck_board_inventory_reserved_within_hand
        CHECK (qty_reserved <= qty_on_hand);

    COMMENT ON COLUMN board_inventory.qty_reserved IS
        'Sheets committed to a cut plan but not yet cut. Written by the '
        'explicit reservation action (Q541); /optimise never touches it.';
    """)

    # ------------------------------------------------------------------
    # 2. Q555 — workspace scoping, only where there is no join path.
    # ------------------------------------------------------------------
    op.execute("""
    ALTER TABLE vendors
        ADD COLUMN workspace_id bigint REFERENCES workspace(id) ON DELETE CASCADE;
    ALTER TABLE cost_centers
        ADD COLUMN workspace_id bigint REFERENCES workspace(id) ON DELETE CASCADE;
    """)

    # Both tables are empty today, so this backfill moves nothing. It is here
    # because a single-workspace install that somehow has rows must not end up
    # with orphans, and because NOT NULL below would fail on them.
    op.execute("""
    UPDATE vendors      SET workspace_id = (SELECT MIN(id) FROM workspace)
     WHERE workspace_id IS NULL;
    UPDATE cost_centers SET workspace_id = (SELECT MIN(id) FROM workspace)
     WHERE workspace_id IS NULL;
    """)

    # Only enforceable once a workspace exists. On a virgin database the
    # backfill above sets NULL (MIN over an empty table), and both tables are
    # empty, so the constraint holds either way.
    op.execute("""
    ALTER TABLE vendors      ALTER COLUMN workspace_id SET NOT NULL;
    ALTER TABLE cost_centers ALTER COLUMN workspace_id SET NOT NULL;
    """)

    # `cost_centers.code` was globally UNIQUE, which is wrong once the table is
    # workspace-scoped: two workspaces may each have a cost centre 'ADMIN'.
    op.execute("""
    ALTER TABLE cost_centers DROP CONSTRAINT IF EXISTS cost_centers_code_key;
    ALTER TABLE cost_centers
        ADD CONSTRAINT uq_cost_centers_ws_code UNIQUE (workspace_id, code);

    -- Supplier names are not unique in the legacy schema and are not made so
    -- here; two 'Bunnings' rows in one workspace is a data-quality problem,
    -- not a constraint violation. The index is for the lookup, not uniqueness.
    CREATE INDEX idx_vendors_workspace      ON vendors (workspace_id);
    CREATE INDEX idx_cost_centers_workspace ON cost_centers (workspace_id);
    """)

    # ------------------------------------------------------------------
    # 3. Q554 — an order reaches its workspace through its project.
    # ------------------------------------------------------------------
    op.execute("""
    ALTER TABLE purchase_orders
        ADD COLUMN project_id bigint REFERENCES projects(project_id) ON DELETE SET NULL;

    CREATE INDEX idx_po_project_id ON purchase_orders (project_id);

    COMMENT ON COLUMN purchase_orders.project_id IS
        'Nullable (Q554). Workspace is derived by joining projects.workspace_id. '
        'NULL means a non-project order (consumables, stock buy) — such a row is '
        'invisible to workspace-scoped reads by design; project_name still labels it.';
    """)

    # Best-effort link of any pre-existing legacy order to a project by its
    # free-text name. No-op today (the table is empty); correct if it is not.
    op.execute("""
    UPDATE purchase_orders po
       SET project_id = p.project_id
      FROM projects p
     WHERE po.project_id IS NULL
       AND po.project_name IS NOT NULL
       AND btrim(po.project_name) <> ''
       AND lower(btrim(p.name)) = lower(btrim(po.project_name));
    """)

    # ------------------------------------------------------------------
    # 4. Q417/Q418 — a related part's order number is what Tracking shows in
    #    place of a cutlist number, so the order must point back at the row.
    #    Q507 = 2 makes orders cover all procurement, not just related parts,
    #    hence a plain items FK rather than a related-part-only one.
    # ------------------------------------------------------------------
    op.execute("""
    ALTER TABLE purchase_orders
        ADD COLUMN item_id bigint REFERENCES items(item_id) ON DELETE SET NULL;

    CREATE INDEX idx_po_item ON purchase_orders (item_id);
    """)

    # ------------------------------------------------------------------
    # 5. Q503 — one generic order form plus a free-form attributes blob.
    #    Header-level and line-level, because screenshots 07–09 vary in both.
    #    Known cost, recorded in §K round 2: fields inside the blob are neither
    #    schema-validated nor easily queryable, so §21's supplier comparison
    #    works on the fixed columns only.
    # ------------------------------------------------------------------
    op.execute("""
    ALTER TABLE purchase_orders
        ADD COLUMN attributes jsonb NOT NULL DEFAULT '{}'::jsonb;
    ALTER TABLE po_line_items
        ADD COLUMN attributes jsonb NOT NULL DEFAULT '{}'::jsonb;

    -- A blob, not an array or a scalar. Without this a caller can PATCH
    -- attributes to `[]` or `null` and every reader has to defend against it.
    ALTER TABLE purchase_orders
        ADD CONSTRAINT ck_po_attributes_is_object
        CHECK (jsonb_typeof(attributes) = 'object');
    ALTER TABLE po_line_items
        ADD CONSTRAINT ck_po_line_attributes_is_object
        CHECK (jsonb_typeof(attributes) = 'object');

    CREATE INDEX idx_po_attributes      ON purchase_orders USING gin (attributes);
    CREATE INDEX idx_po_line_attributes ON po_line_items   USING gin (attributes);
    """)

    # A PO line may name a catalog material. The catalog is six tables with no
    # shared key (a binding invariant — see CLAUDE.md), so the reference is the
    # same (table, id) pair `cv_material_mapping` uses. No FK is possible;
    # the CHECK constrains the table name and the pair is kept whole.
    op.execute("""
    ALTER TABLE po_line_items
        ADD COLUMN material_table text CHECK (material_table IN
            ('board_materials','hardware_materials','custom_made',
             'benchtop_materials','appliances','equipment_hire')),
        ADD COLUMN material_id    bigint;

    ALTER TABLE po_line_items
        ADD CONSTRAINT ck_po_line_material_pair
        CHECK ((material_table IS NULL) = (material_id IS NULL));
    """)

    # ------------------------------------------------------------------
    # 6. Q506 + Q556 — `vendors` IS the supplier entity. The six catalog
    #    tables gain an FK to it BESIDE their free text, which Q435 requires
    #    us to keep: repointing is incremental, and an unmatched supplier name
    #    stays readable rather than being lost.
    # ------------------------------------------------------------------
    for tbl in CATALOG_TABLES:
        op.execute(f"""
        ALTER TABLE {tbl}
            ADD COLUMN supplier_id         bigint REFERENCES vendors(vendor_id) ON DELETE SET NULL,
            ADD COLUMN default_supplier_id bigint REFERENCES vendors(vendor_id) ON DELETE SET NULL;

        CREATE INDEX idx_{tbl}_supplier_id ON {tbl} (supplier_id);
        """)

    # Link existing free text to a vendor where the name matches exactly
    # within the same workspace. Deliberately exact (case- and
    # whitespace-insensitive only): fuzzy supplier matching is a product
    # decision, not a migration's to make. Unmatched rows keep their text.
    #
    # Note the per-table column name — `custom_made` says `vendor`, not
    # `supplier`. See CATALOG_SUPPLIER_COLUMN above.
    for tbl, supplier_col in CATALOG_SUPPLIER_COLUMN.items():
        op.execute(f"""
        UPDATE {tbl} t
           SET supplier_id = v.vendor_id
          FROM vendors v
         WHERE t.supplier_id IS NULL
           AND v.workspace_id = t.workspace_id
           AND t.{supplier_col} IS NOT NULL
           AND lower(btrim(t.{supplier_col})) = lower(btrim(v.name));

        UPDATE {tbl} t
           SET default_supplier_id = v.vendor_id
          FROM vendors v
         WHERE t.default_supplier_id IS NULL
           AND v.workspace_id = t.workspace_id
           AND t.default_supplier IS NOT NULL
           AND lower(btrim(t.default_supplier)) = lower(btrim(v.name));
        """)


def downgrade():
    for tbl in CATALOG_TABLES:
        op.execute(f"""
        DROP INDEX IF EXISTS idx_{tbl}_supplier_id;
        ALTER TABLE {tbl} DROP COLUMN IF EXISTS default_supplier_id;
        ALTER TABLE {tbl} DROP COLUMN IF EXISTS supplier_id;
        """)

    op.execute("""
    DROP INDEX IF EXISTS idx_po_line_attributes;
    DROP INDEX IF EXISTS idx_po_attributes;
    ALTER TABLE po_line_items   DROP CONSTRAINT IF EXISTS ck_po_line_material_pair;
    ALTER TABLE po_line_items   DROP COLUMN IF EXISTS material_id;
    ALTER TABLE po_line_items   DROP COLUMN IF EXISTS material_table;
    ALTER TABLE po_line_items   DROP CONSTRAINT IF EXISTS ck_po_line_attributes_is_object;
    ALTER TABLE purchase_orders DROP CONSTRAINT IF EXISTS ck_po_attributes_is_object;
    ALTER TABLE po_line_items   DROP COLUMN IF EXISTS attributes;
    ALTER TABLE purchase_orders DROP COLUMN IF EXISTS attributes;

    DROP INDEX IF EXISTS idx_po_item;
    ALTER TABLE purchase_orders DROP COLUMN IF EXISTS item_id;

    DROP INDEX IF EXISTS idx_po_project_id;
    ALTER TABLE purchase_orders DROP COLUMN IF EXISTS project_id;

    DROP INDEX IF EXISTS idx_cost_centers_workspace;
    DROP INDEX IF EXISTS idx_vendors_workspace;
    ALTER TABLE cost_centers DROP CONSTRAINT IF EXISTS uq_cost_centers_ws_code;
    ALTER TABLE cost_centers DROP COLUMN IF EXISTS workspace_id;
    ALTER TABLE vendors      DROP COLUMN IF EXISTS workspace_id;
    -- The global UNIQUE on cost_centers.code that 0002 created.
    ALTER TABLE cost_centers
        ADD CONSTRAINT cost_centers_code_key UNIQUE (code);

    ALTER TABLE board_inventory
        DROP CONSTRAINT IF EXISTS ck_board_inventory_reserved_within_hand;
    ALTER TABLE board_inventory DROP COLUMN IF EXISTS reorder_qty;
    ALTER TABLE board_inventory DROP COLUMN IF EXISTS reorder_point;
    ALTER TABLE board_inventory DROP COLUMN IF EXISTS qty_reserved;
    """)

    # Q544's drop is not reversible: `inventory`, `inventory_movements` and
    # `v_inventory_status` are NOT recreated. They held no data (all nine
    # legacy procurement tables are empty and unseeded), so nothing is lost —
    # but a downgrade past this point leaves a schema that 0002 and 0006 would
    # have produced minus those three objects. Recover from 0001 if the exact
    # legacy shape is needed.
