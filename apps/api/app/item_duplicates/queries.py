"""Duplicate a Joinery Item (Plan V1 §2, migration `0050`).

Routes own the transaction boundary (db.commit). Everything below runs in the
caller's transaction, so a failure part-way leaves **no** half-made copy.

**What is copied** (settled with the user, 2026-10-03): the item's own fields,
its modules and parts (the Cut List), its hardware lines, its five attachment
slots and its Document Register, and its QC checklist **unchecked**.

**What is deliberately not copied** — Plan V1 §2's "live execution history", and
everything that merely *belongs to the source*: status (the copy starts `CLEAR`;
an `APPROVED` source would otherwise be born Approval-Locked with an approval that
never happened), stage dates (`item_stages`, due and done alike), the Controlled
and Hard Locks and their owner, QC defects and rework, comments, queries, material
takes, orders and procurement allocations, edit history, and the cutlist — the copy
gets **its own new cutlist** (it must not inherit the source's Shop Floor workflow).

Same project only: catalog links, the project hardware catalog and Area / Room are
project-scoped, so nothing is remapped.

Duplicating *reads* the source and writes only new rows, so the source's locks do
not gate it (they guard changes to the source). *An assumption made while building.*
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.sessions import AuthUser
from ..cutlists.queries import create_cutlist, link_item
from ..cutlists.schemas import CreateCutlistIn
from ..edit_log import write_edit_log
from ..row_types import joinery_items_only

_JOINERY_I = joinery_items_only("i")

# items columns the copy takes from its source, verbatim. Anything not listed here
# starts from its column default (status CLEAR is explicit below).
_COPIED_COLUMNS = (
    "project_id", "stage", "zone", "level", "rm_no", "rm_desc", "code", "description",
    "size", "qty", "assembler", "lister", "item_code", "group_id",
    "floor_plan", "rls", "joiery_details", "painting_req", "solid_surface_req",
    "sketchup_file", "cab_vision_file", "estimator_notes", "paint_after_assembly",
    "area_id", "room_id", "jid_code", "jid_color", "var_boq", "contractor_id",
    "total_amount", "site_measure_notes",
)


def _source(db: Session, *, item_id: int, workspace_id: int) -> dict | None:
    row = db.execute(
        text(
            f"""
            SELECT i.item_id, i.num, i.project_id, i.description
            FROM items i
            WHERE i.item_id = :iid
              AND {_JOINERY_I}
              AND NOT COALESCE(i.deleted, false)
              AND EXISTS (
                  SELECT 1 FROM projects p
                  WHERE p.project_id = i.project_id AND p.workspace_id = :wid
              )
            """
        ),
        {"iid": item_id, "wid": workspace_id},
    ).mappings().first()
    return dict(row) if row is not None else None


def duplicate_item(
    db: Session, *, item_id: int, workspace_id: int, actor: AuthUser
) -> int | None:
    """Make one copy of a Joinery Item and return the new item_id.

    None when the source is not a live Joinery Item of this workspace (a related
    part, a deleted item, an unknown id or another workspace's — all 404).
    """
    src = _source(db, item_id=item_id, workspace_id=workspace_id)
    if src is None:
        return None

    cols = ", ".join(_COPIED_COLUMNS)
    # `items.num` is allocated INSIDE the INSERT from the company-wide
    # `joinery_number_seq` (Q541) — never MAX(num) + 1.
    new_id = db.execute(
        text(
            f"""
            INSERT INTO items (num, status, duplicated_from_item_id, {cols})
            SELECT nextval('joinery_number_seq'), 'CLEAR', i.item_id, {", ".join("i." + c for c in _COPIED_COLUMNS)}
            FROM items i
            WHERE i.item_id = :iid
            RETURNING item_id
            """
        ),
        {"iid": item_id},
    ).scalar()

    # Modules and parts. The mapping old -> new is made module by module so each
    # part lands under the copy of its own module.
    n_modules = n_parts = 0
    for m in db.execute(
        text(
            "SELECT module_id, module_no, name, notes FROM modules "
            "WHERE item_id = :iid ORDER BY module_id"
        ),
        {"iid": item_id},
    ).mappings().all():
        new_module = db.execute(
            text(
                """
                INSERT INTO modules (item_id, module_no, name, notes)
                VALUES (:new, :no, :name, :notes)
                RETURNING module_id
                """
            ),
            {"new": new_id, "no": m["module_no"], "name": m["name"], "notes": m["notes"]},
        ).scalar()
        n_modules += 1
        n_parts += db.execute(
            text(
                """
                INSERT INTO parts (module_id, seq, qty, part_name, len_mm, wid_mm,
                                   board_material_id, edge, colour, edging_spec,
                                   paint_instruction, comment)
                SELECT :new_module, seq, qty, part_name, len_mm, wid_mm,
                       board_material_id, edge, colour, edging_spec,
                       paint_instruction, comment
                FROM parts WHERE module_id = :old ORDER BY part_id
                """
            ),
            {"new_module": new_module, "old": m["module_id"]},
        ).rowcount

    n_hardware = db.execute(
        text(
            """
            INSERT INTO item_hardware_lines (item_id, seq, qty, catalog_id, note)
            SELECT :new, seq, qty, catalog_id, note
            FROM item_hardware_lines WHERE item_id = :old ORDER BY line_id
            """
        ),
        {"new": new_id, "old": item_id},
    ).rowcount

    # Attachments and register documents point at the same stored file (`file_blob`
    # is content-addressed and deduplicated) — no bytes are copied. The copy's
    # uploader is whoever duplicated it.
    n_attachments = db.execute(
        text(
            """
            INSERT INTO item_attachment (item_id, kind, file_blob_id, uploaded_by)
            SELECT :new, kind, file_blob_id, :actor
            FROM item_attachment WHERE item_id = :old
            """
        ),
        {"new": new_id, "old": item_id, "actor": actor.id},
    ).rowcount
    n_documents = db.execute(
        text(
            """
            INSERT INTO item_document (item_id, file_blob_id, label, sort_order, uploaded_by)
            SELECT :new, file_blob_id, label, sort_order, :actor
            FROM item_document WHERE item_id = :old ORDER BY sort_order, document_id
            """
        ),
        {"new": new_id, "old": item_id, "actor": actor.id},
    ).rowcount

    # The QC checklist comes across unchecked: the labels are the "setup", whether
    # they were ticked is a QC result (Plan V1 §2).
    n_checklist = db.execute(
        text(
            """
            INSERT INTO qc_checklist_item (item_id, label, is_checked, sort_order, created_by)
            SELECT :new, label, false, sort_order, :actor
            FROM qc_checklist_item WHERE item_id = :old ORDER BY sort_order, checklist_item_id
            """
        ),
        {"new": new_id, "old": item_id, "actor": actor.id},
    ).rowcount

    # Its own cutlist, numbered from the shared sequence and named after the copy
    # (the source's cutlist, and any production history on it, is left alone).
    cutlist = create_cutlist(
        db,
        project_id=src["project_id"],
        workspace_id=workspace_id,
        payload=CreateCutlistIn(name=src["description"]),
        actor_id=actor.id,
    )
    code, _ = link_item(
        db,
        cutlist_id=cutlist["cutlist_id"],
        item_id=new_id,
        workspace_id=workspace_id,
        actor_id=actor.id,
    )
    if code != "OK":  # a brand-new item in the cutlist's own project cannot fail to link
        raise RuntimeError(f"could not link the duplicate to its new cutlist: {code}")

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor.id,
        event="item.duplicate",
        target=str(new_id),
        payload={
            "source_item_id": item_id,
            "source_item_number": src["num"],
            "cutlist_id": cutlist["cutlist_id"],
            "modules": n_modules,
            "parts": n_parts,
            "hardware_lines": n_hardware,
            "attachments": n_attachments,
            "documents": n_documents,
            "checklist_items": n_checklist,
        },
    )
    write_edit_log(
        db,
        item_id=new_id,
        actor_id=actor.id,
        field="_duplicate",
        old_value=None,
        new_value=f"from #{src['num']}",
    )
    return new_id
