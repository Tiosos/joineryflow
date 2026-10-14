"""The Payment Method / Payment Type list (migration 0063), per workspace.

Shared by an invoice's Payment Method and the authorisation form's Payment Type. A switched-off
entry stays on the rows that use it and cannot be chosen again; there is no delete.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..sql_columns import require_columns

_PATCHABLE_COLUMNS = frozenset({"name", "is_active"})
_COLS = "payment_method_id, name, is_active"


def list_methods(db: Session, *, workspace_id: int) -> list[dict]:
    rows = db.execute(
        text(f"SELECT {_COLS} FROM payment_method WHERE workspace_id = :w ORDER BY lower(name)"),
        {"w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def create_method(db: Session, *, workspace_id: int, actor_id: int, name: str) -> dict | None:
    """None when the name is taken (any case) in this workspace."""
    row = db.execute(
        text(
            f"INSERT INTO payment_method (workspace_id, name) VALUES (:w, :n)"
            f" ON CONFLICT (workspace_id, lower(name)) DO NOTHING RETURNING {_COLS}"
        ),
        {"w": workspace_id, "n": name.strip()},
    ).mappings().first()
    if row is None:
        return None
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="payment_method.create",
                target=str(row["payment_method_id"]), payload={"name": row["name"]})
    return dict(row)


def patch_method(
    db: Session, *, payment_method_id: int, workspace_id: int, actor_id: int, changes: dict
) -> tuple[str, dict | None]:
    """Codes: 'OK' | 'NOT_FOUND' | 'EXISTS'."""
    require_columns(changes, _PATCHABLE_COLUMNS)
    current = db.execute(
        text(f"SELECT {_COLS} FROM payment_method WHERE payment_method_id = :i AND workspace_id = :w FOR UPDATE"),
        {"i": payment_method_id, "w": workspace_id},
    ).mappings().first()
    if current is None:
        return "NOT_FOUND", None
    changes = {k: (v.strip() if isinstance(v, str) else v) for k, v in changes.items() if v != current[k]}
    if not changes:
        return "OK", dict(current)
    if "name" in changes and db.execute(
        text("SELECT 1 FROM payment_method WHERE workspace_id = :w AND lower(name) = lower(:n)"
             " AND payment_method_id <> :i"),
        {"w": workspace_id, "n": changes["name"], "i": payment_method_id},
    ).first():
        return "EXISTS", None
    sets = ", ".join(f"{k} = :{k}" for k in changes)
    row = db.execute(
        text(f"UPDATE payment_method SET {sets} WHERE payment_method_id = :i RETURNING {_COLS}"),
        {**changes, "i": payment_method_id},
    ).mappings().one()
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="payment_method.update",
                target=str(payment_method_id), payload={"fields": sorted(changes)})
    return "OK", dict(row)


def active_in_workspace(db: Session, *, payment_method_id: int, workspace_id: int) -> bool:
    """For a body that names a method: this workspace's and still switched on."""
    return db.execute(
        text("SELECT 1 FROM payment_method WHERE payment_method_id = :i AND workspace_id = :w AND is_active"),
        {"i": payment_method_id, "w": workspace_id},
    ).first() is not None
