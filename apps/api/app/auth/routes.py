from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from .audit import write_audit
from .passwords import verify_password
from .rbac import current_user
from .schemas import LoginIn, MeOut
from .sessions import AuthUser, create_session, revoke_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginIn, resp: Response, db: Session = Depends(get_db)):
    row = db.execute(
        text(
            """
            SELECT u.id, u.password_hash, u.workspace_id, u.is_active
            FROM app_user u
            JOIN workspace w ON w.id = u.workspace_id
            WHERE w.slug = :s AND u.email = :e
            """
        ),
        {"s": body.workspace_slug, "e": body.email},
    ).mappings().first()
    if not row or not row["is_active"] or not verify_password(
        row["password_hash"], body.password
    ):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = create_session(db, row["id"])
    write_audit(
        db,
        workspace_id=row["workspace_id"],
        actor_id=row["id"],
        event="auth.login",
        target=body.email,
    )
    db.commit()
    resp.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
        max_age=settings.session_sliding_days * 86400,
    )
    return {"ok": True}


@router.post("/logout")
def logout(
    request: Request,
    resp: Response,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(current_user),
):
    tok = request.cookies.get(settings.session_cookie_name)
    if tok:
        revoke_session(db, tok)
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event="auth.logout",
    )
    db.commit()
    resp.delete_cookie(settings.session_cookie_name, path="/")
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(user: AuthUser = Depends(current_user)):
    return MeOut(**user.__dict__)
