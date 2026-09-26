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

Workspace isolation: purchase_orders / po_line_items / po_attachments /
approval_workflows are all scoped through `_PO_WORKSPACE_EXISTS` (see below);
budget_transactions / v_budget_utilisation through `_CC_IN_WORKSPACE`, via
cost_centers.workspace_id (added by migration 0029). This module was ported
from a single-tenant app and had none of this at all until now.
"""
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


# ── Workspace isolation ───────────────────────────────────────────────────────
# purchase_orders has no workspace_id of its own. It resolves to one through
# project_id (a column POCreate below never sets, so every PO created via
# this legacy surface is vendor-only today) or, failing that, vendor_id — the
# same join apps/api/app/orders/queries.py's _ORDER_WORKSPACE already
# established for the v1 order layer, since both routers write the same
# purchase_orders table (Q554/Q555).
_PO_WORKSPACE_EXISTS = """
    (
        (po.project_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM projects p2
            WHERE p2.project_id = po.project_id AND p2.workspace_id = :wid
        ))
        OR
        (po.project_id IS NULL AND EXISTS (
            SELECT 1 FROM vendors v2
            WHERE v2.vendor_id = po.vendor_id AND v2.workspace_id = :wid
        ))
    )
"""


def _po_id_in_workspace(col: str) -> str:
    """SQL fragment: the po_id referenced by `col` belongs to the caller's
    workspace. Pass a qualified column (e.g. "aw.po_id") whenever the query
    joins more than one table with its own po_id, to avoid an ambiguous
    reference."""
    return f"{col} IN (SELECT po.po_id FROM purchase_orders po WHERE {_PO_WORKSPACE_EXISTS})"


def po_in_workspace(db: Session, *, po_id: int, workspace_id: int) -> bool:
    """Ownership guard for single-PO routes. Callers check this once and then
    trust po_id for the rest of the route — po_line_items, po_attachments and
    approval_workflows all reach their workspace through it."""
    row = db.execute(
        text(
            f"SELECT 1 FROM purchase_orders po WHERE po.po_id = :po_id AND {_PO_WORKSPACE_EXISTS}"
        ),
        {"po_id": po_id, "wid": workspace_id},
    ).first()
    return row is not None


def vendor_in_workspace(db: Session, *, vendor_id: int, workspace_id: int) -> bool:
    row = db.execute(
        text("SELECT 1 FROM vendors WHERE vendor_id = :v AND workspace_id = :w"),
        {"v": vendor_id, "w": workspace_id},
    ).first()
    return row is not None


def cost_center_in_workspace(db: Session, *, cost_center_id: int, workspace_id: int) -> bool:
    row = db.execute(
        text("SELECT 1 FROM cost_centers WHERE cost_center_id = :c AND workspace_id = :w"),
        {"c": cost_center_id, "w": workspace_id},
    ).first()
    return row is not None


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
    workspace_id: int,
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
    q = f"SELECT * FROM v_po_summary WHERE {_po_id_in_workspace('po_id')}"
    params: dict[str, Any] = {"wid": workspace_id}
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
        f" AND {_po_id_in_workspace('po_id')}"
        " ORDER BY required_date ASC, created_at DESC"
    )


def filter_rto(db: Session, *, workspace_id: int) -> list[dict]:
    return [
        dict(r)
        for r in db.execute(
            text(_filter_query("status = 'Next'")), {"wid": workspace_id}
        ).mappings()
    ]


def filter_tbo(db: Session, *, workspace_id: int) -> list[dict]:
    return [
        dict(r)
        for r in db.execute(
            text(_filter_query("status IN ('Next','Quote')")), {"wid": workspace_id}
        ).mappings()
    ]


def filter_due(db: Session, *, workspace_id: int) -> list[dict]:
    return [
        dict(r)
        for r in db.execute(
            text(
                _filter_query(
                    "due_date IS NOT NULL AND arrived_date IS NULL"
                    " AND status NOT IN ('Cancelled','Rejected')"
                )
            ),
            {"wid": workspace_id},
        ).mappings()
    ]


def filter_overdue(db: Session, *, workspace_id: int) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT * FROM v_po_summary
             WHERE required_date IS NOT NULL
               AND required_date < CURRENT_DATE
               AND arrived_date IS NULL
               AND status NOT IN ('Delivered','Cancelled','Rejected')
               AND {_po_id_in_workspace('po_id')}
             ORDER BY required_date ASC
            """
        ),
        {"wid": workspace_id},
    ).mappings()
    return [dict(r) for r in rows]


def filter_arrived(db: Session, *, workspace_id: int) -> list[dict]:
    return [
        dict(r)
        for r in db.execute(
            text(_filter_query("arrived_date IS NOT NULL")), {"wid": workspace_id}
        ).mappings()
    ]


