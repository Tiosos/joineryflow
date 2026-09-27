"""QC module routes: defects, checklist, rework (Q515-517)."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    ChecklistItemOut,
    CloseReworkIn,
    CreateChecklistItemIn,
    CreateDefectIn,
    CreateReworkIn,
    DefectOut,
    PatchChecklistItemIn,
    PatchDefectIn,
    PatchReworkIn,
    ResolveDefectIn,
    ReworkOut,
)

router = APIRouter(tags=["qc"])


def _conflict(exc: q.Conflict) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": str(exc)})


# ============================================================================
# Defects
# ============================================================================

@router.get("/items/{iid}/qc/defects", response_model=list[DefectOut])
def list_defects_route(
    iid: int,
    user: AuthUser = Depends(require_permission("qc", "read")),
    db: Session = Depends(get_db),
):
    try:
        return q.list_defects(db, item_id=iid, workspace_id=user.workspace_id)
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/items/{iid}/qc/defects", response_model=DefectOut, status_code=201)
def create_defect_route(
    iid: int,
    body: CreateDefectIn,
    user: AuthUser = Depends(require_permission("qc", "write")),
    db: Session = Depends(get_db),
):
    try:
        row = q.create_defect(
            db, item_id=iid, workspace_id=user.workspace_id, actor_id=user.id,
            stage_key=body.stage_key, description=body.description,
        )
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    db.commit()
    return row


@router.patch("/qc/defects/{did}", response_model=DefectOut)
def patch_defect_route(
    did: int,
    body: PatchDefectIn,
    user: AuthUser = Depends(require_permission("qc", "write")),
    db: Session = Depends(get_db),
):
    changes = body.model_dump(include=body.model_fields_set)
    try:
        row = q.patch_defect(db, defect_id=did, workspace_id=user.workspace_id,
                              actor_id=user.id, changes=changes)
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except q.Conflict as exc:
        raise _conflict(exc)
    db.commit()
    return row


@router.post("/qc/defects/{did}/resolve", response_model=DefectOut)
def resolve_defect_route(
    did: int,
    body: ResolveDefectIn,
    user: AuthUser = Depends(require_permission("qc", "approve")),
    db: Session = Depends(get_db),
):
    try:
        row = q.resolve_defect(db, defect_id=did, workspace_id=user.workspace_id,
                                actor_id=user.id, resolved_note=body.resolved_note)
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except q.Conflict as exc:
        raise _conflict(exc)
    db.commit()
    return row


# ============================================================================
# Checklist
# ============================================================================

@router.get("/items/{iid}/qc/checklist", response_model=list[ChecklistItemOut])
def list_checklist_route(
    iid: int,
    user: AuthUser = Depends(require_permission("qc", "read")),
    db: Session = Depends(get_db),
):
    try:
        return q.list_checklist(db, item_id=iid, workspace_id=user.workspace_id)
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/items/{iid}/qc/checklist", response_model=ChecklistItemOut, status_code=201)
def create_checklist_item_route(
    iid: int,
    body: CreateChecklistItemIn,
    user: AuthUser = Depends(require_permission("qc", "write")),
    db: Session = Depends(get_db),
):
    try:
        row = q.create_checklist_item(
            db, item_id=iid, workspace_id=user.workspace_id, actor_id=user.id,
            label=body.label, sort_order=body.sort_order,
        )
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    db.commit()
    return row


@router.patch("/qc/checklist/{cid}", response_model=ChecklistItemOut)
def patch_checklist_item_route(
    cid: int,
    body: PatchChecklistItemIn,
    user: AuthUser = Depends(require_permission("qc", "write")),
    db: Session = Depends(get_db),
):
    changes = body.model_dump(include=body.model_fields_set)
    try:
        row = q.patch_checklist_item(db, checklist_item_id=cid, workspace_id=user.workspace_id,
                                      actor_id=user.id, changes=changes)
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    db.commit()
    return row


@router.delete("/qc/checklist/{cid}", status_code=204)
def delete_checklist_item_route(
    cid: int,
    user: AuthUser = Depends(require_permission("qc", "write")),
    db: Session = Depends(get_db),
):
    try:
        q.delete_checklist_item(db, checklist_item_id=cid, workspace_id=user.workspace_id,
                                 actor_id=user.id)
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    db.commit()
    return Response(status_code=204)


# ============================================================================
# Rework
# ============================================================================

@router.get("/items/{iid}/qc/rework", response_model=list[ReworkOut])
def list_rework_route(
    iid: int,
    user: AuthUser = Depends(require_permission("qc", "read")),
    db: Session = Depends(get_db),
):
    try:
        return q.list_rework(db, item_id=iid, workspace_id=user.workspace_id)
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/items/{iid}/qc/rework", response_model=ReworkOut, status_code=201)
def create_rework_route(
    iid: int,
    body: CreateReworkIn,
    user: AuthUser = Depends(require_permission("qc", "write")),
    db: Session = Depends(get_db),
):
    try:
        row = q.create_rework(
            db, item_id=iid, workspace_id=user.workspace_id, actor_id=user.id,
            kind=body.kind, cause=body.cause, scope=body.scope,
            responsibility=body.responsibility, cost=body.cost,
        )
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    db.commit()
    return row


@router.patch("/qc/rework/{rid}", response_model=ReworkOut)
def patch_rework_route(
    rid: int,
    body: PatchReworkIn,
    user: AuthUser = Depends(require_permission("qc", "write")),
    db: Session = Depends(get_db),
):
    changes = body.model_dump(include=body.model_fields_set)
    try:
        row = q.patch_rework(db, rework_id=rid, workspace_id=user.workspace_id,
                              actor_id=user.id, changes=changes)
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except q.Conflict as exc:
        raise _conflict(exc)
    db.commit()
    return row


@router.post("/qc/rework/{rid}/close", response_model=ReworkOut)
def close_rework_route(
    rid: int,
    body: CloseReworkIn,
    user: AuthUser = Depends(require_permission("qc", "approve")),
    db: Session = Depends(get_db),
):
    try:
        row = q.close_rework(db, rework_id=rid, workspace_id=user.workspace_id,
                              actor_id=user.id, closed_note=body.closed_note)
    except q.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except q.Conflict as exc:
        raise _conflict(exc)
    db.commit()
    return row
