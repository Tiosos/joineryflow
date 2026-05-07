"""SQL queries for the CV import wizard (sub-project #7b).

Routes own the transaction boundary; queries flush only.

Schema notes:
  - parts.board_material_id is the only material FK on parts. CV codes that
    resolve to non-board catalog tables persist as parts with
    board_material_id=NULL; the resolution trace is preserved in the
    cv.import.commit audit payload + the cv_import_run.error_log snapshot.
  - modules.module_no is character varying; we cast int -> str on insert.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..edit_log import write_edit_log_many
from .parser import ParsedPart


# --- Catalog table -> REGISTRY slug + legacy NOT NULL UNIQUE column ----------

_TABLE_REGISTRY: dict[str, tuple[str, str | None]] = {
    "board_materials":     ("board",       "code"),
    "hardware_materials":  ("hardware",    None),
    "custom_made":         ("custom_made", "internal_ref"),
    "benchtop_materials":  ("benchtop",    "slab_id"),
    "appliances":          ("appliance",   "model_number"),
    "equipment_hire":      ("hire",        "contract_ref"),
}


# --- Run lifecycle -----------------------------------------------------------

def insert_run_preview(
    db: Session,
    *,
    project_id: int,
    item_id: int,
    source_filename: str,
    sha256: str,
    row_count: int,
    error_log: dict | list,
    created_by: int,
) -> int:
    """INSERT a cv_import_run row with status='preview'. Returns run_id."""
    run_id = db.execute(
        text("""
            INSERT INTO cv_import_run(
                project_id, item_id, source_filename, sha256,
                row_count, status, error_log, created_by
            )
            VALUES (:pid, :iid, :fn, :sha, :rc, 'preview', CAST(:ej AS jsonb), :cb)
            RETURNING cv_import_run_id
        """),
        {
            "pid": project_id,
            "iid": item_id,
            "fn": source_filename,
            "sha": sha256,
            "rc": row_count,
            "ej": json.dumps(error_log),
            "cb": created_by,
        },
    ).scalar()
    db.flush()
    return run_id


def update_run_committed(db: Session, *, run_id: int) -> None:
    db.execute(
        text("""
            UPDATE cv_import_run
            SET status='committed', completed_at=now()
            WHERE cv_import_run_id = :rid
        """),
        {"rid": run_id},
    )
    db.flush()


def update_run_failed(db: Session, *, run_id: int, message: str) -> None:
    db.execute(
        text("""
            UPDATE cv_import_run
            SET status='failed',
                completed_at=now(),
                error_log = error_log || CAST(:ej AS jsonb)
            WHERE cv_import_run_id = :rid
        """),
        {"rid": run_id, "ej": json.dumps([{"code": "COMMIT_FAILED", "message": message}])},
    )
    db.flush()


def get_run(
    db: Session, *, run_id: int, workspace_id: int
) -> dict | None:
    """Return the run row scoped to workspace via project FK chain."""
    row = db.execute(
        text("""
            SELECT r.cv_import_run_id, r.project_id, r.item_id, r.source_filename,
                   r.sha256, r.row_count, r.status, r.started_at, r.completed_at,
                   r.error_log, r.created_by
            FROM cv_import_run r
            JOIN projects p ON p.project_id = r.project_id
            WHERE r.cv_import_run_id = :rid
              AND p.workspace_id = :w
        """),
        {"rid": run_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def list_runs_for_item(
    db: Session, *, item_id: int, workspace_id: int
) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT r.cv_import_run_id, r.project_id, r.item_id, r.source_filename,
                   r.sha256, r.row_count, r.status, r.started_at, r.completed_at,
                   r.created_by
            FROM cv_import_run r
            JOIN items i ON i.item_id = r.item_id
            JOIN projects p ON p.project_id = i.project_id
            WHERE r.item_id = :iid
              AND p.workspace_id = :w
            ORDER BY r.started_at DESC
        """),
        {"iid": item_id, "w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


# --- Item / project resolution ----------------------------------------------

def get_item_project_for_workspace(
    db: Session, *, item_id: int, workspace_id: int
) -> int | None:
    """Return project_id if item is in workspace, else None."""
    row = db.execute(
        text("""
            SELECT i.project_id
            FROM items i
            JOIN projects p ON p.project_id = i.project_id
            WHERE i.item_id = :iid
              AND p.workspace_id = :w
        """),
        {"iid": item_id, "w": workspace_id},
    ).first()
    return row[0] if row else None


def count_modules_for_item(db: Session, *, item_id: int) -> int:
    return db.execute(
        text("SELECT COUNT(*) FROM modules WHERE item_id = :iid"),
        {"iid": item_id},
    ).scalar() or 0


def delete_modules_for_item(db: Session, *, item_id: int) -> list[int]:
    """DELETE all modules under an item (CASCADE wipes parts).
    Returns the list of deleted module_ids."""
    ids = [r[0] for r in db.execute(
        text("SELECT module_id FROM modules WHERE item_id = :iid"),
        {"iid": item_id},
    ).all()]
    if ids:
        db.execute(
            text("DELETE FROM modules WHERE item_id = :iid"),
            {"iid": item_id},
        )
        db.flush()
    return ids


# --- Catalog inserts (for create_new resolutions) ---------------------------

def insert_catalog_row_from_create_new(
    db: Session,
    *,
    workspace_id: int,
    target_table: str,
    sku: str,
    description: str,
    default_supplier: str | None,
    default_lead_time_days: int | None,
) -> int:
    """INSERT a new catalog row from a Phase B `create_new` resolution.

    Legacy NOT NULL UNIQUE column (e.g. `code`, `internal_ref`) is filled
    from the supplied `sku`. equipment_hire is rejected (use /catalog).
    """
    if target_table == "equipment_hire":
        raise ValueError(
            "equipment_hire create_new is not supported in CV wizard "
            "(use /catalog?tab=hire)"
        )
    if target_table not in _TABLE_REGISTRY:
        raise ValueError(f"unknown target_table: {target_table}")

    legacy_col = _TABLE_REGISTRY[target_table][1]
    cols = ["sku", "description", "workspace_id",
            "synonyms", "default_supplier", "default_lead_time_days"]
    params: dict[str, Any] = {
        "sku": sku,
        "description": description,
        "workspace_id": workspace_id,
        "synonyms": [],
        "default_supplier": default_supplier,
        "default_lead_time_days": default_lead_time_days,
    }
    if legacy_col is not None:
        cols.insert(0, legacy_col)
        params[legacy_col] = sku
    placeholders = ", ".join(":" + c for c in cols)

    sql = text(
        f"INSERT INTO {target_table} ({', '.join(cols)}) "
        f"VALUES ({placeholders}) "
        f"RETURNING material_id"
    )
    return db.execute(sql, params).scalar()


def upsert_cv_mapping_if_missing(
    db: Session,
    *,
    workspace_id: int,
    cv_code: str,
    target_table: str,
    target_material_id: int,
    actor_id: int,
) -> bool:
    """INSERT a cv_material_mapping row unless one already exists.
    Returns True iff a new row was inserted."""
    existing = db.execute(
        text("""
            SELECT 1 FROM cv_material_mapping
            WHERE workspace_id = :w AND cv_code = :code
        """),
        {"w": workspace_id, "code": cv_code},
    ).first()
    if existing:
        return False
    db.execute(
        text("""
            INSERT INTO cv_material_mapping(
                workspace_id, cv_code, target_material_table,
                target_material_id, created_by
            )
            VALUES (:w, :code, :tbl, :tid, :a)
        """),
        {
            "w": workspace_id, "code": cv_code, "tbl": target_table,
            "tid": target_material_id, "a": actor_id,
        },
    )
    db.flush()
    return True


# --- Module / part inserts --------------------------------------------------

def _insert_module(db: Session, *, item_id: int, module_no: str, name: str | None = None) -> int:
    return db.execute(
        text("""
            INSERT INTO modules(item_id, module_no, name)
            VALUES (:iid, :mno, :name)
            RETURNING module_id
        """),
        {"iid": item_id, "mno": module_no, "name": name},
    ).scalar()


def _insert_part(
    db: Session,
    *,
    module_id: int,
    seq: int,
    qty: int,
    part_name: str,
    len_mm: int,
    wid_mm: int,
    board_material_id: int | None,
    edge: str | None,
    colour: str | None,
    comment: str | None,
) -> int:
    return db.execute(
        text("""
            INSERT INTO parts(
                module_id, seq, qty, part_name, len_mm, wid_mm,
                board_material_id, edge, colour,
                paint_instruction, comment
            )
            VALUES (
                :mid, :seq, :qty, :pn, :len, :wid,
                :bmid, :edge, :col, 'NONE', :comment
            )
            RETURNING part_id
        """),
        {
            "mid": module_id, "seq": seq, "qty": qty, "pn": part_name,
            "len": len_mm, "wid": wid_mm, "bmid": board_material_id,
            "edge": edge, "col": colour, "comment": comment,
        },
    ).scalar()


# --- Commit transaction ------------------------------------------------------

def commit_import(
    db: Session,
    *,
    workspace_id: int,
    project_id: int,
    item_id: int,
    run_id: int,
    parsed_parts: list[ParsedPart],
    preview_resolutions: dict[str, dict],
    body_resolutions: list,  # list[CvCommitResolution]
    actor_id: int,
    replace: bool,
) -> dict:
    """Single-transaction commit per spec §6.6."""
    deleted_module_ids: list[int] = []
    if replace:
        deleted_module_ids = delete_modules_for_item(db, item_id=item_id)
        if deleted_module_ids:
            write_audit(
                db, workspace_id=workspace_id, actor_id=actor_id,
                event="cv.import.replace_wipe", target=str(run_id),
                payload={"run_id": run_id, "deleted_module_ids": deleted_module_ids},
            )

    # Body resolutions keyed by cv_code.
    body_by_code: dict[str, dict] = {}
    for r in body_resolutions:
        d = r.model_dump() if hasattr(r, "model_dump") else dict(r)
        body_by_code[d["cv_code"]] = d

    catalog_rows_created = 0
    mappings_created = 0
    final_target: dict[str, tuple[str, int] | None] = {}

    for code, res in preview_resolutions.items():
        kind = res.get("kind")
        if kind in ("mapped", "synonym_match"):
            tgt_tbl = res.get("target_table")
            tgt_id = res.get("target_material_id")
            if tgt_tbl and tgt_id is not None:
                final_target[code] = (tgt_tbl, int(tgt_id))
            else:
                final_target[code] = None
        else:
            final_target[code] = None

    for code, body in body_by_code.items():
        action = body["action"]
        if action == "skip":
            final_target[code] = None
        elif action == "use_existing":
            final_target[code] = (body["target_table"], int(body["target_material_id"]))
            if upsert_cv_mapping_if_missing(
                db, workspace_id=workspace_id, cv_code=code,
                target_table=body["target_table"],
                target_material_id=int(body["target_material_id"]),
                actor_id=actor_id,
            ):
                mappings_created += 1
        elif action == "create_new":
            new_mid = insert_catalog_row_from_create_new(
                db, workspace_id=workspace_id,
                target_table=body["target_table"],
                sku=body["sku"], description=body["description"],
                default_supplier=body.get("default_supplier"),
                default_lead_time_days=body.get("default_lead_time_days"),
            )
            catalog_rows_created += 1
            final_target[code] = (body["target_table"], new_mid)
            if upsert_cv_mapping_if_missing(
                db, workspace_id=workspace_id, cv_code=code,
                target_table=body["target_table"],
                target_material_id=new_mid, actor_id=actor_id,
            ):
                mappings_created += 1

    # Skipped codes: drop their parts.
    skipped_codes = {code for code, tgt in final_target.items() if tgt is None}

    keep_parts = [p for p in parsed_parts if p.cv_code not in skipped_codes]
    module_no_to_id: dict[str, int] = {}
    parts_created = 0
    edit_log_changes: list[tuple[str, str | None, str | None]] = []

    for part in keep_parts:
        mno_str = str(part.module_no)
        if mno_str not in module_no_to_id:
            module_id = _insert_module(db, item_id=item_id, module_no=mno_str)
            module_no_to_id[mno_str] = module_id
            edit_log_changes.append(("_create_module", None, mno_str))
            write_audit(
                db, workspace_id=workspace_id, actor_id=actor_id,
                event="module.create", target=str(module_id),
                payload={"item_id": item_id, "module_no": mno_str,
                         "via": "cv.import", "run_id": run_id},
            )

        target = final_target.get(part.cv_code)
        board_mid: int | None = None
        comment = part.notes
        if target is not None:
            tgt_tbl, tgt_id = target
            if tgt_tbl == "board_materials":
                board_mid = tgt_id
            else:
                tag = f"[material: {tgt_tbl}#{tgt_id}]"
                comment = f"{tag} {comment}" if comment else tag

        new_part_id = _insert_part(
            db,
            module_id=module_no_to_id[mno_str],
            seq=part.row_index,
            qty=part.qty,
            part_name=part.part_name,
            len_mm=part.len_mm,
            wid_mm=part.wid_mm,
            board_material_id=board_mid,
            edge=part.edge,
            colour=part.colour,
            comment=comment,
        )
        parts_created += 1
        edit_log_changes.append(("_create_part", None, part.part_name))
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id,
            event="part.create", target=str(new_part_id),
            payload={"module_id": module_no_to_id[mno_str], "item_id": item_id,
                     "part_name": part.part_name, "via": "cv.import",
                     "run_id": run_id, "cv_code": part.cv_code},
        )

    edit_log_changes.append(
        ("_cv_import", None, f"{run_id} ({parts_created} parts)")
    )
    write_edit_log_many(db, item_id=item_id, actor_id=actor_id,
                        changes=edit_log_changes)

    update_run_committed(db, run_id=run_id)

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="cv.import.commit", target=str(run_id),
        payload={
            "run_id": run_id,
            "modules_created": len(module_no_to_id),
            "parts_created": parts_created,
            "mappings_created": mappings_created,
            "catalog_rows_created": catalog_rows_created,
            "replaced_module_ids": deleted_module_ids,
            "replace": replace,
        },
    )

    return {
        "run_id": run_id,
        "modules_created": len(module_no_to_id),
        "parts_created": parts_created,
        "mappings_created": mappings_created,
        "catalog_rows_created": catalog_rows_created,
        "replaced_module_ids": deleted_module_ids,
    }
