"""Item status, bulk status and lifecycle-stage writes.

Part of the items queries facade (see `queries.py`)."""

from sqlalchemy import text
from sqlalchemy.orm import Session
from ..auth.audit import write_audit
from ..auth.sessions import AuthUser
from ..edit_log import write_edit_log
from ..edit_log import write_edit_log_many
from .schemas import PatchLifecycleIn
from ._q_base import _VALID_STATUS_KEYS, _item_row
from ._q_locks import ItemContentLocked, assert_item_content_unlocked


# ── T16 write helpers ─────────────────────────────────────────────────────────

VALID_STAGE_KEYS = (
    "REQ", "SM", "LISTED", "DOWN", "CNC",
    "EDGED", "PAINTED", "MADE", "PACKING", "DEL", "INST",
)


def patch_item_status(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    status: str,
    note: str,
    actor: AuthUser,
) -> bool:
    """Update items.status.  Returns True if updated, False if item not found.
    Raises `ItemContentLocked` on a Hard Lock or someone else's Controlled Lock
    (not the Approval Lock: this is how it is cleared) — nothing is written.

    Writes to item_status_log (the actual table, which records status changes
    with columns: item_id, status, note, changed_by), audit_log, and item_edit_log.

    note is required and must be non-empty (matches item_status_log.note NOT NULL).
    """
    if not note:
        raise ValueError("note is required for status changes")

    current = _item_row(db, item_id=item_id, workspace_id=workspace_id)
    if current is None:
        return False
    actor_id = actor.id
    assert_item_content_unlocked(
        db, item_id=item_id, workspace_id=workspace_id, actor=actor,
        include_approval=False,
    )

    prev_status = db.execute(
        text("SELECT status FROM items WHERE item_id = :iid"),
        {"iid": item_id},
    ).scalar()

    db.execute(
        text(
            "UPDATE items SET status = :s, updated_at = now() WHERE item_id = :iid"
        ),
        {"s": status, "iid": item_id},
    )
    db.flush()

    db.execute(
        text(
            """
            INSERT INTO item_status_log(item_id, status, note, changed_by)
            VALUES (:iid, :s, :n, :cb)
            """
        ),
        {"iid": item_id, "s": status, "n": note, "cb": str(actor_id)},
    )
    db.flush()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="item.status",
        target=str(item_id),
        payload={"old": prev_status, "new": status, "note": note},
    )
    write_edit_log(
        db,
        item_id=item_id,
        actor_id=actor_id,
        field="item.status",
        old_value=prev_status,
        new_value=status,
    )
    _write_approval_lock_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        item_id=item_id, prev_status=prev_status, new_status=status,
    )
    return True


def _write_approval_lock_audit(
    db: Session,
    *,
    workspace_id: int,
    actor_id: int,
    item_id: int,
    prev_status: str | None,
    new_status: str,
) -> None:
    """§L Approval Lock (Q508/Q516): every lock/unlock is audited, even though
    it is derived from `status` rather than a column of its own."""
    if new_status == "APPROVED" and prev_status != "APPROVED":
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id,
            event="item.approval_lock", target=str(item_id), payload={},
        )
    elif prev_status == "APPROVED" and new_status != "APPROVED":
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id,
            event="item.approval_unlock", target=str(item_id), payload={},
        )


