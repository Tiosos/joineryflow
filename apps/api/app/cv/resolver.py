"""CV code resolver — translates a `material_code` from a parsed CSV row into
a (target_table, target_material_id, description) triple.

Resolution order (per spec §6.2):
  1. cv_material_mapping hit  -> kind='mapped'
  2. catalog synonyms[] hit (single table, archived_at IS NULL)
                              -> kind='synonym_match'
  3. catalog sku exact hit (single table, archived_at IS NULL)
                              -> kind='synonym_match'
  4. otherwise                -> kind='unknown'

Multiple tables with synonym/sku hits for the same code resolves to
`unknown` with hint='multiple_synonym_matches'.

Workspace-isolated everywhere via `workspace_id = :w`.
"""
from __future__ import annotations

import re
from sqlalchemy import text
from sqlalchemy.engine import Connection

from .parser import ParsedPart
from .schemas import CvRowResolution


CATALOG_TABLES: tuple[tuple[str, str], ...] = (
    ("board_materials",     "material_id"),
    ("hardware_materials",  "material_id"),
    ("custom_made",         "material_id"),
    ("benchtop_materials",  "material_id"),
    ("appliances",          "material_id"),
    ("equipment_hire",      "hire_id"),
)


_BOARD_RE = re.compile(r"^\d{2}-")          # 18-PB, 19-MELAMINE-WHITE
_HARDWARE_RE = re.compile(r"^\d{3}\.\d")    # 700.0KC2.054.00


def suggest_table(cv_code: str) -> str | None:
    """Heuristic suggestion for the 'Create new' mini-form's default tab."""
    if _BOARD_RE.match(cv_code):
        return "board_materials"
    if _HARDWARE_RE.match(cv_code):
        return "hardware_materials"
    return None


def _lookup_target_description(conn: Connection, table: str, mid: int, pk_col: str) -> str | None:
    row = conn.execute(
        text(f"SELECT description FROM {table} WHERE {pk_col} = :mid LIMIT 1"),
        {"mid": mid},
    ).first()
    return row[0] if row else None


def _resolve_one(conn: Connection, workspace_id: int, code: str) -> CvRowResolution:
    # 1. Mapping hit
    mapping = conn.execute(
        text("""
            SELECT target_material_table, target_material_id
            FROM cv_material_mapping
            WHERE workspace_id = :w AND cv_code = :code
            LIMIT 1
        """),
        {"w": workspace_id, "code": code},
    ).first()
    if mapping:
        tbl = mapping[0]
        mid = mapping[1]
        pk_col = next((pk for t, pk in CATALOG_TABLES if t == tbl), "material_id")
        desc = _lookup_target_description(conn, tbl, mid, pk_col)
        return CvRowResolution(
            kind="mapped",
            target_table=tbl,
            target_material_id=mid,
            target_description=desc,
        )

    # 2. Synonym hit
    synonym_hits: list[tuple[str, int, str | None]] = []
    for tbl, pk in CATALOG_TABLES:
        row = conn.execute(
            text(f"""
                SELECT {pk}, description
                FROM {tbl}
                WHERE workspace_id = :w
                  AND :code = ANY(synonyms)
                  AND archived_at IS NULL
                LIMIT 1
            """),
            {"w": workspace_id, "code": code},
        ).first()
        if row:
            synonym_hits.append((tbl, row[0], row[1]))

    if len(synonym_hits) == 1:
        tbl, mid, desc = synonym_hits[0]
        return CvRowResolution(
            kind="synonym_match",
            target_table=tbl,
            target_material_id=mid,
            target_description=desc,
        )
    if len(synonym_hits) >= 2:
        return CvRowResolution(kind="unknown", hint="multiple_synonym_matches")

    # 3. Exact-sku hit
    sku_hits: list[tuple[str, int, str | None]] = []
    for tbl, pk in CATALOG_TABLES:
        row = conn.execute(
            text(f"""
                SELECT {pk}, description
                FROM {tbl}
                WHERE workspace_id = :w
                  AND sku = :code
                  AND archived_at IS NULL
                LIMIT 1
            """),
            {"w": workspace_id, "code": code},
        ).first()
        if row:
            sku_hits.append((tbl, row[0], row[1]))

    if len(sku_hits) == 1:
        tbl, mid, desc = sku_hits[0]
        return CvRowResolution(
            kind="synonym_match",
            target_table=tbl,
            target_material_id=mid,
            target_description=desc,
        )
    if len(sku_hits) >= 2:
        return CvRowResolution(kind="unknown", hint="multiple_synonym_matches")

    # 4. Otherwise unknown
    return CvRowResolution(kind="unknown")


def resolve_codes(
    conn: Connection,
    workspace_id: int,
    parts: list[ParsedPart],
) -> dict[str, CvRowResolution]:
    """Return {cv_code: resolution} for every distinct code in `parts`."""
    distinct_codes = {p.cv_code for p in parts}
    return {code: _resolve_one(conn, workspace_id, code) for code in distinct_codes}
