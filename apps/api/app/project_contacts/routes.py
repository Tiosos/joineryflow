"""HTTP routes for project_contact CRUD."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..projects.schemas import ProjectContactOut
from . import queries as q
from .schemas import CreateContactIn, PatchContactIn

router = APIRouter(tags=["project_contacts"])


@router.get("/projects/{pid}/contacts", response_model=list[ProjectContactOut])
def list_contacts_route(
    pid: int,
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    rows = q.list_contacts(db, project_id=pid, workspace_id=user.workspace_id)
    if rows is None:
        raise HTTPException(status_code=404, detail="project not found")
    return rows


@router.post("/projects/{pid}/contacts", response_model=ProjectContactOut, status_code=201)
def create_contact_route(
    pid: int,
    body: CreateContactIn,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    row = q.create_contact(
        db, project_id=pid, workspace_id=user.workspace_id,
        payload=body, actor_id=user.id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    db.commit()
    return row


@router.patch("/contacts/{cid}", response_model=ProjectContactOut)
def patch_contact_route(
    cid: int,
    body: PatchContactIn,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    row = q.patch_contact(
        db, contact_id=cid, workspace_id=user.workspace_id,
        payload=body, actor_id=user.id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="contact not found")
    db.commit()
    return row


@router.delete("/contacts/{cid}", status_code=204)
def delete_contact_route(
    cid: int,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    ok = q.delete_contact(
        db, contact_id=cid, workspace_id=user.workspace_id, actor_id=user.id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="contact not found")
    db.commit()
    return Response(status_code=204)
