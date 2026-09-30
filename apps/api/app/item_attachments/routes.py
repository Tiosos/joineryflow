"""Item attachments routes — GET bundle + POST/DELETE per slot."""
from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy.orm import Session

from ..auth.rbac import require_drafter, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..items.queries import ItemContentLocked
from . import queries as q
from .schemas import AttachmentsBundleOut, BindAttachmentIn

router = APIRouter(tags=["item_attachments"])

KindPath = Path(..., pattern="^(cv_drawing|sketchup|cabvision|floor_plan|site_measure)$")


@router.get("/items/{iid}/attachments", response_model=AttachmentsBundleOut)
def get_attachments_route(
    iid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    bundle = q.get_bundle(db, item_id=iid, workspace_id=user.workspace_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="item not found")
    return bundle


@router.post(
    "/items/{iid}/attachments/{kind}",
    status_code=201,
    dependencies=[Depends(require_drafter())],
)
def bind_attachment_route(
    iid: int,
    kind: str = KindPath,
    body: BindAttachmentIn = ...,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    try:
        result = q.bind_attachment(
            db, item_id=iid, kind=kind, file_blob_id=body.file_blob_id,
            workspace_id=user.workspace_id, actor=user,
        )
    except ItemContentLocked as exc:
        raise HTTPException(status_code=409, detail=exc.detail)
    except ValueError as exc:
        msg = str(exc)
        if "attachments must be" in msg:
            raise HTTPException(status_code=415, detail=msg)
        if "workspace" in msg or "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    db.commit()
    return result


@router.delete(
    "/items/{iid}/attachments/{kind}",
    status_code=204,
    dependencies=[Depends(require_drafter())],
)
def clear_attachment_route(
    iid: int,
    kind: str = KindPath,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    try:
        cleared = q.clear_attachment(db, item_id=iid, kind=kind,
                                     workspace_id=user.workspace_id, actor=user)
    except ItemContentLocked as exc:
        raise HTTPException(status_code=409, detail=exc.detail)
    if not cleared:
        raise HTTPException(status_code=404, detail="no attachment in this slot")
    db.commit()
    return Response(status_code=204)