def bulk_patch_item_status(
    db: Session,
    *,
    item_ids: list[int],
    workspace_id: int,
    status: str,
    note: str,
    actor: AuthUser,
) -> dict:
    """Apply the same status + note to a batch of items.  Single transaction.

    For each id: classify into one of
      - 'updated': existed and was updated; status_log + audit + edit_log written.
      - 'not_found': no item with that id exists in the caller's workspace. An item of
        another workspace is reported exactly like one that does not exist.
      - 'locked': a Hard Lock or someone else's Controlled Lock refuses the
        caller (not the Approval Lock); skipped, nothing written for it.

    Returns {'updated': int, 'not_found': [int],
    'locked': [{'item_id', 'code', 'owner_name'?}]}.
    """
    if not note:
        raise ValueError("note is required for bulk status changes")
    if status not in _VALID_STATUS_KEYS:
        raise ValueError(f"unknown status key: {status}")

    actor_id = actor.id
    not_found: list[int] = []
    locked: list[dict] = []
    updated_count = 0
    bulk_size = len(item_ids)

    for iid in item_ids:
        exists = db.execute(
            text(
                """
                SELECT 1
                FROM items i
                JOIN projects p ON p.project_id = i.project_id
                WHERE i.item_id = :iid AND p.workspace_id = :w AND NOT i.deleted
                """
            ),
            {"iid": iid, "w": workspace_id},
        ).first()
        if exists is None:
            not_found.append(iid)
            continue
        try:
            assert_item_content_unlocked(
                db, item_id=iid, workspace_id=workspace_id, actor=actor,
                include_approval=False,
            )
        except ItemContentLocked as e:
            locked.append(
                {
                    "item_id": iid,
                    "code": e.detail["code"],
                    "owner_name": e.detail.get("owner_name"),
                }
            )
            continue

        prev_status = db.execute(
            text("SELECT status FROM items WHERE item_id = :iid"),
            {"iid": iid},
        ).scalar()

        db.execute(
            text("UPDATE items SET status = :s, updated_at = now() WHERE item_id = :iid"),
            {"s": status, "iid": iid},
        )
        db.execute(
            text(
                """
                INSERT INTO item_status_log(item_id, status, note, changed_by)
                VALUES (:iid, :s, :n, :cb)
                """
            ),
            {"iid": iid, "s": status, "n": note, "cb": str(actor_id)},
        )
        write_audit(
            db,
            workspace_id=workspace_id,
            actor_id=actor_id,
            event="item.status.bulk",
            target=str(iid),
            payload={
                "old": prev_status,
                "new": status,
                "note": note,
                "bulk_size": bulk_size,
            },
        )
        write_edit_log(
            db,
            item_id=iid,
            actor_id=actor_id,
            field="item.status",
            old_value=prev_status,
            new_value=status,
        )
        _write_approval_lock_audit(
            db, workspace_id=workspace_id, actor_id=actor_id,
            item_id=iid, prev_status=prev_status, new_status=status,
        )
        updated_count += 1

    db.flush()
    return {
        "updated": updated_count,
        "not_found": not_found,
        "locked": locked,
    }


def patch_lifecycle(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    stage_key: str,
    payload: PatchLifecycleIn,
    actor: AuthUser,
) -> str:
    """UPSERT item_stages row for (item_id, stage_key).

    Returns 'OK', 'NOT_FOUND', or 'INVALID_STAGE_KEY'.  Raises
    `ItemContentLocked` on a Hard Lock or someone else's Controlled Lock (not
    the Approval Lock — production dates follow approval).  Shop Floor's
    fan-out writes `item_stages` directly and is deliberately not gated.

    Writes audit_log and item_edit_log per changed field.
    Does NOT write to item_status_log — that table is for status changes,
    not lifecycle date changes (schema drift from spec).
    """
    if stage_key not in VALID_STAGE_KEYS:
        return "INVALID_STAGE_KEY"

    current = _item_row(db, item_id=item_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND"

    # Q419: a related part shows no workflow stages at all, so it has no
    # lifecycle to patch.  NOT_FOUND rather than a new sentinel — the stage
    # genuinely does not exist for this row.
    if current["row_type"] != "joinery_item":
        return "NOT_FOUND"

    actor_id = actor.id
    assert_item_content_unlocked(
        db, item_id=item_id, workspace_id=workspace_id, actor=actor,
        include_approval=False,
    )

    # Fetch current stage row (if any) to capture old values for edit_log
    existing = db.execute(
        text(
            """
            SELECT due_date, done_date
            FROM item_stages
            WHERE item_id = :iid AND stage_key = :sk
            """
        ),
        {"iid": item_id, "sk": stage_key},
    ).mappings().first()

    old_due = existing["due_date"] if existing else None
    old_done = existing["done_date"] if existing else None

    # UPSERT: composite PK (item_id, stage_key) guarantees uniqueness
    db.execute(
        text(
            """
            INSERT INTO item_stages(item_id, stage_key, due_date, done_date)
            VALUES (:iid, :sk, :due, :done)
            ON CONFLICT (item_id, stage_key)
            DO UPDATE SET
                due_date  = COALESCE(EXCLUDED.due_date,  item_stages.due_date),
                done_date = COALESCE(EXCLUDED.done_date, item_stages.done_date)
            """
        ),
        {
            "iid": item_id,
            "sk": stage_key,
            "due": payload.due_date,
            "done": payload.done_date,
        },
    )
    db.flush()

    # Audit and edit_log per changed field
    audit_payload: dict = {}
    changes: list[tuple[str, str | None, str | None]] = []

    if payload.due_date is not None and payload.due_date != old_due:
        field_name = f"lifecycle.{stage_key}.due_date"
        audit_payload["due_date"] = str(payload.due_date)
        changes.append((field_name, str(old_due) if old_due else None, str(payload.due_date)))

    if payload.done_date is not None and payload.done_date != old_done:
        field_name = f"lifecycle.{stage_key}.done_date"
        audit_payload["done_date"] = str(payload.done_date)
        changes.append((field_name, str(old_done) if old_done else None, str(payload.done_date)))

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event=f"item.lifecycle.{stage_key}",
        target=str(item_id),
        payload=audit_payload,
    )

    if changes:
        write_edit_log_many(db, item_id=item_id, actor_id=actor_id, changes=changes)

    return "OK"
