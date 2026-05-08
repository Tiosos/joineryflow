"""Sample routes — CRUD + workflow + photo bind/clear + ledger.

10 endpoints. RBAC via require_permission("isample", action). Workspace isolation
through projects.workspace_id direct join (post-hardening).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    ApproveIn,
    BindPhotoIn,
    CreateSampleIn,
    LedgerOut,
    PatchSampleIn,
    RejectIn,
    SampleListOut,
    SampleOut,
)

router = APIRouter(tags=["samples"])

MANAGER_ROLES = ("manager", "admin")


@router.get("/projects/{pid}/samples", response_model=SampleListOut)
def list_samples_route(
    pid: int,
    subtab: str = Query("board", pattern="^(board|archive)$"),
    q_search: str | None = Query(None, alias="q"),
    status: str | None = None,
    supplier: str | None = None,
    user: AuthUser = Depends(require_permission("isample", "read")),
    db: Session = Depends(get_db),
):
    result = q.list_samples(
        db, project_id=pid, workspace_id=user.workspace_id,
        subtab=subtab, q=q_search, status_filter=status, supplier=supplier,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="project not found")
    return result


@router.get("/projects/{pid}/samples/ledger", response_model=LedgerOut)
def list_ledger_route(
    pid: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthUser = Depends(require_permission("isample", "read")),
    db: Session = Depends(get_db),
):
    result = q.list_ledger(db, project_id=pid, workspace_id=user.workspace_id, limit=limit, offset=offset)
    if result is None:
        raise HTTPException(status_code=404, detail="project not found")
    return result


@router.get("/samples/{sid}", response_model=SampleOut)
def get_sample_route(
    sid: int,
    user: AuthUser = Depends(require_permission("isample", "read")),
    db: Session = Depends(get_db),
):
    row = q.get_sample(db, sample_id=sid, workspace_id=user.workspace_id)
    if not row:
        raise HTTPException(status_code=404, detail="sample not found")
    return row


@router.post("/projects/{pid}/samples", response_model=SampleOut, status_code=201)
def create_sample_route(
    pid: int,
    body: CreateSampleIn,
    user: AuthUser = Depends(require_permission("isample", "write")),
    db: Session = Depends(get_db),
):
    try:
        new_id = q.create_sample(
            db, project_id=pid, workspace_id=user.workspace_id, payload=body, actor_id=user.id,
        )
    except ValueError as exc:
        msg = str(exc)
        if "PNG or JPEG" in msg:
            raise HTTPException(status_code=415, detail=msg)
        if "not found" in msg or "workspace" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    db.commit()
    return q.get_sample(db, sample_id=new_id, workspace_id=user.workspace_id)


@router.patch("/samples/{sid}", response_model=SampleOut)
def patch_sample_route(
    sid: int,
    body: PatchSampleIn,
    user: AuthUser = Depends(require_permission("isample", "write")),
    db: Session = Depends(get_db),
):
    if not body.model_dump(exclude_unset=True):
        raise HTTPException(status_code=422, detail="empty patch")
    cur = q.get_sample(db, sample_id=sid, workspace_id=user.workspace_id)
    if not cur:
        raise HTTPException(status_code=404, detail="sample not found")
    if cur["created_by"] != user.id and user.auth_role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="only the creator or a manager can edit")
    row = q.patch_sample(db, sample_id=sid, workspace_id=user.workspace_id, payload=body, actor_id=user.id)
    db.commit()
    return row


def _check_not_creator(cur: dict, user: AuthUser) -> None:
    if cur["created_by"] == user.id:
        raise HTTPException(status_code=403, detail="reviewer cannot be the creator")


@router.post("/samples/{sid}/approve", response_model=SampleOut)
def approve_route(
    sid: int,
    body: ApproveIn,
    user: AuthUser = Depends(require_permission("isample", "approve")),
    db: Session = Depends(get_db),
):
    cur = q.get_sample(db, sample_id=sid, workspace_id=user.workspace_id)
    if not cur:
        raise HTTPException(status_code=404, detail="sample not found")
    _check_not_creator(cur, user)
    try:
        result = q.transition_status(
            db, sample_id=sid, workspace_id=user.workspace_id, action="approve",
            actor_id=user.id, review_note=body.review_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return result


@router.post("/samples/{sid}/reject", response_model=SampleOut)
def reject_route(
    sid: int,
    body: RejectIn,
    user: AuthUser = Depends(require_permission("isample", "approve")),
    db: Session = Depends(get_db),
):
    cur = q.get_sample(db, sample_id=sid, workspace_id=user.workspace_id)
    if not cur:
        raise HTTPException(status_code=404, detail="sample not found")
    _check_not_creator(cur, user)
    try:
        result = q.transition_status(
            db, sample_id=sid, workspace_id=user.workspace_id, action="reject",
            actor_id=user.id, review_note=body.review_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return result


@router.post("/samples/{sid}/archive", status_code=204)
def archive_route(
    sid: int,
    user: AuthUser = Depends(require_permission("isample", "write")),
    db: Session = Depends(get_db),
):
    cur = q.get_sample(db, sample_id=sid, workspace_id=user.workspace_id)
    if not cur:
        raise HTTPException(status_code=404, detail="sample not found")
    if cur["created_by"] != user.id and user.auth_role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="only creator or manager+ can archive")
    if not q.archive_sample(db, sample_id=sid, workspace_id=user.workspace_id, actor_id=user.id):
        raise HTTPException(status_code=409, detail="sample already archived")
    db.commit()
    return Response(status_code=204)


@router.post("/samples/{sid}/photo", status_code=204)
def bind_photo_route(
    sid: int,
    body: BindPhotoIn,
    user: AuthUser = Depends(require_permission("isample", "write")),
    db: Session = Depends(get_db),
):
    cur = q.get_sample(db, sample_id=sid, workspace_id=user.workspace_id)
    if not cur:
        raise HTTPException(status_code=404, detail="sample not found")
    if cur["created_by"] != user.id and user.auth_role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="only creator or manager+ can edit photo")
    try:
        ok = q.bind_photo(db, sample_id=sid, workspace_id=user.workspace_id,
                          file_blob_id=body.file_blob_id, actor_id=user.id)
    except ValueError as exc:
        msg = str(exc)
        if "PNG or JPEG" in msg:
            raise HTTPException(status_code=415, detail=msg)
        raise HTTPException(status_code=404, detail=msg)
    if not ok:
        raise HTTPException(status_code=404, detail="sample not found")
    db.commit()
    return Response(status_code=204)


@router.delete("/samples/{sid}/photo", status_code=204)
def clear_photo_route(
    sid: int,
    user: AuthUser = Depends(require_permission("isample", "write")),
    db: Session = Depends(get_db),
):
    cur = q.get_sample(db, sample_id=sid, workspace_id=user.workspace_id)
    if not cur:
        raise HTTPException(status_code=404, detail="sample not found")
    if cur["created_by"] != user.id and user.auth_role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="only creator or manager+ can edit photo")
    if not q.clear_photo(db, sample_id=sid, workspace_id=user.workspace_id, actor_id=user.id):
        raise HTTPException(status_code=404, detail="no photo to clear")
    db.commit()
    return Response(status_code=204)
