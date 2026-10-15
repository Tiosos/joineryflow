"""The FileMaker orders importer (E3, second slice): `app.importers.orders_grid`.

Synthetic workbooks only: the real export is customer data and never goes in the repo.
"""
import datetime as dt
from decimal import Decimal

import openpyxl
import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.importers import orders_grid as og
from .helpers import login

pytestmark = pytest.mark.usefixtures("truncate_after")

D = dt.datetime
SUM = "T07b_ORD_StockControl::SumTotla"


def _row(**kw) -> dict:
    base = {h: None for h in og.REQUIRED_HEADERS}
    base.update({"_ProjectName": "Pilot fitout", "QTY": 1, "_Cost_Sub": 0, "_Priority": "ORDERED",
                 "Supplier": "Acme Boards", "_BoardGroup": "18mm board", "TAG_Active": 1})
    base.update(kw)
    return base


def _rows() -> list[dict]:
    return [
        # delivered, qty received known, total is the line total
        _row(OrderNumber=100001, QTY=4, _Cost_Sub=100, **{SUM: 4}, Date_Ordered=D(2026, 3, 1),
             Date_Arrived=D(2026, 3, 5), _RequestedByName="Bill", _PCode="X1", CutlistNumber=298001),
        # same order number, supplier written in another case: one vendor
        _row(OrderNumber=100001, Supplier="ACME BOARDS", **{SUM: 0}, Date_Ordered=D(2026, 3, 1),
             Date_Arrived=D(2026, 3, 6)),
        # ordered, not yet arrived
        _row(OrderNumber=100002, Supplier="Hinge Co", Date_Ordered=D(2026, 3, 9)),
        # requests not yet ordered
        _row(_Priority="ON HOLD", TAG_Active=0), _row(_Priority="NEXT", TAG_Active=0),
        _row(_Priority="QUOTE", TAG_Active=0), _row(_Priority="URGENT", TAG_Active=0),
        _row(_Priority=None, TAG_Active=0),
        # no supplier: skipped
        _row(Supplier=None, OrderNumber=100003),
        # an identical pair of rows must both come in
        _row(OrderNumber=100004, Date_Ordered=D(2026, 4, 1)), _row(OrderNumber=100004, Date_Ordered=D(2026, 4, 1)),
    ]


def _xlsx(tmp_path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(og.REQUIRED_HEADERS))
    for r in rows:
        ws.append([r.get(h) for h in og.REQUIRED_HEADERS])
    path = tmp_path / "orders.xlsx"
    wb.save(path)
    return path


def _apply(wid, uid, plan, *, commit=True, code="PILOT"):
    db = SessionLocal()
    try:
        res = og.apply(db, plan, workspace_id=wid, actor_id=uid, project_code=code,
                       project_name="Pilot fitout", source_sha256="x" * 64)
        (db.commit if commit else db.rollback)()
        return res
    finally:
        db.close()


def _q(sql, **p):
    db = SessionLocal()
    try:
        return db.execute(text(sql), p).all()
    finally:
        db.close()


def _plan(tmp_path):
    return og.build_plan(og.read_rows(_xlsx(tmp_path, _rows())))


def test_plan_maps_status_priority_and_money(tmp_path):
    plan = _plan(tmp_path)
    assert len(plan.orders) == 10
    by = [(o.status, o.priority) for o in plan.orders]
    assert by[:3] == [("Delivered", "Medium"), ("Delivered", "Medium"), ("Approved", "Medium")]
    assert by[3:8] == [("Hold", "Medium"), ("Next", "Medium"), ("Quote", "Medium"), ("Pending", "High"),
                       ("Pending", "Medium")]
    first = plan.orders[0]
    assert (first.total, first.unit_cost, first.received_qty) == (Decimal("100.00"), Decimal("25.0000"), Decimal(4))
    assert plan.orders[1].received_qty is None                       # SumTotla 0: no delivery row
    assert first.order_number == "100001" and first.cutlist_no == "298001"
    assert first.requester == "Bill"
    assert [k for k, _ in plan.anomalies] == ["no_supplier"]
    assert len({o.key for o in plan.orders}) == len(plan.orders)     # identical rows still get distinct keys


def test_several_projects_is_refused(tmp_path):
    rows = [_row(), _row(_ProjectName="Other")]
    with pytest.raises(og.ImportErrorReport):
        og.build_plan(og.read_rows(_xlsx(tmp_path, rows)))


