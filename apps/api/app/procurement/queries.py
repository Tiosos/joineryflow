"""SQL query functions for the procurement module.

Ported from legacy/procurement_api.py with mechanical MySQL → Postgres
conversions:
  - LAST_INSERT_ID()       -> RETURNING id
  - CURDATE()              -> CURRENT_DATE
  - NOW() / UTC_TIMESTAMP  -> now()
  - CONCAT(a, b)           -> a || b
  - DATE_SUB(d, INTERVAL n YEAR) -> d - INTERVAL 'n year'
  - SUBSTRING_INDEX(po_number,'-',-1) -> regexp_replace(po_number,'^.*-','')
  - YEAR(x)                -> EXTRACT(YEAR FROM x)
  - FIELD(col, ...)        -> CASE WHEN order
  - IFNULL                 -> COALESCE
  - %s named params        -> :name SQLAlchemy bind params
  - LIMIT n,m              -> LIMIT m OFFSET n

Functions take (db: Session, ...) and return mappings (list[dict] / dict).
NO db.commit() here — routes own the transaction boundary.

User-identity joins use `app_user` (migration 0004) instead of the legacy
`users` table. Procurement-specific user fields (cost_center_id,
approval_limit, extension) are dropped pending a future
procurement_user_profile side-table.
"""
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


# ── Helpers ───────────────────────────────────────────────────────────────────
def generate_po_number(db: Session, year: int) -> str:
    """Generate the next PO number for a given calendar year (PO-YYYY-NNNN)."""
    row = db.execute(
        text(
            """
            SELECT COALESCE(
              MAX(CAST(regexp_replace(po_number, '^.*-', '') AS INTEGER)), 0
            ) + 1 AS seq
            FROM purchase_orders
            WHERE EXTRACT(YEAR FROM created_at) = :yr
            """
        ),
        {"yr": year},
    ).mappings().first()
    seq = row["seq"] if row else 1
    return f"PO-{year}-{str(seq).zfill(4)}"


def commit_budget(
    db: Session,
    po_id: int,
    cost_center_id: int,
    amount: float,
    tx_type: str = "Commitment",
) -> None:
    """Record a budget transaction (Commitment or Expenditure)."""
    db.execute(
        text(
            """
            INSERT INTO budget_transactions
                (cost_center_id, po_id, amount, transaction_type, transaction_date)
            VALUES (:cc, :po, :amt, :type, CURRENT_DATE)
            """
        ),
        {"cc": cost_center_id, "po": po_id, "amt": amount, "type": tx_type},
    )


