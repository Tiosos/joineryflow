"""Atomic per-workspace counter helper.

Single-statement UPSERT keeps allocation race-free without an explicit
SELECT ... FOR UPDATE — Postgres holds the row lock for the duration of
the INSERT ... ON CONFLICT DO UPDATE.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session


def next_value(db: Session, *, workspace_id: int, name: str) -> int:
    """Reserve and return the next integer for (workspace_id, name).

    First call for an unseen (workspace_id, name) returns 1 and seeds
    next_value=2. Subsequent calls return the current next_value and
    advance the row by 1. Atomic under concurrent callers.
    """
    if not name or len(name) > 32:
        raise ValueError("counter name must be 1..32 chars")

    row = db.execute(
        text(
            """
            INSERT INTO workspace_counter (workspace_id, name, next_value)
            VALUES (:wid, :n, 2)
            ON CONFLICT (workspace_id, name) DO UPDATE
              SET next_value = workspace_counter.next_value + 1
            RETURNING next_value - 1 AS reserved
            """
        ),
        {"wid": workspace_id, "n": name},
    ).mappings().first()

    if row is None:
        raise RuntimeError("workspace_counter UPSERT returned no row")

    return int(row["reserved"])
