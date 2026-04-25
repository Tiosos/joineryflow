"""FastAPI routes for the procurement module.

Each endpoint is gated with `require_permission("orderbook", action)` per
the static RBAC matrix in app.auth.permissions.

Transactions: this file owns db.commit() / db.rollback(). queries.py never
commits.
"""
import os
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    ApprovalDecision,
    AttachmentType,
    InventoryMovementCreate,
    POCategory,
    POCreate,
    POPriority,
    POStatus,
    POUpdate,
    VendorCreate,
    VendorStatus,
)

router = APIRouter(prefix="/procurement", tags=["procurement"])

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))


def _enum_value(v):
    return v.value if hasattr(v, "value") else v


# ═══════════════════════════════════════════════════════════════════════════════
# Purchase orders
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/orders")
def list_orders(
    status: Optional[POStatus] = None,
    category: Optional[POCategory] = None,
    priority: Optional[POPriority] = None,
    vendor_id: Optional[int] = None,
    requester_id: Optional[int] = None,
    project_name: Optional[str] = None,
    cutlist_no: Optional[str] = None,
    search: Optional[str] = None,
    required_from: Optional[date] = None,
    required_to: Optional[date] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.list_orders(
        db,
        status=_enum_value(status) if status else None,
        category=_enum_value(category) if category else None,
        priority=_enum_value(priority) if priority else None,
        vendor_id=vendor_id,
        requester_id=requester_id,
        project_name=project_name,
        cutlist_no=cutlist_no,
        search=search,
        required_from=required_from,
        required_to=required_to,
        limit=limit,
        offset=offset,
    )


@router.get("/orders/{po_id}")
def get_order(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    summary = q.get_order_summary(db, po_id)
    if not summary:
        raise HTTPException(404, "Purchase order not found")
    extra = q.get_order_extra(db, po_id) or {}
    return {
        "order": {**summary, **extra},
        "line_items": q.get_order_lines(db, po_id),
        "attachments": q.get_order_attachments(db, po_id),
        "workflow": q.get_order_workflow(db, po_id),
    }


@router.post("/orders", status_code=201)
def create_order(
    payload: POCreate,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    po_number = q.generate_po_number(db, datetime.now().year)
    body = payload.model_dump(exclude={"line_items"})
    for key in ("category", "priority"):
        body[key] = _enum_value(body[key])
    po_id = q.insert_order(db, po_number, body)
    for line in payload.line_items:
        q.insert_line_item(db, po_id, line.model_dump())
    q.append_changelog(db, po_id, f"Created as Draft (PO {po_number})", payload.requester_id)
    db.commit()
    return {"po_id": po_id, "po_number": po_number, "status": "Draft"}


@router.patch("/orders/{po_id}")
def update_order(
    po_id: int,
    payload: POUpdate,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    for k, v in list(fields.items()):
        fields[k] = _enum_value(v)
    q.update_order_fields(db, po_id, fields)
    q.append_changelog(db, po_id, f"Updated fields: {', '.join(fields.keys())}")
    db.commit()
    return {"updated": True, "fields": list(fields.keys())}


@router.patch("/orders/{po_id}/submit")
def submit_for_approval(
    po_id: int,
    approver_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    affected = q.submit_for_approval(db, po_id, approver_id)
    if not affected:
        raise HTTPException(400, "PO is not in Draft status")
    q.append_changelog(db, po_id, f"Submitted for approval → user #{approver_id}")
    db.commit()
    return {"status": "Pending", "message": "Submitted for approval"}


@router.patch("/orders/{po_id}/deliver")
def mark_delivered(
    po_id: int,
    arrived_date: Optional[date] = None,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    po = q.mark_delivered(db, po_id, arrived_date)
    if po:
        q.commit_budget(
            db,
            po_id,
            int(po["cost_center_id"]),
            float(po["grand_total"] or 0),
            "Expenditure",
        )
    q.append_changelog(db, po_id, "Marked Delivered — arrived on site")
    db.commit()
    return {"status": "Delivered"}


@router.delete("/orders/{po_id}")
def cancel_order(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    q.cancel_order(db, po_id)
    q.append_changelog(db, po_id, "Cancelled")
    db.commit()
    return {"status": "Cancelled"}


@router.post("/orders/{po_id}/duplicate", status_code=201)
def duplicate_order(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    src = q.get_order_raw(db, po_id)
    if not src:
        raise HTTPException(404, "Purchase order not found")
    new_po_number = q.generate_po_number(db, datetime.now().year)
    new_id = q.duplicate_order(db, po_id, new_po_number)
    q.append_changelog(db, new_id, f"Duplicated from {src['po_number']}")
    db.commit()
    return {"po_id": new_id, "po_number": new_po_number, "source_po_id": po_id}


# ═══════════════════════════════════════════════════════════════════════════════
# FileMaker quick-filters
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/orders/filter/rto")
def filter_rto(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.filter_rto(db)


@router.get("/orders/filter/tbo")
def filter_tbo(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.filter_tbo(db)


@router.get("/orders/filter/due")
def filter_due(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.filter_due(db)


@router.get("/orders/filter/overdue")
def filter_overdue(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.filter_overdue(db)


@router.get("/orders/filter/arrived")
def filter_arrived(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.filter_arrived(db)


@router.get("/orders/filter/my-orders")
def filter_my_orders(
    requester_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.filter_my_orders(db, requester_id)


@router.get("/orders/filter/clear")
def filter_clear(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.filter_clear(db)


# ═══════════════════════════════════════════════════════════════════════════════
# Attachments
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/orders/{po_id}/attachments")
def list_attachments(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.list_attachments(db, po_id)


@router.post("/orders/{po_id}/attachments", status_code=201)
async def upload_attachment(
    po_id: int,
    file: UploadFile = File(...),
    attachment_type: AttachmentType = Form(AttachmentType.file),
    uploaded_by: Optional[int] = Form(None),
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target_dir = UPLOAD_DIR / str(po_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "attachment").name
    target = target_dir / safe_name

    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    size = target.stat().st_size

    attachment_id = q.insert_attachment(
        db,
        po_id=po_id,
        attachment_type=attachment_type.value,
        file_name=safe_name,
        file_size_bytes=size,
        file_path=str(target),
        uploaded_by=uploaded_by,
    )
    q.append_changelog(
        db,
        po_id,
        f"Attached {attachment_type.value}: {safe_name}",
        uploaded_by,
    )
    db.commit()
    return {
        "attachment_id": attachment_id,
        "po_id": po_id,
        "file_name": safe_name,
        "file_size_bytes": size,
        "attachment_type": attachment_type.value,
    }


@router.delete("/orders/{po_id}/attachments/{attachment_id}")
def delete_attachment(
    po_id: int,
    attachment_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    row = q.get_attachment(db, po_id, attachment_id)
    if not row:
        raise HTTPException(404, "Attachment not found")
    try:
        if row["file_path"] and Path(row["file_path"]).exists():
            Path(row["file_path"]).unlink()
    except OSError:
        pass
    q.delete_attachment(db, attachment_id)
    q.append_changelog(db, po_id, f"Removed attachment: {row['file_name']}")
    db.commit()
    return {"deleted": True}


# ═══════════════════════════════════════════════════════════════════════════════
# Approvals
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/approvals/pending")
def pending_approvals(
    approver_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "approve")),
    db: Session = Depends(get_db),
):
    return q.list_pending_approvals(db, approver_id)


@router.post("/approvals/{workflow_id}/decide")
def decide_approval(
    workflow_id: int,
    action: ApprovalDecision,
    user: AuthUser = Depends(require_permission("orderbook", "approve")),
    db: Session = Depends(get_db),
):
    wf = q.get_workflow(db, workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    if wf["status"] != "Pending":
        raise HTTPException(400, "This approval has already been acted on")

    new_status = "Approved" if action.decision == "approve" else "Rejected"
    q.update_workflow_decision(db, workflow_id, new_status, action.comments)
    q.update_po_status(db, wf["po_id"], new_status)

    if new_status == "Approved":
        po = q.get_po_budget_fields(db, wf["po_id"])
        if po:
            q.commit_budget(
                db,
                wf["po_id"],
                int(po["cost_center_id"]),
                float(po["grand_total"] or 0),
                "Commitment",
            )

    q.append_changelog(
        db,
        wf["po_id"],
        f"{new_status} by approver #{action.approver_id}",
        action.approver_id,
    )
    db.commit()
    return {"workflow_id": workflow_id, "decision": new_status}


@router.get("/approvals/history")
def approval_history(
    approver_id: Optional[int] = None,
    limit: int = Query(50, le=200),
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.approval_history(db, approver_id=approver_id, limit=limit)


# ═══════════════════════════════════════════════════════════════════════════════
# Vendors
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/vendors")
def list_vendors(
    category: Optional[str] = None,
    status: Optional[VendorStatus] = None,
    search: Optional[str] = None,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.list_vendors(
        db,
        category=category,
        status=_enum_value(status) if status else None,
        search=search,
    )


@router.get("/vendors/{vendor_id}")
def get_vendor(
    vendor_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    vendor = q.get_vendor(db, vendor_id)
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    return {
        "vendor": vendor,
        "recent_orders": q.vendor_recent_orders(db, vendor_id),
    }


@router.post("/vendors", status_code=201)
def create_vendor(
    payload: VendorCreate,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    body = payload.model_dump()
    body["category"] = _enum_value(body["category"])
    vendor_id = q.insert_vendor(db, body)
    db.commit()
    return {"vendor_id": vendor_id}


@router.patch("/vendors/{vendor_id}/rating")
def update_vendor_rating(
    vendor_id: int,
    rating: float = Query(..., ge=0, le=5),
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    rounded = round(rating, 1)
    q.update_vendor_rating(db, vendor_id, rounded)
    db.commit()
    return {"vendor_id": vendor_id, "rating": rounded}


# ═══════════════════════════════════════════════════════════════════════════════
# Inventory
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/inventory")
def list_inventory(
    stock_level: Optional[str] = Query(None, pattern="^(OK|Low|Critical)$"),
    search: Optional[str] = None,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.list_inventory(db, stock_level=stock_level, search=search)


@router.get("/inventory/low-stock")
def low_stock_alerts(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.low_stock(db)


@router.post("/inventory/movements", status_code=201)
def record_movement(
    payload: InventoryMovementCreate,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    body = payload.model_dump()
    body["movement_type"] = _enum_value(body["movement_type"])
    q.insert_inventory_movement(db, body)
    direction = 1 if body["movement_type"] == "IN" else -1
    q.adjust_inventory(db, payload.item_id, direction, payload.quantity)
    db.commit()
    return {"recorded": True}


# ═══════════════════════════════════════════════════════════════════════════════
# Budget
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/budget")
def get_budget(
    fiscal_year: Optional[int] = None,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.list_budget(db, fiscal_year=fiscal_year)


@router.get("/budget/summary")
def get_budget_summary(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.budget_summary(db)


@router.get("/budget/{cost_center_id}/transactions")
def cost_center_transactions(
    cost_center_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.cost_center_transactions(db, cost_center_id)


# ═══════════════════════════════════════════════════════════════════════════════
# Meta
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/meta/statuses")
def list_statuses(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
):
    return {
        "statuses": [s.value for s in POStatus],
        "priorities": [p.value for p in POPriority],
        "categories": [c.value for c in POCategory],
    }
