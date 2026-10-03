"""Duplicate a Joinery Item (Plan V1 §2, migration 0050).

Settled with the user, 2026-10-03:

  - the copy gets its OWN new cutlist (never the source's, which carries the Shop Floor
    workflow), and starts `CLEAR` (an APPROVED source must not produce an Approval-Locked
    copy), one copy per call, same project only, Joinery Items only, drafter / manager /
    admin only
  - it copies the item's fields, modules + parts, hardware lines, the five attachment
    slots, the Document Register, and the QC checklist UNCHECKED
  - it does not copy stage dates, locks, QC defects / rework, comments, queries, material
    takes, orders, or the edit history
"""
import io
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

PDF_BYTES = b"%PDF-1.4\n%abc\n" + b"x" * 100 + b"\n%%EOF\n"


@pytest.fixture(autouse=True)
def reset_disk(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    shutil.rmtree(tmp_path, ignore_errors=True)


def _sql(sql: str, params: dict | None = None):
    s = SessionLocal()
    try:
        out = s.execute(text(sql), params or {})
        rows = out.mappings().all() if out.returns_rows else None
        s.commit()
        return rows
    finally:
        s.close()


def _scalar(sql: str, params: dict | None = None):
    rows = _sql(sql, params)
    return list(rows[0].values())[0] if rows else None


ROLES = ("drafter", "manager", "admin", "editor", "viewer")


def _workspace() -> dict:
    """A workspace with one user per role and a project holding one rich Joinery Item:
    area + room, two modules with parts, a hardware line, an attachment, a register
    document, a half-ticked QC checklist, an APPROVED status and a stage date."""
    slug = f"dup-{uuid.uuid4().hex[:8]}"
    s = SessionLocal()
    try:
        for key, order in [("CLEAR", 1), ("APPROVED", 2)]:
            s.execute(text("INSERT INTO status_options(status_key, sort_order)"
                           " VALUES(:k,:o) ON CONFLICT DO NOTHING"), {"k": key, "o": order})
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'Dup') RETURNING id"),
                        {"s": slug}).scalar()
        uids = {}
        for role in ROLES:
            uids[role] = s.execute(
                text("""INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
                        VALUES(:w,:e,:n,:p,:r) RETURNING id"""),
                {"w": wid, "e": f"{role}@{slug}.test", "n": role.title(),
                 "p": hash_password("pw"), "r": role}).scalar()
        pid = s.execute(text("""INSERT INTO projects(project_code,name,workspace_id)
                                VALUES(:c,:c,:w) RETURNING project_id"""),
                        {"c": slug.upper(), "w": wid}).scalar()
        area = s.execute(text("INSERT INTO area(project_id,name,sort_order) VALUES(:p,'Level 1',1)"
                              " RETURNING area_id"), {"p": pid}).scalar()
        room = s.execute(text("INSERT INTO room(area_id,rm_no,rm_desc,sort_order)"
                              " VALUES(:a,'R01','Kitchen',1) RETURNING room_id"),
                         {"a": area}).scalar()
        cl = s.execute(text("""INSERT INTO cutlist(project_id,cutlist_no,name)
                               VALUES(:p, nextval('joinery_number_seq'), 'Source list')
                               RETURNING cutlist_id"""), {"p": pid}).scalar()
        iid = s.execute(
            text("""INSERT INTO items(num, project_id, description, qty, status, code, level,
                                      zone, painting_req, estimator_notes, jid_code, jid_color,
                                      total_amount, area_id, room_id, cutlist_id,
                                      item_locked, cutlist_owner_id, hard_locked_at,
                                      hard_locked_by, cutlist_printed)
                    VALUES (nextval('joinery_number_seq'), :p, 'Vanity', 3, 'APPROVED', 'K-9', 'L1',
                            '2', true, 'Mind the plinth', 'JID-7', '#336699',
                            1234.50, :a, :r, :cl, true, :own, now(), :own, false)
                    RETURNING item_id"""),
            {"p": pid, "a": area, "r": room, "cl": cl, "own": uids["manager"]}).scalar()
        for no, name, parts in (("M01", "Base", [("Side", 720, 560), ("Shelf", 550, 540)]),
                                ("M02", "Doors", [("Door", 700, 400)])):
            mid = s.execute(text("INSERT INTO modules(item_id,module_no,name,notes)"
                                 " VALUES(:i,:n,:name,'note') RETURNING module_id"),
                            {"i": iid, "n": no, "name": name}).scalar()
            for seq, (pn, ln, wd) in enumerate(parts, start=1):
                s.execute(text("""INSERT INTO parts(module_id,seq,qty,part_name,len_mm,wid_mm,
                                                    colour,paint_instruction,comment)
                                  VALUES(:m,:s,2,:n,:l,:w,'White','NONE','cmt')"""),
                          {"m": mid, "s": seq, "n": pn, "l": ln, "w": wd})
        hm = s.execute(text("""INSERT INTO hardware_materials(sku,description,workspace_id,unit_cost)
                               VALUES(:sku,'Damper',:w,5) RETURNING material_id"""),
                       {"w": wid, "sku": "HW-" + slug}).scalar()
        cat = s.execute(text("""INSERT INTO project_hardware_catalog(project_id,material_type,
                                                                      material_id,added_by)
                                VALUES(:p,'HARDWARE',:m,:u) RETURNING catalog_id"""),
                        {"p": pid, "m": hm, "u": uids["drafter"]}).scalar()
        s.execute(text("""INSERT INTO item_hardware_lines(item_id,seq,qty,catalog_id,note)
                          VALUES(:i,1,4,:c,'soft close')"""), {"i": iid, "c": cat})
        s.execute(text("""INSERT INTO item_stages(item_id,stage_key,due_date,done_date)
                          VALUES(:i,'DOWN','2026-01-05','2026-01-06')"""), {"i": iid})
        for label, ticked, order in (("Edges", True, 1), ("Hinges", False, 2)):
            s.execute(text("""INSERT INTO qc_checklist_item(item_id,label,is_checked,checked_by,
                                                              checked_at,sort_order,created_by)
                              VALUES(:i,:l,:t,CASE WHEN :t THEN :u END,
                                     CASE WHEN :t THEN now() END,:o,:u)"""),
                      {"i": iid, "l": label, "t": ticked, "o": order, "u": uids["drafter"]})
        rp = s.execute(text("""INSERT INTO items(num, project_id, description, status, row_type,
                                                 parent_item_id, related_part_type_key)
                               VALUES (nextval('joinery_number_seq'), :p, 'Top', 'CLEAR',
                                       'related_part', :par, 'benchtop') RETURNING item_id"""),
                       {"p": pid, "par": iid}).scalar()
        s.commit()
    finally:
        s.close()
    return {"slug": slug, "wid": wid, "pid": pid, "iid": iid, "rp": rp, "uids": uids,
            "area": area, "room": room, "cutlist": cl}


