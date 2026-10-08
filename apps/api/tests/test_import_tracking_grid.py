"""The FileMaker "Tracking 2.0" importer (E3, first slice): `app.importers.tracking_grid`.

Synthetic workbooks only: the real export is customer data and never goes in the repo.
"""
import datetime as dt

import openpyxl
import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.importers import tracking_grid as tg
from .helpers import login

pytestmark = pytest.mark.usefixtures("truncate_after")

D = dt.datetime


def _row(**kw) -> dict:
    base = {h: None for h in tg.REQUIRED_HEADERS}
    base.update({"PID": 2325, "QTY": 1, "Tag_TgSolidItem": 0, "Date_Created": D(2026, 3, 3)})
    base.update(kw)
    return base


def _rows() -> list[dict]:
    return [
        # a billing line: no cutlist, no room
        _row(ItemId=700001, Item="Prelims 25%", Date_ReqOnSite=D(2026, 5, 1)),
        # two items sharing cutlist 298001 in room A03; one made after it was delivered (an anomaly)
        _row(ItemId=700002, CutlistNumber="298001", STG="A", LevelTXT="G01", RmDesc="Reception", RoomNoTXT="A03",
             Item="Reception Desk", JID="J01", _Contractor="TG", Tag_TgSolidItem=1, Status="LIVE",
             _StatusNoteLatest="Check orientation", ListerName="BILLMA", Assembler="Pero Miroski",
             Notes="8m2", ItemId_Old="1887896523200358877502", DWG_RoomFloorPlan="A460",
             DWG_FullDrawingPlan="A170", DWG_DetailPlan="A302",
             Date_ReqOnSite=D(2026, 7, 27), Date_SiteMeasured=D(2026, 7, 17), Date_Listed=D(2026, 7, 16),
             Date_Optimized=D(2026, 7, 17), Date_Made=D(2026, 8, 20), Date_Delivered=D(2026, 8, 19),
             Date_Installed=D(2026, 8, 25)),
        _row(ItemId=700003, CutlistNumber="298001", STG="A", LevelTXT="G01", RmDesc="Reception", RoomNoTXT="A03",
             Item="Counter Front", JID="J02", _Contractor="TG", Date_Created=D(2026, 2, 1)),
        # a cutlist number that is not a number, a second area, no status
        _row(ItemId=700004, CutlistNumber="#101973", STG="B1", LevelTXT="L01", RmDesc="Staff Work",
             RoomNoTXT="BG06", Item="Bench", Notes="from tender"),
        # a room number reused with another description; a stage that names no area
        _row(ItemId=700005, CutlistNumber="298002", STG="B1", RmDesc="Staff Works", RoomNoTXT="BG06", Item="Shelf"),
        _row(ItemId=700006, CutlistNumber="298003", STG="VARIES", LevelTXT="VARIES", Item="Whiteboard", QTY=2),
        # cutlist text that is neither a number nor `#number`: no cutlist, the text kept in the notes
        _row(ItemId=700007, CutlistNumber="see tender", Item="Odd", Notes="x"),
    ]


def _xlsx(tmp_path, rows: list[dict], headers=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    headers = headers or list(tg.REQUIRED_HEADERS)
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h) for h in headers])
    path = tmp_path / "grid.xlsx"
    wb.save(path)
    return path


def _workspace(role="admin"):
    c, wid, uid = login(role)
    db = SessionLocal()
    try:
        slug = db.execute(text("SELECT slug FROM workspace WHERE id=:w"), {"w": wid}).scalar()
        email = db.execute(text("SELECT email FROM app_user WHERE id=:u"), {"u": uid}).scalar()
    finally:
        db.close()
    return c, wid, uid, slug, email


def _apply(wid, uid, plan, *, code="2325", commit=True, advance=True):
    db = SessionLocal()
    try:
        res = tg.apply(db, plan, workspace_id=wid, actor_id=uid, project_code=code,
                       project_name=f"Pilot school {code}", source_sha256="x" * 64, advance_sequence=advance)
        (db.commit if commit else db.rollback)()
        return res
    finally:
        db.close()


def _scalar(sql, **p):
    db = SessionLocal()
    try:
        return db.execute(text(sql), p).scalar()
    finally:
        db.close()


# ---- the planner (no database) --------------------------------------------------------------------------

