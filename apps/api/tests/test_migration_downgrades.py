"""Downgrades that could lose data say so instead (code-review fixes, 2026-10-20).

Each test builds a scratch database at head, so the worker database is untouched. Alembic runs a
whole `downgrade` in one transaction, so a refused downgrade leaves the database exactly as it was.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

DB_DIR = next(p / "db" for p in Path(__file__).resolve().parents if (p / "db" / "alembic.ini").is_file())

_NINE = ("board_materials", "hardware_materials", "custom_made", "benchtop_materials", "appliances",
         "equipment_hire", "edging_materials", "glass_materials", "timber_materials")


@pytest.fixture()
def scratch():
    base = make_url(os.environ["DATABASE_URL"])
    name = f"{base.database}_mig_{uuid.uuid4().hex[:6]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    eng = create_engine(url)

    def alembic(*args):
        return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=DB_DIR, capture_output=True,
                              text=True, env={**os.environ, "DATABASE_URL": url})

    assert alembic("upgrade", "head").returncode == 0
    try:
        yield eng, alembic
    finally:
        eng.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _to_0078(alembic):
    """The scratch database is at head (`0079`); these tests were written at `0078`, so go down one first."""
    r = alembic("downgrade", "0078")
    assert r.returncode == 0, r.stderr


def _version(eng) -> str:
    with eng.connect() as c:
        return c.execute(text("SELECT version_num FROM alembic_version")).scalar()


def _workspace(eng) -> int:
    with eng.begin() as c:
        return c.execute(text("INSERT INTO workspace(slug, name) VALUES ('m', 'M') RETURNING id")).scalar()


def _unit_cost_types(eng) -> set[tuple[int, int]]:
    with eng.connect() as c:
        return set(c.execute(text(
            "SELECT numeric_precision, numeric_scale FROM information_schema.columns"
            " WHERE column_name = 'unit_cost' AND table_name = ANY(:t)"), {"t": list(_NINE)}).all())


def test_0078_unit_cost_widens_and_a_downgrade_rounds_to_cents(scratch):
    eng, alembic = scratch
    _to_0078(alembic)
    assert _version(eng) == "0078" and _unit_cost_types(eng) == {(14, 4)}
    w = _workspace(eng)
    with eng.begin() as c:
        for sku, cost in (("a", "1.2345"), ("b", "9999999999.9999"), ("c", "2.5050")):
            c.execute(text("INSERT INTO glass_materials(workspace_id, sku, description, unit_cost)"
                           " VALUES (:w, :s, 'd', :c)"), {"w": w, "s": sku, "c": cost})
    r = alembic("downgrade", "0077")
    assert r.returncode == 0, r.stderr
    assert _unit_cost_types(eng) == {(12, 2)}
    with eng.connect() as c:
        got = dict(c.execute(text("SELECT sku, unit_cost FROM glass_materials")).all())
    assert str(got["a"]) == "1.23" and str(got["c"]) == "2.51"           # rounded half up
    assert str(got["b"]) == "9999999999.99"                              # capped, not an overflow
    assert alembic("upgrade", "head").returncode == 0
    assert _unit_cost_types(eng) == {(14, 4)} and _version(eng) == "0079"
    with eng.begin() as c:
        c.execute(text("UPDATE glass_materials SET unit_cost = 1.2345 WHERE sku = 'a'"))
        assert str(c.execute(text("SELECT unit_cost FROM glass_materials WHERE sku = 'a'")).scalar()) == "1.2345"


def _too_long_then_short(scratch, table, floor, legacy_check):
    eng, alembic = scratch
    _to_0078(alembic)
    w = _workspace(eng)
    long_sku = "L" * 70
    with eng.begin() as c:
        c.execute(text(f"INSERT INTO {table}(workspace_id, sku, description)"
                       f" VALUES (:w, :s, 'd')"), {"w": w, "s": long_sku})
        mid = c.execute(text(f"SELECT material_id FROM {table}")).scalar()
    r = alembic("downgrade", floor)
    assert r.returncode != 0
    assert f"{floor_rev(table)} downgrade refused" in r.stderr
    assert f"id {mid} sku '{long_sku}' (70 characters, limit 64)" in r.stderr
    assert _version(eng) == "0078" and _unit_cost_types(eng) == {(14, 4)}   # nothing changed, 0078 included
    with eng.connect() as c:
        assert c.execute(text(f"SELECT sku FROM {table}")).scalar() == long_sku
    with eng.begin() as c:
        c.execute(text(f"UPDATE {table} SET sku = 'short-sku'"))
    r = alembic("downgrade", floor)
    assert r.returncode == 0, r.stderr
    with eng.connect() as c:
        assert c.execute(text(legacy_check)).scalar() == "short-sku"
    assert alembic("upgrade", "head").returncode == 0
    assert _version(eng) == "0079"


def floor_rev(table):
    return {"timber_materials": "0074", "glass_materials": "0070"}[table]


def test_0074_downgrade_refuses_a_timber_sku_the_legacy_column_cannot_hold(scratch):
    _too_long_then_short(scratch, "timber_materials", "0073",
                         "SELECT slab_id FROM benchtop_materials")


def test_0070_downgrade_refuses_a_glass_sku_the_legacy_column_cannot_hold(scratch):
    _too_long_then_short(scratch, "glass_materials", "0069",
                         "SELECT internal_ref FROM custom_made")


# --- 0079: the columns that copy a catalog SKU -------------------------------------------------------

_COPIES = (("estimate_line_part", "sku_snapshot"), ("estimate_line_hardware", "sku_snapshot"),
           ("po_line_items", "sku"), ("purchase_orders", "product_code"))


def _copy_widths(eng) -> dict[tuple[str, str], int]:
    with eng.connect() as c:
        rows = c.execute(text(
            "SELECT table_name, column_name, character_maximum_length FROM information_schema.columns"
            " WHERE table_schema = 'public' AND (table_name, column_name) IN"
            " (('estimate_line_part','sku_snapshot'),('estimate_line_hardware','sku_snapshot'),"
            "  ('po_line_items','sku'),('purchase_orders','product_code'))")).all()
    return {(t, col): n for t, col, n in rows}


def _view(eng) -> str:
    with eng.connect() as c:
        return c.execute(text("SELECT pg_get_viewdef('v_po_summary'::regclass, true)")).scalar()


def _purchase_order(eng, w, code) -> int:
    with eng.begin() as c:
        uid = c.execute(text("INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)"
                             " VALUES (:w, :e, 'U', 'x', 'admin') RETURNING id"),
                        {"w": w, "e": f"u{uuid.uuid4().hex[:6]}@t"}).scalar()
        vid = c.execute(text("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w)"
                             " RETURNING vendor_id"), {"w": w}).scalar()
        return c.execute(text("INSERT INTO purchase_orders(po_number, vendor_id, requester_id, description, category,"
                              " product_code) VALUES (:n, :v, :u, 'd', 'Board', :c) RETURNING po_id"),
                         {"n": f"PO-{uuid.uuid4().hex[:8]}", "v": vid, "u": uid, "c": code}).scalar()


def test_0079_widens_the_four_sku_copies_and_rebuilds_the_view_unchanged(scratch):
    eng, alembic = scratch
    assert _version(eng) == "0079"
    assert set(_copy_widths(eng).values()) == {255}
    after = _view(eng)
    assert alembic("downgrade", "0078").returncode == 0
    assert _copy_widths(eng) == {("estimate_line_part", "sku_snapshot"): 64,
                                 ("estimate_line_hardware", "sku_snapshot"): 64,
                                 ("po_line_items", "sku"): 100, ("purchase_orders", "product_code"): 100}
    before = _view(eng)
    assert before == after and "po.product_code" in before     # the same definition at both widths
    assert alembic("upgrade", "head").returncode == 0
    assert _view(eng) == after and set(_copy_widths(eng).values()) == {255}
    w = _workspace(eng)
    po = _purchase_order(eng, w, "c" * 200)                      # only fits once widened
    with eng.connect() as c:
        assert c.execute(text("SELECT product_code FROM v_po_summary WHERE po_id = :p"), {"p": po}).scalar() == "c" * 200


@pytest.mark.parametrize("which", range(len(_COPIES)))
def test_0079_downgrade_refuses_a_value_the_narrow_column_cannot_hold_then_narrows(scratch, which):
    eng, alembic = scratch
    table, col = _COPIES[which]
    limit = 64 if table.startswith("estimate_line") else 100
    w = _workspace(eng)
    long_value = "V" * (limit + 5)
    rid = None
    with eng.begin() as c:
        if table == "purchase_orders":
            pid = _purchase_order(eng, w, long_value)
            rid = pid
        else:
            pid = _purchase_order(eng, w, "short")
            if table == "po_line_items":
                rid = c.execute(text("INSERT INTO po_line_items(po_id, line_number, item_description, sku, quantity,"
                                     " unit_price) VALUES (:p, 1, 'd', :s, 1, 1) RETURNING line_id"),
                                {"p": pid, "s": long_value}).scalar()
            else:
                cust = c.execute(text("INSERT INTO customer(workspace_id, name) VALUES (:w, 'C') RETURNING customer_id"),
                                 {"w": w}).scalar()
                est = c.execute(text("INSERT INTO estimate(workspace_id, customer_id, estimate_no, title) VALUES (:w, :c, 'E1', 'E')"
                                     " RETURNING estimate_id"), {"w": w, "c": cust}).scalar()
                rev = c.execute(text("INSERT INTO estimate_revision(estimate_id, rev_no, status) VALUES (:e, 1, 'OPPORTUNITY')"
                                     " RETURNING revision_id"), {"e": est}).scalar()
                lid = c.execute(text("INSERT INTO estimate_line(revision_id, description)"
                                     " VALUES (:r, 'L') RETURNING line_id"), {"r": rev}).scalar()
                if table == "estimate_line_part":
                    rid = c.execute(text("INSERT INTO estimate_line_part(line_id, material_type, sku_snapshot, qty,"
                                         " cost_per_unit_snapshot) VALUES (:l, 'GLASS', :s, 1, 1) RETURNING part_id"),
                                    {"l": lid, "s": long_value}).scalar()
                else:
                    rid = c.execute(text("INSERT INTO estimate_line_hardware(line_id, material_type, sku_snapshot, qty,"
                                         " cost_per_unit_snapshot) VALUES (:l, 'APPLIANCE', :s, 1, 1) RETURNING hw_id"),
                                    {"l": lid, "s": long_value}).scalar()
    view_before = _view(eng)
    r = alembic("downgrade", "0078")
    assert r.returncode != 0
    assert f"0079 downgrade refused" in r.stderr and f"{table}.{col}" in r.stderr
    assert f"id {rid} value '{long_value}' ({limit + 5} characters, limit {limit})" in r.stderr
    assert _version(eng) == "0079" and set(_copy_widths(eng).values()) == {255}    # nothing changed
    assert _view(eng) == view_before
    with eng.begin() as c:
        c.execute(text(f"UPDATE {table} SET {col} = 'short' WHERE {col} = :v"), {"v": long_value})
    assert alembic("downgrade", "0078").returncode == 0
    assert _version(eng) == "0078" and _view(eng) == view_before
    assert alembic("upgrade", "head").returncode == 0 and _version(eng) == "0079"