def _client(ws: dict, role: str = "drafter") -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": ws["slug"],
                                    "email": f"{role}@{ws['slug']}.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return c


def _upload(c: TestClient, name="a.pdf") -> int:
    r = c.post("/files", files={"file": (name, io.BytesIO(PDF_BYTES), "application/pdf")})
    assert r.status_code == 201, r.text
    return r.json()["file_blob_id"]


def _with_files(ws: dict) -> dict:
    """Bind one attachment and one register document to the source item."""
    c = _client(ws)
    blob = _upload(c, "plan.pdf")
    assert c.post(f"/items/{ws['iid']}/attachments/floor_plan",
                  json={"file_blob_id": blob}).status_code == 201
    # the item is APPROVED (Approval Lock), so bind through SQL — the lock is the source's
    # business, not the thing under test
    return {**ws, "blob": blob}


def _bind_files_sql(ws: dict) -> int:
    c = _client(ws)
    blob = _upload(c, "plan.pdf")
    _sql("""INSERT INTO item_attachment(item_id,kind,file_blob_id,uploaded_by)
            VALUES(:i,'floor_plan',:b,:u)""",
         {"i": ws["iid"], "b": blob, "u": ws["uids"]["drafter"]})
    _sql("""INSERT INTO item_document(item_id,file_blob_id,label,sort_order,uploaded_by)
            VALUES(:i,:b,'Site photo',3,:u)""",
         {"i": ws["iid"], "b": blob, "u": ws["uids"]["drafter"]})
    return blob


def _dup(c: TestClient, iid: int):
    return c.post(f"/items/{iid}/duplicate")


# ── the copy ──────────────────────────────────────────────────────────────────


def test_duplicate_copies_the_items_own_fields_and_links_back_to_the_source():
    ws = _workspace()
    r = _dup(_client(ws), ws["iid"])
    assert r.status_code == 201, r.text
    d = r.json()
    src_num = _scalar("SELECT num FROM items WHERE item_id=:i", {"i": ws["iid"]})
    assert d["id"] != ws["iid"]
    assert d["item_number"] != src_num                    # its own Item ID
    assert d["duplicated_from_item_id"] == ws["iid"]
    assert d["duplicated_from_item_number"] == src_num
    assert d["project_id"] == ws["pid"]
    for field in ("description", "qty", "code", "level", "zone", "estimator_notes",
                  "painting_required", "jid_code", "jid_color", "area_id", "room_id",
                  "room_no", "room_desc"):
        src = _client(ws).get(f"/items/{ws['iid']}").json()
        assert d[field] == src[field], field
    assert float(d["total_amount"]) == 1234.50