def test_apply_writes_orders_vendors_and_deliveries_and_reruns_safely(tmp_path):
    _, wid, uid = login("admin")
    plan = _plan(tmp_path)
    res = _apply(wid, uid, plan, commit=False)
    assert res.orders_created == 10
    assert _q("SELECT 1 FROM purchase_orders WHERE attributes ? 'fm_import'") == []        # dry run wrote nothing

    res = _apply(wid, uid, plan)
    assert (res.orders_created, res.vendors_created, res.deliveries, res.project_created) == (10, 2, 1, True)
    rows = _q("""SELECT po.status, po.total_amount, po.unit_cost, po.order_number, po.po_number, po.arrived_date,
                        v.name FROM purchase_orders po JOIN vendors v USING (vendor_id)
                 WHERE po.attributes ? 'fm_import' AND po.order_number = '100001' ORDER BY po.po_id""")
    assert [r[0] for r in rows] == ["Delivered", "Delivered"]
    assert rows[0][1:4] == (Decimal("100.00"), Decimal("25.0000"), "100001")
    assert rows[0][4].startswith("PO-") and rows[0][5] == dt.date(2026, 3, 5)
    assert {r[6] for r in rows} == {"Acme Boards"}                                          # one vendor, either case
    assert _q("SELECT qty, date_received FROM order_delivery") == [(Decimal("4.000"), dt.date(2026, 3, 5))]
    assert len(_q("SELECT 1 FROM purchase_orders WHERE order_number = '100004'")) == 2
    assert _q("SELECT count(*) FROM audit_log WHERE event = 'import.orders_grid'")[0][0] == 1

    again = _apply(wid, uid, plan)
    assert (again.orders_created, again.orders_skipped_existing) == (0, 10)
    assert _q("SELECT count(*) FROM purchase_orders WHERE attributes ? 'fm_import'")[0][0] == 10


# ---- requester and item link (settled 2026-10-15) --------------------------------------------------------

def _tracking_rows():
    from app.importers import tracking_grid as tg
    base = {h: None for h in tg.REQUIRED_HEADERS}
    base.update({"PID": 1, "QTY": 1, "Tag_TgSolid": 0, "Tag_TgSolidItem": 0})
    return tg, [
        {**base, "ItemId": 710001, "CutlistNumber": "298101", "Item": "Only item on its cutlist"},
        {**base, "ItemId": 710002, "CutlistNumber": "298102", "Item": "One of two"},
        {**base, "ItemId": 710003, "CutlistNumber": "298102", "Item": "Two of two"},
    ]


def test_requester_is_matched_to_one_staff_member_else_kept_in_internal_comments(tmp_path):
    _, wid, uid = login("admin")
    db = SessionLocal()
    try:
        ids = {}
        for email, name in (("solo@example.test", "Quill Solo"), ("d1@example.test", "Dup One"),
                            ("d2@example.test", "Dup Two"), ("gone@example.test", "Gone Away")):
            ids[name] = db.execute(text("""INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role, is_active)
                                           VALUES (:w, :e, :n, 'x', 'viewer', :a) RETURNING id"""),
                                   {"w": wid, "e": email, "n": name, "a": name != "Gone Away"}).scalar()
        db.commit()
    finally:
        db.close()
    # one active user called Quill: matched; two called Dup: ambiguous; Gone is inactive and Zzyzx is unknown
    rows = [_row(OrderNumber=i, _RequestedByName=n) for i, n in enumerate(["quill", "Dup", "Gone", "Zzyzx"], start=1)]
    res = _apply(wid, uid, og.build_plan(og.read_rows(_xlsx(tmp_path, rows))))
    assert (res.requester_matched, res.requester_ambiguous, res.requester_unmatched) == (1, 1, 2)
    got = {r[0]: (r[1], r[2]) for r in _q(
        "SELECT order_number, requester_id, internal_comments FROM purchase_orders WHERE attributes ? 'fm_import'")}
    assert got["1"] == (ids["Quill Solo"], None)                    # one match: raised by that person
    assert got["2"] == (uid, "Requested by: Dup")                   # two people share it: the importer, name kept
    assert got["3"] == (uid, "Requested by: Gone")                  # an inactive user does not count
    assert got["4"] == (uid, "Requested by: Zzyzx")                 # nobody: the importer, name kept


def test_an_order_is_linked_to_an_item_only_when_its_cutlist_has_exactly_one(tmp_path):
    _, wid, uid = login("admin")
    tg, trows = _tracking_rows()
    db = SessionLocal()
    try:
        tg.apply(db, tg.build_plan(trows), workspace_id=wid, actor_id=uid, project_code="PILOT",
                 project_name="Pilot fitout", source_sha256="y" * 64, advance_sequence=False)
        db.commit()
    finally:
        db.close()
    rows = [_row(OrderNumber=1, CutlistNumber=298101), _row(OrderNumber=2, CutlistNumber=298102),
            _row(OrderNumber=3, CutlistNumber=299999), _row(OrderNumber=4)]
    res = _apply(wid, uid, og.build_plan(og.read_rows(_xlsx(tmp_path, rows))))
    assert (res.linked, res.cutlist_many_items, res.cutlist_not_found) == (1, 1, 1)
    linked = {r[0]: r[1] for r in _q(
        "SELECT order_number, (SELECT num FROM items WHERE item_id = po.item_id) FROM purchase_orders po"
        " WHERE attributes ? 'fm_import'")}
    assert linked == {"1": 710001, "2": None, "3": None, "4": None}
