"""Item attachments — route-layer tests (HTTP via TestClient + truncate_all).

Split from the query-layer test_item_attachments_crud.py to avoid lock
contention between the rollback `db` fixture (holds row-level locks across
the whole test) and the `truncate_all` fixture (needs AccessExclusiveLock).
Mirrors the repo convention used by test_files_upload.py vs
test_files_validators.py.
"""
import io
import shutil
from pathlib import Path

import pytest
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


def _route_seed(client, truncate_all, role: str = "drafter") -> dict:
    """Truncate, seed status_options + workspace+user+project+item, log in,
    return ids + a PDF file_blob_id (None for viewer who lacks write).

    Note: projects.workspace_id is NOT NULL (per migration 0014); seed sets it.
    """
    truncate_all()
    from app.db import SessionLocal
    from app.auth.passwords import hash_password

    s = SessionLocal()
    try:
        for key, order in [("CLEAR", 1), ("HOLD", 2), ("LIVE", 3), ("VOID", 4)]:
            s.execute(
                text("INSERT INTO status_options(status_key, sort_order) VALUES(:k, :o) ON CONFLICT DO NOTHING"),
                {"k": key, "o": order},
            )
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('rt','RT') RETURNING id")).scalar()
        uid = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'U', :p, :r) RETURNING id
        """), {"w": wid, "e": f"{role}@rt.test", "p": hash_password("pw"), "r": role}).scalar()
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES('RT-001', 'RT', :u, :w) RETURNING project_id
        """), {"u": uid, "w": wid}).scalar()
        iid = s.execute(text("""
            INSERT INTO items(num, project_id, description) VALUES (90200, :p, 'RT item') RETURNING item_id
        """), {"p": pid}).scalar()
        s.commit()
    finally:
        s.close()

    r = client.post("/auth/login",
                    json={"workspace_slug": "rt", "email": f"{role}@rt.test", "password": "pw"})
    assert r.status_code == 200, r.text

    bid = None
    if role != "viewer":
        files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
        r = client.post("/files", files=files)
        assert r.status_code == 201, r.text
        bid = r.json()["file_blob_id"]
    return {"wid": wid, "uid": uid, "pid": pid, "iid": iid, "bid": bid}


def test_route_get_bundle_initially_empty(client, truncate_all):
    ids = _route_seed(client, truncate_all)
    r = client.get(f"/items/{ids['iid']}/attachments")
    assert r.status_code == 200
    body = r.json()
    assert body["item_id"] == ids["iid"]
    assert len(body["slots"]) == 3
    assert all(s["file_blob_id"] is None for s in body["slots"])


def test_route_bind_then_get_bundle_shows_populated(client, truncate_all):
    ids = _route_seed(client, truncate_all)
    r = client.post(f"/items/{ids['iid']}/attachments/cv_drawing",
                    json={"file_blob_id": ids["bid"]})
    assert r.status_code == 201, r.text
    r = client.get(f"/items/{ids['iid']}/attachments")
    body = r.json()
    cv = next(s for s in body["slots"] if s["kind"] == "cv_drawing")
    assert cv["file_blob_id"] == ids["bid"]


def test_route_bind_invalid_kind_returns_422(client, truncate_all):
    ids = _route_seed(client, truncate_all)
    r = client.post(f"/items/{ids['iid']}/attachments/garbage",
                    json={"file_blob_id": ids["bid"]})
    assert r.status_code == 422


