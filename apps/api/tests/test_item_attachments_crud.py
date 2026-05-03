"""Item attachments — query-layer tests (no HTTP, uses db fixture)."""
import pytest
from sqlalchemy import text

from app.item_attachments.queries import (
    bind_attachment,
    clear_attachment,
    get_bundle,
)


def _seed(db, workspace_id: int) -> dict:
    """Insert one project + drafter user + one item + one PDF file_blob.

    Note: projects.workspace_id is now NOT NULL (per migration 0014); this seed
    explicitly sets it to the test fixture's workspace_id.
    """
    # Seed status_options reference rows (FK target for items.status default 'CLEAR').
    for key, order in [("CLEAR", 1), ("HOLD", 2), ("LIVE", 3), ("VOID", 4)]:
        db.execute(
            text("INSERT INTO status_options(status_key, sort_order) VALUES(:k, :o) ON CONFLICT DO NOTHING"),
            {"k": key, "o": order},
        )
    uid = db.execute(text("""
        INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
        VALUES (:w, 'ia@test', 'IA', 'x', 'drafter') RETURNING id
    """), {"w": workspace_id}).scalar()
    pid = db.execute(text("""
        INSERT INTO projects(project_code, name, pm_id, workspace_id)
        VALUES('IA-001', 'IA', :u, :w) RETURNING project_id
    """), {"u": uid, "w": workspace_id}).scalar()
    iid = db.execute(text("""
        INSERT INTO items(num, project_id, description) VALUES (90100, :p, 'IA item') RETURNING item_id
    """), {"p": pid}).scalar()
    bid = db.execute(text("""
        INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename, storage_key, uploaded_by)
        VALUES (:w, 'iaaa', 'application/pdf', 200, 'cv.pdf', 'k/ia/iaaa', :u) RETURNING file_blob_id
    """), {"w": workspace_id, "u": uid}).scalar()
    db.flush()
    return {"uid": uid, "pid": pid, "iid": iid, "bid": bid}


def test_bind_inserts_slot_and_returns_metadata(db, workspace_id):
    seed = _seed(db, workspace_id)
    result = bind_attachment(
        db, item_id=seed["iid"], kind="cv_drawing",
        file_blob_id=seed["bid"], workspace_id=workspace_id, actor_id=seed["uid"],
    )
    assert result["kind"] == "cv_drawing"
    assert result["file_blob_id"] == seed["bid"]
    row = db.execute(text(
        "SELECT count(*) FROM item_attachment WHERE item_id = :i AND kind = 'cv_drawing'"
    ), {"i": seed["iid"]}).scalar()
    assert row == 1


def test_bind_replaces_existing_slot_with_upsert(db, workspace_id):
    seed = _seed(db, workspace_id)
    bind_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                    file_blob_id=seed["bid"], workspace_id=workspace_id, actor_id=seed["uid"])
    new_bid = db.execute(text("""
        INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename, storage_key, uploaded_by)
        VALUES (:w, 'iabb', 'application/pdf', 300, 'cv2.pdf', 'k/ia/iabb', :u) RETURNING file_blob_id
    """), {"w": workspace_id, "u": seed["uid"]}).scalar()
    bind_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                    file_blob_id=new_bid, workspace_id=workspace_id, actor_id=seed["uid"])
    row = db.execute(text(
        "SELECT file_blob_id FROM item_attachment WHERE item_id = :i AND kind = 'cv_drawing'"
    ), {"i": seed["iid"]}).scalar()
    assert row == new_bid
    count = db.execute(text(
        "SELECT count(*) FROM item_attachment WHERE item_id = :i"
    ), {"i": seed["iid"]}).scalar()
    assert count == 1


def test_bind_rejects_non_pdf_mime(db, workspace_id):
    seed = _seed(db, workspace_id)
    png_bid = db.execute(text("""
        INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename, storage_key, uploaded_by)
        VALUES (:w, 'iapng', 'image/png', 100, 'sketch.png', 'k/ia/iapng', :u) RETURNING file_blob_id
    """), {"w": workspace_id, "u": seed["uid"]}).scalar()
    db.flush()
    with pytest.raises(ValueError, match="application/pdf"):
        bind_attachment(db, item_id=seed["iid"], kind="floor_plan",
                        file_blob_id=png_bid, workspace_id=workspace_id, actor_id=seed["uid"])


def test_bind_rejects_cross_workspace_blob(db, workspace_id):
    seed = _seed(db, workspace_id)
    other_wid = db.execute(text("INSERT INTO workspace(slug,name) VALUES('other','O') RETURNING id")).scalar()
    other_uid = db.execute(text("""
        INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
        VALUES (:w, 'o@o.test', 'O', 'x', 'drafter') RETURNING id
    """), {"w": other_wid}).scalar()
    foreign_bid = db.execute(text("""
        INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename, storage_key, uploaded_by)
        VALUES (:w, 'oaaa', 'application/pdf', 100, 'x.pdf', 'k/o/oaaa', :u) RETURNING file_blob_id
    """), {"w": other_wid, "u": other_uid}).scalar()
    db.flush()
    with pytest.raises(ValueError, match="workspace"):
        bind_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                        file_blob_id=foreign_bid, workspace_id=workspace_id, actor_id=seed["uid"])


def test_clear_removes_slot(db, workspace_id):
    seed = _seed(db, workspace_id)
    bind_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                    file_blob_id=seed["bid"], workspace_id=workspace_id, actor_id=seed["uid"])
    deleted = clear_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                               workspace_id=workspace_id, actor_id=seed["uid"])
    assert deleted is True
    count = db.execute(text(
        "SELECT count(*) FROM item_attachment WHERE item_id = :i AND kind = 'cv_drawing'"
    ), {"i": seed["iid"]}).scalar()
    assert count == 0


def test_clear_returns_false_if_no_slot(db, workspace_id):
    seed = _seed(db, workspace_id)
    deleted = clear_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                               workspace_id=workspace_id, actor_id=seed["uid"])
    assert deleted is False


def test_get_bundle_returns_three_slots_with_populated_and_null(db, workspace_id):
    seed = _seed(db, workspace_id)
    bind_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                    file_blob_id=seed["bid"], workspace_id=workspace_id, actor_id=seed["uid"])
    bundle = get_bundle(db, item_id=seed["iid"], workspace_id=workspace_id)
    assert bundle["item_id"] == seed["iid"]
    assert len(bundle["slots"]) == 3
    by_kind = {s["kind"]: s for s in bundle["slots"]}
    assert by_kind["cv_drawing"]["file_blob_id"] == seed["bid"]
    assert by_kind["cv_drawing"]["original_filename"] == "cv.pdf"
    assert by_kind["floor_plan"]["file_blob_id"] is None
    assert by_kind["site_measure"]["file_blob_id"] is None


def test_item_delete_cascades_attachments(db, workspace_id):
    seed = _seed(db, workspace_id)
    bind_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                    file_blob_id=seed["bid"], workspace_id=workspace_id, actor_id=seed["uid"])
    db.execute(text("DELETE FROM items WHERE item_id = :i"), {"i": seed["iid"]})
    count = db.execute(text(
        "SELECT count(*) FROM item_attachment WHERE item_id = :i"
    ), {"i": seed["iid"]}).scalar()
    assert count == 0