def test_the_plan_reads_the_rows_and_names_every_oddity():
    plan = tg.build_plan(_rows())
    assert plan.pid == 2325 and len(plan.items) == 7
    assert plan.areas == ["A", "B1"] and plan.factories == ["TG"]
    assert list(plan.cutlists) == [298001, 101973, 298002, 298003]       # `#101973` is cutlist 101973
    assert plan.cutlists[298001] == dt.date(2026, 2, 1)            # the earliest Date_Created on it
    kinds = {k for k, _ in plan.anomalies}
    assert kinds == {"no_cutlist", "bad_cutlist", "hash_cutlist", "varies", "room_desc_conflict", "date_order"}
    assert plan.skipped_optimized == 1
    assert plan.rooms[("B1", "BG06")] == "Staff Work"              # the first description wins


def test_the_date_columns_follow_the_settled_mapping():
    item = next(i for i in tg.build_plan(_rows()).items if i.item_id_fm == 700002)
    assert item.stages == {
        "REQ": ("due_date", dt.date(2026, 7, 27)),                 # required-by: a due date
        "SM": ("done_date", dt.date(2026, 7, 17)), "LISTED": ("done_date", dt.date(2026, 7, 16)),
        "MADE": ("done_date", dt.date(2026, 8, 20)), "DEL": ("done_date", dt.date(2026, 8, 19)),
        "INST": ("done_date", dt.date(2026, 8, 25)),
    }                                                              # Date_Optimized has no stage


def test_a_workbook_missing_columns_is_refused(tmp_path):
    path = _xlsx(tmp_path, _rows(), headers=[h for h in tg.REQUIRED_HEADERS if h != "STG"])
    with pytest.raises(tg.ImportErrorReport, match="STG"):
        tg.read_rows(path)


def test_several_projects_in_one_sheet_need_a_pid():
    rows = _rows() + [_row(ItemId=700099, PID=9999, Item="Other project")]
    with pytest.raises(tg.ImportErrorReport, match="several projects"):
        tg.build_plan(rows)
    assert len(tg.build_plan(rows, pid=2325).items) == 7


def test_a_repeated_item_id_and_an_unreadable_one_are_skipped():
    rows = _rows() + [_row(ItemId=700002, Item="again"), _row(ItemId="n/a", Item="junk")]
    plan = tg.build_plan(rows)
    assert len(plan.items) == 7
    assert {k for k, _ in plan.anomalies} >= {"duplicate_item_id", "bad_item_id"}


# ---- writing it ----------------------------------------------------------------------------------------