def append_changelog(
    db: Session, po_id: int, entry: str, user_id: Optional[int] = None
) -> None:
    """Append a timestamped line to purchase_orders.changelog."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    who = f" [user #{user_id}]" if user_id else ""
    db.execute(
        text(
            """
            UPDATE purchase_orders
               SET changelog = COALESCE(changelog, '') || :line
             WHERE po_id = :id
            """
        ),
        {"line": f"{stamp}{who} — {entry}\n", "id": po_id},
    )


# ── Purchase orders ───────────────────────────────────────────────────────────
def list_orders(
    db: Session,
    *,
    status: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    vendor_id: Optional[int] = None,
    requester_id: Optional[int] = None,
    project_name: Optional[str] = None,
    cutlist_no: Optional[str] = None,
    search: Optional[str] = None,
    required_from: Optional[date] = None,
    required_to: Optional[date] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    q = "SELECT * FROM v_po_summary WHERE 1=1"
    params: dict[str, Any] = {}
    if status:
        q += " AND status = :status"
        params["status"] = status
    if category:
        q += " AND category = :category"
        params["category"] = category
    if priority:
        q += " AND priority = :priority"
        params["priority"] = priority
    if vendor_id:
        q += " AND vendor_id = :vendor_id"
        params["vendor_id"] = vendor_id
    if requester_id:
        q += " AND requester_id = :req_id"
        params["req_id"] = requester_id
    if project_name:
        q += " AND project_name = :proj"
        params["proj"] = project_name
    if cutlist_no:
        q += " AND cutlist_no LIKE :cut"
        params["cut"] = f"%{cutlist_no}%"
    if required_from:
        q += " AND required_date >= :r_from"
        params["r_from"] = required_from
    if required_to:
        q += " AND required_date <= :r_to"
        params["r_to"] = required_to
    if search:
        q += (
            " AND (po_number LIKE :s OR order_number LIKE :s OR vendor_name LIKE :s"
            " OR description LIKE :s OR product_code LIKE :s OR location LIKE :s)"
        )
        params["s"] = f"%{search}%"
    q += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset
    return [dict(r) for r in db.execute(text(q), params).mappings()]


def get_order_summary(db: Session, po_id: int) -> Optional[dict]:
    row = db.execute(
        text("SELECT * FROM v_po_summary WHERE po_id = :id"),
        {"id": po_id},
    ).mappings().first()
    return dict(row) if row else None


def get_order_lines(db: Session, po_id: int) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT * FROM po_line_items WHERE po_id = :id ORDER BY line_number"
        ),
        {"id": po_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def get_order_attachments(db: Session, po_id: int) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT a.*, u.full_name AS uploaded_by_name
              FROM po_attachments a
              LEFT JOIN app_user u ON a.uploaded_by = u.id
             WHERE a.po_id = :id
             ORDER BY a.uploaded_at DESC
            """
        ),
        {"id": po_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def get_order_workflow(db: Session, po_id: int) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT aw.*, u.full_name AS approver_name
              FROM approval_workflows aw
              JOIN app_user u ON aw.approver_id = u.id
             WHERE aw.po_id = :id
             ORDER BY sequence_order
            """
        ),
        {"id": po_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def get_order_extra(db: Session, po_id: int) -> Optional[dict]:
    row = db.execute(
        text(
            """
            SELECT product_website, product_description, product_image_path,
                   line_item_comments, internal_comments, changelog,
                   gst_applicable, gst_included_in_price, unit_cost, notes
              FROM purchase_orders WHERE po_id = :id
            """
        ),
        {"id": po_id},
    ).mappings().first()
    return dict(row) if row else None


def insert_order(db: Session, po_number: str, payload: dict) -> int:
    row = db.execute(
        text(
            """
            INSERT INTO purchase_orders
                (po_number, order_number, cutlist_no, supplier_ref_no,
                 vendor_id, requester_id, cost_center_id,
                 description, category, priority, order_type, project_name, location,
                 required_date, requested_date, requested_time, date_ordered, due_date, arrived_date,
                 product_code, product_website, product_description, product_image_path, stock_tracked,
                 quantity, unit_of_measure, unit_cost,
                 gst_applicable, gst_included_in_price, currency,
                 notes, line_item_comments, internal_comments)
            VALUES
                (:po_number, :order_number, :cutlist_no, :supplier_ref_no,
                 :vendor_id, :requester_id, :cost_center_id,
                 :description, :category, :priority, :order_type, :project_name, :location,
                 :required_date, :requested_date, :requested_time, :date_ordered, :due_date, :arrived_date,
                 :product_code, :product_website, :product_description, :product_image_path, :stock_tracked,
                 :quantity, :unit_of_measure, :unit_cost,
                 :gst_applicable, :gst_included_in_price, :currency,
                 :notes, :line_item_comments, :internal_comments)
            RETURNING po_id
            """
        ),
        {"po_number": po_number, **payload},
    ).mappings().first()
    return int(row["po_id"])


def insert_line_item(db: Session, po_id: int, line: dict) -> None:
    db.execute(
        text(
            """
            INSERT INTO po_line_items
                (po_id, line_number, item_description, sku, quantity, unit, unit_price, tax_rate)
            VALUES
                (:po_id, :line_number, :item_description, :sku, :quantity, :unit, :unit_price, :tax_rate)
            """
        ),
        {"po_id": po_id, **line},
    )


def update_order_fields(db: Session, po_id: int, fields: dict) -> None:
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    params = {**fields, "po_id": po_id}
    db.execute(
        text(f"UPDATE purchase_orders SET {set_clause} WHERE po_id = :po_id"),
        params,
    )


def submit_for_approval(db: Session, po_id: int, approver_id: int) -> int:
    """Returns rowcount affected (0 means PO wasn't in Draft)."""
    result = db.execute(
        text(
            "UPDATE purchase_orders SET status='Pending'"
            " WHERE po_id = :id AND status = 'Draft'"
        ),
        {"id": po_id},
    )
    affected = result.rowcount or 0
    if affected:
        db.execute(
            text(
                """
                INSERT INTO approval_workflows (po_id, approver_id, sequence_order)
                VALUES (:po_id, :approver_id, 1)
                """
            ),
            {"po_id": po_id, "approver_id": approver_id},
        )
    return affected


def mark_delivered(
    db: Session, po_id: int, arrived_date: Optional[date]
) -> Optional[dict]:
    db.execute(
        text(
            """
            UPDATE purchase_orders
               SET status='Delivered',
                   delivery_date = CURRENT_DATE,
                   arrived_date  = COALESCE(:arr, CURRENT_DATE)
             WHERE po_id = :id AND status = 'Approved'
            """
        ),
        {"id": po_id, "arr": arrived_date},
    )
    row = db.execute(
        text(
            "SELECT cost_center_id, grand_total FROM purchase_orders"
            " WHERE po_id = :id"
        ),
        {"id": po_id},
    ).mappings().first()
    return dict(row) if row else None


def cancel_order(db: Session, po_id: int) -> None:
    db.execute(
        text(
            "UPDATE purchase_orders SET status='Cancelled'"
            " WHERE po_id = :id AND status IN ('Draft','Rejected','Hold')"
        ),
        {"id": po_id},
    )


def get_order_raw(db: Session, po_id: int) -> Optional[dict]:
    row = db.execute(
        text("SELECT * FROM purchase_orders WHERE po_id = :id"),
        {"id": po_id},
    ).mappings().first()
    return dict(row) if row else None


def duplicate_order(db: Session, po_id: int, new_po_number: str) -> int:
    row = db.execute(
        text(
            """
            INSERT INTO purchase_orders
                (po_number, order_number, cutlist_no, supplier_ref_no,
                 vendor_id, requester_id, cost_center_id,
                 description, category, priority, order_type, project_name, location,
                 required_date,
                 product_code, product_website, product_description, product_image_path, stock_tracked,
                 quantity, unit_of_measure, unit_cost,
                 gst_applicable, gst_included_in_price, currency,
                 notes, line_item_comments, internal_comments, status)
            SELECT
                 :new_po, order_number, cutlist_no, supplier_ref_no,
                 vendor_id, requester_id, cost_center_id,
                 description, category, priority, order_type, project_name, location,
                 required_date,
                 product_code, product_website, product_description, product_image_path, stock_tracked,
                 quantity, unit_of_measure, unit_cost,
                 gst_applicable, gst_included_in_price, currency,
                 notes, line_item_comments, internal_comments, 'Draft'
              FROM purchase_orders WHERE po_id = :id
            RETURNING po_id
            """
        ),
        {"new_po": new_po_number, "id": po_id},
    ).mappings().first()
    new_id = int(row["po_id"])
    db.execute(
        text(
            """
            INSERT INTO po_line_items
                (po_id, line_number, item_description, sku, quantity, unit, unit_price, tax_rate)
            SELECT :new_id, line_number, item_description, sku, quantity, unit, unit_price, tax_rate
              FROM po_line_items WHERE po_id = :id
            """
        ),
        {"new_id": new_id, "id": po_id},
    )
    return new_id


# ── FileMaker quick-filters ───────────────────────────────────────────────────
def _filter_query(where: str) -> str:
    return (
        f"SELECT * FROM v_po_summary WHERE {where}"
        " ORDER BY required_date ASC, created_at DESC"
    )


def filter_rto(db: Session) -> list[dict]:
    return [
        dict(r)
        for r in db.execute(text(_filter_query("status = 'Next'"))).mappings()
    ]


def filter_tbo(db: Session) -> list[dict]:
    return [
        dict(r)
        for r in db.execute(
            text(_filter_query("status IN ('Next','Quote')"))
        ).mappings()
    ]


def filter_due(db: Session) -> list[dict]:
    return [
        dict(r)
        for r in db.execute(
            text(
                _filter_query(
                    "due_date IS NOT NULL AND arrived_date IS NULL"
                    " AND status NOT IN ('Cancelled','Rejected')"
                )
            )
        ).mappings()
    ]


def filter_overdue(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT * FROM v_po_summary
             WHERE required_date IS NOT NULL
               AND required_date < CURRENT_DATE
               AND arrived_date IS NULL
               AND status NOT IN ('Delivered','Cancelled','Rejected')
             ORDER BY required_date ASC
            """
        )
    ).mappings()
    return [dict(r) for r in rows]


def filter_arrived(db: Session) -> list[dict]:
    return [
        dict(r)
        for r in db.execute(
            text(_filter_query("arrived_date IS NOT NULL"))
        ).mappings()
    ]


def filter_my_orders(db: Session, requester_id: int) -> list[dict]:
    return [
        dict(r)
        for r in db.execute(
            text(_filter_query("requester_id = :rid")), {"rid": requester_id}
        ).mappings()
    ]


def filter_clear(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT * FROM v_po_summary
             WHERE required_date IS NOT NULL
               AND required_date >= CURRENT_DATE - INTERVAL '2 years'
             ORDER BY required_date DESC
            """
        )
    ).mappings()
    return [dict(r) for r in rows]


# ── Attachments ───────────────────────────────────────────────────────────────
def list_attachments(db: Session, po_id: int) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT a.*, u.full_name AS uploaded_by_name
              FROM po_attachments a
              LEFT JOIN app_user u ON a.uploaded_by = u.id
             WHERE a.po_id = :id
             ORDER BY a.uploaded_at DESC
            """
        ),
        {"id": po_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def insert_attachment(
    db: Session,
    *,
    po_id: int,
    attachment_type: str,
    file_name: str,
    file_size_bytes: int,
    file_path: str,
    uploaded_by: Optional[int],
) -> int:
    row = db.execute(
        text(
            """
            INSERT INTO po_attachments
                (po_id, attachment_type, file_name, file_size_bytes, file_path, uploaded_by)
            VALUES
                (:po_id, :atype, :fn, :sz, :fp, :uid)
            RETURNING attachment_id
            """
        ),
        {
            "po_id": po_id,
            "atype": attachment_type,
            "fn": file_name,
            "sz": file_size_bytes,
            "fp": file_path,
            "uid": uploaded_by,
        },
    ).mappings().first()
    return int(row["attachment_id"])


def get_attachment(db: Session, po_id: int, attachment_id: int) -> Optional[dict]:
    row = db.execute(
        text(
            "SELECT file_path, file_name FROM po_attachments"
            " WHERE attachment_id = :a AND po_id = :p"
        ),
        {"a": attachment_id, "p": po_id},
    ).mappings().first()
    return dict(row) if row else None


def delete_attachment(db: Session, attachment_id: int) -> None:
    db.execute(
        text("DELETE FROM po_attachments WHERE attachment_id = :a"),
        {"a": attachment_id},
    )


# ── Approvals ─────────────────────────────────────────────────────────────────
def list_pending_approvals(db: Session, approver_id: int) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT aw.workflow_id, aw.po_id, aw.sequence_order, aw.created_at,
                   ps.po_number, ps.vendor_name, ps.description, ps.total_amount,
                   ps.grand_total, ps.currency, ps.category, ps.priority,
                   ps.project_name, ps.requester_name, ps.cost_center
              FROM approval_workflows aw
              JOIN v_po_summary ps ON aw.po_id = ps.po_id
             WHERE aw.approver_id = :approver_id AND aw.status = 'Pending'
             ORDER BY aw.created_at ASC
            """
        ),
        {"approver_id": approver_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def get_workflow(db: Session, workflow_id: int) -> Optional[dict]:
    row = db.execute(
        text("SELECT * FROM approval_workflows WHERE workflow_id = :id"),
        {"id": workflow_id},
    ).mappings().first()
    return dict(row) if row else None


def update_workflow_decision(
    db: Session, workflow_id: int, status: str, comments: Optional[str]
) -> None:
    db.execute(
        text(
            """
            UPDATE approval_workflows
               SET status = :s, comments = :c, acted_at = now()
             WHERE workflow_id = :id
            """
        ),
        {"s": status, "c": comments, "id": workflow_id},
    )


def update_po_status(db: Session, po_id: int, status: str) -> None:
    db.execute(
        text("UPDATE purchase_orders SET status = :s WHERE po_id = :po_id"),
        {"s": status, "po_id": po_id},
    )


def get_po_budget_fields(db: Session, po_id: int) -> Optional[dict]:
    row = db.execute(
        text(
            "SELECT cost_center_id, grand_total FROM purchase_orders"
            " WHERE po_id = :id"
        ),
        {"id": po_id},
    ).mappings().first()
    return dict(row) if row else None


def approval_history(
    db: Session, *, approver_id: Optional[int] = None, limit: int = 50
) -> list[dict]:
    q = """
        SELECT aw.*, ps.po_number, ps.vendor_name, ps.grand_total,
               ps.requester_name, u.full_name AS approver_name
          FROM approval_workflows aw
          JOIN v_po_summary ps ON aw.po_id = ps.po_id
          JOIN app_user u ON aw.approver_id = u.id
         WHERE aw.status != 'Pending'
    """
    params: dict[str, Any] = {"limit": limit}
    if approver_id:
        q += " AND aw.approver_id = :approver_id"
        params["approver_id"] = approver_id
    q += " ORDER BY aw.acted_at DESC LIMIT :limit"
    return [dict(r) for r in db.execute(text(q), params).mappings()]


# ── Vendors ───────────────────────────────────────────────────────────────────
def list_vendors(
    db: Session,
    *,
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> list[dict]:
    q = """
        SELECT v.*, COUNT(po.po_id) AS active_pos
          FROM vendors v
          LEFT JOIN purchase_orders po ON v.vendor_id = po.vendor_id
              AND po.status NOT IN ('Delivered','Cancelled')
         WHERE 1=1
    """
    params: dict[str, Any] = {}
    if category:
        q += " AND v.category = :cat"
        params["cat"] = category
    if status:
        q += " AND v.status = :status"
        params["status"] = status
    if search:
        q += " AND v.name LIKE :s"
        params["s"] = f"%{search}%"
    q += " GROUP BY v.vendor_id ORDER BY v.name"
    return [dict(r) for r in db.execute(text(q), params).mappings()]


def get_vendor(db: Session, vendor_id: int) -> Optional[dict]:
    row = db.execute(
        text("SELECT * FROM vendors WHERE vendor_id = :id"),
        {"id": vendor_id},
    ).mappings().first()
    return dict(row) if row else None


def vendor_recent_orders(db: Session, vendor_id: int) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT po_number, description, grand_total, status, created_at
              FROM v_po_summary WHERE vendor_id = :id
             ORDER BY created_at DESC LIMIT 20
            """
        ),
        {"id": vendor_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def insert_vendor(db: Session, payload: dict) -> int:
    row = db.execute(
        text(
            """
            INSERT INTO vendors
                (name, category, contact_name, contact_email, contact_phone,
                 address, tax_id, payment_terms)
            VALUES
                (:name, :category, :contact_name, :contact_email, :contact_phone,
                 :address, :tax_id, :payment_terms)
            RETURNING vendor_id
            """
        ),
        payload,
    ).mappings().first()
    return int(row["vendor_id"])


def update_vendor_rating(db: Session, vendor_id: int, rating: float) -> None:
    db.execute(
        text("UPDATE vendors SET rating = :r WHERE vendor_id = :id"),
        {"r": rating, "id": vendor_id},
    )


# ── Inventory ─────────────────────────────────────────────────────────────────
def list_inventory(
    db: Session,
    *,
    stock_level: Optional[str] = None,
    search: Optional[str] = None,
) -> list[dict]:
    q = "SELECT * FROM v_inventory_status WHERE 1=1"
    params: dict[str, Any] = {}
    if stock_level:
        q += " AND stock_level = :lv"
        params["lv"] = stock_level
    if search:
        q += " AND (name LIKE :s OR sku LIKE :s OR category LIKE :s)"
        params["s"] = f"%{search}%"
    q += " ORDER BY stock_level DESC, name"
    return [dict(r) for r in db.execute(text(q), params).mappings()]


def low_stock(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT * FROM v_inventory_status
             WHERE stock_level IN ('Low','Critical')
             ORDER BY
               CASE stock_level WHEN 'Critical' THEN 0 WHEN 'Low' THEN 1 ELSE 2 END,
               (quantity_on_hand / NULLIF(reorder_point, 0)) ASC
            """
        )
    ).mappings()
    return [dict(r) for r in rows]


