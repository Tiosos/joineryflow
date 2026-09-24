"""HTTP routes for item_query CRUD."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import AnswerQueryIn, CreateQueryIn, ItemQueryOut

router = APIRouter(tags=["item_queries"])


@router.get("/items/{iid}/queries", response_model=list[ItemQueryOut])
def list_queries_route(
    iid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    rows = q.list_queries(db, item_id=iid, workspace_id=user.workspace_id)
    if rows is None:
        raise HTTPException(status_code=404, detail="item not found")
    return rows


@router.post("/items/{iid}/queries", response_model=ItemQueryOut, status_code=201)
def create_query_route(
    iid: int,
    body: CreateQueryIn,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    """Asking a question only needs read on `list`.  Drafter+ answers."""
    row = q.create_query(
        db, item_id=iid, workspace_id=user.workspace_id,
        question=body.question, actor_id=user.id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="item not found")
    db.commit()
    return row


@router.post("/queries/{qid}/answer", response_model=ItemQueryOut)
def answer_query_route(
    qid: int,
    body: AnswerQueryIn,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    result = q.answer_query(
        db, query_id=qid, workspace_id=user.workspace_id,
        answer=body.answer, actor_id=user.id,
    )
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="query not found")
    if result == "ALREADY_ANSWERED":
        raise HTTPException(
            status_code=409,
            detail="query already answered; PATCH /queries/{qid}/answer to edit",
        )
    db.commit()
    return result


@router.patch("/queries/{qid}/answer", response_model=ItemQueryOut)
def edit_answer_route(
    qid: int,
    body: AnswerQueryIn,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    result = q.answer_query(
        db, query_id=qid, workspace_id=user.workspace_id,
        answer=body.answer, actor_id=user.id, allow_overwrite=True,
    )
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="query not found")
    db.commit()
    return result
