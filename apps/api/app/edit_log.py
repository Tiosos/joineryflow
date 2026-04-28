"""item_edit_log writer.

Per spec §6.5: every mutation on items / parts / hardware_lines /
project_hardware_catalog writes one item_edit_log row in the SAME txn.
A PATCH that changes 3 fields -> 3 log rows.
POST/DELETE -> one row with field='_create' or '_delete'.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session


def write_edit_log(
    db: Session,
    *,
    item_id: int,
    actor_id: int | None,
    field: str,
    old_value: str | None,
    new_value: str | None,
) -> None:
    db.execute(
        text("""
            INSERT INTO item_edit_log(item_id, actor_id, field, old_value, new_value)
            VALUES (:i, :a, :f, :o, :n)
        """),
        {"i": item_id, "a": actor_id, "f": field, "o": old_value, "n": new_value},
    )
    db.flush()


def write_edit_log_many(
    db: Session,
    *,
    item_id: int,
    actor_id: int | None,
    changes: list[tuple[str, str | None, str | None]],
) -> None:
    """Write N rows in one executemany. Each `changes` tuple is (field, old, new)."""
    if not changes:
        return
    db.execute(
        text("""
            INSERT INTO item_edit_log(item_id, actor_id, field, old_value, new_value)
            VALUES (:i, :a, :f, :o, :n)
        """),
        [
            {"i": item_id, "a": actor_id, "f": f, "o": o, "n": n}
            for (f, o, n) in changes
        ],
    )
    db.flush()
