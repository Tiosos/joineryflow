"""Audit log writer.

Single entry point for inserting into the workspace-scoped `audit_log` table.
Caller passes plain dicts; we serialize to JSON and cast to jsonb at write
time. Like the session helpers, this module flushes but does not commit -
the surrounding request handler owns the transaction lifecycle.
"""
import json

from sqlalchemy import text
from sqlalchemy.orm import Session


def write_audit(
    db: Session,
    *,
    workspace_id: int,
    actor_id: int | None,
    event: str,
    target: str | None = None,
    payload: dict | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO audit_log(workspace_id, actor_id, event, target, payload)
            VALUES (:w, :a, :e, :t, CAST(:p AS jsonb))
            """
        ),
        {
            "w": workspace_id,
            "a": actor_id,
            "e": event,
            "t": target,
            "p": json.dumps(payload or {}),
        },
    )
    db.flush()
