"""Item locks: Hard / Approval / Controlled checks, claim and release, lock requests.

Part of the items queries facade (see `queries.py`)."""

from sqlalchemy import text
from sqlalchemy.orm import Session
import json
from ..auth.audit import write_audit
from ..auth.sessions import AuthUser
from .schemas import PatchItemIn
from ._q_base import _apply_item_changes, _item_row


class ItemContentLocked(Exception):
    """An item's own lock refuses a change to what hangs off it (a module).

    `detail` is the 409 body: `{code: HARD_LOCKED | APPROVAL_LOCKED | ITEM_LOCKED, ...}`.
    """

    def __init__(self, detail: dict) -> None:
        super().__init__(detail["code"])
        self.detail = detail


def assert_item_content_unlocked(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    actor: AuthUser,
    include_approval: bool = True,
    include_controlled: bool = True,
) -> None:
    """Refuse a change to an item's modules while a lock on the item forbids it.

    `patch_item` is the only place the locks are enforced for the item's own
    fields; this is the same three rules for a change that is not a PATCH body,
    so it cannot be held as a Controlled-Lock request and is refused instead:

    - Hard Lock (Q508): everyone, including the owner.
    - Approval Lock (Q508): `status = 'APPROVED'`.
    - Controlled Lock (Q509): `item_locked` with someone else as owner. The owner
      and managers/admins pass — the people who can decide a lock request.

    `include_approval=False` leaves the Approval Lock out: `status` and lifecycle
    dates are the one place it must not apply, because changing status is how an
    approved item is unlocked and approval is when production dates start.

    `include_controlled=False` leaves the Controlled Lock out: for *asking* an item
    query, which anyone with `list:read` may do — a lock must not stop a person
    putting a question to the lock's owner.

    Locks the item row `FOR UPDATE`, so a lock set concurrently is either seen
    here or waits for the caller's transaction. Raises `ItemContentLocked`.
    """
    current = _item_row(db, item_id=item_id, workspace_id=workspace_id, for_update=True)
    if current is None:
        return
    if current["hard_locked_at"] is not None:
        raise ItemContentLocked(
            {"code": "HARD_LOCKED", "locked_by": current["hard_locked_by"]}
        )
    if include_approval and current["status"] == "APPROVED":
        raise ItemContentLocked({"code": "APPROVAL_LOCKED"})
    owner_id = current["cutlist_owner_id"]
    if (
        include_controlled
        and current["item_locked"]
        and owner_id is not None
        and owner_id != actor.id
        and actor.auth_role not in ("manager", "admin")
    ):
        owner_name = db.execute(
            text("SELECT full_name FROM app_user WHERE id = :u"), {"u": owner_id}
        ).scalar()
        raise ItemContentLocked(
            {"code": "ITEM_LOCKED", "owner_id": owner_id, "owner_name": owner_name}
        )