def filter_my_orders(db: Session, requester_id: int, *, workspace_id: int) -> list[dict]:
    return [
        dict(r)
        for r in db.execute(
            text(_filter_query("requester_id = :rid")),
            {"rid": requester_id, "wid": workspace_id},
        ).mappings()
    ]


def filter_clear(db: Session, *, workspace_id: int) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT * FROM v_po_summary
             WHERE required_date IS NOT NULL
               AND required_date >= CURRENT_DATE - INTERVAL '2 years'
               AND {_po_id_in_workspace('po_id')}
             ORDER BY required_date DESC
            """
        ),
        {"wid": workspace_id},
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
def list_pending_approvals(db: Session, approver_id: int, *, workspace_id: int) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT aw.workflow_id, aw.po_id, aw.sequence_order, aw.created_at,
                   ps.po_number, ps.vendor_name, ps.description, ps.total_amount,
                   ps.grand_total, ps.currency, ps.category, ps.priority,
                   ps.project_name, ps.requester_name, ps.cost_center
              FROM approval_workflows aw
              JOIN v_po_summary ps ON aw.po_id = ps.po_id
             WHERE aw.approver_id = :approver_id AND aw.status = 'Pending'
               AND {_po_id_in_workspace('aw.po_id')}
             ORDER BY aw.created_at ASC
            """
        ),
        {"approver_id": approver_id, "wid": workspace_id},
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
    db: Session, *, workspace_id: int, approver_id: Optional[int] = None, limit: int = 50
) -> list[dict]:
    q = f"""
        SELECT aw.*, ps.po_number, ps.vendor_name, ps.grand_total,
               ps.requester_name, u.full_name AS approver_name
          FROM approval_workflows aw
          JOIN v_po_summary ps ON aw.po_id = ps.po_id
          JOIN app_user u ON aw.approver_id = u.id
         WHERE aw.status != 'Pending'
           AND {_po_id_in_workspace('aw.po_id')}
    """
    params: dict[str, Any] = {"limit": limit, "wid": workspace_id}
    if approver_id:
        q += " AND aw.approver_id = :approver_id"
        params["approver_id"] = approver_id
    q += " ORDER BY aw.acted_at DESC LIMIT :limit"
    return [dict(r) for r in db.execute(text(q), params).mappings()]


# ── Vendors ───────────────────────────────────────────────────────────────────










# ── Inventory — RETIRED (Q544): 0029 dropped inventory, inventory_movements
#    and v_inventory_status. Sheet stock lives at /board-inventory (0025).








# ── Budget ────────────────────────────────────────────────────────────────────
# cost_centers.workspace_id was added directly by migration 0029 ("workspace
# scoping, only where there is no join path") — v_budget_utilisation and
# budget_transactions have no workspace_id of their own but both resolve
# through cost_center_id -> cost_centers.workspace_id.
_CC_IN_WORKSPACE = (
    "cost_center_id IN (SELECT cost_center_id FROM cost_centers WHERE workspace_id = :wid)"
)


def list_budget(
    db: Session, *, workspace_id: int, fiscal_year: Optional[int] = None
) -> list[dict]:
    q = f"SELECT * FROM v_budget_utilisation WHERE {_CC_IN_WORKSPACE}"
    params: dict[str, Any] = {"wid": workspace_id}
    if fiscal_year:
        q += " AND fiscal_year = :yr"
        params["yr"] = fiscal_year
    q += " ORDER BY utilisation_pct DESC"
    return [dict(r) for r in db.execute(text(q), params).mappings()]


def budget_summary(db: Session, *, workspace_id: int) -> Optional[dict]:
    row = db.execute(
        text(
            f"""
            SELECT
                SUM(budget_amount)   AS total_budget,
                SUM(total_committed) AS total_spent,
                SUM(remaining)       AS total_remaining,
                ROUND(
                  SUM(total_committed) / NULLIF(SUM(budget_amount), 0) * 100, 1
                ) AS overall_utilisation_pct
              FROM v_budget_utilisation
             WHERE {_CC_IN_WORKSPACE}
            """
        ),
        {"wid": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def cost_center_transactions(
    db: Session, cost_center_id: int, *, workspace_id: int
) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT bt.*, po.po_number, u.full_name AS created_by_name
              FROM budget_transactions bt
              LEFT JOIN purchase_orders po ON bt.po_id = po.po_id
              LEFT JOIN app_user u ON bt.created_by = u.id
             WHERE bt.cost_center_id = :cc
               AND bt.{_CC_IN_WORKSPACE}
             ORDER BY bt.transaction_date DESC
            """
        ),
        {"cc": cost_center_id, "wid": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]
