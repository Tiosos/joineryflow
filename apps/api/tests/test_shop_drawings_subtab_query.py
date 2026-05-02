"""Subtab membership SQL — fixture-driven, no HTTP."""
from datetime import datetime

import pytest
from sqlalchemy import text

from app.shop_drawings.queries import list_drawings_by_subtab


def _seed_minimal(db, workspace_id: int) -> dict:
    """Insert one project, one user, three blobs (one per drawing fixture)."""
    uid = db.execute(text("""
        INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
        VALUES (:w, 'sd@test', 'SD', 'x', 'drafter') RETURNING id
    """), {"w": workspace_id}).scalar()
    pid = db.execute(text("""
        INSERT INTO projects(project_code, name, pm_id, workspace_id)
        VALUES ('ALF-001', 'Alfred', :u, :w) RETURNING project_id
    """), {"u": uid, "w": workspace_id}).scalar()
    blobs = []
    for i, sha in enumerate(["aa" * 32, "bb" * 32, "cc" * 32]):
        bid = db.execute(text("""
            INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename, storage_key, uploaded_by)
            VALUES (:w, :s, 'application/pdf', 100, :n, :k, :u) RETURNING file_blob_id
        """), {"w": workspace_id, "s": sha, "n": f"f{i}.pdf", "k": f"k/{sha[:2]}/{sha}", "u": uid}).scalar()
        blobs.append(bid)
    db.flush()
    return {"uid": uid, "pid": pid, "blobs": blobs}


def test_current_subtab_returns_drawings_with_approved_current_revision(db, workspace_id):
    seed = _seed_minimal(db, workspace_id)
    # Drawing 1: rev 1 approved (set as current); should appear in Current.
    did = db.execute(text("""
        INSERT INTO shop_drawing(project_id, title, room, created_by) VALUES (:p, 'Kitchen', 'Kitchen', :u)
        RETURNING drawing_id
    """), {"p": seed["pid"], "u": seed["uid"]}).scalar()
    rid = db.execute(text("""
        INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by, reviewed_by, reviewed_at)
        VALUES (:d, 1, :b, 'approved', :u, :u, now()) RETURNING revision_id
    """), {"d": did, "b": seed["blobs"][0], "u": seed["uid"]}).scalar()
    db.execute(text("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
               {"r": rid, "d": did})
    db.flush()

    rows = list_drawings_by_subtab(db, project_id=seed["pid"], subtab="current")
    assert len(rows) == 1
    assert rows[0]["drawing_id"] == did


def test_in_review_subtab_returns_drawings_whose_latest_is_draft_or_pending(db, workspace_id):
    seed = _seed_minimal(db, workspace_id)
    # Drawing with only a draft revision.
    did_draft = db.execute(text("""
        INSERT INTO shop_drawing(project_id, title, room, created_by) VALUES (:p, 'Island', 'Kitchen', :u)
        RETURNING drawing_id
    """), {"p": seed["pid"], "u": seed["uid"]}).scalar()
    db.execute(text("""
        INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by)
        VALUES (:d, 1, :b, 'draft', :u)
    """), {"d": did_draft, "b": seed["blobs"][0], "u": seed["uid"]})

    # Drawing with approved rev 1 + pending rev 2 → appears in BOTH subtabs.
    did_both = db.execute(text("""
        INSERT INTO shop_drawing(project_id, title, room, created_by) VALUES (:p, 'Vanity', 'Bathroom', :u)
        RETURNING drawing_id
    """), {"p": seed["pid"], "u": seed["uid"]}).scalar()
    rid1 = db.execute(text("""
        INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by, reviewed_by, reviewed_at)
        VALUES (:d, 1, :b, 'approved', :u, :u, now()) RETURNING revision_id
    """), {"d": did_both, "b": seed["blobs"][1], "u": seed["uid"]}).scalar()
    db.execute(text("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
               {"r": rid1, "d": did_both})
    db.execute(text("""
        INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by)
        VALUES (:d, 2, :b, 'pending', :u)
    """), {"d": did_both, "b": seed["blobs"][2], "u": seed["uid"]})
    db.flush()

    rows = list_drawings_by_subtab(db, project_id=seed["pid"], subtab="in_review")
    drawing_ids = {r["drawing_id"] for r in rows}
    assert did_draft in drawing_ids
    assert did_both in drawing_ids
    assert len(rows) == 2


def test_archive_subtab_returns_only_archived(db, workspace_id):
    seed = _seed_minimal(db, workspace_id)
    did = db.execute(text("""
        INSERT INTO shop_drawing(project_id, title, room, created_by, archived_at, archived_by)
        VALUES (:p, 'Pantry', 'Kitchen', :u, now(), :u) RETURNING drawing_id
    """), {"p": seed["pid"], "u": seed["uid"]}).scalar()
    db.execute(text("""
        INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by)
        VALUES (:d, 1, :b, 'approved', :u)
    """), {"d": did, "b": seed["blobs"][0], "u": seed["uid"]})
    db.flush()

    rows = list_drawings_by_subtab(db, project_id=seed["pid"], subtab="archive")
    assert len(rows) == 1
    assert rows[0]["drawing_id"] == did


def test_filters_apply_room_and_search(db, workspace_id):
    seed = _seed_minimal(db, workspace_id)
    # Two approved drawings, different rooms + titles.
    for room, title, blob in [("Kitchen", "Kitchen base run", seed["blobs"][0]),
                               ("Bedroom", "Walk-in robe",     seed["blobs"][1])]:
        did = db.execute(text("""
            INSERT INTO shop_drawing(project_id, title, room, created_by) VALUES (:p, :t, :r, :u)
            RETURNING drawing_id
        """), {"p": seed["pid"], "t": title, "r": room, "u": seed["uid"]}).scalar()
        rid = db.execute(text("""
            INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by, reviewed_by, reviewed_at)
            VALUES (:d, 1, :b, 'approved', :u, :u, now()) RETURNING revision_id
        """), {"d": did, "b": blob, "u": seed["uid"]}).scalar()
        db.execute(text("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
                   {"r": rid, "d": did})
    db.flush()

    rows = list_drawings_by_subtab(db, project_id=seed["pid"], subtab="current", room="Kitchen")
    assert len(rows) == 1
    assert rows[0]["title"] == "Kitchen base run"

    rows = list_drawings_by_subtab(db, project_id=seed["pid"], subtab="current", q="robe")
    assert len(rows) == 1
    assert rows[0]["title"] == "Walk-in robe"
