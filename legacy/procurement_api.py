"""
Procurement Orderbook System — FastAPI Backend
Stack: FastAPI + SQLAlchemy (MySQL) + Pydantic v2

Aligned with FileMaker Orderbook layout (see filemaker.md §2).

Install:
    pip install fastapi uvicorn sqlalchemy pymysql cryptography pydantic[email] python-multipart

Run:
    uvicorn procurement_api:app --reload

Environment:
    DATABASE_URL  = mysql+pymysql://user:password@localhost/procurement_db
    UPLOAD_DIR    = ./uploads  (directory for PO file attachments)
    ALLOW_ORIGINS = http://localhost:3000,http://localhost:5173
"""

import os
import shutil
from datetime import date, time, datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:password@localhost/procurement_db",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Procurement Orderbook API",
    version="2.0.0",
    description=(
        "Purchase orders, vendors, approvals, inventory, budget tracking, "
        "and FileMaker Orderbook quick-filters (RTO / TBO / Due / Overdue / "
        "Arrived / My Orders)."
    ),
)

_allow_origins = os.getenv("ALLOW_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Enums ─────────────────────────────────────────────────────────────────────
class POStatus(str, Enum):
    draft     = "Draft"
    pending   = "Pending"
    approved  = "Approved"
    rejected  = "Rejected"
    delivered = "Delivered"
    cancelled = "Cancelled"
    hold      = "Hold"       # FileMaker: HOLD
    quote     = "Quote"      # FileMaker: QUOTE
    next_     = "Next"       # FileMaker: NEXT


class POPriority(str, Enum):
    high   = "High"
    medium = "Medium"
    low    = "Low"
    next_  = "Next"
    hold   = "Hold"
    quote  = "Quote"


class POCategory(str, Enum):
    it         = "IT"
    office     = "Office"
    logistics  = "Logistics"
    facilities = "Facilities"
    services   = "Services"
    other      = "Other"


class VendorStatus(str, Enum):
    active       = "Active"
    inactive     = "Inactive"
    under_review = "Under Review"
    blacklisted  = "Blacklisted"


class MovementType(str, Enum):
    incoming   = "IN"
    outgoing   = "OUT"
    adjustment = "ADJUSTMENT"
    returned   = "RETURN"


class AttachmentType(str, Enum):
    file  = "File"
    pdf   = "PDF"
    image = "Image"


# ── Schemas ───────────────────────────────────────────────────────────────────
class LineItemCreate(BaseModel):
    line_number:      int
    item_description: str
    sku:              Optional[str] = None
    quantity:         float
    unit:             Optional[str] = None
    unit_price:       float
    tax_rate:         float = 10.0

    @field_validator("quantity", "unit_price")
    @classmethod
    def must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Must be greater than zero")
        return v


class POCreate(BaseModel):
    # Core relationships
    vendor_id:           int
    requester_id:        int
    cost_center_id:      int

    # Core classification
    description:         str
    category:            POCategory
    priority:            POPriority = POPriority.medium

    # FileMaker identifiers (§2.9.2 Order identification)
    order_number:        Optional[str]  = None
    cutlist_no:          Optional[str]  = None
    supplier_ref_no:     Optional[str]  = None
    order_type:          Optional[str]  = None

    # Project & logistics (§2.9.2)
    project_name:        Optional[str]  = None
    location:            Optional[str]  = None

    # Dates (§2.9.2, §2.9.5)
    required_date:       Optional[date] = None
    requested_date:      Optional[date] = None
    requested_time:      Optional[time] = None
    date_ordered:        Optional[date] = None
    due_date:            Optional[date] = None
    arrived_date:        Optional[date] = None

    # Product detail (§2.9.2 + §2.9.4 Zone C)
    product_code:        Optional[str]  = None
    product_website:     Optional[str]  = None
    product_description: Optional[str]  = None
    product_image_path:  Optional[str]  = None
    stock_tracked:       bool           = False

    # Financials (§2.9.2 Pricing)
    quantity:            float          = 1.0
    unit_of_measure:     Optional[str]  = None
    unit_cost:           Optional[float] = None
    gst_applicable:      bool           = True
    gst_included_in_price: bool         = False
    currency:            str            = "AUD"

    # Notes & comments (§2.9.4 Zone D)
    notes:               Optional[str]  = None
    line_item_comments:  Optional[str]  = None   # PRINTED on PO
    internal_comments:   Optional[str]  = None   # NOT printed

    # Line items
    line_items:          List[LineItemCreate] = []


class POUpdate(BaseModel):
    description:         Optional[str]        = None
    category:            Optional[POCategory] = None
    priority:            Optional[POPriority] = None
    status:              Optional[POStatus]   = None

    order_number:        Optional[str]        = None
    cutlist_no:          Optional[str]        = None
    supplier_ref_no:     Optional[str]        = None
    order_type:          Optional[str]        = None

    project_name:        Optional[str]        = None
    location:            Optional[str]        = None

    required_date:       Optional[date]       = None
    date_ordered:        Optional[date]       = None
    due_date:            Optional[date]       = None
    arrived_date:        Optional[date]       = None

    product_code:        Optional[str]        = None
    product_website:     Optional[str]        = None
    product_description: Optional[str]        = None
    stock_tracked:       Optional[bool]       = None

    quantity:            Optional[float]      = None
    unit_of_measure:     Optional[str]        = None
    unit_cost:           Optional[float]      = None
    gst_applicable:      Optional[bool]       = None
    gst_included_in_price: Optional[bool]     = None

    notes:               Optional[str]        = None
    line_item_comments:  Optional[str]        = None
    internal_comments:   Optional[str]        = None
    changelog:           Optional[str]        = None


class VendorCreate(BaseModel):
    name:          str
    category:      POCategory
    contact_name:  Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    address:       Optional[str] = None
    tax_id:        Optional[str] = None
    payment_terms: Optional[str] = None


class ApprovalDecision(BaseModel):
    approver_id: int
    decision:    str   # "approve" | "reject"
    comments:    Optional[str] = None

    @field_validator("decision")
    @classmethod
    def valid_decision(cls, v):
        if v not in ("approve", "reject"):
            raise ValueError("Decision must be 'approve' or 'reject'")
        return v


class InventoryMovementCreate(BaseModel):
    item_id:          int
    po_id:            Optional[int] = None
    movement_type:    MovementType
    quantity:         float
    unit_cost:        Optional[float] = None
    reference_number: Optional[str] = None
    notes:            Optional[str] = None
    created_by:       Optional[int] = None


# ── Helpers ───────────────────────────────────────────────────────────────────
def _generate_po_number(db: Session, year: int) -> str:
    row = db.execute(
        text("SELECT COALESCE(MAX(CAST(SUBSTRING_INDEX(po_number,'-',-1) AS UNSIGNED)),0)+1 AS seq "
             "FROM purchase_orders WHERE YEAR(created_at) = :yr"),
        {"yr": year},
    ).first()
    seq = row.seq if row else 1
    return f"PO-{year}-{str(seq).zfill(4)}"


def _commit_budget(db: Session, po_id: int, cost_center_id: int, amount: float, tx_type: str = "Commitment"):
    db.execute(text("""
        INSERT INTO budget_transactions (cost_center_id, po_id, amount, transaction_type, transaction_date)
        VALUES (:cc, :po, :amt, :type, CURDATE())
    """), {"cc": cost_center_id, "po": po_id, "amt": amount, "type": tx_type})


def _append_changelog(db: Session, po_id: int, entry: str, user_id: Optional[int] = None):
    """Append a timestamped line to the purchase_orders.changelog column (FileMaker: ChangeLog, §2.9.4 Zone D)."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    who   = f" [user #{user_id}]" if user_id else ""
    db.execute(
        text("UPDATE purchase_orders "
             "SET changelog = CONCAT(COALESCE(changelog,''), :line) "
             "WHERE po_id = :id"),
        {"line": f"{stamp}{who} — {entry}\n", "id": po_id},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Purchase Orders — core CRUD
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/orders", tags=["Orders"])
def list_orders(
    status:       Optional[POStatus]   = None,
    category:     Optional[POCategory] = None,
    priority:     Optional[POPriority] = None,
    vendor_id:    Optional[int]        = None,
    requester_id: Optional[int]        = None,
    project_name: Optional[str]        = None,
    cutlist_no:   Optional[str]        = None,
    search:       Optional[str]        = None,
    required_from: Optional[date]      = None,
    required_to:   Optional[date]      = None,
    limit:        int = Query(50, le=500),
    offset:       int = 0,
    db: Session = Depends(get_db),
):
    q      = "SELECT * FROM v_po_summary WHERE 1=1"
    params: dict = {}
    if status:        q += " AND status = :status";         params["status"]       = status
    if category:      q += " AND category = :category";     params["category"]     = category
    if priority:      q += " AND priority = :priority";     params["priority"]     = priority
    if vendor_id:     q += " AND vendor_id = :vendor_id";   params["vendor_id"]    = vendor_id
    if requester_id:  q += " AND requester_id = :req_id";   params["req_id"]       = requester_id
    if project_name:  q += " AND project_name = :proj";     params["proj"]         = project_name
    if cutlist_no:    q += " AND cutlist_no LIKE :cut";     params["cut"]          = f"%{cutlist_no}%"
    if required_from: q += " AND required_date >= :r_from"; params["r_from"]       = required_from
    if required_to:   q += " AND required_date <= :r_to";   params["r_to"]         = required_to
    if search:
        q += (" AND (po_number LIKE :s OR order_number LIKE :s OR vendor_name LIKE :s "
              "OR description LIKE :s OR product_code LIKE :s OR location LIKE :s)")
        params["s"] = f"%{search}%"
    q += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    params.update({"limit": limit, "offset": offset})
    return [dict(r) for r in db.execute(text(q), params).mappings()]


@app.get("/api/orders/{po_id}", tags=["Orders"])
def get_order(po_id: int, db: Session = Depends(get_db)):
    """Return PO summary + line items + attachments + approval workflow."""
    po = db.execute(
        text("SELECT * FROM v_po_summary WHERE po_id = :id"), {"id": po_id}
    ).mappings().first()
    if not po:
        raise HTTPException(404, "Purchase order not found")

    lines = db.execute(
        text("SELECT * FROM po_line_items WHERE po_id = :id ORDER BY line_number"),
        {"id": po_id},
    ).mappings().all()

    attachments = db.execute(
        text("SELECT a.*, u.name AS uploaded_by_name "
             "FROM po_attachments a LEFT JOIN users u ON a.uploaded_by = u.user_id "
             "WHERE a.po_id = :id ORDER BY a.uploaded_at DESC"),
        {"id": po_id},
    ).mappings().all()

    wf = db.execute(
        text("SELECT aw.*, u.name AS approver_name FROM approval_workflows aw "
             "JOIN users u ON aw.approver_id = u.user_id "
             "WHERE aw.po_id = :id ORDER BY sequence_order"),
        {"id": po_id},
    ).mappings().all()

    # Full record (extra FileMaker fields not in the summary view)
    extra = db.execute(
        text("SELECT product_website, product_description, product_image_path, "
             "       line_item_comments, internal_comments, changelog, "
             "       gst_applicable, gst_included_in_price, unit_cost, notes "
             "  FROM purchase_orders WHERE po_id = :id"),
        {"id": po_id},
    ).mappings().first()

    return {
        "order":       {**dict(po), **(dict(extra) if extra else {})},
        "line_items":  [dict(l) for l in lines],
        "attachments": [dict(a) for a in attachments],
        "workflow":    [dict(w) for w in wf],
    }


@app.post("/api/orders", status_code=201, tags=["Orders"])
def create_order(payload: POCreate, db: Session = Depends(get_db)):
    po_number = _generate_po_number(db, datetime.now().year)

    result = db.execute(text("""
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
    """), {"po_number": po_number, **payload.model_dump(exclude={"line_items"})})

    po_id = result.lastrowid

    for line in payload.line_items:
        db.execute(text("""
            INSERT INTO po_line_items
                (po_id, line_number, item_description, sku, quantity, unit, unit_price, tax_rate)
            VALUES
                (:po_id, :line_number, :item_description, :sku, :quantity, :unit, :unit_price, :tax_rate)
        """), {"po_id": po_id, **line.model_dump()})

    _append_changelog(db, po_id, f"Created as Draft (PO {po_number})", payload.requester_id)
    db.commit()
    return {"po_id": po_id, "po_number": po_number, "status": "Draft"}


@app.patch("/api/orders/{po_id}", tags=["Orders"])
def update_order(po_id: int, payload: POUpdate, db: Session = Depends(get_db)):
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    params = {**fields, "po_id": po_id}
    db.execute(text(f"UPDATE purchase_orders SET {set_clause} WHERE po_id = :po_id"), params)
    _append_changelog(db, po_id, f"Updated fields: {', '.join(fields.keys())}")
    db.commit()
    return {"updated": True, "fields": list(fields.keys())}


@app.patch("/api/orders/{po_id}/submit", tags=["Orders"])
def submit_for_approval(po_id: int, approver_id: int, db: Session = Depends(get_db)):
    """Move PO from Draft → Pending and create approval workflow record."""
    affected = db.execute(
        text("UPDATE purchase_orders SET status='Pending' WHERE po_id=:id AND status='Draft'"),
        {"id": po_id},
    ).rowcount
    if not affected:
        raise HTTPException(400, "PO is not in Draft status")
    db.execute(text("""
        INSERT INTO approval_workflows (po_id, approver_id, sequence_order)
        VALUES (:po_id, :approver_id, 1)
    """), {"po_id": po_id, "approver_id": approver_id})
    _append_changelog(db, po_id, f"Submitted for approval → user #{approver_id}")
    db.commit()
    return {"status": "Pending", "message": "Submitted for approval"}


@app.patch("/api/orders/{po_id}/deliver", tags=["Orders"])
def mark_delivered(po_id: int, arrived_date: Optional[date] = None, db: Session = Depends(get_db)):
    """Mark PO as Delivered; records arrived_date (FileMaker: ARRIVED) and converts commitment to expenditure."""
    db.execute(text("""
        UPDATE purchase_orders
           SET status='Delivered',
               delivery_date = CURDATE(),
               arrived_date  = COALESCE(:arr, CURDATE())
         WHERE po_id = :id AND status = 'Approved'
    """), {"id": po_id, "arr": arrived_date})
    po = db.execute(
        text("SELECT cost_center_id, grand_total FROM purchase_orders WHERE po_id=:id"), {"id": po_id}
    ).first()
    if po:
        _commit_budget(db, po_id, po.cost_center_id, float(po.grand_total or 0), "Expenditure")
    _append_changelog(db, po_id, "Marked Delivered — arrived on site")
    db.commit()
    return {"status": "Delivered"}


@app.delete("/api/orders/{po_id}", tags=["Orders"])
def cancel_order(po_id: int, db: Session = Depends(get_db)):
    db.execute(
        text("UPDATE purchase_orders SET status='Cancelled' WHERE po_id=:id AND status IN ('Draft','Rejected','Hold')"),
        {"id": po_id},
    )
    _append_changelog(db, po_id, "Cancelled")
    db.commit()
    return {"status": "Cancelled"}


@app.post("/api/orders/{po_id}/duplicate", tags=["Orders"], status_code=201)
def duplicate_order(po_id: int, db: Session = Depends(get_db)):
    """FileMaker Details window → DUPLICATE button (§2.9.1)."""
    src = db.execute(text("SELECT * FROM purchase_orders WHERE po_id = :id"), {"id": po_id}).mappings().first()
    if not src:
        raise HTTPException(404, "Purchase order not found")

    new_po = _generate_po_number(db, datetime.now().year)
    # Copy FileMaker-relevant fields; reset status and dates
    db.execute(text("""
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
    """), {"new_po": new_po, "id": po_id})
    new_id = db.execute(text("SELECT LAST_INSERT_ID() AS i")).first().i
    # Copy line items
    db.execute(text("""
        INSERT INTO po_line_items (po_id, line_number, item_description, sku, quantity, unit, unit_price, tax_rate)
        SELECT :new_id, line_number, item_description, sku, quantity, unit, unit_price, tax_rate
          FROM po_line_items WHERE po_id = :id
    """), {"new_id": new_id, "id": po_id})
    _append_changelog(db, new_id, f"Duplicated from {src['po_number']}")
    db.commit()
    return {"po_id": new_id, "po_number": new_po, "source_po_id": po_id}


# ═══════════════════════════════════════════════════════════════════════════════
# FileMaker Orderbook quick-filters (see filemaker.md §2.2)
# ═══════════════════════════════════════════════════════════════════════════════

def _filter_query(where: str, params: Optional[dict] = None) -> str:
    return f"SELECT * FROM v_po_summary WHERE {where} ORDER BY required_date ASC, created_at DESC"


@app.get("/api/orders/filter/rto", tags=["FileMaker Filters"])
def filter_rto(db: Session = Depends(get_db)):
    """RTO — only show items with status NEXT (filemaker.md §2.2)."""
    return [dict(r) for r in db.execute(text(_filter_query("status = 'Next'"))).mappings()]


@app.get("/api/orders/filter/tbo", tags=["FileMaker Filters"])
def filter_tbo(db: Session = Depends(get_db)):
    """TBO — only show items with status NEXT or QUOTE (filemaker.md §2.2)."""
    return [dict(r) for r in db.execute(text(_filter_query("status IN ('Next','Quote')"))).mappings()]


@app.get("/api/orders/filter/due", tags=["FileMaker Filters"])
def filter_due(db: Session = Depends(get_db)):
    """Due — show items with a due_date set and not yet arrived (filemaker.md §2.2)."""
    return [dict(r) for r in db.execute(
        text(_filter_query("due_date IS NOT NULL AND arrived_date IS NULL "
                           "AND status NOT IN ('Cancelled','Rejected')"))
    ).mappings()]


@app.get("/api/orders/filter/overdue", tags=["FileMaker Filters"])
def filter_overdue(db: Session = Depends(get_db)):
    """Over Due — required_date has passed, item not yet arrived (filemaker.md §2.2)."""
    return [dict(r) for r in db.execute(text("""
        SELECT * FROM v_po_summary
         WHERE required_date IS NOT NULL
           AND required_date < CURDATE()
           AND arrived_date IS NULL
           AND status NOT IN ('Delivered','Cancelled','Rejected')
         ORDER BY required_date ASC
    """)).mappings()]


@app.get("/api/orders/filter/arrived", tags=["FileMaker Filters"])
def filter_arrived(db: Session = Depends(get_db)):
    """Arrived — items that have been received (arrived_date is set)."""
    return [dict(r) for r in db.execute(
        text(_filter_query("arrived_date IS NOT NULL"))
    ).mappings()]


@app.get("/api/orders/filter/my-orders", tags=["FileMaker Filters"])
def filter_my_orders(requester_id: int, db: Session = Depends(get_db)):
    """My Orders — orders raised by the given requester."""
    return [dict(r) for r in db.execute(
        text(f"{_filter_query('requester_id = :rid')}"), {"rid": requester_id}
    ).mappings()]


@app.get("/api/orders/filter/clear", tags=["FileMaker Filters"])
def filter_clear(db: Session = Depends(get_db)):
    """CLEAR — show only items with required_date within the past two years (filemaker.md §2.2)."""
    return [dict(r) for r in db.execute(text("""
        SELECT * FROM v_po_summary
         WHERE required_date IS NOT NULL
           AND required_date >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
         ORDER BY required_date DESC
    """)).mappings()]


# ═══════════════════════════════════════════════════════════════════════════════
# PO Attachments (FileMaker Details HOME tab Zones B & C — §2.9.4)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/orders/{po_id}/attachments", tags=["Attachments"])
def list_attachments(po_id: int, db: Session = Depends(get_db)):
    return [dict(r) for r in db.execute(text("""
        SELECT a.*, u.name AS uploaded_by_name
          FROM po_attachments a
          LEFT JOIN users u ON a.uploaded_by = u.user_id
         WHERE a.po_id = :id
         ORDER BY a.uploaded_at DESC
    """), {"id": po_id}).mappings()]


@app.post("/api/orders/{po_id}/attachments", status_code=201, tags=["Attachments"])
async def upload_attachment(
    po_id: int,
    file: UploadFile = File(...),
    attachment_type: AttachmentType = Form(AttachmentType.file),
    uploaded_by: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """Accept a file upload and register metadata in po_attachments.
    Storage: local UPLOAD_DIR/<po_id>/<filename>. Swap for S3/Azure in prod.
    """
    target_dir = UPLOAD_DIR / str(po_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name
    target    = target_dir / safe_name

    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    size = target.stat().st_size

    result = db.execute(text("""
        INSERT INTO po_attachments
            (po_id, attachment_type, file_name, file_size_bytes, file_path, uploaded_by)
        VALUES
            (:po_id, :atype, :fn, :sz, :fp, :uid)
    """), {
        "po_id": po_id, "atype": attachment_type, "fn": safe_name,
        "sz": size, "fp": str(target), "uid": uploaded_by,
    })
    _append_changelog(db, po_id, f"Attached {attachment_type.value}: {safe_name}", uploaded_by)
    db.commit()
    return {
        "attachment_id": result.lastrowid,
        "po_id": po_id,
        "file_name": safe_name,
        "file_size_bytes": size,
        "attachment_type": attachment_type,
    }


@app.delete("/api/orders/{po_id}/attachments/{attachment_id}", tags=["Attachments"])
def delete_attachment(po_id: int, attachment_id: int, db: Session = Depends(get_db)):
    row = db.execute(
        text("SELECT file_path, file_name FROM po_attachments WHERE attachment_id=:a AND po_id=:p"),
        {"a": attachment_id, "p": po_id},
    ).first()
    if not row:
        raise HTTPException(404, "Attachment not found")
    try:
        if row.file_path and Path(row.file_path).exists():
            Path(row.file_path).unlink()
    except OSError:
        pass
    db.execute(text("DELETE FROM po_attachments WHERE attachment_id=:a"), {"a": attachment_id})
    _append_changelog(db, po_id, f"Removed attachment: {row.file_name}")
    db.commit()
    return {"deleted": True}


# ═══════════════════════════════════════════════════════════════════════════════
# Approvals
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/approvals/pending", tags=["Approvals"])
def pending_approvals(approver_id: int, db: Session = Depends(get_db)):
    return [dict(r) for r in db.execute(text("""
        SELECT aw.workflow_id, aw.po_id, aw.sequence_order, aw.created_at,
               ps.po_number, ps.vendor_name, ps.description, ps.total_amount, ps.grand_total,
               ps.currency, ps.category, ps.priority, ps.project_name,
               ps.requester_name, ps.cost_center
        FROM approval_workflows aw
        JOIN v_po_summary ps ON aw.po_id = ps.po_id
        WHERE aw.approver_id = :approver_id AND aw.status = 'Pending'
        ORDER BY aw.created_at ASC
    """), {"approver_id": approver_id}).mappings()]


@app.post("/api/approvals/{workflow_id}/decide", tags=["Approvals"])
def decide_approval(workflow_id: int, action: ApprovalDecision, db: Session = Depends(get_db)):
    wf = db.execute(
        text("SELECT * FROM approval_workflows WHERE workflow_id = :id"), {"id": workflow_id}
    ).mappings().first()
    if not wf:
        raise HTTPException(404, "Workflow not found")
    if wf["status"] != "Pending":
        raise HTTPException(400, "This approval has already been acted on")

    new_status = "Approved" if action.decision == "approve" else "Rejected"

    db.execute(text("""
        UPDATE approval_workflows SET status=:s, comments=:c, acted_at=NOW()
        WHERE workflow_id=:id
    """), {"s": new_status, "c": action.comments, "id": workflow_id})

    db.execute(text("UPDATE purchase_orders SET status=:s WHERE po_id=:po_id"),
               {"s": new_status, "po_id": wf["po_id"]})

    if new_status == "Approved":
        po = db.execute(
            text("SELECT cost_center_id, grand_total FROM purchase_orders WHERE po_id=:id"),
            {"id": wf["po_id"]},
        ).first()
        if po:
            _commit_budget(db, wf["po_id"], po.cost_center_id, float(po.grand_total or 0), "Commitment")

    _append_changelog(db, wf["po_id"], f"{new_status} by approver #{action.approver_id}", action.approver_id)
    db.commit()
    return {"workflow_id": workflow_id, "decision": new_status}


@app.get("/api/approvals/history", tags=["Approvals"])
def approval_history(
    approver_id: Optional[int] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    q = """
        SELECT aw.*, ps.po_number, ps.vendor_name, ps.grand_total, ps.requester_name, u.name AS approver_name
        FROM approval_workflows aw
        JOIN v_po_summary ps ON aw.po_id = ps.po_id
        JOIN users u ON aw.approver_id = u.user_id
        WHERE aw.status != 'Pending'
    """
    params: dict = {"limit": limit}
    if approver_id:
        q += " AND aw.approver_id = :approver_id"
        params["approver_id"] = approver_id
    q += " ORDER BY aw.acted_at DESC LIMIT :limit"
    return [dict(r) for r in db.execute(text(q), params).mappings()]


# ═══════════════════════════════════════════════════════════════════════════════
# Vendors
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/vendors", tags=["Vendors"])
def list_vendors(
    category: Optional[str]          = None,
    status:   Optional[VendorStatus] = None,
    search:   Optional[str]          = None,
    db: Session = Depends(get_db),
):
    q = """
        SELECT v.*, COUNT(po.po_id) AS active_pos
        FROM vendors v
        LEFT JOIN purchase_orders po ON v.vendor_id = po.vendor_id
            AND po.status NOT IN ('Delivered','Cancelled')
        WHERE 1=1
    """
    params: dict = {}
    if category: q += " AND v.category = :cat";  params["cat"]    = category
    if status:   q += " AND v.status = :status"; params["status"] = status
    if search:   q += " AND v.name LIKE :s";     params["s"]      = f"%{search}%"
    q += " GROUP BY v.vendor_id ORDER BY v.name"
    return [dict(r) for r in db.execute(text(q), params).mappings()]


@app.get("/api/vendors/{vendor_id}", tags=["Vendors"])
def get_vendor(vendor_id: int, db: Session = Depends(get_db)):
    vendor = db.execute(
        text("SELECT * FROM vendors WHERE vendor_id = :id"), {"id": vendor_id}
    ).mappings().first()
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    orders = db.execute(
        text("SELECT po_number, description, grand_total, status, created_at "
             "FROM v_po_summary WHERE vendor_id = :id ORDER BY created_at DESC LIMIT 20"),
        {"id": vendor_id},
    ).mappings().all()
    return {"vendor": dict(vendor), "recent_orders": [dict(o) for o in orders]}


@app.post("/api/vendors", status_code=201, tags=["Vendors"])
def create_vendor(payload: VendorCreate, db: Session = Depends(get_db)):
    result = db.execute(text("""
        INSERT INTO vendors (name, category, contact_name, contact_email, contact_phone, address, tax_id, payment_terms)
        VALUES (:name, :category, :contact_name, :contact_email, :contact_phone, :address, :tax_id, :payment_terms)
    """), payload.model_dump())
    db.commit()
    return {"vendor_id": result.lastrowid}


@app.patch("/api/vendors/{vendor_id}/rating", tags=["Vendors"])
def update_vendor_rating(vendor_id: int, rating: float = Query(..., ge=0, le=5), db: Session = Depends(get_db)):
    db.execute(text("UPDATE vendors SET rating = :r WHERE vendor_id = :id"), {"r": round(rating, 1), "id": vendor_id})
    db.commit()
    return {"vendor_id": vendor_id, "rating": round(rating, 1)}


# ═══════════════════════════════════════════════════════════════════════════════
# Inventory
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/inventory", tags=["Inventory"])
def list_inventory(
    stock_level: Optional[str] = Query(None, pattern="^(OK|Low|Critical)$"),
    search:      Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = "SELECT * FROM v_inventory_status WHERE 1=1"
    params: dict = {}
    if stock_level: q += " AND stock_level = :lv"; params["lv"] = stock_level
    if search:      q += " AND (name LIKE :s OR sku LIKE :s OR category LIKE :s)"; params["s"] = f"%{search}%"
    q += " ORDER BY stock_level DESC, name"
    return [dict(r) for r in db.execute(text(q), params).mappings()]


@app.get("/api/inventory/low-stock", tags=["Inventory"])
def low_stock_alerts(db: Session = Depends(get_db)):
    """Returns items at or below reorder point, sorted by urgency."""
    return [dict(r) for r in db.execute(text("""
        SELECT * FROM v_inventory_status
        WHERE stock_level IN ('Low','Critical')
        ORDER BY FIELD(stock_level,'Critical','Low'), (quantity_on_hand / NULLIF(reorder_point,0)) ASC
    """)).mappings()]


@app.post("/api/inventory/movements", status_code=201, tags=["Inventory"])
def record_movement(payload: InventoryMovementCreate, db: Session = Depends(get_db)):
    db.execute(text("""
        INSERT INTO inventory_movements (item_id, po_id, movement_type, quantity, unit_cost, reference_number, notes, created_by)
        VALUES (:item_id, :po_id, :movement_type, :quantity, :unit_cost, :reference_number, :notes, :created_by)
    """), payload.model_dump())
    direction = 1 if payload.movement_type == "IN" else -1
    db.execute(text("""
        UPDATE inventory SET quantity_on_hand = quantity_on_hand + (:direction * :quantity), updated_at = NOW()
        WHERE item_id = :item_id
    """), {"direction": direction, "quantity": payload.quantity, "item_id": payload.item_id})
    db.commit()
    return {"recorded": True}


# ═══════════════════════════════════════════════════════════════════════════════
# Budget
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/budget", tags=["Budget"])
def get_budget(fiscal_year: Optional[int] = None, db: Session = Depends(get_db)):
    q = "SELECT * FROM v_budget_utilisation WHERE 1=1"
    params: dict = {}
    if fiscal_year: q += " AND fiscal_year = :yr"; params["yr"] = fiscal_year
    q += " ORDER BY utilisation_pct DESC"
    return [dict(r) for r in db.execute(text(q), params).mappings()]


@app.get("/api/budget/summary", tags=["Budget"])
def get_budget_summary(db: Session = Depends(get_db)):
    return dict(db.execute(text("""
        SELECT
            SUM(budget_amount)    AS total_budget,
            SUM(total_committed)  AS total_spent,
            SUM(remaining)        AS total_remaining,
            ROUND(SUM(total_committed) / NULLIF(SUM(budget_amount),0) * 100, 1) AS overall_utilisation_pct
        FROM v_budget_utilisation
    """)).mappings().first())


@app.get("/api/budget/{cost_center_id}/transactions", tags=["Budget"])
def cost_center_transactions(cost_center_id: int, db: Session = Depends(get_db)):
    return [dict(r) for r in db.execute(text("""
        SELECT bt.*, po.po_number, u.name AS created_by_name
        FROM budget_transactions bt
        LEFT JOIN purchase_orders po ON bt.po_id = po.po_id
        LEFT JOIN users u ON bt.created_by = u.user_id
        WHERE bt.cost_center_id = :cc
        ORDER BY bt.transaction_date DESC
    """), {"cc": cost_center_id}).mappings()]


# ═══════════════════════════════════════════════════════════════════════════════
# Meta / Health
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/meta/statuses", tags=["Meta"])
def list_statuses():
    """Return all PO statuses + FileMaker priority values used in the UI dropdowns."""
    return {
        "statuses":   [s.value for s in POStatus],
        "priorities": [p.value for p in POPriority],
        "categories": [c.value for c in POCategory],
    }


@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok", "service": "Procurement Orderbook API", "version": app.version}
