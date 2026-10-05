"""Tests for the CV import routes (sub-project #7b).

Covers preview + commit + history + RBAC + cross-workspace + size caps.
"""
import uuid

import pytest
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal

from .helpers import login
from .conftest import truncate_fixture


_cleanup = truncate_fixture(
    "batch_allocations",
    "procurement_batches",
    "equipment_hire",
    "appliances",
    "benchtop_materials",
    "custom_made",
    "hardware_materials",
    "board_materials",
)


def _login(role: str = "drafter"):
    """A logged-in user with a project and one item -> (client, wid, uid, pid, iid)."""
    c, wid, uid = login(role, prefix="r")
    suffix = uuid.uuid4().hex[:8]
    s = SessionLocal()
    try:
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES (:pc, :pn, :u, :w) RETURNING project_id
        """), {"pc": f"P-{suffix}", "pn": f"Project {suffix}", "w": wid, "u": uid}).scalar()
        # items.num is UNIQUE — derive a stable-but-unique value from the
        # workspace id (this fixture only creates one item per workspace).
        iid = s.execute(text("""
            INSERT INTO items(num, project_id, description)
            VALUES (:n, :p, 'Item 1') RETURNING item_id
        """), {"n": wid * 1000 + 1, "p": pid}).scalar()
        s.commit()
    finally:
        s.close()
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


_BIG_CSV = "Module,Part Name,Qty,Length,Width,Material\n" + (
    "1,A,1,720,580,18-PB\n" * 60_000  # ~1.2 MB, over MAX_CSV_BYTES (1 MiB)
)


def test_preview_uploaded_file_too_large_is_415_file_too_large():
    c, wid, uid, pid, iid = _login("drafter")
    r = c.post(f"/items/{iid}/cv-imports/preview",
               files={"file": ("big.csv", _BIG_CSV.encode(), "text/csv")})
    assert r.status_code == 415
    assert r.json()["detail"]["code"] == "FILE_TOO_LARGE"


@pytest.mark.parametrize("encoding", ["urlencoded", "multipart"])
def test_preview_pasted_body_too_large_is_415_file_too_large(encoding):
    """A pasted body answers exactly like an uploaded file: Starlette's own ~1 MiB
    form-field limit must not turn it into a plain 400. `multipart` is what the
    wizard's FormData sends; `urlencoded` is the other encoding a client may use."""
    c, wid, uid, pid, iid = _login("drafter")
    kwargs = ({"data": {"body": _BIG_CSV}} if encoding == "urlencoded"
              else {"files": {"body": (None, _BIG_CSV)}})
    r = c.post(f"/items/{iid}/cv-imports/preview", **kwargs)
    assert r.status_code == 415
    assert r.json()["detail"]["code"] == "FILE_TOO_LARGE"
    assert r.json()["detail"]["max_bytes"] == 1_048_576


def test_preview_with_both_file_and_body_is_422():
    c, wid, uid, pid, iid = _login("drafter")
    csv = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,18-PB\n"
    r = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv},
               files={"file": ("a.csv", csv.encode(), "text/csv")})
    assert r.status_code == 422


def test_preview_with_neither_file_nor_body_is_422():
    c, wid, uid, pid, iid = _login("drafter")
    assert c.post(f"/items/{iid}/cv-imports/preview").status_code == 422


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


def _create_new_body(**extra):
    return {
        "resolutions": [{
            "action": "create_new", "cv_code": "99-NEW", "target_table": "board_materials",
            "sku": "99-NEW", "description": "New board", **extra,
        }],
        "replace": False,
    }


def _vendor_for(wid: int, name: str = "Plyco") -> int:
    s = SessionLocal()
    try:
        vid = s.execute(
            text("INSERT INTO vendors(workspace_id, name, category)"
                 " VALUES (:w, :n, 'Board') RETURNING vendor_id"),
            {"w": wid, "n": name},
        ).scalar()
        s.commit()
        return vid
    finally:
        s.close()


