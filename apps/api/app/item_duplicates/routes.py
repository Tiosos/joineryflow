"""POST /items/{id}/duplicate — one copy of a Joinery Item (Plan V1 §2)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import require_drafter, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..items.queries import get_item_detail
from ..items.schemas import ItemOut
from .queries import duplicate_item

router = APIRouter(tags=["item_duplicates"])


@router.post(
    "/items/{iid}/duplicate",
    response_model=ItemOut,
    status_code=201,
    dependencies=[Depends(require_drafter())],
)
def duplicate_item_route(
    iid: int,
    # Creating an item: the same gate as POST /projects/{pid}/items.
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    new_id = duplicate_item(db, item_id=iid, workspace_id=user.workspace_id, actor=user)
    if new_id is None:
        raise HTTPException(status_code=404, detail="item not found")
    db.commit()
    return get_item_detail(
        db, item_id=new_id, workspace_id=user.workspace_id, current_user_id=user.id
    )
