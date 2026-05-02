"""SQL query functions for the parts module (modules + parts CRUD).

Workspace scoping chain:
  modules -> items.project_id -> projects.workspace_id  (direct FK, since 0014)
  parts   -> modules.item_id  -> items.project_id -> projects.workspace_id

All mutations write to both audit_log and item_edit_log.
item_edit_log.item_id is always the parent item_id (resolved via JOIN).

Schema drift notes:
  - modules.module_no is NOT NULL UNIQUE(item_id, module_no). Required on create.
  - parts.board_material_id is a FK to board_materials.material_id (not a text column).
  - parts.paint_instruction has CHECK: NONE | DOUBLE_SIDE | SINGLE_SIDE | EDGE_ONLY.
  - parts.is_rev_c does not exist — hardcoded False in get_part() output.
  - board_material resolved via LEFT JOIN board_materials bm ON bm.material_id = p.board_material_id.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..edit_log import write_edit_log, write_edit_log_many
from .schemas import CreateModuleIn, CreatePartIn, PatchModuleIn, PatchPartIn

# ── Workspace isolation helpers ───────────────────────────────────────────────


def _item_id_for_module(db: Session, *, module_id: int, workspace_id: int) -> int | None:
    """Return item_id if module's item is in workspace, else None."""
    row = db.execute(
        text(
            """
            SELECT m.item_id
            FROM modules m
            JOIN items i ON i.item_id = m.item_id
            WHERE m.module_id = :mid
              AND EXISTS (
                  SELECT 1 FROM projects p2
                  WHERE p2.project_id = i.project_id
                    AND p2.workspace_id = :wid
              )
            """
        ),
        {"mid": module_id, "wid": workspace_id},
    ).scalar()
    return row


def _item_id_for_part(db: Session, *, part_id: int, workspace_id: int) -> int | None:
    """Return item_id if part's module's item is in workspace, else None."""
    row = db.execute(
        text(
            """
            SELECT m.item_id
            FROM parts p
            JOIN modules m ON m.module_id = p.module_id
            JOIN items i ON i.item_id = m.item_id
            WHERE p.part_id = :pid
              AND EXISTS (
                  SELECT 1 FROM projects p2
                  WHERE p2.project_id = i.project_id
                    AND p2.workspace_id = :wid
              )
            """
        ),
        {"pid": part_id, "wid": workspace_id},
    ).scalar()
    return row


def _item_in_workspace(db: Session, *, item_id: int, workspace_id: int) -> bool:
    """Return True if item is in workspace."""
    row = db.execute(
        text(
            """
            SELECT 1
            FROM items i
            WHERE i.item_id = :iid
              AND EXISTS (
                  SELECT 1 FROM projects p2
                  WHERE p2.project_id = i.project_id
                    AND p2.workspace_id = :wid
              )
            """
        ),
        {"iid": item_id, "wid": workspace_id},
    ).first()
    return row is not None


# ── Module read helper ─────────────────────────────────────────────────────────


def get_module(db: Session, *, module_id: int, workspace_id: int) -> dict | None:
    """Return ModuleOut-shaped dict (with empty parts list) for a single module."""
    row = db.execute(
        text(
            """
            SELECT m.module_id AS id, m.name
            FROM modules m
            JOIN items i ON i.item_id = m.item_id
            WHERE m.module_id = :mid
              AND EXISTS (
                  SELECT 1 FROM projects p2
                  WHERE p2.project_id = i.project_id
                    AND p2.workspace_id = :wid
              )
            """
        ),
        {"mid": module_id, "wid": workspace_id},
    ).mappings().first()
    if row is None:
        return None
    return {"id": row["id"], "name": row["name"], "parts": []}


# ── Module mutations ───────────────────────────────────────────────────────────


def create_module(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    payload: CreateModuleIn,
    actor_id: int,
) -> int | None:
    """INSERT a new module. Returns new module_id, or None if item not in workspace.

    Writes audit_log + item_edit_log(field='_create_module', new_value=module_no).
    """
    if not _item_in_workspace(db, item_id=item_id, workspace_id=workspace_id):
        return None

    mid = db.execute(
        text(
            """
            INSERT INTO modules(item_id, module_no, name, notes)
            VALUES (:iid, :mno, :name, :notes)
            RETURNING module_id
            """
        ),
        {
            "iid": item_id,
            "mno": payload.module_no,
            "name": payload.name,
            "notes": payload.notes,
        },
    ).scalar()
    db.flush()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="module.create",
        target=str(mid),
        payload={"item_id": item_id, "module_no": payload.module_no, "name": payload.name},
    )
    write_edit_log(
        db,
        item_id=item_id,
        actor_id=actor_id,
        field="_create_module",
        old_value=None,
        new_value=payload.module_no,
    )
    return mid


