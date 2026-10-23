"""HTTP routes for project_contract + variations (Q491).

Gated `tracking:{read,write}`, matching `project_contacts`/
`project_lift_access` — Contract Value lives on the project page alongside
them. `original_value` is set once by `estimating.convert_to_project` at
handover; there is no create/patch route for it here, only for variations.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .actual_costs import actual_costs_for_project
from .schemas import ActualCostsOut, ContractOut, CreateVariationIn, DecideVariationIn, PatchVariationIn, VoidVariationIn

router = APIRouter(tags=["project_contracts"])


def _is_manager(user: AuthUser) -> bool:
    return user.auth_role in ("manager", "admin")


@router.get("/projects/{pid}/contract", response_model=ContractOut)
def get_contract_route(
    pid: int,
    user: AuthUser = Depends(require_permission("tracking", "read", project_param="pid")),
    db: Session = Depends(get_db),
):
    row = q.get_contract(db, project_id=pid, workspace_id=user.workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="contract not found")
    return row


@router.post("/projects/{pid}/contract/variations", response_model=ContractOut, status_code=201)
def create_variation_route(
    pid: int,
    body: CreateVariationIn,
    user: AuthUser = Depends(require_permission("tracking", "write", project_param="pid")),
    db: Session = Depends(get_db),
):
    row = q.create_variation(
        db, project_id=pid, workspace_id=user.workspace_id,
        description=body.description, amount_delta=body.amount_delta,
        actor_id=user.id, auto_approve=_is_manager(user), item_ids=body.item_ids,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="contract not found")
    db.commit()
    return row


@router.patch("/projects/{pid}/contract/variations/{vid}", response_model=ContractOut)
def patch_variation_route(
    pid: int,
    vid: int,
    body: PatchVariationIn,
    user: AuthUser = Depends(require_permission("tracking", "write", project_param="pid")),
    db: Session = Depends(get_db),
):
    row = q.patch_variation(
        db, project_id=pid, variation_id=vid, workspace_id=user.workspace_id,
        actor_id=user.id, actor_is_manager=_is_manager(user),
        changes=body.model_dump(exclude_unset=True),
    )
    db.commit()
    return row


@router.post("/projects/{pid}/contract/variations/{vid}/decision", response_model=ContractOut)
def decide_variation_route(
    pid: int,
    vid: int,
    body: DecideVariationIn,
    user: AuthUser = Depends(require_permission("tracking", "write", project_param="pid")),
    db: Session = Depends(get_db),
):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail={"code": "DECISION_FORBIDDEN"})
    row = q.decide_variation(
        db, project_id=pid, variation_id=vid, workspace_id=user.workspace_id,
        actor_id=user.id, decision=body.decision, note=body.note,
    )
    db.commit()
    return row


@router.post("/projects/{pid}/contract/variations/{vid}/void", response_model=ContractOut)
def void_variation_route(
    pid: int,
    vid: int,
    body: VoidVariationIn,
    user: AuthUser = Depends(require_permission("tracking", "write", project_param="pid")),
    db: Session = Depends(get_db),
):
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail={"code": "DECISION_FORBIDDEN"})
    row = q.void_variation(
        db, project_id=pid, variation_id=vid, workspace_id=user.workspace_id,
        actor_id=user.id, reason=body.reason,
    )
    db.commit()
    return row


@router.get("/projects/{pid}/actual-costs", response_model=ActualCostsOut)
def get_actual_costs_route(
    pid: int,
    user: AuthUser = Depends(require_permission("tracking", "read", project_param="pid")),
    db: Session = Depends(get_db),
):
    row = actual_costs_for_project(db, project_id=pid, workspace_id=user.workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    return row
