"""Material Summary routes (spec §5, §8). Gated `("list", …)`; building and
editing also need `require_drafter()` — §20 names PM / Coordinator /
Designer, which is drafter / manager / admin, not every `list` writer."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import require_drafter, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..material_takes.queries import Conflict, NotFound
from . import queries as q
from .schemas import CurrentSummaryOut, PatchSummaryLineIn, SummaryListOut

router = APIRouter(tags=["material_summaries"])


def _call(fn, *args):
    try:
        return fn(*args)
    except NotFound:
        raise HTTPException(404, "not found")
    except Conflict as c:
        raise HTTPException(409, {"code": c.code, **c.extra})


@router.get("/projects/{pid}/material-summary", response_model=CurrentSummaryOut)
def get_current(pid: int, user: AuthUser = Depends(require_permission("list", "read")),
                db: Session = Depends(get_db)):
    return _call(q.current, db, pid, user.workspace_id)


@router.get("/projects/{pid}/material-summaries", response_model=list[SummaryListOut])
def get_history(pid: int, user: AuthUser = Depends(require_permission("list", "read")),
                db: Session = Depends(get_db)):
    return _call(q.history, db, pid, user.workspace_id)


@router.post("/projects/{pid}/material-summary", status_code=201,
             dependencies=[Depends(require_drafter())])
def post_build(pid: int, user: AuthUser = Depends(require_permission("list", "write")),
               db: Session = Depends(get_db)):
    sid = _call(q.build, db, pid, user.workspace_id, user.id)
    db.commit()
    return {"summary_id": sid}


@router.patch("/material-summaries/{sid}/lines/{lid}", status_code=204,
              dependencies=[Depends(require_drafter())])
def patch_line(sid: int, lid: int, body: PatchSummaryLineIn,
               user: AuthUser = Depends(require_permission("list", "write")),
               db: Session = Depends(get_db)):
    _call(q.patch_line, db, sid, lid, user.workspace_id, user.id, body.model_dump(exclude_unset=True))
    db.commit()


@router.post("/material-summaries/{sid}/confirm", status_code=204)
def post_confirm(sid: int, user: AuthUser = Depends(require_permission("list", "approve")),
                 db: Session = Depends(get_db)):
    _call(q.confirm, db, sid, user.workspace_id, user.id)
    db.commit()