def test_create_new_can_link_the_new_row_to_a_supplier():
    c, wid, uid, pid, iid = _login("drafter")
    vid = _vendor_for(wid)
    csv = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,99-NEW\n"
    run_id = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv}).json()["run_id"]
    r = c.post(f"/items/{iid}/cv-imports/{run_id}/commit", json=_create_new_body(default_supplier_id=vid))
    assert r.status_code == 200, r.text
    s = SessionLocal()
    try:
        link = s.execute(text(
            "SELECT default_supplier_id FROM board_materials WHERE sku = '99-NEW' AND workspace_id = :w"
        ), {"w": wid}).scalar()
    finally:
        s.close()
    assert link == vid


def test_create_new_without_a_supplier_stays_unlinked():
    c, wid, uid, pid, iid = _login("drafter")
    _vendor_for(wid)
    csv = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,99-NEW\n"
    run_id = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv}).json()["run_id"]
    r = c.post(f"/items/{iid}/cv-imports/{run_id}/commit", json=_create_new_body())
    assert r.status_code == 200, r.text
    s = SessionLocal()
    try:
        link = s.execute(text(
            "SELECT default_supplier_id FROM board_materials WHERE sku = '99-NEW' AND workspace_id = :w"
        ), {"w": wid}).scalar()
    finally:
        s.close()
    assert link is None


def test_create_new_refuses_a_foreign_supplier_and_the_run_stays_a_preview():
    c, wid, uid, pid, iid = _login("drafter")
    _, other_wid, *_ = _login("drafter")
    foreign = _vendor_for(other_wid, "Foreign Co")
    csv = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,99-NEW\n"
    run_id = c.post(f"/items/{iid}/cv-imports/preview", data={"body": csv}).json()["run_id"]
    for sid in (foreign, 999999):
        r = c.post(f"/items/{iid}/cv-imports/{run_id}/commit", json=_create_new_body(default_supplier_id=sid))
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["code"] == "UNKNOWN_SUPPLIER"
        assert "Foreign Co" not in r.text
    s = SessionLocal()
    try:
        status = s.execute(text(
            "SELECT status FROM cv_import_run WHERE cv_import_run_id = :r"), {"r": run_id}).scalar()
        made = s.execute(text(
            "SELECT count(*) FROM board_materials WHERE sku = '99-NEW'")).scalar()
    finally:
        s.close()
    assert status == "preview" and made == 0
    # and the same run still commits once the supplier is dropped
    r = c.post(f"/items/{iid}/cv-imports/{run_id}/commit", json=_create_new_body())
    assert r.status_code == 200, r.text


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


_CSV = "Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,18-PB\n"


def _committed_item():
    """A drafter, their workspace, and an item that already has an imported module."""
    c, wid, uid, pid, iid = _login("drafter")
    _seed_board_with_mapping(wid, uid, code="18-PB", sku="18-PB", cv_code="18-PB")
    run = c.post(f"/items/{iid}/cv-imports/preview", data={"body": _CSV}).json()["run_id"]
    r = c.post(f"/items/{iid}/cv-imports/{run}/commit", json={"resolutions": []})
    assert r.status_code == 200, r.text
    return c, wid, uid, pid, iid


def _comment_on_modules(wid: int, uid: int, iid: int) -> int:
    """Threads on the item's module: two live top-level comments, a live reply, and
    a soft-deleted one. Returns the number that are *live* (3)."""
    s = SessionLocal()
    try:
        mid = s.execute(text("SELECT module_id FROM modules WHERE item_id = :i"),
                        {"i": iid}).scalar()

        def add(body, parent=None, deleted=False):
            return s.execute(text("""
                INSERT INTO comment(workspace_id, module_id, author_id, body,
                                    parent_comment_id, deleted_at)
                VALUES (:w, :m, :u, :b, :p, CASE WHEN :d THEN now() END)
                RETURNING comment_id
            """), {"w": wid, "m": mid, "u": uid, "b": body, "p": parent, "d": deleted}).scalar()

        first = add("first")
        add("second")
        add("a reply", parent=first)
        add("soft deleted", deleted=True)
        s.commit()
        return 3
    finally:
        s.close()


