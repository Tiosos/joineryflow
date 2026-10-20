"""The columns that copy a catalog SKU take 255 characters, as the catalog does

Seven catalog `sku` columns are `varchar(255)` (Board, Custom, Benchtop, Appliance, Equipment Hire,
Glass, Solid Timber; Hardware and Edging are 64) but the SKU is copied into narrower columns when a
material goes onto a quote line or an order: `estimate_line_part.sku_snapshot` and
`estimate_line_hardware.sku_snapshot` (64), `po_line_items.sku` and `purchase_orders.product_code`
(100). A Glass row with a 150-character SKU added to a quote line ended in `StringDataRightTruncation`
(a 500). User decision (2026-10-20): widen those four copies to `varchar(255)` (the widest a catalog SKU
can be), then let the catalog accept the full column width.

`v_po_summary` selects `purchase_orders.product_code`, and Postgres cannot change the type of a column a
view uses, so the view is dropped and created again with the identical definition (copied from `0045`,
which last replaced it; nothing else depends on it, it has no grants, and the migration test compares
`pg_get_viewdef` before and after). No index, constraint, trigger or generated column refers to the four
columns (`po_line_items.line_total` is `round(quantity * unit_price, 2)`).

Downgrade narrows back to 64 / 64 / 100 / 100 and **refuses**, naming the rows, if any value is longer
(the same approach as `0070` / `0074`); Alembic runs the whole downgrade in one transaction, so a
refusal changes nothing.

Revision ID: 0079
Revises: 0078
Create Date: 2026-10-20
"""
from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

# (table, column, id column, width before this migration)
_COPIES = (
    ("estimate_line_part", "sku_snapshot", "part_id", 64),
    ("estimate_line_hardware", "sku_snapshot", "hw_id", 64),
    ("po_line_items", "sku", "line_id", 100),
    ("purchase_orders", "product_code", "po_id", 100),
)

# Identical to `0045`'s upgrade (the live definition at 0078).
_V_PO_SUMMARY = """
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
    u.id            AS requester_id,
    u.full_name     AS requester_name,
    pup.extension   AS requester_ext,
    cc.cost_center_id,
    cc.name         AS cost_center,
    cc.code         AS cost_center_code
  FROM purchase_orders po
  JOIN vendors v          ON po.vendor_id      = v.vendor_id
  JOIN app_user u         ON po.requester_id   = u.id
  LEFT JOIN cost_centers cc    ON po.cost_center_id = cc.cost_center_id
  LEFT JOIN procurement_user_profile pup ON pup.user_id = u.id;
"""


def _retype(width_of):
    op.execute("DROP VIEW IF EXISTS v_po_summary;")
    for table, col, _id, old in _COPIES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE varchar({width_of(old)});")
    op.execute(_V_PO_SUMMARY)


def upgrade():
    _retype(lambda old: 255)


def _refuse_too_long():
    """Name the rows a narrower column would cut (first 50 per column) and stop before changing anything."""
    for table, col, id_col, old in _COPIES:
        op.execute(f"""
            DO $$
            DECLARE bad text; n integer;
            BEGIN
                SELECT count(*) INTO n FROM {table} WHERE char_length({col}) > {old};
                IF n > 0 THEN
                    SELECT string_agg(format('id %s value %L (%s characters, limit {old})', {id_col}, {col},
                                             char_length({col})), '; ' ORDER BY {id_col})
                      INTO bad
                      FROM (SELECT {id_col}, {col} FROM {table} WHERE char_length({col}) > {old}
                             ORDER BY {id_col} LIMIT 50) x;
                    RAISE EXCEPTION '0079 downgrade refused, % value(s) in {table}.{col} are longer than {old} characters and would be cut short; shorten or remove them first. Rows %', n, bad;
                END IF;
            END $$;
        """)


def downgrade():
    _refuse_too_long()
    _retype(lambda old: old)
