"""A catalog row's price on the hardware screens is `unit_cost`, else the table's own cost column
(the same rule Generate Orders starts an order line from; user decision 2026-10-20)."""
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers import create_project, login

_cleanup = truncate_fixture(
    "item_hardware_lines", "project_hardware_catalog_log", "project_hardware_catalog",
    "board_materials", "hardware_materials", "custom_made", "benchtop_materials", "appliances",
    "equipment_hire", "edging_materials", "glass_materials", "timber_materials",
)

# kind, table, own cost column, extra NOT NULL code column
_CASES = [
    ("BOARD", "board_materials", "cost_per_sheet", "code"),
    ("HARDWARE", "hardware_materials", "cost_per_unit", None),
    ("CUSTOM", "custom_made", "cost", "internal_ref"),
    ("BENCHTOP", "benchtop_materials", "cost_per_slab", "slab_id"),
    ("APPLIANCE", "appliances", "cost_per_unit", "model_number"),
    ("EDGING", "edging_materials", "cost_per_unit", None),
    ("GLASS", "glass_materials", "cost_per_unit", None),
    ("TIMBER", "timber_materials", "cost_per_unit", None),
]


def _row(db, wid, table, own_col, code_col, unit_cost, own):
    sku = f"P{uuid.uuid4().hex[:8]}"
    cols = ["workspace_id", "sku", "description", "unit_cost", own_col]
    vals = [":w", ":sku", "'price'", ":uc", ":own"]
    if code_col:
        cols.append(code_col)
        vals.append(":sku")
    return db.execute(
        text(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING material_id"),
        {"w": wid, "sku": sku, "uc": unit_cost, "own": own},
    ).scalar(), sku


@pytest.mark.parametrize("kind,table,own_col,code_col", _CASES)
def test_project_catalog_and_source_list_price_is_unit_cost_then_own_column(kind, table, own_col, code_col):
    c, wid, uid = login()
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid)
        expected = {}
        for name, uc, own, want in (("uc", "12.3456", None, 12.3456), ("own", None, "7.50", 7.5),
                                    ("both", "12.3456", "7.50", 12.3456)):
            mid, sku = _row(db, wid, table, own_col, code_col, uc, own)
            db.execute(
                text("INSERT INTO project_hardware_catalog(project_id, material_type, material_id, added_by)"
                     " VALUES (:p, :k, :m, :u)"),
                {"p": pid, "k": kind, "m": mid, "u": uid},
            )
            expected[sku] = want
        db.commit()
    finally:
        db.close()

    rows = c.get(f"/projects/{pid}/hardware_catalog").json()["rows"]
    assert {r["sku"]: round(r["unit_cost"], 4) for r in rows} == expected
    src = c.get(f"/source_catalog/{table}").json()["rows"]
    assert {r["sku"]: round(r["unit_cost"], 4) for r in src} == expected
