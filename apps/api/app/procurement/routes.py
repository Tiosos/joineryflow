"""FastAPI routes for the procurement module.

Each endpoint is gated with `require_permission("orderbook", action)` per
the static RBAC matrix in app.auth.permissions.

Transactions: this file owns db.commit() / db.rollback(). queries.py never
commits.

Workspace isolation: every order/attachment/approval route either passes
`workspace_id=user.workspace_id` into a list/filter query or checks
`q.po_in_workspace(...)` before touching a specific po_id; budget routes pass
`workspace_id` through to the `_CC_IN_WORKSPACE` filter — see the note atop
queries.py.
"""
import os
import uuid
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
from ..files.validators import MAX_BYTE_SIZE
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
    limit: int = Query(50, ge=0, le=500),
    offset: int = Query(0, ge=0),
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.list_orders(
        db,
        workspace_id=user.workspace_id,
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
    if not q.po_in_workspace(db, po_id=po_id, workspace_id=user.workspace_id):
        raise HTTPException(404, "Purchase order not found")
    summary = q.get_order_summary(db, po_id)
    if not summary:
        raise HTTPException(404, "Purchase order not found")
    extra = q.get_order_extra(db, po_id) or {}
    return {
        "order": {**summary, **extra},
        "line_items": q.get_order_lines(db, po_id),
        "attachments": q.get_order_attachments(db, po_id, workspace_id=user.workspace_id),
        "workflow": q.get_order_workflow(db, po_id),
    }


@router.post("/orders", status_code=201)
def create_order(
    payload: POCreate,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    if not q.vendor_in_workspace(db, vendor_id=payload.vendor_id, workspace_id=user.workspace_id):
        raise HTTPException(422, "vendor not found in this workspace")
    if not q.cost_center_in_workspace(
        db, cost_center_id=payload.cost_center_id, workspace_id=user.workspace_id
    ):
        raise HTTPException(422, "cost center not found in this workspace")
    if not q.user_in_workspace(db, user_id=payload.requester_id, workspace_id=user.workspace_id):
        raise HTTPException(422, "requester not found in this workspace")
    po_number = q.generate_po_number(db, datetime.now().year)
    body = payload.model_dump(exclude={"line_items"})
    for key in ("category", "priority"):
        body[key] = _enum_value(body[key])
    po_id = q.insert_order(db, po_number, body)
    for line in payload.line_items:
        q.insert_line_item(db, po_id, line.model_dump())
    # The MySQL triggers that summed the lines into `total_amount` were not ported (0002
    # left it to the application and this route never did it), so every commitment and
    # expenditure posted $0. The same rollup the v1 orders module uses.
    q.recompute_total_amount(db, po_id=po_id)
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
    if not q.po_in_workspace(db, po_id=po_id, workspace_id=user.workspace_id):
        raise HTTPException(404, "Purchase order not found")
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    for k, v in list(fields.items()):
        fields[k] = _enum_value(v)

    # The same rule as the v1 orders module: a Cancelled / Delivered order is read-only
    # except for `status`, the deliberate way back in. On any other order `status` is not
    # writable here — it moves through submit / decide / deliver / delete, which post the
    # budget rows; a PATCH used to jump Draft → Approved (no workflow, no commitment),
    # → Delivered (no expenditure) or Approved → Cancelled (commitment left behind).
    current = q.get_order_status_for_update(db, po_id)
    if current in q.FROZEN_STATUSES:
        blocked = sorted(k for k in fields if k != "status")
        if blocked:
            raise HTTPException(
                409,
                {"code": "ORDER_LOCKED", "status": current, "blocked_fields": blocked},
            )
    elif "status" in fields:
        raise HTTPException(
            409,
            {
                "code": "STATUS_NOT_PATCHABLE",
                "status": current,
                "message": "Status changes through submit, approve / reject, deliver or cancel",
            },
        )

    q.update_order_fields(db, po_id, fields)
    entry = f"Updated fields: {', '.join(fields.keys())}"
    if "status" in fields:
        entry += f" (status {current} → {fields['status']})"
    q.append_changelog(db, po_id, entry)
    db.commit()
    return {"updated": True, "fields": list(fields.keys())}


@router.patch("/orders/{po_id}/submit")
def submit_for_approval(
    po_id: int,
    approver_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    if not q.po_in_workspace(db, po_id=po_id, workspace_id=user.workspace_id):
        raise HTTPException(404, "Purchase order not found")
    if not q.user_in_workspace(db, user_id=approver_id, workspace_id=user.workspace_id):
        raise HTTPException(422, "approver not found in this workspace")
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
    if not q.po_in_workspace(db, po_id=po_id, workspace_id=user.workspace_id):
        raise HTTPException(404, "Purchase order not found")
    po = q.mark_delivered(db, po_id, arrived_date)
    if po is None:
        # Only an Approved order can be delivered; before this check the expenditure
        # and changelog were written for any status (and again on a second call).
        raise HTTPException(
            409,
            {"code": "BAD_STATUS", "message": "Only an Approved order can be marked Delivered"},
        )
    entry = "Marked Delivered — arrived on site"
    if po["cost_center_id"] is None:
        # `0031` made cost_center_id nullable (Q563): an order with no cost centre belongs
        # to no cost-centre budget, so there is nothing to post an expenditure against.
        entry += " (no cost centre — no expenditure posted)"
    else:
        q.commit_budget(
            db,
            po_id,
            int(po["cost_center_id"]),
            float(po["grand_total"] or 0),
            "Expenditure",
        )
        # The expenditure replaces the commitment; without this release the view counted
        # the same order twice.
        q.release_commitment(db, po_id, int(po["cost_center_id"]))
    q.append_changelog(db, po_id, entry)
    db.commit()
    return {"status": "Delivered"}


@router.delete("/orders/{po_id}")
def cancel_order(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    if not q.po_in_workspace(db, po_id=po_id, workspace_id=user.workspace_id):
        raise HTTPException(404, "Purchase order not found")
    if not q.cancel_order(db, po_id):
        # Only a Draft, Rejected or Hold order can be cancelled. This used to answer 200
        # "Cancelled" and log it for any status, with the order unchanged.
        raise HTTPException(
            409,
            {
                "code": "BAD_STATUS",
                "message": "Only a Draft, Rejected or Hold order can be cancelled",
            },
        )
    q.append_changelog(db, po_id, "Cancelled")
    db.commit()
    return {"status": "Cancelled"}


@router.post("/orders/{po_id}/duplicate", status_code=201)
def duplicate_order(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    if not q.po_in_workspace(db, po_id=po_id, workspace_id=user.workspace_id):
        raise HTTPException(404, "Purchase order not found")
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
    return q.filter_rto(db, workspace_id=user.workspace_id)


@router.get("/orders/filter/tbo")
def filter_tbo(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.filter_tbo(db, workspace_id=user.workspace_id)


@router.get("/orders/filter/due")
def filter_due(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.filter_due(db, workspace_id=user.workspace_id)


@router.get("/orders/filter/overdue")
def filter_overdue(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.filter_overdue(db, workspace_id=user.workspace_id)


@router.get("/orders/filter/arrived")
def filter_arrived(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.filter_arrived(db, workspace_id=user.workspace_id)


@router.get("/orders/filter/my-orders")
def filter_my_orders(
    requester_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.filter_my_orders(db, requester_id, workspace_id=user.workspace_id)


@router.get("/orders/filter/clear")
def filter_clear(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.filter_clear(db, workspace_id=user.workspace_id)


# ═══════════════════════════════════════════════════════════════════════════════
# Attachments
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/orders/{po_id}/attachments")
def list_attachments(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    if not q.po_in_workspace(db, po_id=po_id, workspace_id=user.workspace_id):
        raise HTTPException(404, "Purchase order not found")
    return q.list_attachments(db, po_id, workspace_id=user.workspace_id)


def _assert_order_not_frozen(db: Session, po_id: int) -> None:
    """Attachments are part of the order: a Cancelled / Delivered one is read-only (the
    rule the v1 orders module applies to its lines), and this route took none of it."""
    status = q.get_order_status_for_update(db, po_id)
    if status in q.FROZEN_STATUSES:
        raise HTTPException(409, {"code": "ORDER_LOCKED", "status": status})


@router.post("/orders/{po_id}/attachments", status_code=201)
async def upload_attachment(
    po_id: int,
    file: UploadFile = File(...),
    attachment_type: AttachmentType = Form(AttachmentType.file),
    uploaded_by: Optional[int] = Form(None),
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    if not q.po_in_workspace(db, po_id=po_id, workspace_id=user.workspace_id):
        raise HTTPException(404, "Purchase order not found")
    # `uploaded_by` is joined to `app_user.full_name` when the attachments are listed, so an
    # unvalidated id leaked another workspace's user name; a nonexistent one was a raw 500
    # after the file had already been written.
    if uploaded_by is not None and not q.user_in_workspace(
        db, user_id=uploaded_by, workspace_id=user.workspace_id
    ):
        raise HTTPException(422, "uploader not found in this workspace")
    _assert_order_not_frozen(db, po_id)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target_dir = UPLOAD_DIR / str(po_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "attachment").name
    # A unique name on disk: two uploads called `quote.pdf` used to share one path, the
    # second silently replacing the first's content, and deleting one removed both.
    target = target_dir / f"{uuid.uuid4().hex}_{safe_name}"

    try:
        size = 0
        with target.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTE_SIZE:
                    raise HTTPException(413, f"file size exceeds {MAX_BYTE_SIZE} bytes")
                out.write(chunk)
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
    except Exception:
        # Whatever failed (too large, a constraint), do not leave the file behind.
        target.unlink(missing_ok=True)
        raise
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
    if not q.po_in_workspace(db, po_id=po_id, workspace_id=user.workspace_id):
        raise HTTPException(404, "Attachment not found")
    row = q.get_attachment(db, po_id, attachment_id)
    if not row:
        raise HTTPException(404, "Attachment not found")
    _assert_order_not_frozen(db, po_id)
    try:
        # Uploads made before each got its own file name can share one path with another
        # row; the file stays while any other row still points at it.
        if (
            row["file_path"]
            and Path(row["file_path"]).exists()
            and not q.attachment_file_is_shared(db, row["file_path"], attachment_id)
        ):
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
    return q.list_pending_approvals(db, approver_id, workspace_id=user.workspace_id)


@router.post("/approvals/{workflow_id}/decide")
def decide_approval(
    workflow_id: int,
    action: ApprovalDecision,
    user: AuthUser = Depends(require_permission("orderbook", "approve")),
    db: Session = Depends(get_db),
):
    wf = q.get_workflow(db, workflow_id)
    if not wf or not q.po_in_workspace(db, po_id=wf["po_id"], workspace_id=user.workspace_id):
        raise HTTPException(404, "Workflow not found")
    if wf["status"] != "Pending":
        raise HTTPException(400, "This approval has already been acted on")

    new_status = "Approved" if action.decision == "approve" else "Rejected"
    # Only a Pending order can be decided. This used to move the order whatever its
    # status, so approving a Cancelled or Delivered order made it Approved again (and
    # posted a commitment for it). Checked first so a refusal writes nothing.
    if not q.update_po_status(db, wf["po_id"], new_status, from_status="Pending"):
        raise HTTPException(
            409,
            {
                "code": "BAD_STATUS",
                "message": "Only a Pending order can be approved or rejected",
            },
        )
    q.update_workflow_decision(db, workflow_id, new_status, action.comments)

    entry = f"{new_status} by approver #{action.approver_id}"
    if new_status == "Approved":
        po = q.get_po_budget_fields(db, wf["po_id"])
        if po and po["cost_center_id"] is None:
            # `0031` made cost_center_id nullable (Q563): an order with no cost centre
            # belongs to no cost-centre budget, so there is nothing to commit against.
            entry += " (no cost centre — no commitment posted)"
        elif po:
            q.commit_budget(
                db,
                wf["po_id"],
                int(po["cost_center_id"]),
                float(po["grand_total"] or 0),
                "Commitment",
            )

    q.append_changelog(db, wf["po_id"], entry, action.approver_id)
    db.commit()
    return {"workflow_id": workflow_id, "decision": new_status}


@router.get("/approvals/history")
def approval_history(
    approver_id: Optional[int] = None,
    limit: int = Query(50, ge=0, le=200),
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.approval_history(db, workspace_id=user.workspace_id, approver_id=approver_id, limit=limit)


# ═══════════════════════════════════════════════════════════════════════════════
# Vendors — RETIRED (Q565).  Inventory — RETIRED (Q544).
#
# The four `/vendors*` endpoints are gone: `/suppliers` (B5) is now the single
# surface over `vendors`, workspace-scoped as the rest of the product is. The
# legacy pair were never scoped — `workspace` appeared zero times in this
# module — and `0029`'s `workspace_id NOT NULL` had already broken the POST.
# Same shape as #7a retiring `/catalogs/*` in favour of `/catalog/*`.
#
# The three `/inventory*` endpoints are gone because `0029` **dropped** the
# tables under them: `inventory`, `inventory_movements` and the
# `v_inventory_status` view (Q544, which kept `board_inventory` instead).
# They had been returning 500 ever since. Sheet stock lives at
# `/board-inventory` (0025).
#
# Everything else in this namespace now has workspace isolation (see the
# module docstring).
# ═══════════════════════════════════════════════════════════════════════════════




# ═══════════════════════════════════════════════════════════════════════════════
# Budget
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/budget")
def get_budget(
    fiscal_year: Optional[int] = None,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.list_budget(db, workspace_id=user.workspace_id, fiscal_year=fiscal_year)


@router.get("/budget/summary")
def get_budget_summary(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.budget_summary(db, workspace_id=user.workspace_id)


@router.get("/budget/{cost_center_id}/transactions")
def cost_center_transactions(
    cost_center_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return q.cost_center_transactions(db, cost_center_id, workspace_id=user.workspace_id)


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
