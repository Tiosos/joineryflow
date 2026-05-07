"""CV import HTTP routes — sub-project #7b.

Routes:
  POST /items/{iid}/cv-imports/preview        - parse + resolve, persist run
  POST /items/{iid}/cv-imports/{run_id}/commit - apply resolutions in one txn
  GET  /items/{iid}/cv-imports                - history (newest first)
  GET  /cv-imports/{run_id}                   - single run + cached preview

Gated by ("cut_floor", action). Workspace isolation through
projects.workspace_id. Audit + item_edit_log on every write.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .parser import ParsedPart, parse_csv
from .resolver import resolve_codes, suggest_table
from .schemas import (
    CvCommitIn,
    CvCommitOut,
    CvImportRunOut,
    CvParsedModule,
    CvParsedPart,
    CvPreviewOut,
    CvPreviewSummary,
    CvRowResolution,
    CvUnknownCode,
)


router = APIRouter(tags=["cv"])

MAX_CSV_BYTES = 1_048_576       # 1 MB
MAX_LOGICAL_ROWS = 10_000


# --- helpers ----------------------------------------------------------------

def _resolve_workspace_project(
    db: Session, *, item_id: int, workspace_id: int
) -> int:
    project_id = q.get_item_project_for_workspace(
        db, item_id=item_id, workspace_id=workspace_id
    )
    if project_id is None:
        raise HTTPException(404, "item not found")
    return project_id


def _build_preview_payload(
    parsed_parts: list[ParsedPart],
    errors: list,
    resolutions: dict[str, CvRowResolution],
    row_count: int,
    run_id: int,
) -> CvPreviewOut:
    by_module: dict[int, list[CvParsedPart]] = defaultdict(list)
    for p in parsed_parts:
        res = resolutions.get(p.cv_code, CvRowResolution(kind="unknown"))
        by_module[p.module_no].append(CvParsedPart(
            row_index=p.row_index,
            part_name=p.part_name,
            qty=p.qty,
            len_mm=p.len_mm,
            wid_mm=p.wid_mm,
            thickness_mm=p.thickness_mm,
            cv_code=p.cv_code,
            edge=p.edge,
            colour=p.colour,
            notes=p.notes,
            resolution=res,
        ))
    modules: list[CvParsedModule] = [
        CvParsedModule(module_no=mno, parts=parts)
        for mno, parts in sorted(by_module.items(), key=lambda x: x[0])
    ]

    mapped = sum(
        1 for p in parsed_parts
        if resolutions.get(p.cv_code, CvRowResolution(kind="unknown")).kind == "mapped"
    )
    synonym = sum(
        1 for p in parsed_parts
        if resolutions.get(p.cv_code, CvRowResolution(kind="unknown")).kind == "synonym_match"
    )
    unknown_part_count = sum(
        1 for p in parsed_parts
        if resolutions.get(p.cv_code, CvRowResolution(kind="unknown")).kind == "unknown"
    )
    invalid = len(errors)

    unknown_codes_count: dict[str, int] = defaultdict(int)
    for p in parsed_parts:
        if resolutions.get(p.cv_code, CvRowResolution(kind="unknown")).kind == "unknown":
            unknown_codes_count[p.cv_code] += 1
    unknown_codes = [
        CvUnknownCode(
            cv_code=code,
            occurrences=cnt,
            suggested_table=suggest_table(code),
        )
        for code, cnt in unknown_codes_count.items()
    ]

    return CvPreviewOut(
        run_id=run_id,
        summary=CvPreviewSummary(
            row_count=row_count,
            mapped=mapped,
            synonym=synonym,
            unknown=unknown_part_count,
            invalid=invalid,
        ),
        modules=modules,
        unknown_codes=unknown_codes,
        errors=errors,
    )


# --- POST preview ------------------------------------------------------------

@router.post("/items/{iid}/cv-imports/preview")
async def preview_cv_import(
    iid: int,
    file: UploadFile | None = File(None),
    body: str | None = Form(None),
    user: AuthUser = Depends(require_permission("cut_floor", "write")),
    db: Session = Depends(get_db),
) -> CvPreviewOut:
    project_id = _resolve_workspace_project(
        db, item_id=iid, workspace_id=user.workspace_id
    )

    if file is not None and body:
        raise HTTPException(422, "provide either `file` or `body`, not both")
    if file is not None:
        raw_bytes = await file.read()
        source_filename = file.filename or "upload.csv"
    elif body is not None:
        raw_bytes = body.encode("utf-8")
        source_filename = "pasted.csv"
    else:
        raise HTTPException(422, "no CSV body provided")

    if len(raw_bytes) > MAX_CSV_BYTES:
        raise HTTPException(
            415,
            {"code": "FILE_TOO_LARGE", "max_bytes": MAX_CSV_BYTES,
             "actual_bytes": len(raw_bytes)},
        )

    try:
        parsed_parts, errors, row_count = parse_csv(raw_bytes)
    except ValueError as e:
        raise HTTPException(422, str(e))

    if row_count > MAX_LOGICAL_ROWS:
        raise HTTPException(
            415,
            {"code": "TOO_MANY_ROWS", "max_rows": MAX_LOGICAL_ROWS,
             "actual_rows": row_count},
        )

    resolutions = resolve_codes(db, user.workspace_id, parsed_parts)

    sha = hashlib.sha256(raw_bytes).hexdigest()

    run_id = q.insert_run_preview(
        db,
        project_id=project_id,
        item_id=iid,
        source_filename=source_filename,
        sha256=sha,
        row_count=row_count,
        error_log=[],
        created_by=user.id,
    )

    payload = _build_preview_payload(
        parsed_parts, errors, resolutions, row_count, run_id
    )

    snapshot = {
        "_preview_snapshot": payload.model_dump(mode="json"),
        "_parsed_parts": [
            {
                "row_index": p.row_index, "module_no": p.module_no,
                "part_name": p.part_name, "qty": p.qty,
                "len_mm": p.len_mm, "wid_mm": p.wid_mm,
                "thickness_mm": p.thickness_mm, "cv_code": p.cv_code,
                "edge": p.edge, "colour": p.colour, "notes": p.notes,
            }
            for p in parsed_parts
        ],
        "_resolutions": {
            code: res.model_dump(mode="json") for code, res in resolutions.items()
        },
    }
    db.execute(
        text(
            "UPDATE cv_import_run SET error_log = CAST(:s AS jsonb) "
            "WHERE cv_import_run_id = :rid"
        ),
        {"s": json.dumps(snapshot), "rid": run_id},
    )
    db.flush()

    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cv.import.preview", target=str(run_id),
        payload={
            "run_id": run_id,
            "source_filename": source_filename,
            "row_count": row_count,
            "summary": payload.summary.model_dump(),
        },
    )
    db.commit()
    return payload


# --- POST commit -------------------------------------------------------------

@router.post("/items/{iid}/cv-imports/{run_id}/commit")
def commit_cv_import_route(
    iid: int,
    run_id: int,
    body: CvCommitIn,
    mode: str = Query("default"),
    user: AuthUser = Depends(require_permission("cut_floor", "write")),
    db: Session = Depends(get_db),
) -> CvCommitOut:
    project_id = _resolve_workspace_project(
        db, item_id=iid, workspace_id=user.workspace_id
    )

    run = q.get_run(db, run_id=run_id, workspace_id=user.workspace_id)
    if run is None or run["item_id"] != iid:
        raise HTTPException(404, "run not found")
    if run["status"] != "preview":
        raise HTTPException(
            409, {"code": "RUN_NOT_PENDING", "status": run["status"]},
        )

    error_log = run.get("error_log") or {}
    if not isinstance(error_log, dict):
        raise HTTPException(409, {"code": "PREVIEW_SNAPSHOT_MISSING"})
    parsed_blobs = error_log.get("_parsed_parts") or []
    resolutions_blob = error_log.get("_resolutions") or {}

    parsed_parts = [ParsedPart(**b) for b in parsed_blobs]

    unknown_codes = {
        code for code, res in resolutions_blob.items()
        if (res or {}).get("kind") == "unknown"
    }
    body_codes = {r.cv_code for r in body.resolutions}
    missing = unknown_codes - body_codes
    if missing:
        raise HTTPException(
            422,
            {"code": "UNRESOLVED_CODES", "codes": sorted(missing)},
        )

    replace = (mode == "replace") or body.replace

    if not replace and q.count_modules_for_item(db, item_id=iid) > 0:
        raise HTTPException(
            409, {"code": "ITEM_NOT_EMPTY"},
        )

    try:
        result = q.commit_import(
            db,
            workspace_id=user.workspace_id,
            project_id=project_id,
            item_id=iid,
            run_id=run_id,
            parsed_parts=parsed_parts,
            preview_resolutions=resolutions_blob,
            body_resolutions=body.resolutions,
            actor_id=user.id,
            replace=replace,
        )
    except ValueError as e:
        db.rollback()
        q.update_run_failed(db, run_id=run_id, message=str(e))
        write_audit(
            db, workspace_id=user.workspace_id, actor_id=user.id,
            event="cv.import.fail", target=str(run_id),
            payload={"run_id": run_id, "error": str(e)},
        )
        db.commit()
        raise HTTPException(422, str(e))
    except Exception as e:
        db.rollback()
        q.update_run_failed(db, run_id=run_id, message=str(e))
        write_audit(
            db, workspace_id=user.workspace_id, actor_id=user.id,
            event="cv.import.fail", target=str(run_id),
            payload={"run_id": run_id, "error": str(e)},
        )
        db.commit()
        raise

    db.commit()
    return CvCommitOut(**result)


# --- GET history -------------------------------------------------------------

@router.get("/items/{iid}/cv-imports")
def list_cv_imports_route(
    iid: int,
    user: AuthUser = Depends(require_permission("cut_floor", "read")),
    db: Session = Depends(get_db),
) -> list[CvImportRunOut]:
    _resolve_workspace_project(
        db, item_id=iid, workspace_id=user.workspace_id
    )
    rows = q.list_runs_for_item(
        db, item_id=iid, workspace_id=user.workspace_id
    )
    return [CvImportRunOut(**r) for r in rows]


@router.get("/cv-imports/{run_id}")
def get_cv_import_run_route(
    run_id: int,
    user: AuthUser = Depends(require_permission("cut_floor", "read")),
    db: Session = Depends(get_db),
) -> dict:
    run = q.get_run(db, run_id=run_id, workspace_id=user.workspace_id)
    if run is None:
        raise HTTPException(404, "run not found")
    error_log = run.get("error_log") or {}
    preview = None
    if isinstance(error_log, dict):
        preview = error_log.get("_preview_snapshot")
    run_out = {k: v for k, v in run.items() if k != "error_log"}
    return {"run": run_out, "preview": preview}
