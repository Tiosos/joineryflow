"""HTTP routes for comments (Plan V1 §29, Q473).

Reading a thread needs `tracking:read`; posting, editing and deleting need
`tracking:comment` — the first place the `comment` action is actually enforced.
The author-only edit rule and the author-or-manager delete rule are in the
query layer (per-object rules stay out of the matrix, Q472 not being built).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    CommentOut,
    CommentThreadOut,
    CreateCommentIn,
    EditCommentIn,
    ObjectType,
)

router = APIRouter(tags=["comments"])


def _fail(code: str, payload: object = None) -> HTTPException:
    if code == "NOT_FOUND":
        return HTTPException(404, "not found")
    if code == "BAD_MENTION":
        return HTTPException(422, {"code": "BAD_MENTION", "user_ids": payload})
    if code in ("NOT_AUTHOR", "FORBIDDEN"):
        return HTTPException(403, {"code": code})
    return HTTPException(409, {"code": code})  # PARENT_DELETED, REPLY_TO_REPLY, ...


@router.get("/comments", response_model=CommentThreadOut)
def list_comments_route(
    object_type: ObjectType = Query(...),
    object_id: int = Query(...),
    user: AuthUser = Depends(require_permission(q.MODULE, "read")),
    db: Session = Depends(get_db),
):
    rows = q.list_comments(
        db, object_type=object_type, object_id=object_id,
        workspace_id=user.workspace_id,
    )
    if rows is None:
        raise HTTPException(404, "not found")
    return {"comments": rows}


@router.post("/comments", response_model=CommentOut, status_code=201)
def create_comment_route(
    body: CreateCommentIn,
    user: AuthUser = Depends(require_permission(q.MODULE, "comment")),
    db: Session = Depends(get_db),
):
    code, out = q.create_comment(
        db, actor=user, object_type=body.object_type, object_id=body.object_id,
        parent_id=body.parent_id, body=body.body,
        mentioned_user_ids=body.mentioned_user_ids,
    )
    if code != "OK":
        raise _fail(code, out)
    db.commit()
    return out


@router.patch("/comments/{cid}", response_model=CommentOut)
def edit_comment_route(
    cid: int,
    body: EditCommentIn,
    user: AuthUser = Depends(require_permission(q.MODULE, "comment")),
    db: Session = Depends(get_db),
):
    code, out = q.edit_comment(
        db, actor=user, comment_id=cid, body=body.body,
        mentioned_user_ids=body.mentioned_user_ids,
    )
    if code != "OK":
        raise _fail(code, out)
    db.commit()
    return out


@router.delete("/comments/{cid}", status_code=204)
def delete_comment_route(
    cid: int,
    user: AuthUser = Depends(require_permission(q.MODULE, "comment")),
    db: Session = Depends(get_db),
):
    code = q.delete_comment(db, actor=user, comment_id=cid)
    if code != "OK":
        raise _fail(code)
    db.commit()
    return None