def patch_module(
    db: Session,
    *,
    module_id: int,
    workspace_id: int,
    payload: PatchModuleIn,
    actor_id: int,
) -> dict | None:
    """Apply a partial update to a module. Returns updated ModuleOut dict, or None if not found.

    Writes one item_edit_log row per changed field.
    """
    item_id = _item_id_for_module(db, module_id=module_id, workspace_id=workspace_id)
    if item_id is None:
        return None

    current = db.execute(
        text("SELECT name, notes FROM modules WHERE module_id = :mid"),
        {"mid": module_id},
    ).mappings().first()
    if current is None:
        return None

    updates: dict = {}
    changes: list[tuple[str, str | None, str | None]] = []

    if payload.name is not None and payload.name != current["name"]:
        updates["name"] = payload.name
        changes.append(("module.name", current["name"], payload.name))

    if payload.notes is not None and payload.notes != current["notes"]:
        updates["notes"] = payload.notes
        changes.append(("module.notes", current["notes"], payload.notes))

    if updates:
        set_clauses = ", ".join(f"{col} = :{col}" for col in updates)
        db.execute(
            text(f"UPDATE modules SET {set_clauses} WHERE module_id = :mid"),
            {"mid": module_id, **updates},
        )
        db.flush()

    if changes:
        write_edit_log_many(db, item_id=item_id, actor_id=actor_id, changes=changes)

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="module.patch",
        target=str(module_id),
        payload={c[0]: c[2] for c in changes},
    )

    return get_module(db, module_id=module_id, workspace_id=workspace_id)


def delete_module(
    db: Session,
    *,
    module_id: int,
    workspace_id: int,
    actor_id: int,
) -> str:
    """Delete a module (and its parts via CASCADE). Returns 'OK' or 'NOT_FOUND'.

    Writes audit_log + item_edit_log BEFORE delete.
    """
    item_id = _item_id_for_module(db, module_id=module_id, workspace_id=workspace_id)
    if item_id is None:
        return "NOT_FOUND"

    module_no = db.execute(
        text("SELECT module_no FROM modules WHERE module_id = :mid"),
        {"mid": module_id},
    ).scalar()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="module.delete",
        target=str(module_id),
        payload={"item_id": item_id, "module_no": module_no},
    )
    write_edit_log(
        db,
        item_id=item_id,
        actor_id=actor_id,
        field="_delete_module",
        old_value=module_no,
        new_value=None,
    )

    db.execute(text("DELETE FROM modules WHERE module_id = :mid"), {"mid": module_id})
    db.flush()
    return "OK"


# ── Part read helper ───────────────────────────────────────────────────────────


def get_part(db: Session, *, part_id: int, workspace_id: int) -> dict | None:
    """Return PartOut-shaped dict for a single part.

    board_material is resolved via LEFT JOIN to board_materials.description.
    is_rev_c is hardcoded False (no DB column per T11).
    """
    row = db.execute(
        text(
            """
            SELECT
                p.part_id           AS id,
                p.module_id,
                p.qty,
                p.part_name,
                p.len_mm,
                p.wid_mm,
                bm.description      AS board_material,
                p.edge,
                p.colour,
                p.paint_instruction,
                p.comment
            FROM parts p
            JOIN modules m ON m.module_id = p.module_id
            JOIN items i ON i.item_id = m.item_id
            LEFT JOIN board_materials bm ON bm.material_id = p.board_material_id
            WHERE p.part_id = :pid
              AND EXISTS (
                  SELECT 1 FROM projects p2
                  WHERE p2.project_id = i.project_id
                    AND p2.workspace_id = :wid
              )
            """
        ),
        {"pid": part_id, "wid": workspace_id},
    ).mappings().first()
    if row is None:
        return None
    return {
        "id": row["id"],
        "module_id": row["module_id"],
        "qty": row["qty"],
        "part_name": row["part_name"],
        "len_mm": row["len_mm"],
        "wid_mm": row["wid_mm"],
        "board_material": row["board_material"],
        "edge": row["edge"],
        "colour": row["colour"],
        "paint_instruction": row["paint_instruction"],
        "comment": row["comment"],
        "is_rev_c": False,
    }


# ── Part mutations ─────────────────────────────────────────────────────────────


