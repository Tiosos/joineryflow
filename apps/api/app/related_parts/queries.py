"""Related-part query layer.

A related part is a row in `items` with `row_type = 'related_part'` (Q447), so
most of its invariants are already enforced by `0028`'s constraints. This layer
exists for the ones a CHECK cannot express, and to turn the rest into clean
409s rather than raw constraint violations:

* **Q449** — one level only. `0028`'s composite FK against `(item_id, row_type)`
  makes a related part an illegal parent; this layer says so with a code.
* **Q450** — a related part carries its **own** status, so `status` is an
  ordinary editable field here and is never copied from the parent.
* **Q419** — **no `item_stages` rows are ever created.** That is enforced by
  absence: nothing in this module writes to `item_stages`, and B1 keeps related
  parts out of every Shop Floor surface. Do not "fix" it by seeding stages.
* **Q452** — reparenting moves `group_id` to the new parent's number **and**
  re-points every linked supplier order's CUTLIST NO. through B6's
  `sync_orders_for_item`, which is what "Q431-style order reference updates"
  meant.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..edit_log import write_edit_log
from ..orders.queries import sync_orders_for_item
from .schemas import CreateRelatedPartIn, PatchRelatedPartIn

_PART_COLS = """
    i.item_id,
    i.num                       AS item_number,
    i.parent_item_id,
    parent.num                  AS parent_item_number,
    i.group_id,
    i.related_part_type_key,
    rpt.label                   AS related_part_type_label,
    i.description,
    i.qty,
    i.status,
    i.project_id,
    i.created_at,
    i.updated_at
"""

_PART_FROM = """
    FROM items i
    JOIN items parent ON parent.item_id = i.parent_item_id
    LEFT JOIN related_part_type rpt ON rpt.type_key = i.related_part_type_key