def test_the_item_id_comes_from_the_shared_sequence_and_is_unique_per_copy():
    ws = _workspace()
    c = _client(ws)
    a, b = _dup(c, ws["iid"]).json(), _dup(c, ws["iid"]).json()
    nums = {a["item_number"], b["item_number"],
            _scalar("SELECT num FROM items WHERE item_id=:i", {"i": ws["iid"]})}
    assert len(nums) == 3
    assert b["item_number"] > a["item_number"]            # advances, never reused


def test_modules_parts_hardware_attachments_documents_and_checklist_are_copied():
    ws = _workspace()
    blob = _bind_files_sql(ws)
    new = _dup(_client(ws), ws["iid"]).json()["id"]

    mods = _sql("SELECT module_id,module_no,name,notes FROM modules WHERE item_id=:i ORDER BY module_no",
                {"i": new})
    assert [(m["module_no"], m["name"], m["notes"]) for m in mods] == [
        ("M01", "Base", "note"), ("M02", "Doors", "note")]
    src_mods = {m["module_no"]: m["module_id"] for m in _sql(
        "SELECT module_id,module_no FROM modules WHERE item_id=:i", {"i": ws["iid"]})}
    assert {m["module_id"] for m in mods}.isdisjoint(src_mods.values())  # new rows, not shared

    def parts(mid):
        return [(p["seq"], p["part_name"], p["qty"], p["len_mm"], p["wid_mm"], p["colour"],
                 p["paint_instruction"], p["comment"]) for p in _sql(
            "SELECT * FROM parts WHERE module_id=:m ORDER BY seq", {"m": mid})]

    for m in mods:
        assert parts(m["module_id"]) == parts(src_mods[m["module_no"]]), m["module_no"]

    hw = _sql("SELECT seq,qty,catalog_id,note FROM item_hardware_lines WHERE item_id=:i", {"i": new})
    assert [(h["seq"], h["qty"], h["note"]) for h in hw] == [(1, 4, "soft close")]

    att = _sql("SELECT kind,file_blob_id,uploaded_by FROM item_attachment WHERE item_id=:i", {"i": new})
    assert [(a["kind"], a["file_blob_id"], a["uploaded_by"]) for a in att] == [
        ("floor_plan", blob, ws["uids"]["drafter"])]            # the same stored file, not a copy of bytes
    doc = _sql("SELECT label,sort_order,file_blob_id FROM item_document WHERE item_id=:i", {"i": new})
    assert [(d["label"], d["sort_order"], d["file_blob_id"]) for d in doc] == [("Site photo", 3, blob)]

    chk = _sql("SELECT label,is_checked,checked_by,checked_at,sort_order FROM qc_checklist_item"
               " WHERE item_id=:i ORDER BY sort_order", {"i": new})
    assert [(c["label"], c["is_checked"], c["checked_by"], c["checked_at"]) for c in chk] == [
        ("Edges", False, None, None), ("Hinges", False, None, None)]   # labels yes, ticks no


def test_the_copy_gets_its_own_new_cutlist_and_the_source_keeps_its_own():
    ws = _workspace()
    new = _dup(_client(ws), ws["iid"]).json()["id"]
    new_cl = _scalar("SELECT cutlist_id FROM items WHERE item_id=:i", {"i": new})
    assert new_cl is not None and new_cl != ws["cutlist"]
    assert _scalar("SELECT cutlist_id FROM items WHERE item_id=:i", {"i": ws["iid"]}) == ws["cutlist"]
    assert _scalar("SELECT count(*) FROM items WHERE cutlist_id=:c", {"c": new_cl}) == 1
    assert _scalar("SELECT count(*) FROM items WHERE cutlist_id=:c", {"c": ws["cutlist"]}) == 1
    assert _scalar("SELECT project_id FROM cutlist WHERE cutlist_id=:c", {"c": new_cl}) == ws["pid"]
    assert _scalar("SELECT name FROM cutlist WHERE cutlist_id=:c", {"c": new_cl}) == "Vanity"


# ── what is not copied ────────────────────────────────────────────────────────


