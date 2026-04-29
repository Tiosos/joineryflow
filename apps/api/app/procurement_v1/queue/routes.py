"""HTTP route for /procurement-queue (Procurement Workbench v1, Task 13).

Cross-project rollup of in-flight procurement batches, filtered to the
caller's workspace (via projects.pm_id -> app_user.workspace_id).

RBAC: requires `(orderbook, read)` — purchase_officer + manager + admin.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...auth.rbac import require_permission
from ...auth.sessions import AuthUser
from ...db import get_db
from .queries import queue
from .schemas import QueueOut

router = APIRouter(prefix="", tags=["procurement-v1"])


@router.get("/procurement-queue", response_model=QueueOut)
def get_queue(
    status: str | None = None,
    supplier: str | None = None,
    project_id: int | None = None,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return {
        "rows": queue(
            db,
            workspace_id=user.workspace_id,
            status=status,
            supplier=supplier,
            project_id=project_id,
        )
    }
