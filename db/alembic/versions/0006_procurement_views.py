"""procurement views

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-25

Ports the four procurement views from `legacy/procurement_schema.sql`:
v_po_summary, v_budget_utilisation, v_inventory_status, v_orders_due.

Faithful port (Q2-A). Patches applied:

  1. `users.name` -> `users.full_name`. The 0001 port renamed this column
     when it ported the legacy tracking schema.
  2. `users.extension` -> `procurement_user_profile.extension` via LEFT JOIN.
     The 0005 side-table now owns procurement-specific user attributes.
  3. MySQL `DATEDIFF(a, b)` -> Postgres `(a - b)::int` (date subtraction
     yields integer days).
  4. MySQL `CURDATE()` -> Postgres `CURRENT_DATE`.
  5. Division by zero in `v_budget_utilisation` guarded with
     `NULLIF(cc.budget_amount, 0)`; the legacy view would raise on
     budget_amount=0.

Endpoints currently consuming these views (apps/api/app/procurement/routes.py):
- v_po_summary: GET /procurement/orders, GET /procurement/orders/{po_id}
- v_budget_utilisation: GET /procurement/budget, GET /procurement/budget/summary
- v_inventory_status: GET /procurement/inventory, /inventory/low-stock
- v_orders_due: GET /procurement/orders/filter/{due,overdue,...}
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    CREATE VIEW v_po_summary AS
    SELECT
        po.po_id,
        po.po_number,
        po.order_number,
        po.cutlist_no,
        po.supplier_ref_no,
        po.status,
        po.priority,
        po.category,
        po.order_type,
        po.project_name,
        po.location,
        po.description,
        po.product_code,
        po.quantity,
        po.unit_of_measure,
        po.total_amount,
        po.gst_amount,
        po.grand_total,
        po.currency,
        po.required_date,
        po.requested_date,
        po.date_ordered,
        po.due_date,
        po.arrived_date,
        po.stock_tracked,
        po.line_item_comments,
        po.created_at,
        v.vendor_id,
        v.name          AS vendor_name,
        v.rating        AS vendor_rating,
        u.user_id       AS requester_id,
        u.full_name     AS requester_name,
        pup.extension   AS requester_ext,
        cc.cost_center_id,
        cc.name         AS cost_center,
        cc.code         AS cost_center_code
    FROM purchase_orders po
    JOIN vendors      v   ON po.vendor_id      = v.vendor_id
    JOIN users        u   ON po.requester_id   = u.user_id
    JOIN cost_centers cc  ON po.cost_center_id = cc.cost_center_id
    LEFT JOIN procurement_user_profile pup ON pup.user_id = u.user_id;

    CREATE VIEW v_budget_utilisation AS
    SELECT
        cc.cost_center_id,
        cc.code,
        cc.name,
        cc.fiscal_year,
        cc.budget_amount,
        COALESCE(SUM(CASE WHEN bt.transaction_type IN ('Commitment','Expenditure')
                          THEN bt.amount ELSE 0 END), 0) AS total_committed,
        cc.budget_amount
            - COALESCE(SUM(CASE WHEN bt.transaction_type IN ('Commitment','Expenditure')
                                THEN bt.amount ELSE 0 END), 0) AS remaining,
        round(
            COALESCE(SUM(CASE WHEN bt.transaction_type IN ('Commitment','Expenditure')
                              THEN bt.amount ELSE 0 END), 0)
            / NULLIF(cc.budget_amount, 0) * 100, 1
        ) AS utilisation_pct
    FROM cost_centers cc
    LEFT JOIN budget_transactions bt ON cc.cost_center_id = bt.cost_center_id
    GROUP BY cc.cost_center_id;

    CREATE VIEW v_inventory_status AS
    SELECT
        item_id,
        name,
        sku,
        category,
        quantity_on_hand,
        quantity_reserved,
        (quantity_on_hand - quantity_reserved) AS available_qty,
        reorder_point,
        reorder_quantity,
        unit,
        unit_cost,
        location,
        CASE
            WHEN quantity_on_hand <= 0             THEN 'Critical'
            WHEN quantity_on_hand <= reorder_point THEN 'Low'
            ELSE 'OK'
        END AS stock_level
    FROM inventory
    WHERE is_active = TRUE;

    CREATE VIEW v_orders_due AS
    SELECT
        po.po_id,
        po.po_number,
        po.status,
        po.priority,
        po.required_date,
        po.due_date,
        po.arrived_date,
        (CURRENT_DATE - po.required_date)::int AS days_overdue,
        (po.required_date - CURRENT_DATE)::int AS days_until_due,
        v.name      AS vendor_name,
        u.full_name AS requester_name,
        po.description,
        po.project_name
    FROM purchase_orders po
    JOIN vendors v ON po.vendor_id    = v.vendor_id
    JOIN users   u ON po.requester_id = u.user_id
    WHERE po.status NOT IN ('Delivered','Cancelled')
      AND po.required_date IS NOT NULL;
    """)


def downgrade():
    op.execute("""
    DROP VIEW IF EXISTS v_orders_due;
    DROP VIEW IF EXISTS v_inventory_status;
    DROP VIEW IF EXISTS v_budget_utilisation;
    DROP VIEW IF EXISTS v_po_summary;
    """)
