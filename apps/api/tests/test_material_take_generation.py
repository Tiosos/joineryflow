"""Material Take generation (plan task B1; spec §4, Q581)."""
from decimal import Decimal

from sqlalchemy import text

from app.material_takes.generation import (
    SheetSize, estimate_sheets, generate_lines, generated_signature, pick_sheet_size,
    summary_sheets,
)

SHEET = SheetSize(2440, 1220)  # 2.9768 m²


# --- pure arithmetic --------------------------------------------------------

def test_sheets_are_fractional_rounded_up_to_cents():
    assert estimate_sheets(3_150_000, SHEET) == ("sheet", Decimal("1.06"))  # 1.0582
    assert estimate_sheets(1, SHEET) == ("sheet", Decimal("0.01"))          # never zero


def test_exact_multiple_stays_exact():
    assert estimate_sheets(SHEET.area * 3, SHEET) == ("sheet", Decimal("3.00"))


def test_summary_rounds_up_once_not_per_item():
    """Q586: ten small items sharing a board must not become ten sheets."""
    per_item = [estimate_sheets(1_118_000, SHEET)[1]] * 10   # 11.18 m² in total
    assert per_item[0] == Decimal("0.38")
    assert summary_sheets(per_item) == Decimal(4)
    assert summary_sheets([Decimal("2.00"), Decimal("1.00")]) == Decimal(3)


def test_no_size_falls_back_to_m2():
    assert estimate_sheets(900_000, None) == ("m2", Decimal("0.90"))


def test_zero_area_is_zero_sheets():
    assert estimate_sheets(0, SHEET) == ("sheet", Decimal(0))


def test_pick_prefers_largest_in_stock():
    inv = [(2440, 1220, 15), (3600, 1800, 4), (4000, 2000, 0)]
    assert pick_sheet_size(inv, (None, None)) == SheetSize(3600, 1800)


def test_pick_uses_recorded_size_when_none_in_stock():
    """The plan's clarification: PLY-12-BIR's only size has qty 0."""
    assert pick_sheet_size([(2440, 1220, 0)], (None, None)) == SheetSize(2440, 1220)


def test_pick_falls_back_to_catalog_then_none():
    assert pick_sheet_size([], (2400, 1200)) == SheetSize(2400, 1200)
    assert pick_sheet_size([], (None, None)) is None


# --- against the database ---------------------------------------------------

def _one(db, sql, **p):
    return db.execute(text(sql), p).scalar()


def _item(db, workspace_id):
    pid = _one(db, "INSERT INTO projects(project_code, name, workspace_id)"
                   " VALUES ('MT-1', 'Take project', :w) RETURNING project_id", w=workspace_id)
    iid = _one(db, """INSERT INTO items(num, project_id, description, status)
                      VALUES (nextval('joinery_number_seq'), :p, 'Vanity', 'LIVE')
                      RETURNING item_id""", p=pid)
    mid = _one(db, "INSERT INTO modules(item_id, module_no) VALUES (:i, 1) RETURNING module_id", i=iid)
    return pid, iid, mid


def _board(db, w, code, stock=None):
    bid = _one(db, """INSERT INTO board_materials(code, description, sku, workspace_id)
                      VALUES (:c, :c, :c, :w) RETURNING material_id""", c=code, w=w)
    for ln, wd, q in stock or []:
        db.execute(text("INSERT INTO board_inventory(workspace_id, material_id, len_mm, wid_mm, qty_on_hand)"
                        " VALUES (:w, :m, :l, :d, :q)"), {"w": w, "m": bid, "l": ln, "d": wd, "q": q})
    return bid


def _part(db, mid, board, ln, wd, qty):
    db.execute(text("INSERT INTO parts(module_id, qty, len_mm, wid_mm, board_material_id)"
                    " VALUES (:m, :q, :l, :d, :b)"), {"m": mid, "q": qty, "l": ln, "d": wd, "b": board})


def test_generate_boards_in_sheets_and_m2(db, workspace_id):
    _, iid, mid = _item(db, workspace_id)
    stocked = _board(db, workspace_id, "MT-BM", [(2440, 1220, 5)])
    unsized = _board(db, workspace_id, "MT-SS")
    _part(db, mid, stocked, 2000, 600, 4)     # 4.8 m²
    _part(db, mid, stocked, 700, 500, 2)      # +0.7 m² → 5.5 m² → 1.85 sheets
    _part(db, mid, unsized, 1500, 600, 1)     # 0.90 m², no size anywhere
    lines = {l["material_id"]: l for l in generate_lines(db, iid, workspace_id)}
    assert (lines[stocked]["unit"], lines[stocked]["qty_generated"]) == ("sheet", Decimal("1.85"))
    assert (lines[unsized]["unit"], lines[unsized]["qty_generated"]) == ("m2", Decimal("0.90"))
    assert all(l["source"] == "generated" and l["qty"] == l["qty_generated"] for l in lines.values())


def test_generate_hardware_sums_per_material(db, workspace_id):
    pid, iid, _ = _item(db, workspace_id)
    uid = _one(db, """INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                      VALUES (:w, 'mt@x.test', 'D', 'x', 'drafter') RETURNING id""", w=workspace_id)
    hm = _one(db, "INSERT INTO hardware_materials(sku, description, workspace_id)"
                  " VALUES ('MT-HW', 'Soft-close hinge', :w) RETURNING material_id", w=workspace_id)
    cat = _one(db, """INSERT INTO project_hardware_catalog(project_id, material_type, material_id, added_by)
                      VALUES (:p, 'HARDWARE', :m, :u) RETURNING catalog_id""", p=pid, m=hm, u=uid)
    for q in (4, 6):
        db.execute(text("INSERT INTO item_hardware_lines(item_id, catalog_id, qty) VALUES (:i, :c, :q)"),
                   {"i": iid, "c": cat, "q": q})
    [line] = generate_lines(db, iid, workspace_id)
    assert (line["material_type"], line["unit"], line["qty_generated"]) == ("HARDWARE", "each", Decimal(10))
    assert line["description"] == "Soft-close hinge"


def test_other_workspaces_stock_is_ignored(db, workspace_id):
    other = _one(db, "INSERT INTO workspace(slug, name) VALUES ('mt-other', 'O') RETURNING id")
    _, iid, mid = _item(db, workspace_id)
    board = _board(db, workspace_id, "MT-BM2")
    db.execute(text("INSERT INTO board_inventory(workspace_id, material_id, len_mm, wid_mm, qty_on_hand)"
                    " VALUES (:w, :m, 2440, 1220, 9)"), {"w": other, "m": board})
    _part(db, mid, board, 1000, 1000, 1)
    [line] = generate_lines(db, iid, workspace_id)
    assert line["unit"] == "m2"


def test_signature_ignores_manual_lines_and_adjustments():
    gen = {"material_type": "BOARD", "material_id": 1, "unit": "sheet",
           "qty_generated": Decimal(2), "qty": Decimal(3), "wastage_pct": Decimal(10),
           "source": "generated"}
    manual = {"material_type": "OTHER", "material_id": None, "unit": "m",
              "qty_generated": None, "qty": Decimal(12), "source": "manual"}
    assert generated_signature([gen, manual]) == [("BOARD", 1, "sheet", Decimal(2))]
