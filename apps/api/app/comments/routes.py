"""HTTP routes for comments (Plan V1 §29, Q473).

Which module governs a thread depends on what it is a thread on
(`queries.COMMENT_MODULE` / `READ_MODULES`): `tracking` for Project / Area /
Room / Item, `list` for a Module, `shop_dwgs` for a shop-drawing revision.
Reading needs `read` on every module the thread links into; posting, editing
and deleting need `comment` on the object's own module — the first place the
`comment` action is actually enforced. Because the module is a property of the
object, the edit / delete / reply routes look the comment's type up first.
The author-only edit rule and the author-or-manager delete rule are in the
query layer (per-object rules stay out of the matrix, Q472 not being built).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth.rbac import current_user, require_permission
from ..auth.rbac_engine import has_permission_db
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    CommentCountsOut,
    CommentOut,
    CommentThreadOut,
    CreateCommentIn,
    EditCommentIn,
    ObjectType,
)

router = APIRouter(tags=["comments"])


def _forbidden() -> HTTPException:
    return HTTPException(403, "forbidden")


def _require_read_access(db: Session, user: AuthUser, object_type: str) -> None:
    """`read` on every module the thread links into (`READ_MODULES`)."""
    for module in q.READ_MODULES[object_type]:
        if not has_permission_db(db, user, module, "read"):
            raise _forbidden()


def _require_comment(db: Session, user: AuthUser, object_type: str) -> None:
    """`comment` on the object's own module (`COMMENT_MODULE`)."""
    if not has_permission_db(db, user, q.COMMENT_MODULE[object_type], "comment"):
        raise _forbidden()


def _type_of_existing(db: Session, user: AuthUser, comment_id: int) -> str:
    t = q.object_type_of(db, comment_id=comment_id, workspace_id=user.workspace_id)
    if t is None:
        raise HTTPException(404, "not found")
    return t


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
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_read_access(db, user, object_type)
    rows = q.list_comments(
        db, object_type=object_type, object_id=object_id,
        workspace_id=user.workspace_id,
    )
    if rows is None:
        raise HTTPException(404, "not found")
    return {"comments": rows}


@router.get("/projects/{pid}/comment-counts", response_model=CommentCountsOut)
def comment_counts_route(
    pid: int,
    user: AuthUser = Depends(require_permission(q.MODULE, "read")),
    db: Session = Depends(get_db),
):
    """Backs the project page's Areas & Rooms card: how many live comments each
    area and room has. Read-only; same gate as reading a thread."""
    out = q.counts_for_project(db, project_id=pid, workspace_id=user.workspace_id)
    if out is None:
        raise HTTPException(404, "not found")
    return out


@router.post("/comments", response_model=CommentOut, status_code=201)
def create_comment_route(
    body: CreateCommentIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    # A reply names no object: its type is its parent's. An unknown parent falls
    # through to `create_comment`, which answers 404.
    object_type = body.object_type
    if object_type is None:
        object_type = q.object_type_of(
            db, comment_id=body.parent_id, workspace_id=user.workspace_id)
    if object_type is not None:
        _require_comment(db, user, object_type)
        _require_read_access(db, user, object_type)
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
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_comment(db, user, _type_of_existing(db, user, cid))
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
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_comment(db, user, _type_of_existing(db, user, cid))
    code = q.delete_comment(db, actor=user, comment_id=cid)
    if code != "OK":
        raise _fail(code)
    db.commit()
    return None
