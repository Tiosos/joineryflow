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
    assert _unit_cost_types(eng) == {(14, 4)} and _version(eng) == "0078"
    with eng.begin() as c:
        c.execute(text("UPDATE glass_materials SET unit_cost = 1.2345 WHERE sku = 'a'"))
        assert str(c.execute(text("SELECT unit_cost FROM glass_materials WHERE sku = 'a'")).scalar()) == "1.2345"


def _too_long_then_short(scratch, table, floor, legacy_check):
    eng, alembic = scratch
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
    assert _version(eng) == "0078"


def floor_rev(table):
    return {"timber_materials": "0074", "glass_materials": "0070"}[table]


def test_0074_downgrade_refuses_a_timber_sku_the_legacy_column_cannot_hold(scratch):
    _too_long_then_short(scratch, "timber_materials", "0073",
                         "SELECT slab_id FROM benchtop_materials")


def test_0070_downgrade_refuses_a_glass_sku_the_legacy_column_cannot_hold(scratch):
    _too_long_then_short(scratch, "glass_materials", "0069",
                         "SELECT internal_ref FROM custom_made")
