"""app/workspace_scope.py: each check says yes for the owner's workspace, no for any other or a missing id."""
from sqlalchemy import text

from app import workspace_scope as ws
from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers import create_project, login

truncate_after = truncate_fixture()


def test_scope_checks_follow_the_workspace(truncate_after):
    _, wid, uid = login("admin")
    _, other_wid, _ = login("admin", prefix="scope-other")
    with SessionLocal() as db:
        pid = create_project(db, uid=uid)
        db.commit()
        vid = db.execute(text("SELECT vendor_id FROM vendors WHERE workspace_id = :w LIMIT 1"), {"w": wid}).scalar()
        assert ws.project_in_workspace(db, project_id=pid, workspace_id=wid)
        assert not ws.project_in_workspace(db, project_id=pid, workspace_id=other_wid)
        assert not ws.project_in_workspace(db, project_id=-1, workspace_id=wid)
        assert ws.user_in_workspace(db, user_id=uid, workspace_id=wid)
        assert not ws.user_in_workspace(db, user_id=uid, workspace_id=other_wid)
        if vid is not None:
            assert ws.vendor_in_workspace(db, vendor_id=vid, workspace_id=wid)
            assert not ws.vendor_in_workspace(db, vendor_id=vid, workspace_id=other_wid)
        assert not ws.vendor_in_workspace(db, vendor_id=-1, workspace_id=wid)
