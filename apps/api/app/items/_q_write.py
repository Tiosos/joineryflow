"""Item create, patch, soft delete and restore.

Part of the items queries facade (see `queries.py`)."""

from sqlalchemy import text
from sqlalchemy.orm import Session
from ..auth.audit import write_audit
from ..auth.sessions import AuthUser
from ..concurrency import check_field_conflicts
from ..concurrency import conflict_safe_value
from ..edit_log import write_edit_log
from .schemas import CreateItemIn
from .schemas import PatchItemIn
from ._q_base import _PATCH_FIELD_MAP, _apply_item_changes, _changed_fields, _item_row, _project_in_workspace, _user_in_workspace
from ._q_locks import _upsert_lock_request, assert_item_content_unlocked


def create_item(
    db: Session,
    *,
    workspace_id: int,
    project_id: int,
    payload: CreateItemIn,
    actor_id: int,
) -> int | None:
    """INSERT a new item.  Returns new item_id, or None if project not in workspace.

    `items.num` has a global UNIQUE constraint (legacy FK artefact) and is
    allocated from **`joinery_number_seq`** (migration `0027`), the single
    company-wide counter Q541 requires: Item IDs, cutlist numbers and related
    parts all draw from it, so a six-digit number never means two things.

    This replaced `nextval('items_item_id_seq') + 100000`, which borrowed the
    PK sequence and therefore burned two values per insert (the explicit
    nextval here, plus the column DEFAULT for `item_id`).
    """
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return None

    iid = db.execute(
        text(
            """
            INSERT INTO items(
                num, project_id, status,
                description, qty, stage, code, level,
                rm_no, rm_desc, zone, item_locked
            )
            VALUES (
                nextval('joinery_number_seq'),
                :pid, 'CLEAR',
                :desc, :qty, :stage, :code, :level,
                :room_no, :room_desc, :zone, false
            )
            RETURNING item_id
            """
        ),
        {
            "pid": project_id,
            "desc": payload.description,
            "qty": payload.qty,
            "stage": payload.stage,
            "code": payload.code,
            "level": payload.level,
            "room_no": payload.room_no,
            "room_desc": payload.room_desc,
            "zone": payload.zone,
        },
    ).scalar()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="item.create",
        target=str(iid),
        payload={"project_id": project_id, "description": payload.description},
    )
    write_edit_log(
        db,
        item_id=iid,
        actor_id=actor_id,
        field="_create",
        old_value=None,
        new_value=str(payload.model_dump(exclude_none=True)),
    )
    return iid


def patch_item(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    payload: PatchItemIn,
    actor_id: int,
) -> dict | None:
    """Apply a partial update to an item.  None if not found/out-of-workspace.

    Controlled Lock (Q509, replacing the advisory soft-lock of spec §6.4):
    - cutlist_owner_id IS NULL:      first save claims — item_locked=true, owner=actor.
    - item_locked AND owner != actor: the save does **not** apply.  It is held as
      a pending `item_lock_request` for the owner or a manager to decide, and
      the caller gets 409.  Saving again revises your own pending request
      rather than stacking a second one (uniq_pending_lock_request).
    - otherwise:                     applies directly.

    Returns `{"outcome": "applied"}` or `{"outcome": "lock_request", "request": {...}}`.
    Edit log: one row per changed field.
    """
    # §L Q511/Q512: locks the row for this whole transaction, so a concurrent
    # PATCH on the same item serialises instead of racing on the
    # read-then-write field-version check below.
    current = _item_row(db, item_id=item_id, workspace_id=workspace_id, for_update=True)
    if current is None:
        return None

    # §L — Hard Lock (Q508): blocks everyone, including the owner, until a
    # manager/admin explicitly clears it via POST|DELETE /items/{id}/hard-lock.
    # Checked before everything else — unlike the Controlled Lock, there is no
    # request-and-approve path around a Hard Lock.
    if current["hard_locked_at"] is not None:
        return {"outcome": "HARD_LOCKED", "locked_by": current["hard_locked_by"]}

    # §L — Approval Lock (Q508): "information automatically locks when
    # approved" binds directly to the existing Status taxonomy's APPROVED
    # value — there is no separate column to check. Unlocking is moving
    # status away from APPROVED via PATCH /items/{id}/status, which (like
    # the Controlled Lock) this endpoint never consults.
    if current["status"] == "APPROVED":
        return {"outcome": "APPROVAL_LOCKED"}

    # Tracking 2.0: cross-workspace contractor reference blocked at app layer.
    # Checked before the lock branch so an invalid contractor is never held in
    # a pending Controlled-Lock request.
    if payload.contractor_id is not None and not _user_in_workspace(
        db, user_id=payload.contractor_id, workspace_id=workspace_id
    ):
        return {"outcome": "CROSS_WORKSPACE_CONTRACTOR"}

    owner_id: int | None = current["cutlist_owner_id"]
    is_locked: bool = bool(current["item_locked"])

    if is_locked and owner_id is not None and owner_id != actor_id:
        proposed = _changed_fields(payload, current)
        if not proposed:
            # Nothing would change — no request to raise, and nothing applied.
            return {"outcome": "applied"}
        request = _upsert_lock_request(
            db,
            item_id=item_id,
            workspace_id=workspace_id,
            requester_id=actor_id,
            owner_id=owner_id,
            proposed=proposed,
        )
        return {"outcome": "lock_request", "request": request}

    # §L — Q511/Q512: field-level optimistic concurrency, checked only on this
    # direct-apply path. When the item is Controlled-Locked by someone else
    # (the branch above), nothing is written here — the save becomes a
    # pending request instead — so there is no concurrent-write race for
    # versioning to catch; Controlled Lock already serialises that case
    # through its own approve/reject flow.
    conflicts = check_field_conflicts(
        current.get("field_versions"), payload.expected_versions
    )
    if conflicts:
        row_key_by_attr = {attr: rk for attr, _col, rk in _PATCH_FIELD_MAP}
        for field, info in conflicts.items():
            info["current_value"] = conflict_safe_value(
                current.get(row_key_by_attr.get(field, field))
            )
        return {"outcome": "FIELD_CONFLICT", "conflicts": conflicts}

    extra: dict[str, object] = {}
    if owner_id is None:
        # First-save claim
        extra = {"item_locked": True, "cutlist_owner_id": actor_id}

    applied = _apply_item_changes(
        db,
        item_id=item_id,
        current=current,
        payload=payload,
        author_id=actor_id,
        extra_updates=extra,
    )
    if isinstance(applied, str):
        # The area/room pair does not resolve — see `_resolve_area_room`.
        return {"outcome": applied}
    # `_apply_item_changes` already bumped field_versions in the same UPDATE
    # as the changed columns — nothing further to do here.
    return {"outcome": "applied"}