def test_replace_impact_counts_live_comments_only_and_only_this_items():
    c, wid, uid, pid, iid = _committed_item()
    live = _comment_on_modules(wid, uid, iid)
    s = SessionLocal()
    try:  # a neighbouring item's module thread is not this item's to lose
        other = s.execute(text("INSERT INTO items(num, project_id, description)"
                               " VALUES (:n, :p, 'Other') RETURNING item_id"),
                          {"n": wid * 1000 + 2, "p": pid}).scalar()
        om = s.execute(text("INSERT INTO modules(item_id, module_no) VALUES (:i, '1')"
                            " RETURNING module_id"), {"i": other}).scalar()
        s.execute(text("INSERT INTO comment(workspace_id, module_id, author_id, body)"
                       " VALUES (:w, :m, :u, 'elsewhere')"), {"w": wid, "m": om, "u": uid})
        s.commit()
    finally:
        s.close()
    r = c.get(f"/items/{iid}/cv-imports/replace-impact")
    assert r.status_code == 200, r.text
    assert r.json() == {"modules": 1, "live_comments": live}


def test_replace_impact_is_zero_without_comments():
    c, *_rest, iid = _committed_item()
    assert c.get(f"/items/{iid}/cv-imports/replace-impact").json() == {
        "modules": 1, "live_comments": 0}


def test_replace_impact_needs_cut_floor_write_and_this_workspace():
    c, wid, uid, pid, iid = _committed_item()
    viewer, *_ = _login("viewer")
    other_item = _login("viewer")[4]
    assert viewer.get(f"/items/{other_item}/cv-imports/replace-impact").status_code == 403
    theirs, *_ = _login("drafter")
    assert theirs.get(f"/items/{iid}/cv-imports/replace-impact").status_code == 404
    assert c.get("/items/99999999/cv-imports/replace-impact").status_code == 404


def test_replace_reports_and_audits_the_comments_it_deleted():
    c, wid, uid, pid, iid = _committed_item()
    live = _comment_on_modules(wid, uid, iid)
    run2 = c.post(f"/items/{iid}/cv-imports/preview", data={"body": _CSV}).json()["run_id"]
    r = c.post(f"/items/{iid}/cv-imports/{run2}/commit?mode=replace",
               json={"resolutions": [], "replace": True})
    assert r.status_code == 200, r.text
    assert r.json()["replaced_comment_count"] == live
    s = SessionLocal()
    try:
        left = s.execute(text("SELECT count(*) FROM comment WHERE workspace_id = :w"),
                         {"w": wid}).scalar()
        wipe = s.execute(text("""SELECT payload FROM audit_log
                                 WHERE event = 'cv.import.replace_wipe' AND target = :t"""),
                         {"t": str(run2)}).scalar()
        commit = s.execute(text("""SELECT payload FROM audit_log
                                   WHERE event = 'cv.import.commit' AND target = :t"""),
                           {"t": str(run2)}).scalar()
    finally:
        s.close()
    assert left == 0                       # the cascade took every row, soft-deleted too
    assert wipe["deleted_comment_count"] == live
    assert commit["replaced_comment_count"] == live


def test_first_import_reports_no_deleted_comments():
    c, wid, uid, pid, iid = _login("drafter")
    _seed_board_with_mapping(wid, uid, code="18-PB", sku="18-PB", cv_code="18-PB")
    run = c.post(f"/items/{iid}/cv-imports/preview", data={"body": _CSV}).json()["run_id"]
    r = c.post(f"/items/{iid}/cv-imports/{run}/commit", json={"resolutions": []})
    assert r.json()["replaced_comment_count"] == 0


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


# --- Locks on the item refuse a commit ---------------------------------------


def _lock_item(iid: int, uid: int, kind: str, owner_id: int | None = None) -> None:
    s = SessionLocal()
    try:
        if kind == "hard":
            s.execute(text("UPDATE items SET hard_locked_at = now(), hard_locked_by = :u"
                           " WHERE item_id = :i"), {"u": uid, "i": iid})
        elif kind == "approval":
            s.execute(text("INSERT INTO status_options(status_key, sort_order)"
                           " VALUES ('APPROVED', 5) ON CONFLICT DO NOTHING"))
            s.execute(text("UPDATE items SET status = 'APPROVED' WHERE item_id = :i"), {"i": iid})
        else:
            s.execute(text("UPDATE items SET item_locked = true, cutlist_owner_id = :o"
                           " WHERE item_id = :i"), {"o": owner_id, "i": iid})
        s.commit()
    finally:
        s.close()