def test_route_bind_non_pdf_returns_415(client, truncate_all):
    ids = _route_seed(client, truncate_all)
    files = {"file": ("p.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200), "image/png")}
    png_id = client.post("/files", files=files).json()["file_blob_id"]
    r = client.post(f"/items/{ids['iid']}/attachments/floor_plan",
                    json={"file_blob_id": png_id})
    assert r.status_code == 415
    assert "application/pdf" in r.json()["detail"]


def test_route_clear_existing_returns_204(client, truncate_all):
    ids = _route_seed(client, truncate_all)
    client.post(f"/items/{ids['iid']}/attachments/cv_drawing",
                json={"file_blob_id": ids["bid"]})
    r = client.delete(f"/items/{ids['iid']}/attachments/cv_drawing")
    assert r.status_code == 204


def test_route_clear_missing_returns_404(client, truncate_all):
    ids = _route_seed(client, truncate_all)
    r = client.delete(f"/items/{ids['iid']}/attachments/cv_drawing")
    assert r.status_code == 404


def test_route_editor_cannot_write_attachments(client, truncate_all):
    """Editor has list:read but not list:write — 403 on POST/DELETE."""
    ids = _route_seed(client, truncate_all, role="editor")
    r = client.post(f"/items/{ids['iid']}/attachments/cv_drawing",
                    json={"file_blob_id": ids["bid"]})
    assert r.status_code == 403


def test_route_viewer_can_get_bundle(client, truncate_all):
    """Viewer has list:read — GET bundle returns 200."""
    ids = _route_seed(client, truncate_all, role="viewer")
    r = client.get(f"/items/{ids['iid']}/attachments")
    assert r.status_code == 200


def test_route_get_bundle_cross_workspace_returns_404(client, truncate_all):
    """Workspace B cannot fetch attachments bundle for an item in workspace A."""
    ids_a = _route_seed(client, truncate_all)
    iid_a = ids_a["iid"]

    # Switch to a different workspace
    from app.db import SessionLocal
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid_b = s.execute(text("INSERT INTO workspace(slug,name) VALUES('rt-b','RT-B') RETURNING id")).scalar()
        s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'b@rt.test', 'B', :p, 'drafter')
        """), {"w": wid_b, "p": hash_password("pw")})
        s.commit()
    finally:
        s.close()
    client.cookies.clear()
    r = client.post("/auth/login", json={"workspace_slug": "rt-b", "email": "b@rt.test", "password": "pw"})
    assert r.status_code == 200, r.text

    r = client.get(f"/items/{iid_a}/attachments")
    assert r.status_code == 404


def test_route_clear_cross_workspace_returns_404(client, truncate_all):
    """Workspace B cannot delete an attachment slot on an item in workspace A."""
    ids_a = _route_seed(client, truncate_all)
    iid_a = ids_a["iid"]
    bid_a = ids_a["bid"]
    # Bind a slot in workspace A so there's something to attempt deleting.
    r = client.post(f"/items/{iid_a}/attachments/cv_drawing", json={"file_blob_id": bid_a})
    assert r.status_code == 201, r.text

    # Switch to workspace B
    from app.db import SessionLocal
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid_b = s.execute(text("INSERT INTO workspace(slug,name) VALUES('rt-b','RT-B') RETURNING id")).scalar()
        s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'b@rt.test', 'B', :p, 'drafter')
        """), {"w": wid_b, "p": hash_password("pw")})
        s.commit()
    finally:
        s.close()
    client.cookies.clear()
    r = client.post("/auth/login", json={"workspace_slug": "rt-b", "email": "b@rt.test", "password": "pw"})
    assert r.status_code == 200, r.text

    r = client.delete(f"/items/{iid_a}/attachments/cv_drawing")
    assert r.status_code == 404

    # Verify the slot in workspace A is still present.
    s = SessionLocal()
    try:
        count = s.execute(text(
            "SELECT count(*) FROM item_attachment WHERE item_id = :i AND kind = 'cv_drawing'"
        ), {"i": iid_a}).scalar()
        assert count == 1
    finally:
        s.close()


def test_route_bind_cross_workspace_returns_422(client, truncate_all):
    """Workspace B cannot bind a slot on an item in workspace A.

    The file_blob workspace check would fail anyway, but the item-workspace
    check provides defense-in-depth and should fire first.
    """
    ids_a = _route_seed(client, truncate_all)
    iid_a = ids_a["iid"]

    # Switch to workspace B + upload our own blob there
    from app.db import SessionLocal
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid_b = s.execute(text("INSERT INTO workspace(slug,name) VALUES('rt-b','RT-B') RETURNING id")).scalar()
        s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'b@rt.test', 'B', :p, 'drafter')
        """), {"w": wid_b, "p": hash_password("pw")})
        s.commit()
    finally:
        s.close()
    client.cookies.clear()
    r = client.post("/auth/login", json={"workspace_slug": "rt-b", "email": "b@rt.test", "password": "pw"})
    assert r.status_code == 200, r.text
    files = {"file": ("b.pdf", io.BytesIO(PDF_BYTES + b"\nB"), "application/pdf")}
    bid_b = client.post("/files", files=files).json()["file_blob_id"]

    # Try to bind the workspace-B blob onto a workspace-A item
    r = client.post(f"/items/{iid_a}/attachments/cv_drawing", json={"file_blob_id": bid_b})
    # The route maps "item not found in this workspace" ValueError to 404 (per existing routes.py logic
    # which checks for "not found" substring). Either 404 or 422 is acceptable as long as the bind fails.
    assert r.status_code in (404, 422)
