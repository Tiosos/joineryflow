"""QC module query layer: defects, checklist, rework (Q515-517).

Routes own the transaction boundary (db.commit). Queries flush only.
Every mutation writes audit_log and item_edit_log in the caller's
transaction, per the PM Workbench invariant.

Joinery Items only (the item_documents precedent) — a related part gets
NotFound, the same as a foreign/unknown item_id.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..edit_log import write_edit_log
from ..row_types import joinery_items_only

_JOINERY_ITEM = joinery_items_only("i")


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def _item_in_workspace(db: Session, *, item_id: int, workspace_id: int) -> bool:
    return db.execute(
        text(
            f"""
            SELECT 1 FROM items i
              JOIN projects p ON p.project_id = i.project_id
             WHERE i.item_id = :i AND p.workspace_id = :w
               AND {_JOINERY_ITEM}
            """
        ),
        {"i": item_id, "w": workspace_id},
    ).first() is not None


def _log(db: Session, *, workspace_id: int, actor_id: int, item_id: int,
         event: str, payload: dict, field: str,
         old: str | None, new: str | None) -> None:
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event=event,
                target=str(item_id), payload=payload)
    write_edit_log(db, item_id=item_id, actor_id=actor_id, field=field,
                   old_value=old, new_value=new)


# ============================================================================
# Defects
# ============================================================================

_DEFECT_COLS = """
    d.defect_id, d.item_id, d.stage_key, d.description, d.status,
    d.resolved_note, d.resolved_by, ru.full_name AS resolved_by_name,
    d.resolved_at, d.created_by, cu.full_name AS created_by_name,
    d.created_at, d.updated_at
"""

_DEFECT_JOINS = """
    LEFT JOIN app_user cu ON cu.id = d.created_by
    LEFT JOIN app_user ru ON ru.id = d.resolved_by
"""


def _defect(db: Session, *, defect_id: int, workspace_id: int) -> dict:
    row = db.execute(
        text(
            f"""
            SELECT {_DEFECT_COLS}
              FROM qc_defect d
              {_DEFECT_JOINS}
              JOIN items i ON i.item_id = d.item_id
              JOIN projects p ON p.project_id = i.project_id
             WHERE d.defect_id = :d AND p.workspace_id = :w
               AND {_JOINERY_ITEM}
            """
        ),
        {"d": defect_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        raise NotFound("defect not found")
    return dict(row)


def list_defects(db: Session, *, item_id: int, workspace_id: int) -> list[dict]:
    if not _item_in_workspace(db, item_id=item_id, workspace_id=workspace_id):
        raise NotFound("item not found")
    rows = db.execute(
        text(
            f"""
            SELECT {_DEFECT_COLS}
              FROM qc_defect d
              {_DEFECT_JOINS}
             WHERE d.item_id = :i
             ORDER BY d.created_at DESC
            """
        ),
        {"i": item_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def create_defect(
    db: Session, *, item_id: int, workspace_id: int, actor_id: int,
    stage_key: str | None, description: str,
) -> dict:
    if not _item_in_workspace(db, item_id=item_id, workspace_id=workspace_id):
        raise NotFound("item not found")
    did = db.execute(
        text(
            """
            INSERT INTO qc_defect(item_id, stage_key, description, created_by)
            VALUES (:i, :s, :d, :a)
            RETURNING defect_id
            """
        ),
        {"i": item_id, "s": stage_key, "d": description, "a": actor_id},
    ).scalar()
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=item_id,
         event="qc.defect.create", payload={"defect_id": did, "stage_key": stage_key},
         field="_qc_defect_create", old=None, new=description)
    db.flush()
    return _defect(db, defect_id=did, workspace_id=workspace_id)


def patch_defect(
    db: Session, *, defect_id: int, workspace_id: int, actor_id: int, changes: dict,
) -> dict:
    current = _defect(db, defect_id=defect_id, workspace_id=workspace_id)
    if current["status"] != "open":
        raise Conflict("DEFECT_NOT_OPEN")
    diff = {k: v for k, v in changes.items() if current[k] != v}
    if not diff:
        return current

    sets = ", ".join(f"{k} = :{k}" for k in diff)
    db.execute(
        text(f"UPDATE qc_defect SET {sets}, updated_at = now() WHERE defect_id = :d"),
        {**diff, "d": defect_id},
    )
    for k, v in diff.items():
        write_audit(db, workspace_id=workspace_id, actor_id=actor_id,
                    event="qc.defect.update", target=str(current["item_id"]),
                    payload={"defect_id": defect_id, "field": k, "before": current[k], "after": v})
        write_edit_log(db, item_id=current["item_id"], actor_id=actor_id,
                       field=f"qc_defect.{defect_id}.{k}",
                       old_value=None if current[k] is None else str(current[k]),
                       new_value=None if v is None else str(v))
    db.flush()
    return _defect(db, defect_id=defect_id, workspace_id=workspace_id)


def resolve_defect(
    db: Session, *, defect_id: int, workspace_id: int, actor_id: int,
    resolved_note: str | None,
) -> dict:
    current = _defect(db, defect_id=defect_id, workspace_id=workspace_id)
    if current["status"] != "open":
        raise Conflict("DEFECT_NOT_OPEN")
    db.execute(
        text(
            """
            UPDATE qc_defect
               SET status = 'resolved', resolved_note = :n,
                   resolved_by = :a, resolved_at = now(), updated_at = now()
             WHERE defect_id = :d
            """
        ),
        {"n": resolved_note, "a": actor_id, "d": defect_id},
    )
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=current["item_id"],
         event="qc.defect.resolve", payload={"defect_id": defect_id},
         field=f"qc_defect.{defect_id}.status", old="open", new="resolved")
    db.flush()
    return _defect(db, defect_id=defect_id, workspace_id=workspace_id)


# ============================================================================
# Checklist
# ============================================================================

_CHECKLIST_COLS = """
    c.checklist_item_id, c.item_id, c.label, c.is_checked,
    c.checked_by, ku.full_name AS checked_by_name, c.checked_at,
    c.sort_order, c.created_by, c.created_at
