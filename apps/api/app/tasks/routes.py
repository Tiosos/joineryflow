"""HTTP routes for tasks (Plan V1 §10, Q524). Rules: `tasks/queries.py`."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth.rbac import current_user
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import CreateTaskIn, PatchTaskIn, TaskListOut, TaskOut, TaskStatusIn

router = APIRouter(tags=["tasks"])


def _require_targets(db: Session, user: AuthUser, *, project_id=None, item_id=None, cutlist_id=None):
    """A filter that names a record which does not exist for this caller (missing, deleted,
    another workspace's) answers 404, as an item's own routes do."""
    for kind, tid in (("project", project_id), ("item", item_id), ("cutlist", cutlist_id)):
        if tid is not None and not q.target_exists(
            db, workspace_id=user.workspace_id, target_type=kind, target_id=tid
        ):
            raise HTTPException(404, "not found")


def _fail(code: str, payload: object = None) -> HTTPException:
    if code == "NOT_FOUND":
        return HTTPException(404, "not found")
    if code == "ASSIGNEE_NOT_FOUND":
        return HTTPException(404, {"code": code})
    if code == "FORBIDDEN":
        return HTTPException(403, "forbidden")
    if code == "FIELD_CONFLICT":
        return HTTPException(409, {"code": code, "conflicts": payload})
    return HTTPException(409, {"code": code})  # TASK_CLOSED, ASSIGNEE_CANNOT_READ_TARGET


# Literal paths before parameterised ones (CLAUDE.md §8): `/tasks` has no literal sibling
# yet, but keep the order if one is added.
@router.get("/tasks", response_model=TaskListOut)
def list_tasks_route(
    assignee: str | None = Query(None, description="`me` or a user id"),
    status: Literal["open", "in_progress", "done", "cancelled", "active"] | None = Query(
        None, description="`active` = open + in_progress"),
    project_id: int | None = None,
    item_id: int | None = None,
    cutlist_id: int | None = None,
    due_before: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    if assignee is None:
        assignee_id = None
    elif assignee == "me":
        assignee_id = user.id
    elif assignee.isdigit():
        assignee_id = int(assignee)
    else:
        raise HTTPException(422, "assignee must be 'me' or a user id")
    _require_targets(db, user, project_id=project_id, item_id=item_id, cutlist_id=cutlist_id)
    return q.list_tasks(
        db, actor=user, assignee_id=assignee_id, status=status, project_id=project_id,
        item_id=item_id, cutlist_id=cutlist_id, due_before=due_before,
        limit=limit, offset=offset,
    )


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task_route(
    payload: CreateTaskIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    code, row = q.create_task(db, actor=user, payload=payload)
    if code != "OK":
        db.rollback()
        raise _fail(code)
    db.commit()
    return row


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task_route(
    task_id: int,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = q.get_task(db, actor=user, task_id=task_id)
    if row is None:
        raise HTTPException(404, "not found")
    return row


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def patch_task_route(
    task_id: int,
    payload: PatchTaskIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    code, value = q.patch_task(db, actor=user, task_id=task_id, payload=payload)
    if code != "OK":
        db.rollback()
        raise _fail(code, value)
    db.commit()
    return value


@router.post("/tasks/{task_id}/status", response_model=TaskOut)
def set_status_route(
    task_id: int,
    payload: TaskStatusIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    code, row = q.set_status(db, actor=user, task_id=task_id, status=payload.status)
    if code != "OK":
        db.rollback()
        raise _fail(code)
    db.commit()
    return row


@router.get("/items/{item_id}/tasks", response_model=TaskListOut)
def item_tasks_route(
    item_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_targets(db, user, item_id=item_id)
    return q.list_tasks(
        db, actor=user, assignee_id=None, status=None, project_id=None, item_id=item_id,
        cutlist_id=None, due_before=None, limit=limit, offset=offset,
    )