"""


def list_types(db: Session) -> list[dict]:
    """Q448 — a configurable lookup, not a frozen list."""
    rows = db.execute(
        text(
            # `0028` created this lookup with no archive column — unlike
            # `order_category`, which `0031` gave one. Nothing is filtered out.
            "SELECT type_key, label FROM related_part_type"
            " ORDER BY sort_order, type_key"
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def _parent_row(db: Session, *, item_id: int, workspace_id: int) -> dict | None:
    """The prospective parent. Returns its row_type so the caller can refuse a
    related part as a parent (Q449) with a clearer error than the FK gives."""
    row = db.execute(
        text(
            """
            SELECT i.item_id, i.num, i.project_id, i.row_type
            FROM items i
            JOIN projects p ON p.project_id = i.project_id
            WHERE i.item_id = :i AND p.workspace_id = :w
            """
        ),
        {"i": item_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def get_related_part(
    db: Session, *, item_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            f"""
            SELECT {_PART_COLS} {_PART_FROM}
            JOIN projects p ON p.project_id = i.project_id
            WHERE i.item_id = :i AND p.workspace_id = :w
              AND i.row_type = 'related_part'
            """
        ),
        {"i": item_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def list_for_parent(
    db: Session, *, parent_item_id: int, workspace_id: int
) -> list[dict] | None:
    parent = _parent_row(db, item_id=parent_item_id, workspace_id=workspace_id)
    if parent is None:
        return None
    rows = db.execute(
        text(
            f"""
            SELECT {_PART_COLS} {_PART_FROM}
            WHERE i.parent_item_id = :p AND i.row_type = 'related_part'
            ORDER BY COALESCE(i.num, CAST(i.item_id AS integer))
            """
        ),
        {"p": parent_item_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def create_related_part(
    db: Session,
    *,
    parent_item_id: int,
    workspace_id: int,
    payload: CreateRelatedPartIn,
    actor_id: int,
) -> tuple[str, dict | None]:
    """('OK', part) | ('PARENT_NOT_FOUND'|'PARENT_IS_RELATED_PART'|'UNKNOWN_TYPE', None)."""
    parent = _parent_row(db, item_id=parent_item_id, workspace_id=workspace_id)
    if parent is None:
        return "PARENT_NOT_FOUND", None
    if parent["row_type"] != "joinery_item":
        # Q449: one level only. 0028's composite FK would also refuse this, but
        # as an opaque constraint violation.
        return "PARENT_IS_RELATED_PART", None

    known = db.execute(
        text("SELECT 1 FROM related_part_type WHERE type_key = :k"),
        {"k": payload.related_part_type_key},
    ).first()
    if known is None:
        return "UNKNOWN_TYPE", None

    item_id = db.execute(
        text(
            """
            INSERT INTO items (
                num, project_id, description, qty, status,
                row_type, parent_item_id, related_part_type_key, group_id
            )
            VALUES (
                nextval('joinery_number_seq'), :proj, :descr, :qty,
                COALESCE(:status, 'CLEAR'),
                'related_part', :parent, :type_key,
                -- Q416/Q453: a related part shares its PARENT's Group ID.
                :group_id
            )
            RETURNING item_id
            """
        ),
        {
            "proj": parent["project_id"], "descr": payload.description,
            "qty": payload.qty, "status": payload.status,
            "parent": parent_item_id, "type_key": payload.related_part_type_key,
            "group_id": str(parent["num"]) if parent["num"] is not None else None,
        },
    ).scalar()
    db.flush()

    # Q419: deliberately no item_stages rows. See the module docstring.
    write_edit_log(
        db, item_id=item_id, actor_id=actor_id,
        field="_create", old_value=None,
        new_value=f"related part ({payload.related_part_type_key}) under item {parent_item_id}",
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="related_part.create", target=str(item_id),
        payload={
            "parent_item_id": parent_item_id,
            "type": payload.related_part_type_key,
            "project_id": parent["project_id"],
        },
    )
    return "OK", get_related_part(db, item_id=item_id, workspace_id=workspace_id)


def patch_related_part(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    payload: PatchRelatedPartIn,
    actor_id: int,
) -> tuple[str, dict | None]:
    """('OK', part) | ('NOT_FOUND'|'UNKNOWN_TYPE', None)."""
    current = get_related_part(db, item_id=item_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND", None

    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return "OK", current

    if "related_part_type_key" in fields and fields["related_part_type_key"] is not None:
        known = db.execute(
            text("SELECT 1 FROM related_part_type WHERE type_key = :k"),
            {"k": fields["related_part_type_key"]},
        ).first()
        if known is None:
            return "UNKNOWN_TYPE", None

    # Column names match the payload keys one-for-one here; `status` is an
    # ordinary field because Q450 gives a related part its own.
    sets, params = [], {"i": item_id}
    for n, (col, val) in enumerate(fields.items()):
        sets.append(f"{col} = :v{n}")
        params[f"v{n}"] = val
    db.execute(
        text(f"UPDATE items SET {', '.join(sets)}, updated_at = now() WHERE item_id = :i"),
        params,
    )
    db.flush()

    for col, val in fields.items():
        write_edit_log(
            db, item_id=item_id, actor_id=actor_id, field=col,
            old_value=None if current.get(col) is None else str(current[col]),
            new_value=None if val is None else str(val),
        )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="related_part.update", target=str(item_id),
        payload={"fields": sorted(fields)},
    )
    return "OK", get_related_part(db, item_id=item_id, workspace_id=workspace_id)


def reparent(
    db: Session,
    *,
    item_id: int,
    new_parent_item_id: int,
    workspace_id: int,
    actor_id: int,
) -> tuple[str, dict | None]:
    """Q452 — move a related part to another Joinery Item.

    Three things move together, which is why this is not a plain PATCH:
      1. `parent_item_id`
      2. `group_id`, to the new parent's Item ID (Q416/Q453)
      3. every linked supplier order's CUTLIST NO., via B6's sync — the
         "Q431-style order reference updates" Q452 asks for

    Codes: OK | NOT_FOUND | PARENT_NOT_FOUND | PARENT_IS_RELATED_PART |
           CROSS_PROJECT | SAME_PARENT
    """
    current = get_related_part(db, item_id=item_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND", None
    if current["parent_item_id"] == new_parent_item_id:
        return "SAME_PARENT", None

    new_parent = _parent_row(db, item_id=new_parent_item_id, workspace_id=workspace_id)
    if new_parent is None:
        return "PARENT_NOT_FOUND", None
    if new_parent["row_type"] != "joinery_item":
        return "PARENT_IS_RELATED_PART", None
    if new_parent["project_id"] != current["project_id"]:
        # Nothing in Plan V1 contemplates a related part crossing projects, and
        # its order already carries the old project's name and location.
        return "CROSS_PROJECT", None

    old_parent_id = current["parent_item_id"]
    old_group_id = current["group_id"]
    new_group_id = str(new_parent["num"]) if new_parent["num"] is not None else None

    db.execute(
        text(
            """
            UPDATE items
               SET parent_item_id = :p, group_id = :g, updated_at = now()
             WHERE item_id = :i
            """
        ),
        {"p": new_parent_item_id, "g": new_group_id, "i": item_id},
    )
    db.flush()

    # Q452 -> Q431: the order's reference follows the new parent's cutlist.
    synced = sync_orders_for_item(
        db, item_id=new_parent_item_id, workspace_id=workspace_id, actor_id=actor_id
    )

    write_edit_log(
        db, item_id=item_id, actor_id=actor_id, field="parent_item_id",
        old_value=str(old_parent_id), new_value=str(new_parent_item_id),
    )
    write_edit_log(
        db, item_id=item_id, actor_id=actor_id, field="group_id",
        old_value=old_group_id, new_value=new_group_id,
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="related_part.reparent", target=str(item_id),
        payload={
            "old_parent_item_id": old_parent_id,
            "new_parent_item_id": new_parent_item_id,
            "old_group_id": old_group_id,
            "new_group_id": new_group_id,
            "orders_synced": [o["po_id"] for o in synced],
        },
    )
    return "OK", get_related_part(db, item_id=item_id, workspace_id=workspace_id)


def delete_related_part(
    db: Session, *, item_id: int, workspace_id: int, actor_id: int
) -> str:
    """'OK' | 'NOT_FOUND'.

    A hard delete: unlike a Joinery Item, a related part has no cutlist, no
    stages and no production history to preserve. `purchase_orders.item_id` is
    ON DELETE SET NULL (`0029`), so an issued order survives the row it was
    raised for, which is what an order already sent to a supplier requires.
    """
    current = get_related_part(db, item_id=item_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND"

    orders = db.execute(
        text("SELECT po_id FROM purchase_orders WHERE item_id = :i"), {"i": item_id}
    ).scalars().all()

    db.execute(text("DELETE FROM items WHERE item_id = :i"), {"i": item_id})
    db.flush()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="related_part.delete", target=str(item_id),
        payload={
            "parent_item_id": current["parent_item_id"],
            "type": current["related_part_type_key"],
            "orphaned_order_ids": list(orders),
        },
    )
    return "OK"