"""

_CHECKLIST_JOINS = """
    LEFT JOIN app_user ku ON ku.id = c.checked_by
"""


def _checklist_item(db: Session, *, checklist_item_id: int, workspace_id: int) -> dict:
    row = db.execute(
        text(
            f"""
            SELECT {_CHECKLIST_COLS}
              FROM qc_checklist_item c
              {_CHECKLIST_JOINS}
              JOIN items i ON i.item_id = c.item_id
              JOIN projects p ON p.project_id = i.project_id
             WHERE c.checklist_item_id = :c AND p.workspace_id = :w
               AND {_JOINERY_ITEM}
            """
        ),
        {"c": checklist_item_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        raise NotFound("checklist item not found")
    return dict(row)


def list_checklist(db: Session, *, item_id: int, workspace_id: int) -> list[dict]:
    if not _item_in_workspace(db, item_id=item_id, workspace_id=workspace_id):
        raise NotFound("item not found")
    rows = db.execute(
        text(
            f"""
            SELECT {_CHECKLIST_COLS}
              FROM qc_checklist_item c
              {_CHECKLIST_JOINS}
             WHERE c.item_id = :i
             ORDER BY c.sort_order, c.checklist_item_id
            """
        ),
        {"i": item_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def create_checklist_item(
    db: Session, *, item_id: int, workspace_id: int, actor_id: int,
    label: str, sort_order: int,
) -> dict:
    if not _item_in_workspace(db, item_id=item_id, workspace_id=workspace_id):
        raise NotFound("item not found")
    cid = db.execute(
        text(
            """
            INSERT INTO qc_checklist_item(item_id, label, sort_order, created_by)
            VALUES (:i, :l, :s, :a)
            RETURNING checklist_item_id
            """
        ),
        {"i": item_id, "l": label, "s": sort_order, "a": actor_id},
    ).scalar()
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=item_id,
         event="qc.checklist.add", payload={"checklist_item_id": cid},
         field="_qc_checklist_add", old=None, new=label)
    db.flush()
    return _checklist_item(db, checklist_item_id=cid, workspace_id=workspace_id)


def patch_checklist_item(
    db: Session, *, checklist_item_id: int, workspace_id: int, actor_id: int,
    changes: dict,
) -> dict:
    current = _checklist_item(db, checklist_item_id=checklist_item_id, workspace_id=workspace_id)
    diff = {k: v for k, v in changes.items() if current[k] != v}
    if not diff:
        return current

    params: dict = {"c": checklist_item_id, **diff}
    set_clauses = [f"{k} = :{k}" for k in diff]
    if "is_checked" in diff:
        params["checked_by"] = actor_id if diff["is_checked"] else None
        set_clauses.append("checked_by = :checked_by")
        set_clauses.append("checked_at = " + ("now()" if diff["is_checked"] else "NULL"))

    db.execute(
        text(f"UPDATE qc_checklist_item SET {', '.join(set_clauses)} WHERE checklist_item_id = :c"),
        params,
    )
    event = "qc.checklist.check" if diff.get("is_checked") else (
        "qc.checklist.uncheck" if "is_checked" in diff else "qc.checklist.update"
    )
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event=event,
                target=str(current["item_id"]),
                payload={"checklist_item_id": checklist_item_id,
                         "before": {k: current[k] for k in diff}, "after": diff})
    for k, v in diff.items():
        write_edit_log(db, item_id=current["item_id"], actor_id=actor_id,
                       field=f"qc_checklist.{checklist_item_id}.{k}",
                       old_value=None if current[k] is None else str(current[k]),
                       new_value=None if v is None else str(v))
    db.flush()
    return _checklist_item(db, checklist_item_id=checklist_item_id, workspace_id=workspace_id)


def delete_checklist_item(
    db: Session, *, checklist_item_id: int, workspace_id: int, actor_id: int,
) -> None:
    current = _checklist_item(db, checklist_item_id=checklist_item_id, workspace_id=workspace_id)
    db.execute(text("DELETE FROM qc_checklist_item WHERE checklist_item_id = :c"),
               {"c": checklist_item_id})
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=current["item_id"],
         event="qc.checklist.remove", payload={"checklist_item_id": checklist_item_id},
         field="_qc_checklist_remove", old=current["label"], new=None)
    db.flush()


# ============================================================================
# Rework
# ============================================================================

_REWORK_COLS = """
    r.rework_id, r.item_id, r.kind, r.cause, r.scope, r.responsibility, r.cost,
    r.status, r.closed_note, r.closed_by, clu.full_name AS closed_by_name,
    r.closed_at, r.created_by, cru.full_name AS created_by_name,
    r.created_at, r.updated_at
