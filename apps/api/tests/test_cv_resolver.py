"""Tests for the CV resolver (sub-project #7b).

Resolution order: cv_material_mapping > catalog synonyms[] > catalog sku exact > unknown.
"""
import uuid

import pytest
from sqlalchemy import text

from app.cv.parser import ParsedPart
from app.cv.resolver import resolve_codes, suggest_table
from app.db import SessionLocal

from .conftest import TRUNCATE_TABLES


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        extra = (
            "batch_allocations",
            "procurement_batches",
            "equipment_hire",
            "appliances",
            "benchtop_materials",
            "custom_made",
            "hardware_materials",
            "board_materials",
        )
        all_tables = ", ".join(list(extra) + list(TRUNCATE_TABLES))
        s.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _new_workspace_and_user() -> tuple[int, int]:
    s = SessionLocal()
    try:
        slug = f"r-{uuid.uuid4().hex[:8]}"
        wid = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'R') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = s.execute(
            text("""
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', 'x', 'drafter') RETURNING id
            """),
            {"w": wid, "e": f"{slug}@t"},
        ).scalar()
        s.commit()
        return wid, uid
    finally:
        s.close()


def _insert_board(wid: int, *, code: str, sku: str, synonyms: list[str] | None = None,
                  archived: bool = False, description: str = "Board") -> int:
    s = SessionLocal()
    try:
        mid = s.execute(text("""
            INSERT INTO board_materials(code, sku, description, workspace_id, synonyms)
            VALUES (:c, :s, :d, :w, :syn) RETURNING material_id
        """), {
            "c": code, "s": sku, "d": description, "w": wid,
            "syn": synonyms or [],
        }).scalar()
        if archived:
            s.execute(text("UPDATE board_materials SET archived_at = now() WHERE material_id = :m"), {"m": mid})
        s.commit()
        return mid
    finally:
        s.close()


def _insert_hardware(wid: int, *, sku: str, synonyms: list[str] | None = None,
                     description: str = "Hardware") -> int:
    s = SessionLocal()
    try:
        mid = s.execute(text("""
            INSERT INTO hardware_materials(sku, description, workspace_id, synonyms)
            VALUES (:s, :d, :w, :syn) RETURNING material_id
        """), {"s": sku, "d": description, "w": wid, "syn": synonyms or []}).scalar()
        s.commit()
        return mid
    finally:
        s.close()


def _insert_mapping(wid: int, *, cv_code: str, target_table: str, target_id: int, uid: int) -> None:
    s = SessionLocal()
    try:
        s.execute(text("""
            INSERT INTO cv_material_mapping(workspace_id, cv_code, target_material_table,
                                            target_material_id, created_by)
            VALUES (:w, :c, :t, :tid, :u)
        """), {"w": wid, "c": cv_code, "t": target_table, "tid": target_id, "u": uid})
        s.commit()
    finally:
        s.close()


def _make_parts(*codes: str) -> list[ParsedPart]:
    return [
        ParsedPart(
            row_index=i + 1, module_no=1, part_name=f"P{i}", qty=1,
            len_mm=720, wid_mm=580, thickness_mm=None,
            cv_code=c, edge=None, colour=None, notes=None,
        )
        for i, c in enumerate(codes)
    ]


# --- Tests -------------------------------------------------------------------

def test_mapping_hit_beats_synonym():
    wid, uid = _new_workspace_and_user()
    bmid_with_synonym = _insert_board(wid, code="18-PB", sku="18-PB-SKU", synonyms=["18-PB"])
    bmid_alt = _insert_board(wid, code="ALT", sku="ALT-SKU")
    _insert_mapping(wid, cv_code="18-PB", target_table="board_materials",
                    target_id=bmid_alt, uid=uid)

    s = SessionLocal()
    try:
        res = resolve_codes(s, wid, _make_parts("18-PB"))
    finally:
        s.close()
    assert res["18-PB"].kind == "mapped"
    # Mapping points at bmid_alt, not bmid_with_synonym.
    assert res["18-PB"].target_material_id == bmid_alt


def test_synonym_hit_when_no_mapping():
    wid, _ = _new_workspace_and_user()
    bmid = _insert_board(wid, code="18-PB", sku="18-PB-SKU", synonyms=["MY-SYN"])

    s = SessionLocal()
    try:
        res = resolve_codes(s, wid, _make_parts("MY-SYN"))
    finally:
        s.close()
    assert res["MY-SYN"].kind == "synonym_match"
    assert res["MY-SYN"].target_material_id == bmid
    assert res["MY-SYN"].target_table == "board_materials"


def test_exact_sku_hit():
    wid, _ = _new_workspace_and_user()
    bmid = _insert_board(wid, code="18-PB", sku="EXACT-SKU")

    s = SessionLocal()
    try:
        res = resolve_codes(s, wid, _make_parts("EXACT-SKU"))
    finally:
        s.close()
    assert res["EXACT-SKU"].kind == "synonym_match"
    assert res["EXACT-SKU"].target_material_id == bmid


def test_unknown_returns_unknown_kind():
    wid, _ = _new_workspace_and_user()

    s = SessionLocal()
    try:
        res = resolve_codes(s, wid, _make_parts("NEVER-SEEN"))
    finally:
        s.close()
    assert res["NEVER-SEEN"].kind == "unknown"
    assert res["NEVER-SEEN"].hint is None


def test_multiple_synonym_tables_returns_unknown_with_hint():
    wid, _ = _new_workspace_and_user()
    _insert_board(wid, code="X", sku="X1", synonyms=["DUP"])
    _insert_hardware(wid, sku="X2", synonyms=["DUP"])

    s = SessionLocal()
    try:
        res = resolve_codes(s, wid, _make_parts("DUP"))
    finally:
        s.close()
    assert res["DUP"].kind == "unknown"
    assert res["DUP"].hint == "multiple_synonym_matches"


def test_workspace_isolation():
    wid_a, uid_a = _new_workspace_and_user()
    wid_b, _ = _new_workspace_and_user()
    bmid = _insert_board(wid_a, code="18-PB", sku="18-PB-SKU")
    _insert_mapping(wid_a, cv_code="18-PB", target_table="board_materials",
                    target_id=bmid, uid=uid_a)

    s = SessionLocal()
    try:
        res = resolve_codes(s, wid_b, _make_parts("18-PB"))
    finally:
        s.close()
    assert res["18-PB"].kind == "unknown"


def test_archived_synonym_excluded():
    wid, _ = _new_workspace_and_user()
    s = SessionLocal()
    try:
        s.execute(text("""
            INSERT INTO board_materials(code, sku, description, workspace_id, synonyms, archived_at)
            VALUES ('Z', 'Z-SKU', 'Archived', :w, ARRAY['HIDDEN'], now())
        """), {"w": wid})
        s.commit()
    finally:
        s.close()

    s = SessionLocal()
    try:
        res = resolve_codes(s, wid, _make_parts("HIDDEN"))
    finally:
        s.close()
    assert res["HIDDEN"].kind == "unknown"


def test_suggest_table_heuristic():
    assert suggest_table("18-PB") == "board_materials"
    assert suggest_table("19-MELAMINE-WHITE") == "board_materials"
    assert suggest_table("700.0KC2.054.00") == "hardware_materials"
    assert suggest_table("weirdcode") is None
    assert suggest_table("ABC-123") is None
