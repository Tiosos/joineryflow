"""Print routes — cutlist.pdf, hardware.pdf, combined.pdf."""
import io
import shutil
from pathlib import Path

import pytest
import pypdf
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app


PDF_BYTES = b"%PDF-1.4\n%abc\n" + b"x" * 100 + b"\n%%EOF\n"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_disk(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


def _seed_full_item(client, truncate_all, *, with_painting: bool = False, attachments: int = 0,
                    role: str = "drafter") -> dict:
    """Seed workspace+user+project+item+module+parts. Optionally bind N attachments.

    Note: projects.workspace_id is NOT NULL (per migration 0014); seed sets it.
    Status options must be seeded for items.status default 'CLEAR' to satisfy FK.
    """
    truncate_all()
    from app.db import SessionLocal
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        for key, order in [("CLEAR", 1), ("HOLD", 2), ("LIVE", 3), ("VOID", 4)]:
            s.execute(text("INSERT INTO status_options(status_key, sort_order) VALUES(:k, :o) ON CONFLICT DO NOTHING"),
                      {"k": key, "o": order})
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('pr','PR') RETURNING id")).scalar()
        uid = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'U', :p, :r) RETURNING id
        """), {"w": wid, "e": f"{role}@pr.test", "p": hash_password("pw"), "r": role}).scalar()
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES('PR-001','PR',:u,:w) RETURNING project_id
        """), {"u": uid, "w": wid}).scalar()
        iid = s.execute(text("""
            INSERT INTO items(num, project_id, description, rm_no, rm_desc, stage, lister)
            VALUES (90300, :p, 'PR Test Item', '1.01', 'Kitchen', 'Joinery Lab', 'Rin Park')
            RETURNING item_id
        """), {"p": pid}).scalar()
        mid = s.execute(text("""
            INSERT INTO modules(item_id, module_no, name) VALUES (:i, 'M1', 'Module 1') RETURNING module_id
        """), {"i": iid}).scalar()
        s.execute(text("""
            INSERT INTO parts(module_id, qty, part_name, len_mm, wid_mm, paint_instruction)
            VALUES (:m, 2, 'Side panel', 720, 580, 'NONE')
        """), {"m": mid})
        s.execute(text("""
            INSERT INTO parts(module_id, qty, part_name, len_mm, wid_mm, paint_instruction)
            VALUES (:m, 1, 'Door', 715, 395, :pi)
        """), {"m": mid, "pi": "DOUBLE_SIDE" if with_painting else "NONE"})
        s.commit()
    finally:
        s.close()
    r = client.post("/auth/login",
                    json={"workspace_slug": "pr", "email": f"{role}@pr.test", "password": "pw"})
    assert r.status_code == 200, r.text

    bid_for = []
    kinds = ("cv_drawing", "floor_plan", "site_measure")
    for n in range(attachments):
        files = {"file": (f"a{n}.pdf", io.BytesIO(PDF_BYTES + bytes([n])), "application/pdf")}
        bid = client.post("/files", files=files).json()["file_blob_id"]
        bid_for.append(bid)
        client.post(f"/items/{iid}/attachments/{kinds[n]}", json={"file_blob_id": bid})

    return {"wid": wid, "uid": uid, "pid": pid, "iid": iid, "attachment_blob_ids": bid_for}


def test_print_cutlist_returns_pdf(client, truncate_all):
    ids = _seed_full_item(client, truncate_all)
    r = client.get(f"/items/{ids['iid']}/cutlist.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:5] == b"%PDF-"
    assert "inline" in r.headers["content-disposition"]
    assert "no-store" in r.headers.get("cache-control", "")


def test_print_hardware_returns_pdf(client, truncate_all):
    ids = _seed_full_item(client, truncate_all)
    r = client.get(f"/items/{ids['iid']}/hardware.pdf")
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"


def test_print_combined_with_zero_attachments_renders_three_placeholders(client, truncate_all):
    ids = _seed_full_item(client, truncate_all, attachments=0)
    r = client.get(f"/items/{ids['iid']}/combined.pdf")
    assert r.status_code == 200
    pdf = pypdf.PdfReader(io.BytesIO(r.content))
    assert len(pdf.pages) >= 6


def test_print_combined_with_three_attachments_includes_them(client, truncate_all):
    ids = _seed_full_item(client, truncate_all, attachments=3)
    r = client.get(f"/items/{ids['iid']}/combined.pdf")
    assert r.status_code == 200
    pdf = pypdf.PdfReader(io.BytesIO(r.content))
    assert len(pdf.pages) >= 6


def test_print_combined_includes_painting_when_paint_required(client, truncate_all):
    ids = _seed_full_item(client, truncate_all, with_painting=True, attachments=0)
    r = client.get(f"/items/{ids['iid']}/combined.pdf")
    assert r.status_code == 200
    pdf = pypdf.PdfReader(io.BytesIO(r.content))
    assert len(pdf.pages) >= 7


def test_print_combined_skips_painting_when_no_paint_required(client, truncate_all):
    ids_no_paint = _seed_full_item(client, truncate_all, with_painting=False, attachments=0)
    r = client.get(f"/items/{ids_no_paint['iid']}/combined.pdf")
    pages_no = len(pypdf.PdfReader(io.BytesIO(r.content)).pages)

    ids_paint = _seed_full_item(client, truncate_all, with_painting=True, attachments=0)
    r = client.get(f"/items/{ids_paint['iid']}/combined.pdf")
    pages_yes = len(pypdf.PdfReader(io.BytesIO(r.content)).pages)

    assert pages_yes > pages_no


def test_print_item_not_found_returns_404(client, truncate_all):
    _seed_full_item(client, truncate_all)
    r = client.get("/items/9999999/cutlist.pdf")
    assert r.status_code == 404


def test_print_audit_row_written(client, truncate_all):
    ids = _seed_full_item(client, truncate_all)
    client.get(f"/items/{ids['iid']}/cutlist.pdf")
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        row = s.execute(text("""
            SELECT event, target FROM audit_log
            WHERE workspace_id = :w AND event = 'item.print.cutlist'
            ORDER BY id DESC LIMIT 1
        """), {"w": ids["wid"]}).first()
        assert row is not None
        assert row[0] == "item.print.cutlist"
        assert row[1] == str(ids["iid"])
    finally:
        s.close()


def test_print_combined_ignores_sketchup_and_cabvision(client, truncate_all):
    """Combined keeps its three attachment slots; the 0036 kinds are not merged."""
    baseline = _seed_full_item(client, truncate_all)
    baseline_pages = len(pypdf.PdfReader(io.BytesIO(
        client.get(f"/items/{baseline['iid']}/combined.pdf").content)).pages)

    ids = _seed_full_item(client, truncate_all)
    files = {"file": ("s.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    bid = client.post("/files", files=files).json()["file_blob_id"]
    for kind in ("sketchup", "cabvision"):
        assert client.post(f"/items/{ids['iid']}/attachments/{kind}",
                           json={"file_blob_id": bid}).status_code == 201
    r = client.get(f"/items/{ids['iid']}/combined.pdf")
    assert r.status_code == 200
    assert len(pypdf.PdfReader(io.BytesIO(r.content)).pages) == baseline_pages

    from app.db import SessionLocal
    s = SessionLocal()
    try:
        payload = s.execute(text("""
            SELECT payload FROM audit_log
             WHERE workspace_id = :w AND event = 'item.print.combined'
             ORDER BY id DESC LIMIT 1
        """), {"w": ids["wid"]}).scalar()
    finally:
        s.close()
    assert payload["attachments_present"] == {
        "cv_drawing": False, "floor_plan": False, "site_measure": False}
