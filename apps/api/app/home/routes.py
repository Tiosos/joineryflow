"""FastAPI route handler for the home dashboard endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth.rbac import current_user
from ..auth.sessions import AuthUser
from ..db import get_db
from .queries import dashboard
from .schemas import HomeDashboardOut

router = APIRouter(prefix="", tags=["home"])


@router.get("/home/dashboard", response_model=HomeDashboardOut)
def get_home_dashboard(
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Composite landing payload personalised by role.

    Returns 4 metric cards + my_day + deliveries_today + team_activity
    + favourite_projects + all_projects_count. Role-shaped per auth_role.
    """
    return dashboard(db, user=user)