def test_commit_creates_everything_with_the_fileMaker_numbers(tmp_path):
    _, wid, uid, _, _ = _workspace()
    plan = tg.build_plan(tg.read_rows(_xlsx(tmp_path, _rows())))
    res = _apply(wid, uid, plan)
    assert (res.items_created, res.cutlists_created, res.areas_created, res.rooms_created,
            res.factories_created) == (7, 4, 2, 2, 1)

    db = SessionLocal()
    try:
        item = db.execute(text("""
            SELECT i.*, a.name AS area, r.rm_no AS room, f.code AS factory, c.cutlist_no
              FROM items i LEFT JOIN area a USING (area_id) LEFT JOIN room r ON r.room_id = i.room_id
              LEFT JOIN factory f ON f.factory_id = i.factory_id LEFT JOIN cutlist c ON c.cutlist_id = i.cutlist_id
             WHERE i.num = 700002""")).mappings().one()
        assert (item["description"], item["qty"], item["cutlist_no"], item["area"], item["room"]) == \
            ("Reception Desk", 1, 298001, "A", "A03")
        assert (item["stage"], item["level"], item["rm_no"], item["rm_desc"]) == ("A", "G01", "A03", "Reception")
        assert (item["jid_code"], item["status"], item["lister"], item["assembler"]) == \
            ("J01", "LIVE", "BILLMA", "Pero Miroski")
        assert (item["factory"], item["tg_solid"], item["legacy_item_ref"]) == ("TG", True, "1887896523200358877502")
        assert (item["floor_plan"], item["rls"], item["joiery_details"], item["estimator_notes"]) == \
            ("A460", "A170", "A302", "8m2")
        stages = {r["stage_key"]: (r["due_date"], r["done_date"]) for r in db.execute(
            text("SELECT * FROM item_stages WHERE item_id = :i"), {"i": item["item_id"]}).mappings()}
        assert stages["REQ"] == (dt.date(2026, 7, 27), None) and stages["SM"] == (None, dt.date(2026, 7, 17))
        assert "CNC" not in stages
        note = db.execute(text("SELECT status, note FROM item_status_log WHERE item_id = :i"),
                          {"i": item["item_id"]}).one()
        assert tuple(note) == ("LIVE", "Check orientation")

        # the two items on one cutlist share it; created_at is the FileMaker creation date
        assert db.execute(text("SELECT count(DISTINCT cutlist_id) FROM items WHERE num IN (700002, 700003)")).scalar() == 1
        assert db.execute(text("SELECT created_at::date FROM items WHERE num = 700003")).scalar() == dt.date(2026, 2, 1)

        # `#101973` becomes cutlist 101973 (the `#` is stripped); the status defaults to CLEAR
        hashed = db.execute(text("""SELECT c.cutlist_no, i.estimator_notes, i.status FROM items i
                                     JOIN cutlist c ON c.cutlist_id = i.cutlist_id WHERE i.num = 700004""")).one()
        assert tuple(hashed) == (101973, "from tender", "CLEAR")
        # other cutlist text is not a number: no cutlist, the text kept in the notes
        odd = db.execute(text("SELECT cutlist_id, estimator_notes FROM items WHERE num = 700007")).one()
        assert odd.cutlist_id is None and odd.estimator_notes == "x\nFileMaker cutlist number: see tender"
        # no area for 'VARIES'

        varies = db.execute(text("SELECT area_id, room_id, stage, level, qty FROM items WHERE num = 700006")).one()
        assert (varies.area_id, varies.room_id, varies.stage, varies.level, varies.qty) == (None, None, "VARIES", "VARIES", 2)
        assert db.execute(text("SELECT cutlist_id FROM items WHERE num = 700001")).scalar() is None
        assert db.execute(text("SELECT count(*) FROM audit_log WHERE event = 'import.tracking_grid'")).scalar() == 1
    finally:
        db.close()


def test_the_shared_number_sequence_moves_past_the_highest_imported_number(tmp_path):
    _, wid, uid, _, _ = _workspace()
    _apply(wid, uid, tg.build_plan(_rows() + [_row(ItemId=900123, CutlistNumber="450000", Item="High")]))
    assert _scalar("SELECT last_value FROM joinery_number_seq") >= 900123
    assert _scalar("SELECT nextval('joinery_number_seq')") > 900123


def test_a_dry_run_changes_nothing(tmp_path, capsys):
    _, wid, uid, slug, email = _workspace()
    path = _xlsx(tmp_path, _rows())
    before = _scalar("SELECT last_value FROM joinery_number_seq")
    code = tg.main([str(path), "--workspace-slug", slug, "--actor-email", email,
                    "--project-code", "2325", "--project-name", "Pilot"])
    out = capsys.readouterr().out
    assert code == 0 and "DRY RUN" in out and "7 items" in out and "anomalies:" in out
    assert _scalar("SELECT count(*) FROM items WHERE project_id IN (SELECT project_id FROM projects WHERE workspace_id=:w)", w=wid) == 0
    assert _scalar("SELECT count(*) FROM projects WHERE workspace_id=:w AND project_code='2325'", w=wid) == 0
    assert _scalar("SELECT count(*) FROM audit_log WHERE event='import.tracking_grid'") == 0
    assert _scalar("SELECT last_value FROM joinery_number_seq") == before          # never touched by a dry run


def test_commit_through_the_command_line_keeps_it(tmp_path, capsys):
    _, wid, uid, slug, email = _workspace()
    code = tg.main([str(_xlsx(tmp_path, _rows())), "--workspace-slug", slug, "--actor-email", email,
                    "--project-code", "2325", "--project-name", "Pilot", "--commit"])
    assert code == 0 and "COMMITTED" in capsys.readouterr().out
    assert _scalar("SELECT count(*) FROM items WHERE num BETWEEN 700001 AND 700007") == 7


