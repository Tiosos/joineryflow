from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import current_user, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("")
def get_workspace(
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.execute(
        text("SELECT id, slug, name FROM workspace WHERE id = :i"),
        {"i": user.workspace_id},
    ).mappings().first()
    if not row:
        raise HTTPException(404)
    return dict(row)


class PlanningOut(BaseModel):
    at_risk_days: int


class PatchPlanningIn(BaseModel):
    at_risk_days: int = Field(ge=0, le=90)


@router.get("/planning", response_model=PlanningOut)
def get_planning(user: AuthUser = Depends(current_user), db: Session = Depends(get_db)):
    """The workspace's At risk window, in days (Q591; `items/card_filters.py`)."""
    return {"at_risk_days": db.execute(text("SELECT at_risk_days FROM workspace WHERE id = :w"),
                                       {"w": user.workspace_id}).scalar_one()}


@router.patch("/planning", response_model=PlanningOut)
def patch_planning(
    body: PatchPlanningIn,
    user: AuthUser = Depends(require_permission("it_management", "write")),
    db: Session = Depends(get_db),
):
    old = db.execute(text("SELECT at_risk_days FROM workspace WHERE id = :w FOR UPDATE"),
                     {"w": user.workspace_id}).scalar_one()
    db.execute(text("UPDATE workspace SET at_risk_days = :d WHERE id = :w"),
               {"d": body.at_risk_days, "w": user.workspace_id})
    write_audit(db, workspace_id=user.workspace_id, actor_id=user.id, event="workspace.planning",
                payload={"at_risk_days": {"old": old, "new": body.at_risk_days}})
    db.commit()
    return {"at_risk_days": body.at_risk_days}
