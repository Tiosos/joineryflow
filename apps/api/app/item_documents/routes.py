"""Item Document Register routes — list, bind, relabel/reorder, unbind."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import BindDocumentIn, ItemDocumentOut, PatchDocumentIn

router = APIRouter(tags=["item_documents"])


@router.get("/items/{iid}/documents", response_model=list[ItemDocumentOut])
def list_documents_route(
    iid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    try:
        return q.list_documents(db, item_id=iid, workspace_id=user.workspace_id)
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/items/{iid}/documents", response_model=ItemDocumentOut, status_code=201)
def bind_document_route(
    iid: int,
    body: BindDocumentIn,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    try:
        row = q.bind_document(
            db, item_id=iid, file_blob_id=body.file_blob_id, label=body.label,
            sort_order=body.sort_order, workspace_id=user.workspace_id,
            actor_id=user.id,
        )
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except q.UnsupportedMime as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    db.commit()
    return row


@router.patch("/documents/{did}", response_model=ItemDocumentOut)
def patch_document_route(
    did: int,
    body: PatchDocumentIn,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    changes = body.model_dump(include=body.model_fields_set)
    if changes.get("sort_order", 0) is None:
        raise HTTPException(status_code=422, detail="sort_order cannot be null")
    try:
        row = q.patch_document(db, document_id=did, changes=changes,
                               workspace_id=user.workspace_id, actor_id=user.id)
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    db.commit()
    return row


@router.delete("/documents/{did}", status_code=204)
def unbind_document_route(
    did: int,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    try:
        q.unbind_document(db, document_id=did, workspace_id=user.workspace_id,
                          actor_id=user.id)
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    db.commit()
    return Response(status_code=204)
