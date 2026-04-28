"""user_id repoint

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-25
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    -- 1. projects.optimisation_drafter_id FK -> app_user(id)
    ALTER TABLE projects
        DROP CONSTRAINT IF EXISTS projects_optimisation_drafter_id_fkey;
    ALTER TABLE projects
        ADD CONSTRAINT projects_optimisation_drafter_id_fkey
        FOREIGN KEY (optimisation_drafter_id) REFERENCES app_user(id) ON DELETE SET NULL;

    -- 2. project_favourites.user_id FK -> app_user(id)
    ALTER TABLE project_favourites
        DROP CONSTRAINT IF EXISTS project_favourites_user_id_fkey;
    ALTER TABLE project_favourites
        ADD CONSTRAINT project_favourites_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE CASCADE;

    -- 3. project_hardware_catalog.added_by FK -> app_user(id)
    ALTER TABLE project_hardware_catalog
        DROP CONSTRAINT IF EXISTS project_hardware_catalog_added_by_fkey;
    ALTER TABLE project_hardware_catalog
        ADD CONSTRAINT project_hardware_catalog_added_by_fkey
        FOREIGN KEY (added_by) REFERENCES app_user(id) ON DELETE SET NULL;

    -- 4. project_hardware_catalog_log.changed_by FK -> app_user(id)
    ALTER TABLE project_hardware_catalog_log
        DROP CONSTRAINT IF EXISTS project_hardware_catalog_log_changed_by_fkey;
    ALTER TABLE project_hardware_catalog_log
        ADD CONSTRAINT project_hardware_catalog_log_changed_by_fkey
        FOREIGN KEY (changed_by) REFERENCES app_user(id) ON DELETE SET NULL;

    -- 5. items.cutlist_owner_id: already has FK to users(user_id) per 0001, repoint to app_user(id)
    ALTER TABLE items
        DROP CONSTRAINT IF EXISTS items_cutlist_owner_id_fkey;
    ALTER TABLE items
        ADD CONSTRAINT items_cutlist_owner_id_fkey
        FOREIGN KEY (cutlist_owner_id) REFERENCES app_user(id) ON DELETE SET NULL;

    -- 6. Procurement-side FKs (from migration 0002)
    ALTER TABLE purchase_orders
        DROP CONSTRAINT IF EXISTS purchase_orders_requester_id_fkey;
    ALTER TABLE purchase_orders
        ADD CONSTRAINT purchase_orders_requester_id_fkey
        FOREIGN KEY (requester_id) REFERENCES app_user(id) ON DELETE SET NULL;

    ALTER TABLE po_attachments
        DROP CONSTRAINT IF EXISTS po_attachments_uploaded_by_fkey;
    ALTER TABLE po_attachments
        ADD CONSTRAINT po_attachments_uploaded_by_fkey
        FOREIGN KEY (uploaded_by) REFERENCES app_user(id) ON DELETE SET NULL;

    ALTER TABLE approval_workflows
        DROP CONSTRAINT IF EXISTS approval_workflows_approver_id_fkey;
    ALTER TABLE approval_workflows
        ADD CONSTRAINT approval_workflows_approver_id_fkey
        FOREIGN KEY (approver_id) REFERENCES app_user(id) ON DELETE SET NULL;

    ALTER TABLE budget_transactions
        DROP CONSTRAINT IF EXISTS budget_transactions_created_by_fkey;
    ALTER TABLE budget_transactions
        ADD CONSTRAINT budget_transactions_created_by_fkey
        FOREIGN KEY (created_by) REFERENCES app_user(id) ON DELETE SET NULL;

    ALTER TABLE inventory_movements
        DROP CONSTRAINT IF EXISTS inventory_movements_created_by_fkey;
    ALTER TABLE inventory_movements
        ADD CONSTRAINT inventory_movements_created_by_fkey
        FOREIGN KEY (created_by) REFERENCES app_user(id) ON DELETE SET NULL;

    ALTER TABLE cost_centers
        DROP CONSTRAINT IF EXISTS cost_centers_manager_id_fkey;
    ALTER TABLE cost_centers
        ADD CONSTRAINT cost_centers_manager_id_fkey
        FOREIGN KEY (manager_id) REFERENCES app_user(id) ON DELETE SET NULL;

    -- 7. New PM scoping column (FK)
    ALTER TABLE projects
        ADD COLUMN pm_id BIGINT
        REFERENCES app_user(id) ON DELETE SET NULL;
    CREATE INDEX projects_pm_id_idx ON projects(pm_id);

    -- 8. Replace the two views that JOIN legacy users -> now JOIN app_user.
    --    Preserving the full column list from the 0006 originals.
    DROP VIEW IF EXISTS v_po_summary;
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
      JOIN cost_centers cc    ON po.cost_center_id = cc.cost_center_id
      LEFT JOIN procurement_user_profile pup ON pup.user_id = u.id;

    DROP VIEW IF EXISTS v_orders_due;
    CREATE VIEW v_orders_due AS
      SELECT
        po.po_id,
        po.po_number,
        po.status,
        po.priority,
        po.required_date,
        po.due_date,
        po.arrived_date,
        (CURRENT_DATE - po.required_date) AS days_overdue,
        (po.required_date - CURRENT_DATE) AS days_until_due,
        v.name          AS vendor_name,
        u.full_name     AS requester_name,
        po.description,
        po.project_name
      FROM purchase_orders po
      JOIN vendors v    ON po.vendor_id    = v.vendor_id
      JOIN app_user u   ON po.requester_id = u.id
      WHERE po.status <> ALL (ARRAY['Delivered', 'Cancelled'])
        AND po.required_date IS NOT NULL;

    -- 9. Drop the legacy table itself (CASCADE removes any remaining dependent objects).
    DROP TABLE IF EXISTS users CASCADE;
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-PM-Workbench schema is recoverable from migrations 0001-0007 only")