"""

_REWORK_JOINS = """
    LEFT JOIN app_user cru ON cru.id = r.created_by
    LEFT JOIN app_user clu ON clu.id = r.closed_by
"""


def _rework(db: Session, *, rework_id: int, workspace_id: int) -> dict:
    row = db.execute(
        text(
            f"""
            SELECT {_REWORK_COLS}
              FROM rework r
              {_REWORK_JOINS}
              JOIN items i ON i.item_id = r.item_id
              JOIN projects p ON p.project_id = i.project_id
             WHERE r.rework_id = :r AND p.workspace_id = :w
               AND {_JOINERY_ITEM}
            """
        ),
        {"r": rework_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        raise NotFound("rework not found")
    return dict(row)


def list_rework(db: Session, *, item_id: int, workspace_id: int) -> list[dict]:
    if not _item_in_workspace(db, item_id=item_id, workspace_id=workspace_id):
        raise NotFound("item not found")
    rows = db.execute(
        text(
            f"""
            SELECT {_REWORK_COLS}
              FROM rework r
              {_REWORK_JOINS}
             WHERE r.item_id = :i
             ORDER BY r.created_at DESC
            """
        ),
        {"i": item_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def create_rework(
    db: Session, *, item_id: int, workspace_id: int, actor_id: int,
    kind: str, cause: str, scope: str, responsibility: str | None, cost,
) -> dict:
    if not _item_in_workspace(db, item_id=item_id, workspace_id=workspace_id):
        raise NotFound("item not found")
    rid = db.execute(
        text(
            """
            INSERT INTO rework(item_id, kind, cause, scope, responsibility, cost, created_by)
            VALUES (:i, :k, :c, :s, :r, :co, :a)
            RETURNING rework_id
            """
        ),
        {"i": item_id, "k": kind, "c": cause, "s": scope, "r": responsibility,
         "co": cost, "a": actor_id},
    ).scalar()
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=item_id,
         event="qc.rework.create", payload={"rework_id": rid, "kind": kind},
         field="_qc_rework_create", old=None, new=f"{kind}: {cause}")
    db.flush()
    return _rework(db, rework_id=rid, workspace_id=workspace_id)


def patch_rework(
    db: Session, *, rework_id: int, workspace_id: int, actor_id: int, changes: dict,
) -> dict:
    current = _rework(db, rework_id=rework_id, workspace_id=workspace_id)
    if current["status"] != "open":
        raise Conflict("REWORK_NOT_OPEN")
    diff = {k: v for k, v in changes.items() if current[k] != v}
    if not diff:
        return current

    sets = ", ".join(f"{k} = :{k}" for k in diff)
    db.execute(
        text(f"UPDATE rework SET {sets}, updated_at = now() WHERE rework_id = :r"),
        {**diff, "r": rework_id},
    )
    for k, v in diff.items():
        write_audit(db, workspace_id=workspace_id, actor_id=actor_id,
                    event="qc.rework.update", target=str(current["item_id"]),
                    payload={"rework_id": rework_id, "field": k, "before": current[k], "after": v})
        write_edit_log(db, item_id=current["item_id"], actor_id=actor_id,
                       field=f"qc_rework.{rework_id}.{k}",
                       old_value=None if current[k] is None else str(current[k]),
                       new_value=None if v is None else str(v))
    db.flush()
    return _rework(db, rework_id=rework_id, workspace_id=workspace_id)


def close_rework(
    db: Session, *, rework_id: int, workspace_id: int, actor_id: int,
    closed_note: str | None,
) -> dict:
    current = _rework(db, rework_id=rework_id, workspace_id=workspace_id)
    if current["status"] != "open":
        raise Conflict("REWORK_NOT_OPEN")
    db.execute(
        text(
            """
            UPDATE rework
               SET status = 'closed', closed_note = :n,
                   closed_by = :a, closed_at = now(), updated_at = now()
             WHERE rework_id = :r
            """
        ),
        {"n": closed_note, "a": actor_id, "r": rework_id},
    )
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=current["item_id"],
         event="qc.rework.close", payload={"rework_id": rework_id},
         field=f"qc_rework.{rework_id}.status", old="open", new="closed")
    db.flush()
    return _rework(db, rework_id=rework_id, workspace_id=workspace_id)
