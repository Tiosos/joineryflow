"""Context builder for the print engine.

Pulls item + parts + hardware + attachments from the DB and reshapes them into
the dict the templates expect. Workspace isolation enforced via the new
projects.workspace_id direct FK from migration 0014.
"""
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from .catalog_enrich import group_hardware_for_print


def build_context(item_id: int, db: Session, *, workspace_id: int) -> dict | None:
    """Return the template context for printing this item, or None if not found / not in workspace."""
    item = db.execute(text("""
        SELECT i.item_id, i.num, i.description, i.code, i.item_code,
               i.rm_no, i.rm_desc, i.stage, i.zone, i.level,
               i.lister, i.assembler,
               i.project_id, p.project_code, p.name AS project_name
          FROM items i
          JOIN projects p ON p.project_id = i.project_id
         WHERE i.item_id = :i
           AND p.workspace_id = :w
    """), {"i": item_id, "w": workspace_id}).mappings().first()
    if not item:
        return None

    parts = db.execute(text("""
        SELECT p.qty, p.part_name, p.len_mm, p.wid_mm,
               p.board_material_id,
               bm.description AS material_description, bm.code AS material_code,
               p.edge, p.colour, p.edging_spec,
               p.paint_instruction
          FROM parts p
          JOIN modules m ON m.module_id = p.module_id
          LEFT JOIN board_materials bm ON bm.material_id = p.board_material_id
         WHERE m.item_id = :i
         ORDER BY m.module_id, p.seq, p.part_id
    """), {"i": item_id}).mappings().all()

    hardware_lines = db.execute(text("""
        SELECT ihl.qty, ihl.note,
               phc.material_type, phc.material_id, phc.catalog_id
          FROM item_hardware_lines ihl
          JOIN project_hardware_catalog phc ON phc.catalog_id = ihl.catalog_id
         WHERE ihl.item_id = :i
         ORDER BY ihl.line_id
    """), {"i": item_id}).mappings().all()
    hardware_groups = group_hardware_for_print(db, [dict(r) for r in hardware_lines])

    attachments = db.execute(text("""
        SELECT ia.kind, ia.file_blob_id, fb.original_filename, fb.byte_size, fb.storage_key
          FROM item_attachment ia
          JOIN file_blob fb ON fb.file_blob_id = ia.file_blob_id
         WHERE ia.item_id = :i
    """), {"i": item_id}).mappings().all()
    attachments_by_kind = {a["kind"]: dict(a) for a in attachments}

    return {
        "item": dict(item),
        "parts": [dict(p) for p in parts],
        "hardware": hardware_groups,
        "attachments": attachments_by_kind,
        "has_painting": any((p["paint_instruction"] or "NONE") != "NONE" for p in parts),
        "rendered_at": datetime.now(timezone.utc),
    }
