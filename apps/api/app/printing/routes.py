"""Print routes — cutlist.pdf / hardware.pdf / combined.pdf.

All return inline-disposition PDFs with Cache-Control: no-store.
Audit row written per render.
"""
from io import BytesIO

import pypdf
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..files.store import FileStore, get_default_store
from .context import build_context
from .engine import merge_pdfs, render_template_to_pdf


def _is_parseable_pdf(data: bytes) -> bool:
    """Return True if pypdf can read the bytes as a PDF.

    Attachments come from user uploads validated only by magic bytes; a
    technically-PDF-looking but structurally-broken file would otherwise
    crash the combined-PDF merge step.
    """
    try:
        pypdf.PdfReader(BytesIO(data), strict=False)
        return True
    except Exception:  # pypdf raises various PdfReadError subtypes
        return False

router = APIRouter(tags=["printing"])


def _get_store() -> FileStore:
    return get_default_store()


def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
            "Content-Length": str(len(content)),
        },
    )


@router.get("/items/{iid}/cutlist.pdf")
def print_cutlist(
    iid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    ctx = build_context(iid, db, workspace_id=user.workspace_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="item not found")
    pdf = render_template_to_pdf("cutlist.html", ctx)
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="item.print.cutlist", target=str(iid),
        payload={"byte_size": len(pdf), "part_count": len(ctx["parts"])},
    )
    db.commit()
    return _pdf_response(pdf, f"cutlist-{iid}.pdf")


@router.get("/items/{iid}/hardware.pdf")
def print_hardware(
    iid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    ctx = build_context(iid, db, workspace_id=user.workspace_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="item not found")
    pdf = render_template_to_pdf("hardware.html", ctx)
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="item.print.hardware", target=str(iid),
        payload={
            "byte_size": len(pdf),
            "hardware_line_count": sum(len(g["lines"]) for g in ctx["hardware"]),
            "supplier_count": len(ctx["hardware"]),
        },
    )
    db.commit()
    return _pdf_response(pdf, f"hardware-{iid}.pdf")


@router.get("/items/{iid}/combined.pdf")
def print_combined(
    iid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
    store: FileStore = Depends(_get_store),
):
    ctx = build_context(iid, db, workspace_id=user.workspace_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="item not found")

    parts: list[bytes] = []
    parts.append(render_template_to_pdf("cover_combined.html", ctx))
    parts.append(render_template_to_pdf("cutlist.html", ctx))
    parts.append(render_template_to_pdf("hardware.html", ctx))

    for kind in ("cv_drawing", "floor_plan", "site_measure"):
        slot = ctx["attachments"].get(kind)
        attachment_bytes: bytes | None = None
        if slot:
            with store.get(slot["storage_key"]) as fh:
                attachment_bytes = fh.read()
        if attachment_bytes and _is_parseable_pdf(attachment_bytes):
            parts.append(attachment_bytes)
        else:
            parts.append(render_template_to_pdf(
                "missing_attachment.html",
                {**ctx, "kind": kind},
            ))

    if ctx["has_painting"]:
        parts.append(render_template_to_pdf("painting.html", ctx))

    pdf = merge_pdfs(parts)
    attachments_present = {k: bool(ctx["attachments"].get(k)) for k in ("cv_drawing", "floor_plan", "site_measure")}
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="item.print.combined", target=str(iid),
        payload={
            "byte_size": len(pdf),
            "attachments_present": attachments_present,
            "has_painting": ctx["has_painting"],
        },
    )
    db.commit()
    return _pdf_response(pdf, f"combined-{iid}.pdf")
