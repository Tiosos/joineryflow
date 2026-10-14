"""Shared "is this row in my workspace" checks (CLAUDE.md §7, workspace isolation).

A foreign id taken from a request body or path is answered like a missing one,
so each check is a plain existence test scoped by `workspace_id`. New code
imports these instead of writing the SELECT again; older modules move over as
they are touched.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session


def project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    return db.execute(
        text("SELECT 1 FROM projects WHERE project_id = :p AND workspace_id = :w"),
        {"p": project_id, "w": workspace_id},
    ).first() is not None


def user_in_workspace(db: Session, *, user_id: int, workspace_id: int) -> bool:
    return db.execute(
        text("SELECT 1 FROM app_user WHERE id = :u AND workspace_id = :w"),
        {"u": user_id, "w": workspace_id},
    ).first() is not None


def vendor_in_workspace(db: Session, *, vendor_id: int, workspace_id: int) -> bool:
    return db.execute(
        text("SELECT 1 FROM vendors WHERE vendor_id = :v AND workspace_id = :w"),
        {"v": vendor_id, "w": workspace_id},
    ).first() is not None
