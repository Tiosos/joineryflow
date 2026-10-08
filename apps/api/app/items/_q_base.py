"""Shared item helpers: workspace filter, `_item_row`, patch-field mapping and `_apply_item_changes`.

Part of the items queries facade (see `queries.py`)."""

from sqlalchemy import text
from sqlalchemy.orm import Session
import json
from ..concurrency import bump_field_versions
from ..edit_log import write_edit_log_many
from ..row_types import live_joinery_items
from ..row_types import not_deleted
from .schemas import PatchItemIn


# The drafter editor and the availability drawer are cutlist surfaces: neither
# means anything for a related part (Q417/Q447), so both 404 on its id.  The
# Tracking LIST is deliberately different — it returns related parts inline,
# nested under their parent (Q420/Q422) — and so carries no filter.
_JOINERY_I = live_joinery_items("i")


# Status keys writable by /status and /bulk-status endpoints (matches PatchItemStatusIn).
_VALID_STATUS_KEYS = frozenset({"CLEAR", "VOID", "NOTE!", "LIVE", "APPROVED", "HOLD"})


# Workspace isolation clause (items -> projects.workspace_id direct FK, since 0014).
_WORKSPACE_FILTER = """
    EXISTS (
        SELECT 1 FROM projects p2
        WHERE p2.project_id = i.project_id
          AND p2.workspace_id = :wid
    )
"""


# ── Write helpers (T15) ────────────────────────────────────────────────────────


def _project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    """Return True if the project belongs to workspace_id (direct FK, since 0014)."""
    row = db.execute(
        text(
            """
            SELECT 1 FROM projects p
            WHERE p.project_id = :pid AND p.workspace_id = :wid
            """
        ),
        {"pid": project_id, "wid": workspace_id},
    ).first()
    return row is not None


def _item_row(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    for_update: bool = False,
    include_deleted: bool = False,
) -> dict | None:
    """Fetch bare item columns for mutation helpers.  Returns None if 404.

    Deliberately **not** filtered to Joinery Items: the related-part routes
    (Q450 own status, Q452 reparent) reach their rows through this helper.
    It returns `row_type` so each caller can decide — see `patch_lifecycle`
    and `claim_or_release_lock`, which refuse related parts.

    `for_update=True` (§L Q511/Q512) locks the row for the rest of the
    caller's transaction, so a concurrent PATCH on the same item serialises
    instead of racing on the read-then-write field-version check — the same
    shape `_lock_order_for_update` / `lock_revision_for_update` already use
    elsewhere in this codebase. Only the write paths (`patch_item`,
    `decide_lock_request`'s approval) pass it; plain reads leave it False so
    a GET never takes a row lock.

    A soft-deleted item answers None like a missing one; only `restore_item` passes
    `include_deleted=True`.
    """
    row = db.execute(
        text(
            f"""
            SELECT
                i.item_id,
                i.row_type,
                i.project_id,
                i.status,
                i.description,
                i.qty,
                i.stage,
                i.code,
                i.level,
                i.rm_no,
                i.rm_desc,
                i.zone,
                i.estimator_notes,
                i.painting_req,
                i.solid_surface_req,
                i.item_locked,
                i.cutlist_owner_id,
                i.area_id,
                i.room_id,
                i.jid_code,
                i.jid_color,
                i.var_boq,
                i.contractor_id,
                i.total_amount,
                i.site_measure_notes,
                i.floor_plan,
                i.rls,
                i.joiery_details,
                i.cutlist_printed,
                i.hard_locked_at,
                i.hard_locked_by,
                i.field_versions
            FROM items i
            WHERE i.item_id = :iid
              AND {_WORKSPACE_FILTER}
              {"" if include_deleted else "AND " + not_deleted("i")}
            {"FOR UPDATE OF i" if for_update else ""}
            """
        ),
        {"iid": item_id, "wid": workspace_id},
    ).mappings().first()
    return dict(row) if row is not None else None


def _user_in_workspace(db: Session, *, user_id: int, workspace_id: int) -> bool:
    """Return True if app_user belongs to the workspace.  Guards contractor_id writes."""
    row = db.execute(
        text("SELECT 1 FROM app_user WHERE id = :uid AND workspace_id = :wid"),
        {"uid": user_id, "wid": workspace_id},
    ).first()
    return row is not None