def test_running_it_twice_creates_nothing_new_even_if_an_item_was_deleted(tmp_path):
    c, wid, uid, _, _ = _workspace()
    plan = tg.build_plan(_rows())
    assert _apply(wid, uid, plan).items_created == 7
    assert c.delete(f"/items/{_scalar('SELECT item_id FROM items WHERE num = 700002')}").status_code == 204
    again = _apply(wid, uid, tg.build_plan(_rows()))
    assert again.items_created == 0 and again.items_skipped_existing == 7 and again.cutlists_created == 0
    assert _scalar("SELECT count(*) FROM items WHERE num = 700002") == 1          # not recreated


def test_a_number_used_by_another_project_stops_the_import_and_writes_nothing():
    _, wid, uid, _, _ = _workspace()
    _apply(wid, uid, tg.build_plan(_rows()), code="OTHER")
    items_before = _scalar("SELECT count(*) FROM items")
    db = SessionLocal()
    try:
        with pytest.raises(tg.ImportErrorReport, match="another project"):
            tg.apply(db, tg.build_plan(_rows()), workspace_id=wid, actor_id=uid, project_code="2325",
                     project_name="x", source_sha256="y", advance_sequence=True)
        db.rollback()
    finally:
        db.close()
    assert _scalar("SELECT count(*) FROM items") == items_before
    assert _scalar("SELECT count(*) FROM projects WHERE project_code = '2325'") == 0


def test_tracking_serves_the_factory_and_the_tg_solid_tag(tmp_path):
    c, wid, uid, _, _ = _workspace()
    _apply(wid, uid, tg.build_plan(_rows()))
    pid = _scalar("SELECT project_id FROM projects WHERE workspace_id=:w AND project_code='2325'", w=wid)
    rows = {r["item_number"]: r for r in c.get(f"/projects/{pid}/items").json()["items"]}
    assert (rows[700002]["factory_code"], rows[700002]["tg_solid"]) == ("TG", True)
    assert (rows[700003]["factory_code"], rows[700003]["tg_solid"]) == ("TG", False)
    assert (rows[700001]["factory_code"], rows[700001]["tg_solid"]) == (None, False)


def test_factory_codes_are_unique_per_workspace_and_isolated():
    _, wid_a, uid_a, _, _ = _workspace()
    _, wid_b, uid_b, _, _ = _workspace()
    _apply(wid_a, uid_a, tg.build_plan(_rows()), code="A-1")
    plan_b = tg.build_plan([_row(ItemId=800001, Item="B item", _Contractor="TG", PID=1)])
    _apply(wid_b, uid_b, plan_b, code="B-1")
    assert _scalar("SELECT count(*) FROM factory WHERE code='TG'") == 2          # one each, never shared
    assert _scalar("SELECT count(DISTINCT workspace_id) FROM factory WHERE code='TG'") == 2


# ---- one number space: an Item ID and a cutlist number must never be the same number (Q541) ------------------

def _refuses(wid, uid, rows, match):
    db = SessionLocal()
    try:
        with pytest.raises(tg.ImportErrorReport, match=match):
            tg.apply(db, tg.build_plan(rows), workspace_id=wid, actor_id=uid, project_code="2325",
                     project_name="x", source_sha256="y", advance_sequence=True)
        db.rollback()
    finally:
        db.close()
    assert _scalar("SELECT count(*) FROM projects WHERE project_code = '2325'") == 0


def test_a_cutlist_number_that_is_already_an_item_id_stops_the_import():
    _, wid, uid, _, _ = _workspace()
    _apply(wid, uid, tg.build_plan([_row(ItemId=101973, Item="Existing", CutlistNumber="298500")]), code="OLD")
    _refuses(wid, uid, _rows(), "already an Item ID")                  # `#101973` strips to 101973


def test_an_item_id_that_is_already_a_cutlist_number_stops_the_import():
    _, wid, uid, _, _ = _workspace()
    _apply(wid, uid, tg.build_plan([_row(ItemId=799999, Item="Existing", CutlistNumber="700002")]), code="OLD")
    _refuses(wid, uid, _rows(), "already a cutlist number")            # ItemId 700002 is cutlist 700002 there


def test_one_number_used_as_both_in_the_file_stops_the_import():
    _, wid, uid, _, _ = _workspace()
    rows = _rows() + [_row(ItemId=700008, CutlistNumber="#700002", Item="Clash")]
    _refuses(wid, uid, rows, "both an Item ID and a cutlist number")
