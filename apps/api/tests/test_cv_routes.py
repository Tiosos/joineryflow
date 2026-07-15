"""Tests for the CV import routes (sub-project #7b).

Covers preview + commit + history + RBAC + cross-workspace + size caps.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

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


def _login(role: str = "drafter"):
    suffix = uuid.uuid4().hex[:8]
    slug = f"r-{suffix}"
    email = f"u-{suffix}@example.com"
    s = SessionLocal()
    try:
        wid = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'R') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = s.execute(
            text("""
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, :r) RETURNING id
            """),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
        ).scalar()
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES (:pc, :pn, :u, :w) RETURNING project_id
        """), {"pc": f"P-{suffix}", "pn": f"Project {suffix}", "w": wid, "u": uid}).scalar()
        # items.num is UNIQUE — derive a stable-but-unique value from the
        # workspace id (same workspace -> same num is not possible since this
        # fixture only creates one item per workspace).
        iid = s.execute(text("""
            INSERT INTO items(num, project_id, description)
            VALUES (:n, :p, 'Item 1') RETURNING item_id
        """), {"n": wid * 1000 + 1, "p": pid}).scalar()
        s.commit()
    finally:
        s.close()
    c = TestClient(app)
    r = c.post("/auth/login",
               json={"workspace_slug": slug, "email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    return c, wid, uid, pid, iid


def _seed_board_with_mapping(wid: int, uid: int, *, code: str, sku: str,
                             cv_code: str | None = None) -> int:
    s = SessionLocal()
    try:
        bmid = s.execute(text("""
            INSERT INTO board_materials(code, sku, description, workspace_id)
            VALUES (:c, :s, 'Board', :w) RETURNING material_id
        """), {"c": code, "s": sku, "w": wid}).scalar()
        if cv_code is not None:
            s.execute(text("""
                INSERT INTO cv_material_mapping(workspace_id, cv_code,
                    target_material_table, target_material_id, created_by)
                VALUES (:w, :code, 'board_materials', :m, :u)
            """), {"w": wid, "code": cv_code, "m": bmid, "u": uid})
        s.commit()
        return bmid
    finally:
        s.close()


# --- Tests -------------------------------------------------------------------


def test_drafter_can_preview():
    c, wid, uid, pid, iid = _login("drafter")
    _seed_board_with_mapping(wid, uid, code="18-PB", sku="18-PB", cv_code="18-PB")

    csv = (
        "Module,Part Name,Qty,Length,Width,Material\n"
        "1,Side L,1,720,580,18-PB\n"
        "1,Side R,1,720,580,18-PB\n"
    )
    r = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["row_count"] == 2
    assert body["summary"]["mapped"] == 2
    assert body["summary"]["unknown"] == 0
    assert body["run_id"] > 0


def test_preview_writes_audit_event():
    c, wid, uid, pid, iid = _login("drafter")
    _seed_board_with_mapping(wid, uid, code="18-PB", sku="18-PB", cv_code="18-PB")

    csv = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,18-PB\n"
    r = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    run_id = r.json()["run_id"]

    s = SessionLocal()
    try:
        row = s.execute(text("""
            SELECT event, target FROM audit_log
            WHERE event = 'cv.import.preview' AND target = :t
        """), {"t": str(run_id)}).first()
    finally:
        s.close()
    assert row is not None
    assert row[0] == "cv.import.preview"


def test_preview_unknown_code_classifies_as_unknown():
    c, wid, uid, pid, iid = _login("drafter")
    csv = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,99-MYSTERY\n"
    r = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    body = r.json()
    assert body["summary"]["unknown"] == 1
    assert any(u["cv_code"] == "99-MYSTERY" for u in body["unknown_codes"])


def test_preview_invalid_numeric_returns_in_errors():
    c, wid, uid, pid, iid = _login("drafter")
    csv = (
        "Module,Part Name,Qty,Length,Width,Material\n"
        "1,Bad,1,abc,580,18-PB\n"
    )
    r = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    body = r.json()
    assert body["summary"]["invalid"] == 1
    assert body["errors"][0]["code"] == "INVALID_NUMERIC"


def test_preview_missing_required_column_returns_422():
    c, wid, uid, pid, iid = _login("drafter")
    csv = "Module,Part Name,Qty,Length,Width\n1,A,1,720,580\n"
    r = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    assert r.status_code == 422


def test_preview_file_too_large_is_rejected():
    c, wid, uid, pid, iid = _login("drafter")
    big_body = "Module,Part Name,Qty,Length,Width,Material\n" + (
        "1,A,1,720,580,18-PB\n" * 60_000  # ~1.2 MB, over MAX_CSV_BYTES (1 MiB)
    )
    r = c.post(f"/items/{iid}/cv-imports/preview", data={"body": big_body})
    # The app's own guard returns 415 FILE_TOO_LARGE, but Starlette's form
    # size limit (also ~1 MiB) can reject an oversized form field with a
    # generic 400 *before* the handler runs — which layer wins depends on the
    # installed starlette/python-multipart version. Either way the contract
    # holds: oversized input is rejected. Assert the structured code when the
    # app guard is the one that fired.
    assert r.status_code in (400, 415)
    if r.status_code == 415:
        assert r.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_drafter_can_commit_simple():
    c, wid, uid, pid, iid = _login("drafter")
    _seed_board_with_mapping(wid, uid, code="18-PB", sku="18-PB", cv_code="18-PB")

    csv = (
        "Module,Part Name,Qty,Length,Width,Material\n"
        "1,Side L,1,720,580,18-PB\n"
        "1,Side R,1,720,580,18-PB\n"
    )
    p = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    run_id = p.json()["run_id"]

    r = c.post(f"/items/{iid}/cv-imports/{run_id}/commit",
               json={"resolutions": [], "replace": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["modules_created"] == 1
    assert body["parts_created"] == 2

    s = SessionLocal()
    try:
        status = s.execute(text(
            "SELECT status FROM cv_import_run WHERE cv_import_run_id = :r"
        ), {"r": run_id}).scalar()
    finally:
        s.close()
    assert status == "committed"


def test_commit_with_create_new_inserts_catalog_row():
    c, wid, uid, pid, iid = _login("drafter")
    csv = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,99-NEW\n"
    p = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    run_id = p.json()["run_id"]

    body = {
        "resolutions": [{
            "action": "create_new",
            "cv_code": "99-NEW",
            "target_table": "board_materials",
            "sku": "99-NEW",
            "description": "New board",
        }],
        "replace": False,
    }
    r = c.post(f"/items/{iid}/cv-imports/{run_id}/commit", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["catalog_rows_created"] == 1
    assert out["mappings_created"] == 1
    assert out["parts_created"] == 1

    s = SessionLocal()
    try:
        bm = s.execute(text(
            "SELECT material_id FROM board_materials WHERE sku = '99-NEW' AND workspace_id = :w"
        ), {"w": wid}).scalar()
        m = s.execute(text(
            "SELECT target_material_id FROM cv_material_mapping "
            "WHERE workspace_id = :w AND cv_code = '99-NEW'"
        ), {"w": wid}).scalar()
    finally:
        s.close()
    assert bm is not None
    assert m == bm


def test_commit_re_import_without_replace_returns_409():
    c, wid, uid, pid, iid = _login("drafter")
    _seed_board_with_mapping(wid, uid, code="18-PB", sku="18-PB", cv_code="18-PB")
    csv = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,18-PB\n"

    p = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    run1 = p.json()["run_id"]
    c.post(f"/items/{iid}/cv-imports/{run1}/commit",
           json={"resolutions": [], "replace": False})

    p2 = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    run2 = p2.json()["run_id"]
    r = c.post(f"/items/{iid}/cv-imports/{run2}/commit",
               json={"resolutions": [], "replace": False})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ITEM_NOT_EMPTY"


def test_commit_re_import_with_replace_wipes_and_re_inserts():
    c, wid, uid, pid, iid = _login("drafter")
    _seed_board_with_mapping(wid, uid, code="18-PB", sku="18-PB", cv_code="18-PB")
    csv = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,18-PB\n"

    p1 = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    c.post(f"/items/{iid}/cv-imports/{p1.json()['run_id']}/commit",
           json={"resolutions": [], "replace": False})

    p2 = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    run2 = p2.json()["run_id"]
    r = c.post(f"/items/{iid}/cv-imports/{run2}/commit?mode=replace",
               json={"resolutions": [], "replace": True})
    assert r.status_code == 200, r.text

    s = SessionLocal()
    try:
        rows = s.execute(text("""
            SELECT event FROM audit_log
            WHERE event = 'cv.import.replace_wipe' AND target = :t
        """), {"t": str(run2)}).all()
    finally:
        s.close()
    assert len(rows) == 1


def test_viewer_cannot_preview():
    c, wid, uid, pid, iid = _login("viewer")
    csv = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,18-PB\n"
    r = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    assert r.status_code == 403


def test_purchase_officer_cannot_preview():
    c, wid, uid, pid, iid = _login("purchase_officer")
    csv = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,18-PB\n"
    r = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    assert r.status_code == 403


def test_cross_workspace_get_run_returns_404():
    c_a, wid_a, uid_a, pid_a, iid_a = _login("drafter")
    _seed_board_with_mapping(wid_a, uid_a, code="18-PB", sku="18-PB", cv_code="18-PB")
    csv = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,18-PB\n"
    p = c_a.post(f"/items/{iid_a}/cv-imports/preview", data={"body": csv})
    run_id = p.json()["run_id"]

    c_b, _, _, _, _ = _login("drafter")
    r = c_b.get(f"/cv-imports/{run_id}")
    assert r.status_code == 404


def test_commit_with_skip_drops_rows():
    c, wid, uid, pid, iid = _login("drafter")
    _seed_board_with_mapping(wid, uid, code="18-PB", sku="18-PB", cv_code="18-PB")
    csv = (
        "Module,Part Name,Qty,Length,Width,Material\n"
        "1,Keep1,1,720,580,18-PB\n"
        "1,Skip,1,720,580,99-DROP\n"
        "1,Keep2,1,720,580,18-PB\n"
    )
    p = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    run_id = p.json()["run_id"]

    body = {
        "resolutions": [{"action": "skip", "cv_code": "99-DROP"}],
        "replace": False,
    }
    r = c.post(f"/items/{iid}/cv-imports/{run_id}/commit", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["parts_created"] == 2


def test_get_history_orders_by_started_at_desc():
    c, wid, uid, pid, iid = _login("drafter")
    _seed_board_with_mapping(wid, uid, code="18-PB", sku="18-PB", cv_code="18-PB")
    csv = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,18-PB\n"

    r1 = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})
    r2 = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv})

    h = c.get(f"/items/{iid}/cv-imports")
    assert h.status_code == 200
    rows = h.json()
    assert len(rows) >= 2
    assert rows[0]["cv_import_run_id"] == r2.json()["run_id"]
    assert rows[1]["cv_import_run_id"] == r1.json()["run_id"]
