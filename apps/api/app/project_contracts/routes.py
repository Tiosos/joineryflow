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
from .schemas import ActualCostsOut, ContractOut, CreateVariationIn

router = APIRouter(tags=["project_contracts"])


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
        actor_id=user.id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="contract not found")
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
