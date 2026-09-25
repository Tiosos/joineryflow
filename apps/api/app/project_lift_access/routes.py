"""HTTP routes for project_lift_access (PUT/GET/DELETE — 1 row per project)."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..projects.schemas import ProjectLiftAccessOut
from . import queries as q
from .schemas import UpsertLiftAccessIn

router = APIRouter(tags=["project_lift_access"])


@router.get("/projects/{pid}/lift-access", response_model=ProjectLiftAccessOut)
def get_lift_access_route(
    pid: int,
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    row = q.get_lift_access(db, project_id=pid, workspace_id=user.workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    return row


@router.put("/projects/{pid}/lift-access", response_model=ProjectLiftAccessOut)
def upsert_lift_access_route(
    pid: int,
    body: UpsertLiftAccessIn,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    result = q.upsert_lift_access(
        db, project_id=pid, workspace_id=user.workspace_id,
        payload=body, actor_id=user.id,
    )
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="project not found")
    if result == "CROSS_WORKSPACE_BLOB":
        raise HTTPException(
            status_code=422,
            detail="sketch_file_blob_id must be in the caller's workspace",
        )
    if result == "UNSUPPORTED_BLOB":
        raise HTTPException(status_code=415, detail="sketch must be a PDF, PNG or JPEG")
    db.commit()
    return result


@router.delete("/projects/{pid}/lift-access", status_code=204)
def delete_lift_access_route(
    pid: int,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    if not q.delete_lift_access(
        db, project_id=pid, workspace_id=user.workspace_id, actor_id=user.id,
    ):
        raise HTTPException(status_code=404, detail="project or row not found")
    db.commit()
    return Response(status_code=204)
