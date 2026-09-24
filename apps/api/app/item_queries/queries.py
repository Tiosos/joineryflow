"""SQL helpers for item_query CRUD.  Workspace-isolated through items->projects."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit


_QUERY_COLS = """
    q.query_id, q.item_id, q.asked_by, ua.full_name AS asked_by_name,
    q.asked_at, q.question,
    q.answered_by, ub.full_name AS answered_by_name,
    q.answered_at, q.answer
"""

_QUERY_JOINS = """
    LEFT JOIN app_user ua ON ua.id = q.asked_by
    LEFT JOIN app_user ub ON ub.id = q.answered_by
"""


def _item_in_workspace(db: Session, *, item_id: int, workspace_id: int) -> bool:
    row = db.execute(
        text(
            """
            SELECT 1 FROM items i
            JOIN projects p ON p.project_id = i.project_id
            WHERE i.item_id = :iid AND p.workspace_id = :wid
            """
        ),
        {"iid": item_id, "wid": workspace_id},
    ).first()
    return row is not None


def list_queries(
    db: Session, *, item_id: int, workspace_id: int
) -> list[dict] | None:
    if not _item_in_workspace(db, item_id=item_id, workspace_id=workspace_id):
        return None
    rows = db.execute(
        text(
            f"""
            SELECT {_QUERY_COLS}
              FROM item_query q
              {_QUERY_JOINS}
             WHERE q.item_id = :iid
             ORDER BY q.asked_at DESC
            """
        ),
        {"iid": item_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def _query_in_workspace(
    db: Session, *, query_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            f"""
            SELECT {_QUERY_COLS}
              FROM item_query q
              {_QUERY_JOINS}
              JOIN items i ON i.item_id = q.item_id
              JOIN projects p ON p.project_id = i.project_id
             WHERE q.query_id = :qid AND p.workspace_id = :wid
            """
        ),
        {"qid": query_id, "wid": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def create_query(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    question: str,
    actor_id: int,
) -> dict | None:
    if not _item_in_workspace(db, item_id=item_id, workspace_id=workspace_id):
        return None

    qid = db.execute(
        text(
            """
            INSERT INTO item_query(item_id, asked_by, question)
            VALUES (:iid, :ab, :q)
            RETURNING query_id
            """
        ),
        {"iid": item_id, "ab": actor_id, "q": question},
    ).scalar()
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="item.query.create",
        target=str(item_id),
        payload={"query_id": qid},
    )
    db.flush()
    return _query_in_workspace(db, query_id=qid, workspace_id=workspace_id)


def answer_query(
    db: Session,
    *,
    query_id: int,
    workspace_id: int,
    answer: str,
    actor_id: int,
    allow_overwrite: bool = False,
) -> str | dict:
    """Returns 'NOT_FOUND', 'ALREADY_ANSWERED' (when not overwriting), or row dict."""
    current = _query_in_workspace(db, query_id=query_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND"
    if current["answer"] is not None and not allow_overwrite:
        return "ALREADY_ANSWERED"

    db.execute(
        text(
            """
            UPDATE item_query
               SET answered_by = :uid,
                   answered_at = now(),
                   answer      = :a
             WHERE query_id    = :qid
            """
        ),
        {"uid": actor_id, "a": answer, "qid": query_id},
    )
    event = "item.query.edit_answer" if allow_overwrite else "item.query.answer"
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event=event,
        target=str(current["item_id"]),
        payload={"query_id": query_id},
    )
    db.flush()
    return _query_in_workspace(db, query_id=query_id, workspace_id=workspace_id)
