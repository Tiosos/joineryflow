"""v_po_summary: LEFT JOIN cost_centers

`0031` made ``purchase_orders.cost_center_id`` nullable (Q563) so a joinery
order need not belong to an office cost centre. ``v_po_summary`` (`0006`,
redefined by `0009`) still INNER JOINed ``cost_centers``, so such an order was
absent from the view: the legacy ``GET /procurement/orders/{id}`` answered 404
and the legacy list, filters and approval queues omitted it, although the row
existed. The join becomes a LEFT JOIN; the ``cost_center_id`` / ``cost_center``
/ ``cost_center_code`` columns read NULL for such an order. Every other join
(vendor, requester) is on a NOT NULL column and is unchanged.

``CREATE OR REPLACE`` is valid because the output columns, their order and their
types are identical, so nothing that depends on the view has to be dropped.

Revision ID: 0045
Revises: 0044
Create Date: 2026-09-30
"""
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

_VIEW_TEMPLATE = """
CREATE OR REPLACE VIEW v_po_summary AS
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
    u.id            AS requester_id,
    u.full_name     AS requester_name,
    pup.extension   AS requester_ext,
    cc.cost_center_id,
    cc.name         AS cost_center,
    cc.code         AS cost_center_code
  FROM purchase_orders po
  JOIN vendors v          ON po.vendor_id      = v.vendor_id
  JOIN app_user u         ON po.requester_id   = u.id
  {cc_join} cost_centers cc    ON po.cost_center_id = cc.cost_center_id
  LEFT JOIN procurement_user_profile pup ON pup.user_id = u.id;
"""


def upgrade():
    op.execute(_VIEW_TEMPLATE.format(cc_join="LEFT JOIN"))


def downgrade():
    # Back to the `0009` definition: an order with no cost centre drops out again.
    op.execute(_VIEW_TEMPLATE.format(cc_join="JOIN"))
