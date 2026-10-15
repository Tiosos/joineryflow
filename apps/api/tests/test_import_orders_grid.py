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
    assert first.notes == "Requested by: Bill"
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