def test_status_starts_clear_so_a_copy_of_an_approved_item_is_not_born_locked():
    ws = _workspace()
    c = _client(ws)
    d = _dup(c, ws["iid"]).json()
    assert d["status"] == "CLEAR"
    # not Approval-Locked: an ordinary edit is accepted
    r = c.patch(f"/items/{d['id']}", json={"description": "Vanity (copy)"})
    assert r.status_code == 200, r.text


def test_stage_dates_locks_and_owner_are_not_copied():
    ws = _workspace()
    new = _dup(_client(ws), ws["iid"]).json()["id"]
    assert _scalar("SELECT count(*) FROM item_stages WHERE item_id=:i", {"i": new}) == 0
    row = _sql("SELECT item_locked,cutlist_owner_id,hard_locked_at,hard_locked_by,status_symbol,"
               "omitted,fav,deleted,void_flag,field_versions FROM items WHERE item_id=:i", {"i": new})[0]
    assert (row["item_locked"], row["cutlist_owner_id"], row["hard_locked_at"],
            row["hard_locked_by"]) == (False, None, None, None)
    assert not (row["omitted"] or row["fav"] or row["deleted"] or row["void_flag"])
    assert row["status_symbol"] is None and row["field_versions"] == {}


def test_qc_defects_rework_comments_queries_and_history_are_not_copied():
    ws = _workspace()
    c = _client(ws, "manager")   # a drafter has no qc:write
    # history on the source: a defect, a comment, a query, a rework record
    assert c.post(f"/items/{ws['iid']}/qc/defects", json={"description": "Chipped edge"}).status_code == 201
    assert c.post("/comments", json={"object_type": "item", "object_id": ws["iid"],
                                     "body": "Please check"}).status_code == 201
    _sql("INSERT INTO item_query(item_id,asked_by,question) VALUES(:i,:u,'Which handle?')",
         {"i": ws["iid"], "u": ws["uids"]["drafter"]})   # the source is Hard-Locked: asking is refused
    _sql("""INSERT INTO rework(item_id,kind,cause,scope,created_by)
            VALUES(:i,'internal','c','s',:u)""", {"i": ws["iid"], "u": ws["uids"]["drafter"]})
    new = _dup(c, ws["iid"]).json()["id"]
    for table in ("qc_defect", "rework", "comment", "item_query", "material_take",
                  "worker_assignment"):
        col = "item_id"
        if table == "worker_assignment":
            continue  # keyed by cutlist since 0030 — the copy's cutlist is brand new
        assert _scalar(f"SELECT count(*) FROM {table} WHERE {col}=:i", {"i": new}) == 0, table
    log = [r["field"] for r in _sql("SELECT field FROM item_edit_log WHERE item_id=:i", {"i": new})]
    assert "_duplicate" in log and "_create" not in log
    assert not any(f.startswith(("status", "lifecycle", "query", "comment")) for f in log)


def test_duplicating_changes_nothing_on_the_source():
    ws = _workspace()
    _bind_files_sql(ws)

    def snapshot():
        return (
            _sql("SELECT * FROM items WHERE item_id=:i", {"i": ws["iid"]})[0],
            _scalar("SELECT count(*) FROM modules WHERE item_id=:i", {"i": ws["iid"]}),
            _scalar("SELECT count(*) FROM parts p JOIN modules m USING(module_id) WHERE m.item_id=:i",
                    {"i": ws["iid"]}),
            _scalar("SELECT count(*) FROM item_hardware_lines WHERE item_id=:i", {"i": ws["iid"]}),
            _scalar("SELECT count(*) FROM item_stages WHERE item_id=:i", {"i": ws["iid"]}),
            _scalar("SELECT count(*) FROM qc_checklist_item WHERE item_id=:i AND is_checked", {"i": ws["iid"]}),
            _scalar("SELECT count(*) FROM item_edit_log WHERE item_id=:i", {"i": ws["iid"]}),
        )

    before = snapshot()
    assert _dup(_client(ws), ws["iid"]).status_code == 201
    assert snapshot() == before


def test_a_locked_source_can_still_be_duplicated():
    """Duplicating only reads the source, so its locks (which guard changes to it) do not apply."""
    ws = _workspace()
    _sql("UPDATE items SET hard_locked_at=now(), hard_locked_by=:u WHERE item_id=:i",
         {"i": ws["iid"], "u": ws["uids"]["manager"]})
    assert _dup(_client(ws), ws["iid"]).status_code == 201