# Field map: PatchItemIn attribute -> (DB column, old_value_key_in_row)
_PATCH_FIELD_MAP: list[tuple[str, str, str]] = [
    ("description",          "description",     "description"),
    ("qty",                  "qty",             "qty"),
    ("stage",                "stage",           "stage"),
    ("code",                 "code",            "code"),
    ("level",                "level",           "level"),
    ("room_no",              "rm_no",           "rm_no"),
    ("room_desc",            "rm_desc",         "rm_desc"),
    ("zone",                 "zone",            "zone"),
    ("estimator_notes",      "estimator_notes", "estimator_notes"),
    ("painting_required",    "painting_req",    "painting_req"),
    ("solid_surface_required","solid_surface_req","solid_surface_req"),
    # Tracking 2.0 enrichment (#10) — contractor_id is validated in patch_item()
    ("jid_code",             "jid_code",          "jid_code"),
    ("jid_color",            "jid_color",         "jid_color"),
    ("var_boq",              "var_boq",           "var_boq"),
    ("contractor_id",        "contractor_id",     "contractor_id"),
    ("total_amount",         "total_amount",      "total_amount"),
    ("site_measure_notes",   "site_measure_notes","site_measure_notes"),
    # Item & Project Detail 2.0 — pre-existing columns made writable
    ("floor_plan",           "floor_plan",        "floor_plan"),
    ("rls",                  "rls",               "rls"),
    ("joiery_details",       "joiery_details",    "joiery_details"),
    ("cutlist_printed",      "cutlist_printed",   "cutlist_printed"),
]


def _resolve_area_room(
    db: Session,
    *,
    current: dict,
    payload: PatchItemIn,
) -> tuple[str, dict[str, object], list[tuple[str, str | None, str | None]]]:
    """Turn `area_id` / `room_id` into column writes, or explain the refusal.

    Returns ('OK', updates, changes) | ('BAD_AREA'|'BAD_ROOM'|'ROOM_WITHOUT_AREA', {}, []).

    Two things make this more than an assignment:

    * **The legacy columns keep being written.** `items.stage` / `rm_no` /
      `rm_desc` stay populated until a later migration drops them (Q435), and
      25 read sites across printing, orders, cutlists and Tracking still read
      them. Picking an area writes its name into `stage`; picking a room writes
      its `rm_no` / `rm_desc`. Nothing downstream has to know this shipped.
    * **Room is nested under Area** (Q552), enforced by the composite FK
      `items (area_id, room_id) → room`. Setting a room therefore needs an area
      that actually owns it — validated here, so the caller gets a 409 naming
      the problem rather than a raw constraint violation as a 500.
    """
    if payload.area_id is None and payload.room_id is None:
        return "OK", {}, []

    updates: dict[str, object] = {}
    changes: list[tuple[str, str | None, str | None]] = []

    # The area an item will be in after this patch: the one supplied, else the
    # one it already holds.
    area_id = payload.area_id if payload.area_id is not None else current["area_id"]
    if payload.room_id is not None and area_id is None:
        return "ROOM_WITHOUT_AREA", {}, []

    if payload.area_id is not None and payload.area_id != current["area_id"]:
        area = db.execute(
            text("SELECT area_id, name FROM area WHERE area_id = :a AND project_id = :p"),
            {"a": payload.area_id, "p": current["project_id"]},
        ).mappings().first()
        if area is None:
            return "BAD_AREA", {}, []
        updates["area_id"] = area["area_id"]
        updates["stage"] = area["name"]
        changes.append(("area", current["stage"], area["name"]))
        # Moving area orphans the old room — it belonged to the area left
        # behind, and the composite FK would refuse the pair. Cleared unless
        # this same patch names a new one.
        if payload.room_id is None and current["room_id"] is not None:
            updates["room_id"] = None
            updates["rm_no"] = None
            updates["rm_desc"] = None
            changes.append(("room", _room_label(current["rm_no"], current["rm_desc"]), None))

    if payload.room_id is not None and payload.room_id != current["room_id"]:
        room = db.execute(
            text("SELECT room_id, area_id, rm_no, rm_desc FROM room"
                 " WHERE room_id = :r AND area_id = :a"),
            {"r": payload.room_id, "a": area_id},
        ).mappings().first()
        if room is None:
            return "BAD_ROOM", {}, []
        updates["room_id"] = room["room_id"]
        updates["rm_no"] = room["rm_no"]
        updates["rm_desc"] = room["rm_desc"]
        # Q458: moving room is allowed and audited. `item_edit_log` already
        # records field changes, so the move rides the existing mechanism.
        changes.append((
            "room",
            _room_label(current["rm_no"], current["rm_desc"]),
            _room_label(room["rm_no"], room["rm_desc"]),
        ))

    return "OK", updates, changes


