"""Tests for project_contract + variations (Q491) and the actual-costs
rollup (Q493/Q549)."""
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers import login



pytestmark = pytest.mark.usefixtures("truncate_after")


def _login(role: str = "manager"):
    return login(role, prefix="pc")




def _make_project(wid: int, uid: int, code: str) -> int:
    s = SessionLocal()
    try:
        pid = s.execute(
            text(
                "INSERT INTO projects(project_code, name, workspace_id, created_by) "
                "VALUES (:c, :c, :w, :cb) RETURNING project_id"
            ),
            {"c": code, "w": wid, "cb": str(uid)},
        ).scalar()
        s.commit()
        return pid
    finally:
        s.close()


def _make_contract(pid: int, uid: int, original_value: str) -> None:
    s = SessionLocal()
    try:
        s.execute(
            text(
                "INSERT INTO project_contract(project_id, original_value, created_by) "
                "VALUES (:p, :v, :u)"
            ),
            {"p": pid, "v": original_value, "u": uid},
        )
        s.commit()
    finally:
        s.close()


def test_get_contract_404_when_missing():
    c, wid, uid = _login()
    pid = _make_project(wid, uid, "P1")
    r = c.get(f"/projects/{pid}/contract")
    assert r.status_code == 404


def test_get_contract_returns_original_with_no_variations():
    c, wid, uid = _login()
    pid = _make_project(wid, uid, "P1")
    _make_contract(pid, uid, "100000.00")
    r = c.get(f"/projects/{pid}/contract")
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["original_value"]) == 100000.00
    assert float(body["current_value"]) == 100000.00
    assert body["variations"] == []


def test_create_variation_updates_current_value():
    c, wid, uid = _login()
    pid = _make_project(wid, uid, "P1")
    _make_contract(pid, uid, "100000.00")
    r = c.post(f"/projects/{pid}/contract/variations",
               json={"description": "Extra bench", "amount_delta": "2500.00"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert float(body["current_value"]) == 102500.00
    assert float(body["original_value"]) == 100000.00  # never overwritten (§17)
    assert len(body["variations"]) == 1


def test_negative_variation_reduces_current_value():
    c, wid, uid = _login()
    pid = _make_project(wid, uid, "P1")
    _make_contract(pid, uid, "100000.00")
    c.post(f"/projects/{pid}/contract/variations",
           json={"description": "Descope tiling", "amount_delta": "-3000.00"})
    r = c.get(f"/projects/{pid}/contract")
    assert float(r.json()["current_value"]) == 97000.00


def test_contract_workspace_isolation():
    c1, wid1, uid1 = _login()
    pid = _make_project(wid1, uid1, "P1")
    _make_contract(pid, uid1, "50000.00")
    c2, *_ = _login()
    assert c2.get(f"/projects/{pid}/contract").status_code == 404
    r = c2.post(f"/projects/{pid}/contract/variations",
                json={"description": "x", "amount_delta": "1"})
    assert r.status_code == 404


def test_drafter_cannot_write_but_can_read():
    c, wid, uid = _login(role="drafter")
    pid = _make_project(wid, uid, "P1")
    _make_contract(pid, uid, "10000.00")
    assert c.get(f"/projects/{pid}/contract").status_code == 200
    r = c.post(f"/projects/{pid}/contract/variations",
               json={"description": "x", "amount_delta": "1"})
    assert r.status_code == 201  # drafter has tracking:write too


def test_viewer_cannot_write():
    c, wid, uid = _login(role="viewer")
    pid = _make_project(wid, uid, "P1")
    _make_contract(pid, uid, "10000.00")
    r = c.post(f"/projects/{pid}/contract/variations",
               json={"description": "x", "amount_delta": "1"})
    assert r.status_code == 403


# --- Actual costs (Q493/Q549) ---------------------------------------------

def test_actual_costs_zero_for_untouched_project():
    c, wid, uid = _login()
    pid = _make_project(wid, uid, "P1")
    r = c.get(f"/projects/{pid}/actual-costs")
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["materials_actual"]) == 0
    assert float(body["labour_actual"]) == 0
    assert float(body["total_actual"]) == 0


def test_actual_costs_materials_from_received_batches():
    c, wid, uid = _login()
    pid = _make_project(wid, uid, "P1")
    s = SessionLocal()
    try:
        board_id = s.execute(
            text(
                """
                INSERT INTO board_materials(workspace_id, sku, code, description,
                    cost_per_sheet, unit_cost, default_supplier)
                VALUES (:w, 'SKU1', 'SKU1', 'Board', 50, 50, 'Sup')
                RETURNING material_id
                """
            ),
            {"w": wid},
        ).scalar()
        s.execute(
            text(
                """
                INSERT INTO procurement_batches(
                    project_id, material_type, material_id, qty_ordered,
                    qty_received, cost_per_unit
                ) VALUES (:p, 'BOARD', :m, 10, 4, 25.00)
                """
            ),
            {"p": pid, "m": board_id},
        )
        s.commit()
    finally:
        s.close()
    r = c.get(f"/projects/{pid}/actual-costs")
    assert r.status_code == 200, r.text
    assert float(r.json()["materials_actual"]) == 100.00  # 4 * 25.00


def test_actual_costs_workspace_isolation():
    c1, wid1, uid1 = _login()
    pid = _make_project(wid1, uid1, "P1")
    c2, *_ = _login()
    assert c2.get(f"/projects/{pid}/actual-costs").status_code == 404