def test_a_duplicate_of_a_duplicate_links_to_its_immediate_source():
    ws = _workspace()
    c = _client(ws)
    first = _dup(c, ws["iid"]).json()
    second = _dup(c, first["id"]).json()
    assert second["duplicated_from_item_id"] == first["id"]
    assert second["duplicated_from_item_number"] == first["item_number"]


def test_deleting_the_source_does_not_delete_its_copies():
    ws = _workspace()
    new = _dup(_client(ws), ws["iid"]).json()["id"]
    _sql("DELETE FROM items WHERE item_id=:rp", {"rp": ws["rp"]})   # its related part goes first
    _sql("DELETE FROM items WHERE item_id=:i", {"i": ws["iid"]})
    row = _sql("SELECT item_id, duplicated_from_item_id FROM items WHERE item_id=:i", {"i": new})
    assert len(row) == 1 and row[0]["duplicated_from_item_id"] is None


# ── audit ─────────────────────────────────────────────────────────────────────


def test_a_duplicate_is_audited_with_what_was_copied():
    ws = _workspace()
    _bind_files_sql(ws)
    new = _dup(_client(ws), ws["iid"]).json()["id"]
    a = _sql("SELECT actor_id, payload FROM audit_log WHERE event='item.duplicate' AND target=:t",
             {"t": str(new)})
    assert len(a) == 1 and a[0]["actor_id"] == ws["uids"]["drafter"]
    p = a[0]["payload"]
    assert (p["source_item_id"], p["modules"], p["parts"], p["hardware_lines"], p["attachments"],
            p["documents"], p["checklist_items"]) == (ws["iid"], 2, 3, 1, 1, 1, 2)
    log = _sql("SELECT field,new_value FROM item_edit_log WHERE item_id=:i AND field='_duplicate'",
               {"i": new})
    assert len(log) == 1 and log[0]["new_value"].startswith("from #")


# ── access ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["drafter", "manager", "admin"])
def test_drafter_manager_and_admin_may_duplicate(role):
    ws = _workspace()
    assert _dup(_client(ws, role), ws["iid"]).status_code == 201


@pytest.mark.parametrize("role", ["editor", "viewer"])
def test_editor_and_viewer_may_not_and_nothing_is_created(role):
    ws = _workspace()
    before = _scalar("SELECT count(*) FROM items WHERE project_id=:p", {"p": ws["pid"]})
    assert _dup(_client(ws, role), ws["iid"]).status_code == 403
    assert _scalar("SELECT count(*) FROM items WHERE project_id=:p", {"p": ws["pid"]}) == before


def test_a_related_part_an_unknown_id_and_a_deleted_item_are_404():
    ws = _workspace()
    c = _client(ws)
    assert _dup(c, ws["rp"]).status_code == 404
    assert _dup(c, 99999999).status_code == 404
    _sql("UPDATE items SET deleted=true WHERE item_id=:i", {"i": ws["iid"]})
    assert _dup(c, ws["iid"]).status_code == 404


def test_another_workspaces_item_is_404():
    ws, other = _workspace(), _workspace()
    before = _scalar("SELECT count(*) FROM items")
    assert _dup(_client(other), ws["iid"]).status_code == 404
    assert _scalar("SELECT count(*) FROM items") == before


# ── all or nothing ────────────────────────────────────────────────────────────


def test_a_failure_part_way_leaves_no_half_made_copy(monkeypatch):
    ws = _workspace()
    import app.item_duplicates.queries as dq

    def boom(*a, **k):
        raise RuntimeError("cutlist allocation failed")

    monkeypatch.setattr(dq, "create_cutlist", boom)
    c = TestClient(app, raise_server_exceptions=False)
    assert c.post("/auth/login", json={"workspace_slug": ws["slug"],
                                       "email": f"drafter@{ws['slug']}.test",
                                       "password": "pw"}).status_code == 200
    items_before = _scalar("SELECT count(*) FROM items WHERE project_id=:p", {"p": ws["pid"]})
    modules_before = _scalar("SELECT count(*) FROM modules m JOIN items i USING(item_id)"
                             " WHERE i.project_id=:p", {"p": ws["pid"]})
    assert c.post(f"/items/{ws['iid']}/duplicate").status_code == 500
    assert _scalar("SELECT count(*) FROM items WHERE project_id=:p", {"p": ws["pid"]}) == items_before
    assert _scalar("SELECT count(*) FROM modules m JOIN items i USING(item_id)"
                   " WHERE i.project_id=:p", {"p": ws["pid"]}) == modules_before
    assert _scalar("SELECT count(*) FROM audit_log WHERE event='item.duplicate'"
                   " AND workspace_id=:w", {"w": ws["wid"]}) == 0