def _room_label(rm_no: str | None, rm_desc: str | None) -> str | None:
    """How a room reads in the edit log — the number plus its description."""
    if rm_no is None and rm_desc is None:
        return None
    return " · ".join(p for p in (rm_no, rm_desc) if p)


def _apply_item_changes(
    db: Session,
    *,
    item_id: int,
    current: dict,
    payload: PatchItemIn,
    author_id: int,
    extra_updates: dict[str, object] | None = None,
) -> list[tuple[str, str | None, str | None]] | str:
    """Write the fields of `payload` that actually differ from `current`.

    Shared by the owner's own save and by the approval of someone else's
    Controlled-Lock request, so an approved request lands exactly as a direct
    save would.  `author_id` is who gets credited in `item_edit_log` — the
    person whose change it is, which on an approval is the *requester*, not the
    approver (the approver is named in the audit row instead).

    Returns the (field, old, new) tuples it logged, or a refusal **code**
    string when the payload's area/room pair cannot be resolved.
    """
    updates: dict[str, object] = dict(extra_updates or {})
    changes: list[tuple[str, str | None, str | None]] = []

    # Area/Room first: they write three legacy columns between them, and the
    # generic loop below must not then overwrite `stage` / `rm_no` / `rm_desc`
    # with stale free text from the same payload.
    outcome, ar_updates, ar_changes = _resolve_area_room(
        db, current=current, payload=payload
    )
    if outcome != "OK":
        return outcome
    updates.update(ar_updates)
    changes.extend(ar_changes)
    _moved = {"stage", "rm_no", "rm_desc"} & set(ar_updates)

    for attr, col, row_key in _PATCH_FIELD_MAP:
        if col in _moved:
            continue
        new_val = getattr(payload, attr)
        if new_val is None:
            continue
        old_val = current.get(row_key)
        if new_val != old_val:
            updates[col] = new_val
            changes.append((attr, None if old_val is None else str(old_val), str(new_val)))

    if changes:
        # §L Q511/Q512: bump the touched fields' versions in the SAME UPDATE
        # as the rest of the write, not a second round trip. Area/Room log
        # under the labels "area"/"room" (see `_resolve_area_room`), which
        # `_VERSION_KEY_BY_LABEL` maps back to the `expected_versions` keys
        # a caller actually uses (`area_id`/`room_id`).
        version_fields = [_VERSION_KEY_BY_LABEL.get(label, label) for label, _o, _n in changes]
        updates["field_versions"] = bump_field_versions(
            current.get("field_versions"), version_fields
        )

    if updates:
        set_clauses = ", ".join(
            f"{col} = CAST(:{col} AS jsonb)" if col == "field_versions" else f"{col} = :{col}"
            for col in updates
        )
        params = {
            "iid": item_id,
            **{
                k: (json.dumps(v) if k == "field_versions" else v)
                for k, v in updates.items()
            },
        }
        db.execute(
            text(f"UPDATE items SET {set_clauses}, updated_at = now() WHERE item_id = :iid"),
            params,
        )
        db.flush()

    if changes:
        write_edit_log_many(db, item_id=item_id, actor_id=author_id, changes=changes)

    return changes


# Edit-log labels that don't match the payload attribute name used for
# `expected_versions` — area_id/room_id resolve through _resolve_area_room
# and log as "area"/"room", but callers version them as "area_id"/"room_id".
_VERSION_KEY_BY_LABEL = {"area": "area_id", "room": "room_id"}


def _changed_fields(payload: PatchItemIn, current: dict) -> dict[str, object]:
    """The submitted fields that would actually change `current`, as a jsonb body."""
    out: dict[str, object] = {}
    for attr, _col, row_key in _PATCH_FIELD_MAP:
        new_val = getattr(payload, attr)
        if new_val is None:
            continue
        if new_val != current.get(row_key):
            out[attr] = new_val
    # Area and Room are not in the field map — they resolve to three columns
    # between them — but a held Controlled-Lock request has to carry them or
    # approving it would silently drop the move.
    for attr in ("area_id", "room_id"):
        new_val = getattr(payload, attr)
        if new_val is not None and new_val != current.get(attr):
            out[attr] = new_val
    return out