def _unlock_item(iid: int) -> None:
    s = SessionLocal()
    try:
        s.execute(text("UPDATE items SET hard_locked_at = NULL, hard_locked_by = NULL,"
                       " status = 'CLEAR', item_locked = false WHERE item_id = :i"), {"i": iid})
        s.commit()
    finally:
        s.close()


def _other_user(wid: int, role: str) -> int:
    s = SessionLocal()
    try:
        uid = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'Olive Owner', :p, :r) RETURNING id
        """), {"w": wid, "e": f"o-{uuid.uuid4().hex[:8]}@example.com",
               "p": hash_password("pw"), "r": role}).scalar()
        s.commit()
        return uid
    finally:
        s.close()


def _cv_state(iid: int, run_id: int) -> tuple:
    s = SessionLocal()
    try:
        return (
            s.execute(text("SELECT count(*) FROM modules WHERE item_id = :i"), {"i": iid}).scalar(),
            s.execute(text("SELECT count(*) FROM parts WHERE module_id IN"
                           " (SELECT module_id FROM modules WHERE item_id = :i)"), {"i": iid}).scalar(),
            s.execute(text("SELECT status FROM cv_import_run WHERE cv_import_run_id = :r"),
                      {"r": run_id}).scalar(),
        )
    finally:
        s.close()


_EXPECTED_LOCK = {
    "hard": lambda uid, owner: {"code": "HARD_LOCKED", "locked_by": uid},
    "approval": lambda uid, owner: {"code": "APPROVAL_LOCKED"},
    "controlled": lambda uid, owner: {"code": "ITEM_LOCKED", "owner_id": owner,
                                      "owner_name": "Olive Owner"},
}


@pytest.mark.parametrize("kind", ["hard", "approval", "controlled"])
@pytest.mark.parametrize("mode", ["first_import", "replace"])
def test_locked_item_refuses_cv_commit_and_leaves_the_run_pending(kind, mode):
    if mode == "replace":
        c, wid, uid, pid, iid = _committed_item()     # already holds an imported module
        url_suffix = "?mode=replace"
        body = {"resolutions": [], "replace": True}
    else:
        c, wid, uid, pid, iid = _login("drafter")
        _seed_board_with_mapping(wid, uid, code="18-PB", sku="18-PB", cv_code="18-PB")
        url_suffix, body = "", {"resolutions": []}
    owner = _other_user(wid, "drafter")
    run = c.post(f"/items/{iid}/cv-imports/preview", data={"body": _CSV}).json()["run_id"]
    before = _cv_state(iid, run)
    _lock_item(iid, uid, kind, owner_id=owner)

    r = c.post(f"/items/{iid}/cv-imports/{run}/commit{url_suffix}", json=body)
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == _EXPECTED_LOCK[kind](uid, owner)
    assert _cv_state(iid, run) == before          # nothing written, run still 'preview'
    assert before[2] == "preview"

    # the same run commits once the lock is gone
    _unlock_item(iid)
    r = c.post(f"/items/{iid}/cv-imports/{run}/commit{url_suffix}", json=body)
    assert r.status_code == 200, r.text
    assert _cv_state(iid, run)[2] == "committed"


def test_owner_and_manager_pass_a_controlled_lock_on_cv_commit():
    c, wid, uid, pid, iid = _login("drafter")
    _seed_board_with_mapping(wid, uid, code="18-PB", sku="18-PB", cv_code="18-PB")
    # the lock is held by the caller themselves...
    _lock_item(iid, uid, "controlled", owner_id=uid)
    run = c.post(f"/items/{iid}/cv-imports/preview", data={"body": _CSV}).json()["run_id"]
    assert c.post(f"/items/{iid}/cv-imports/{run}/commit",
                  json={"resolutions": []}).status_code == 200


def test_manager_passes_someone_elses_controlled_lock_on_cv_commit():
    c, wid, uid, pid, iid = _login("manager")
    _seed_board_with_mapping(wid, uid, code="18-PB", sku="18-PB", cv_code="18-PB")
    _lock_item(iid, uid, "controlled", owner_id=_other_user(wid, "drafter"))
    run = c.post(f"/items/{iid}/cv-imports/preview", data={"body": _CSV}).json()["run_id"]
    assert c.post(f"/items/{iid}/cv-imports/{run}/commit",
                  json={"resolutions": []}).status_code == 200