def create_part(
    db: Session,
    *,
    module_id: int,
    workspace_id: int,
    payload: CreatePartIn,
    actor_id: int,
) -> int | None:
    """INSERT a new part. Returns new part_id, or None if module not in workspace.

    Writes audit_log + item_edit_log(field='_create_part', new_value=part_name).
    """
    item_id = _item_id_for_module(db, module_id=module_id, workspace_id=workspace_id)
    if item_id is None:
        return None

    pid = db.execute(
        text(
            """
            INSERT INTO parts(
                module_id, qty, part_name, len_mm, wid_mm,
                board_material_id, edge, colour, paint_instruction, comment
            )
            VALUES (
                :mid, :qty, :part_name, :len_mm, :wid_mm,
                :board_material_id, :edge, :colour,
                COALESCE(:paint_instruction, 'NONE'),
                :comment
            )
            RETURNING part_id
            """
        ),
        {
            "mid": module_id,
            "qty": payload.qty,
            "part_name": payload.part_name,
            "len_mm": payload.len_mm,
            "wid_mm": payload.wid_mm,
            "board_material_id": payload.board_material_id,
            "edge": payload.edge,
            "colour": payload.colour,
            "paint_instruction": payload.paint_instruction,
            "comment": payload.comment,
        },
    ).scalar()
    db.flush()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="part.create",
        target=str(pid),
        payload={"module_id": module_id, "item_id": item_id, "part_name": payload.part_name},
    )
    write_edit_log(
        db,
        item_id=item_id,
        actor_id=actor_id,
        field="_create_part",
        old_value=None,
        new_value=payload.part_name,
    )
    return pid


# Field map: PatchPartIn attribute -> DB column name
_PART_FIELD_MAP: list[tuple[str, str]] = [
    ("qty",               "qty"),
    ("part_name",         "part_name"),
    ("len_mm",            "len_mm"),
    ("wid_mm",            "wid_mm"),
    ("board_material_id", "board_material_id"),
    ("edge",              "edge"),
    ("colour",            "colour"),
    ("paint_instruction", "paint_instruction"),
    ("comment",           "comment"),
]


def patch_part(
    db: Session,
    *,
    part_id: int,
    workspace_id: int,
    payload: PatchPartIn,
    actor_id: int,
) -> dict | None:
    """Apply a partial update to a part. Returns updated PartOut dict, or None if not found.

    Writes one item_edit_log row per changed field with names like 'parts.qty', 'parts.len_mm'.
    """
    item_id = _item_id_for_part(db, part_id=part_id, workspace_id=workspace_id)
    if item_id is None:
        return None

    current = db.execute(
        text(
            """
            SELECT qty, part_name, len_mm, wid_mm, board_material_id,
                   edge, colour, paint_instruction, comment
            FROM parts WHERE part_id = :pid
            """
        ),
        {"pid": part_id},
    ).mappings().first()
    if current is None:
        return None

    updates: dict = {}
    changes: list[tuple[str, str | None, str | None]] = []

    for attr, col in _PART_FIELD_MAP:
        new_val = getattr(payload, attr)
        if new_val is None:
            continue
        old_val = current[col]
        if new_val != old_val:
            updates[col] = new_val
            changes.append(
                (f"parts.{attr}", None if old_val is None else str(old_val), str(new_val))
            )

    if updates:
        set_clauses = ", ".join(f"{col} = :{col}" for col in updates)
        db.execute(
            text(
                f"UPDATE parts SET {set_clauses}, updated_at = now() WHERE part_id = :pid"
            ),
            {"pid": part_id, **updates},
        )
        db.flush()

    if changes:
        write_edit_log_many(db, item_id=item_id, actor_id=actor_id, changes=changes)

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="part.patch",
        target=str(part_id),
        payload={c[0]: c[2] for c in changes},
    )

    return get_part(db, part_id=part_id, workspace_id=workspace_id)


def delete_part(
    db: Session,
    *,
    part_id: int,
    workspace_id: int,
    actor_id: int,
) -> str:
    """Delete a part. Returns 'OK' or 'NOT_FOUND'.

    Writes audit_log + item_edit_log BEFORE delete.
    """
    item_id = _item_id_for_part(db, part_id=part_id, workspace_id=workspace_id)
    if item_id is None:
        return "NOT_FOUND"

    part_name = db.execute(
        text("SELECT part_name FROM parts WHERE part_id = :pid"),
        {"pid": part_id},
    ).scalar()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="part.delete",
        target=str(part_id),
        payload={"item_id": item_id, "part_name": part_name},
    )
    write_edit_log(
        db,
        item_id=item_id,
        actor_id=actor_id,
        field="_delete_part",
        old_value=part_name,
        new_value=None,
    )

    db.execute(text("DELETE FROM parts WHERE part_id = :pid"), {"pid": part_id})
    db.flush()
    return "OK"