def delete_item(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    actor: AuthUser,
) -> str:
    """Soft-delete an item.  Returns 'OK' or 'NOT_FOUND'.
    Raises `ItemContentLocked` (HARD_LOCKED) on a Hard Lock, which blocks everyone: a
    manager/admin clears it first. The Approval and Controlled Locks do not stop a delete.

    Sets `deleted` on the item, on its related parts, and on its cutlist when no live
    item is left in it. Nothing is removed, so production history, QC records, orders
    and audit stay as they were, and `restore_item` brings it all back. A deleted item
    answers 404 everywhere (`_item_row`, `row_types.not_deleted`).
    """
    assert_item_content_unlocked(
        db, item_id=item_id, workspace_id=workspace_id, actor=actor,
        include_approval=False, include_controlled=False,
    )
    current = _item_row(db, item_id=item_id, workspace_id=workspace_id, for_update=True)
    if current is None:
        return "NOT_FOUND"
    actor_id = actor.id

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="item.delete",
        target=str(item_id),
        payload={"description": current.get("description")},
    )
    write_edit_log(
        db,
        item_id=item_id,
        actor_id=actor_id,
        field="_delete",
        old_value=str(current.get("description")),
        new_value=None,
    )

    db.execute(
        text(
            "UPDATE items SET deleted = true, updated_at = now()"
            " WHERE item_id = :iid OR parent_item_id = :iid"
        ),
        {"iid": item_id},
    )
    # One statement, so "no live item left" and the flag cannot be split by a concurrent link.
    db.execute(
        text(
            """
            UPDATE cutlist c SET deleted = true, updated_at = now()
            WHERE c.cutlist_id = (SELECT cutlist_id FROM items WHERE item_id = :iid)
              AND NOT EXISTS (
                  SELECT 1 FROM items i WHERE i.cutlist_id = c.cutlist_id AND NOT i.deleted
              )
            """
        ),
        {"iid": item_id},
    )
    return "OK"


def restore_item(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    actor_id: int,
) -> str:
    """Undo `delete_item`.  Returns 'OK', 'NOT_FOUND', 'NOT_DELETED' or, for a related part
    whose parent is still deleted, 'PARENT_DELETED' (restore the parent instead).
    Not stopped by a Hard Lock: it only undoes a delete."""
    current = _item_row(
        db, item_id=item_id, workspace_id=workspace_id,
        for_update=True, include_deleted=True,
    )
    if current is None:
        return "NOT_FOUND"
    if not db.execute(
        text("SELECT deleted FROM items WHERE item_id = :iid"), {"iid": item_id}
    ).scalar():
        return "NOT_DELETED"
    if current["row_type"] == "related_part" and db.execute(
        text(
            "SELECT p.deleted FROM items p"
            " WHERE p.item_id = (SELECT parent_item_id FROM items WHERE item_id = :iid)"
        ),
        {"iid": item_id},
    ).scalar():
        return "PARENT_DELETED"

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="item.restore",
        target=str(item_id),
        payload={"description": current.get("description")},
    )
    write_edit_log(
        db,
        item_id=item_id,
        actor_id=actor_id,
        field="_restore",
        old_value=None,
        new_value=str(current.get("description")),
    )
    db.execute(
        text(
            "UPDATE items SET deleted = false, updated_at = now()"
            " WHERE item_id = :iid OR parent_item_id = :iid"
        ),
        {"iid": item_id},
    )
    db.execute(
        text(
            "UPDATE cutlist SET deleted = false, updated_at = now()"
            " WHERE cutlist_id = (SELECT cutlist_id FROM items WHERE item_id = :iid)"
        ),
        {"iid": item_id},
    )
    return "OK"
