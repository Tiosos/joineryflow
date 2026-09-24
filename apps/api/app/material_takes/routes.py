"""Material Take routes (spec §8). No RBAC matrix change: `("list", …)`
throughout — `write` (+ `require_drafter`, as parts use) to edit a draft,
`approve` to approve a take or record an impact review."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import require_drafter, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import AddLineIn, CurrentTakeOut, PatchLineIn, ReviewIn, TakeSummaryOut

router = APIRouter(tags=["material_takes"])

_read = require_permission("list", "read")
_write = require_permission("list", "write")
_approve = require_permission("list", "approve")


def _call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except q.NotFound:
        raise HTTPException(404, "not found")
    except q.Conflict as c:
        raise HTTPException(409, {"code": c.code, **c.extra})


@router.get("/items/{iid}/material-take", response_model=CurrentTakeOut)
def get_current(iid: int, user: AuthUser = Depends(_read), db: Session = Depends(get_db)):
    return _call(q.current, db, iid, user.workspace_id)


@router.get("/items/{iid}/material-takes", response_model=list[TakeSummaryOut])
def get_history(iid: int, user: AuthUser = Depends(_read), db: Session = Depends(get_db)):
    return _call(q.history, db, iid, user.workspace_id)


@router.post("/items/{iid}/material-take/generate", status_code=201,
             dependencies=[Depends(require_drafter())])
def post_generate(iid: int, user: AuthUser = Depends(_write), db: Session = Depends(get_db)):
    tid = _call(q.generate, db, iid, user.workspace_id, user.id)
    db.commit()
    return {"take_id": tid}


@router.post("/material-takes/{tid}/regenerate", status_code=204,
             dependencies=[Depends(require_drafter())])
def post_regenerate(tid: int, user: AuthUser = Depends(_write), db: Session = Depends(get_db)):
    _call(q.regenerate, db, tid, user.workspace_id, user.id)
    db.commit()


@router.post("/material-takes/{tid}/lines", status_code=201,
             dependencies=[Depends(require_drafter())])
def post_line(tid: int, body: AddLineIn, user: AuthUser = Depends(_write),
              db: Session = Depends(get_db)):
    if body.material_type == "OTHER" and body.material_id is not None:
        raise HTTPException(422, {"code": "OTHER_HAS_NO_MATERIAL"})
    lid = _call(q.add_line, db, tid, user.workspace_id, user.id, body.model_dump())
    db.commit()
    return {"line_id": lid}


@router.patch("/material-takes/{tid}/lines/{lid}", status_code=204,
              dependencies=[Depends(require_drafter())])
def patch_line(tid: int, lid: int, body: PatchLineIn, user: AuthUser = Depends(_write),
               db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_unset=True)
    if changes.get("material_type") == "OTHER" and changes.get("material_id") is not None:
        raise HTTPException(422, {"code": "OTHER_HAS_NO_MATERIAL"})
    _call(q.patch_line, db, tid, lid, user.workspace_id, user.id, changes)
    db.commit()


@router.delete("/material-takes/{tid}/lines/{lid}", status_code=204,
               dependencies=[Depends(require_drafter())])
def delete_line(tid: int, lid: int, user: AuthUser = Depends(_write),
                db: Session = Depends(get_db)):
    _call(q.delete_line, db, tid, lid, user.workspace_id, user.id)
    db.commit()


@router.post("/material-takes/{tid}/approve", status_code=204)
def post_approve(tid: int, user: AuthUser = Depends(_approve), db: Session = Depends(get_db)):
    _call(q.approve, db, tid, user.workspace_id, user.id)
    db.commit()


@router.post("/material-takes/{tid}/reviews", status_code=201)
def post_review(tid: int, body: ReviewIn, user: AuthUser = Depends(_approve),
                db: Session = Depends(get_db)):
    new_tid = _call(q.review, db, tid, user.workspace_id, user.id, body.outcome, body.note)
    db.commit()
    return {"new_take_id": new_tid}