def claim_or_release_lock(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    actor: AuthUser,
    action: str,
    owner_id: int | None = None,
) -> str:
    """Manage soft-lock state.  action ∈ {'claim', 'release', 'transfer'}.

    Returns 'OK', 'NOT_FOUND', or 'FORBIDDEN'.

    claim   (POST /items/{id}/lock, no body):
        Always takes lock for actor.
    release (DELETE /items/{id}/lock):
        Clears item_locked; cutlist_owner_id is NOT cleared (sticky claim).
    transfer (POST /items/{id}/lock with {owner_id: N}):
        Requires actor == current owner OR auth_role in {manager, admin}.
        Verifies new owner_id is in caller's workspace.
    """
    current = _item_row(db, item_id=item_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND"

    # The soft-lock guards cutlist ownership, and a related part has no
    # cutlist (Q417), so it can neither be claimed nor assigned.
    if current["row_type"] != "joinery_item":
        return "NOT_FOUND"

    prior_owner: int | None = current["cutlist_owner_id"]

    if action == "claim":
        db.execute(
            text(
                """
                UPDATE items
                   SET item_locked = true,
                       cutlist_owner_id = :actor_id,
                       updated_at = now()
                 WHERE item_id = :iid
                """
            ),
            {"actor_id": actor.id, "iid": item_id},
        )
        db.flush()
        write_audit(
            db,
            workspace_id=workspace_id,
            actor_id=actor.id,
            event="item.lock",
            target=str(item_id),
            payload={},
        )

    elif action == "release":
        db.execute(
            text(
                """
                UPDATE items
                   SET item_locked = false,
                       updated_at = now()
                 WHERE item_id = :iid
                """
            ),
            {"iid": item_id},
        )
        db.flush()
        write_audit(
            db,
            workspace_id=workspace_id,
            actor_id=actor.id,
            event="item.unlock",
            target=str(item_id),
            payload={},
        )

    elif action == "transfer":
        # Permission: must be current owner OR manager/admin
        if prior_owner != actor.id and actor.auth_role not in ("manager", "admin"):
            return "FORBIDDEN"

        # Validate new owner is in caller's workspace
        new_owner_row = db.execute(
            text("SELECT 1 FROM app_user WHERE id = :uid AND workspace_id = :wid"),
            {"uid": owner_id, "wid": workspace_id},
        ).first()
        if new_owner_row is None:
            return "FORBIDDEN"

        db.execute(
            text(
                """
                UPDATE items
                   SET cutlist_owner_id = :new_owner,
                       item_locked = true,
                       updated_at = now()
                 WHERE item_id = :iid
                """
            ),
            {"new_owner": owner_id, "iid": item_id},
        )
        db.flush()
        write_audit(
            db,
            workspace_id=workspace_id,
            actor_id=actor.id,
            event="item.lock_transfer",
            target=str(item_id),
            payload={"from": prior_owner, "to": owner_id},
        )

    return "OK"


# ── §L Hard Lock (Q508) ───────────────────────────────────────────────────────


def set_hard_lock(
    db: Session, *, item_id: int, workspace_id: int, actor: AuthUser
) -> str:
    """'OK' | 'NOT_FOUND' | 'FORBIDDEN'.

    Manager/admin only — the "authorised management" Q508's wording names.
    Unlike the Controlled Lock there is nothing to decide: a Hard Lock blocks
    PATCH /items/{id} for everyone, including the current owner, until this
    same authority clears it via `clear_hard_lock`.
    """
    if actor.auth_role not in ("manager", "admin"):
        return "FORBIDDEN"
    current = _item_row(db, item_id=item_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND"

    db.execute(
        text(
            "UPDATE items SET hard_locked_at = now(), hard_locked_by = :a"
            " WHERE item_id = :iid"
        ),
        {"a": actor.id, "iid": item_id},
    )
    db.flush()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor.id,
        event="item.hard_lock", target=str(item_id), payload={},
    )
    return "OK"


def clear_hard_lock(
    db: Session, *, item_id: int, workspace_id: int, actor: AuthUser
) -> str:
    """'OK' | 'NOT_FOUND' | 'FORBIDDEN'."""
    if actor.auth_role not in ("manager", "admin"):
        return "FORBIDDEN"
    current = _item_row(db, item_id=item_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND"

    db.execute(
        text(
            "UPDATE items SET hard_locked_at = NULL, hard_locked_by = NULL"
            " WHERE item_id = :iid"
        ),
        {"iid": item_id},
    )
    db.flush()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor.id,
        event="item.hard_unlock", target=str(item_id), payload={},
    )
    return "OK"


# ── Controlled Lock: requests (B7 / Q509) ─────────────────────────────────────

_LOCK_REQUEST_COLS = """
    r.request_id,
    r.item_id,
    r.requested_by,
    ru.full_name                    AS requested_by_name,
    r.requested_changes,
    r.status,
    r.created_at,
    r.updated_at,
    r.decided_by,
    du.full_name                    AS decided_by_name,
    r.decided_at,
    r.decision_note
"""


def _lock_request_row(db: Session, *, request_id: int, workspace_id: int) -> dict | None:
    """One request, scoped to the caller's workspace through its item's project."""
    row = db.execute(
        text(
            f"""
            SELECT {_LOCK_REQUEST_COLS}, i.cutlist_owner_id
              FROM item_lock_request r
              JOIN items i    ON i.item_id = r.item_id
              JOIN projects p ON p.project_id = i.project_id
              JOIN app_user ru ON ru.id = r.requested_by
         LEFT JOIN app_user du ON du.id = r.decided_by
             WHERE r.request_id = :rid
               AND p.workspace_id = :wid
               AND NOT i.deleted
            """
        ),
        {"rid": request_id, "wid": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def _upsert_lock_request(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    requester_id: int,
    owner_id: int,
    proposed: dict,
) -> dict:
    """Record (or revise) the requester's pending request on this item.

    `uniq_pending_lock_request` makes this an upsert: a second save by the same
    person replaces their own undecided proposal, so the owner always decides
    on the latest version rather than a queue of stale ones.
    """
    rid = db.execute(
        text(
            """
            INSERT INTO item_lock_request (item_id, requested_by, requested_changes)
            VALUES (:iid, :uid, CAST(:changes AS jsonb))
            ON CONFLICT (item_id, requested_by) WHERE status = 'pending'
            DO UPDATE SET requested_changes = EXCLUDED.requested_changes,
                          updated_at = now()
            RETURNING request_id
            """
        ),
        {"iid": item_id, "uid": requester_id, "changes": json.dumps(proposed)},
    ).scalar()
    db.flush()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=requester_id,
        event="item.lock_request.create",
        target=str(item_id),
        payload={
            "request_id": rid,
            "owner_id": owner_id,
            "fields": sorted(proposed),
        },
    )
    return _lock_request_row(db, request_id=rid, workspace_id=workspace_id) or {}


def list_lock_requests(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    status: str | None = None,
) -> list[dict] | None:
    """Requests on an item, newest first.  None if the item is out of workspace."""
    if _item_row(db, item_id=item_id, workspace_id=workspace_id) is None:
        return None
    rows = db.execute(
        text(
            f"""
            SELECT {_LOCK_REQUEST_COLS}
              FROM item_lock_request r
              JOIN app_user ru ON ru.id = r.requested_by
         LEFT JOIN app_user du ON du.id = r.decided_by
             WHERE r.item_id = :iid
               AND (CAST(:status AS varchar) IS NULL OR r.status = :status)
          ORDER BY r.request_id DESC
            """
        ),
        {"iid": item_id, "status": status},
    ).mappings().all()
    return [dict(r) for r in rows]


def decide_lock_request(
    db: Session,
    *,
    request_id: int,
    workspace_id: int,
    actor: AuthUser,
    decision: str,
    note: str | None,
) -> str | dict:
    """Approve or reject a pending request.  decision ∈ {'approved', 'rejected'}.

    Returns 'NOT_FOUND', 'FORBIDDEN', 'ALREADY_DECIDED', or the decided row.

    Who may decide: the current lock owner, or a manager/admin — the same rule
    `claim_or_release_lock` already applies to transferring the lock, since
    both amount to overriding the owner.

    Approval replays the stored body through the ordinary save path, so fields
    the owner has since changed to the requested value are simply no-ops and
    the edit log still credits the requester.
    """
    row = _lock_request_row(db, request_id=request_id, workspace_id=workspace_id)
    if row is None:
        return "NOT_FOUND"
    if row["status"] != "pending":
        return "ALREADY_DECIDED"
    if row["cutlist_owner_id"] != actor.id and actor.auth_role not in ("manager", "admin"):
        return "FORBIDDEN"

    item_id = row["item_id"]
    applied: list[str] = []

    if decision == "approved":
        # §L Q511/Q512: lock the row for the rest of this transaction, same
        # as `patch_item`'s own direct-apply path.
        current = _item_row(
            db, item_id=item_id, workspace_id=workspace_id, for_update=True
        )
        if current is None:          # item deleted between request and decision
            return "NOT_FOUND"
        # §L — Hard Lock / Approval Lock (Q508): a request approved after the
        # item was locked by either mechanism must not slip through — the
        # owner deciding is not the same authority as the one who locked it.
        if current["hard_locked_at"] is not None:
            return "HARD_LOCKED"
        if current["status"] == "APPROVED":
            return "APPROVAL_LOCKED"
        changes = _apply_item_changes(
            db,
            item_id=item_id,
            current=current,
            payload=PatchItemIn(**row["requested_changes"]),
            author_id=row["requested_by"],
        )
        if isinstance(changes, str):
            # The held request named an area or room that no longer resolves —
            # deleted, or renamed out from under it while it waited.
            return changes
        applied = [field for field, _old, _new in changes]

    db.execute(
        text(
            """
            UPDATE item_lock_request
               SET status = :status,
                   decided_by = :actor,
                   decided_at = now(),
                   decision_note = :note,
                   updated_at = now()
             WHERE request_id = :rid
            """
        ),
        {"status": decision, "actor": actor.id, "note": note, "rid": request_id},
    )
    db.flush()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor.id,
        event=f"item.lock_request.{'approve' if decision == 'approved' else 'reject'}",
        target=str(item_id),
        payload={
            "request_id": request_id,
            "requested_by": row["requested_by"],
            "fields": sorted(row["requested_changes"]),
            "applied_fields": applied,
            "note": note,
        },
    )
    return _lock_request_row(db, request_id=request_id, workspace_id=workspace_id) or {}