def insert_inventory_movement(db: Session, payload: dict) -> None:
    db.execute(
        text(
            """
            INSERT INTO inventory_movements
                (item_id, po_id, movement_type, quantity, unit_cost,
                 reference_number, notes, created_by)
            VALUES
                (:item_id, :po_id, :movement_type, :quantity, :unit_cost,
                 :reference_number, :notes, :created_by)
            """
        ),
        payload,
    )


def adjust_inventory(
    db: Session, item_id: int, direction: int, quantity: float
) -> None:
    db.execute(
        text(
            """
            UPDATE inventory
               SET quantity_on_hand = quantity_on_hand + (:direction * :quantity),
                   updated_at = now()
             WHERE item_id = :item_id
            """
        ),
        {"direction": direction, "quantity": quantity, "item_id": item_id},
    )


# ── Budget ────────────────────────────────────────────────────────────────────
def list_budget(db: Session, *, fiscal_year: Optional[int] = None) -> list[dict]:
    q = "SELECT * FROM v_budget_utilisation WHERE 1=1"
    params: dict[str, Any] = {}
    if fiscal_year:
        q += " AND fiscal_year = :yr"
        params["yr"] = fiscal_year
    q += " ORDER BY utilisation_pct DESC"
    return [dict(r) for r in db.execute(text(q), params).mappings()]


def budget_summary(db: Session) -> Optional[dict]:
    row = db.execute(
        text(
            """
            SELECT
                SUM(budget_amount)   AS total_budget,
                SUM(total_committed) AS total_spent,
                SUM(remaining)       AS total_remaining,
                ROUND(
                  SUM(total_committed) / NULLIF(SUM(budget_amount), 0) * 100, 1
                ) AS overall_utilisation_pct
              FROM v_budget_utilisation
            """
        )
    ).mappings().first()
    return dict(row) if row else None


def cost_center_transactions(db: Session, cost_center_id: int) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT bt.*, po.po_number, u.full_name AS created_by_name
              FROM budget_transactions bt
              LEFT JOIN purchase_orders po ON bt.po_id = po.po_id
              LEFT JOIN app_user u ON bt.created_by = u.id
             WHERE bt.cost_center_id = :cc
             ORDER BY bt.transaction_date DESC
            """
        ),
        {"cc": cost_center_id},
    ).mappings().all()
    return [dict(r) for r in rows]
