"""`GET /public/stats` is the one route with no login (the login page's brand panel).

It must return exactly three whole-workspace counts for the slug it is given, nothing else, and
never count a soft-deleted item's parts or another workspace's rows. docs/REVIEW-2026-10.md A4.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import SessionLocal
from app.main import app

from .conftest import truncate_after  # noqa: F401

pytestmark = pytest.mark.usefixtures("truncate_after")


def _sql(sql, **p):
    s = SessionLocal()
    try:
        r = s.execute(text(sql), p)
        out = r.scalar() if r.returns_rows else None
        s.commit()
        return out
    finally:
        s.close()


def _workspace() -> tuple[str, int]:
    slug = f"pub-{uuid.uuid4().hex[:8]}"
    return slug, _sql("INSERT INTO workspace(slug, name) VALUES (:s, 'P') RETURNING id", s=slug)


def _item_with_parts(wid: int, parts: int, *, deleted: bool = False) -> None:
    pid = _sql("INSERT INTO projects(project_code, name, workspace_id) VALUES (:c, :n, :w)"
               " RETURNING project_id", c=f"P{uuid.uuid4().hex[:5]}", n=f"P {uuid.uuid4().hex[:8]}", w=wid)
    iid = _sql("INSERT INTO items(num, project_id, description, status, deleted)"
               " VALUES (nextval('joinery_number_seq'), :p, 'x', 'LIVE', :d) RETURNING item_id",
               p=pid, d=deleted)
    mid = _sql("INSERT INTO modules(item_id, module_no) VALUES (:i, 1) RETURNING module_id", i=iid)
    for _ in range(parts):
        _sql("INSERT INTO parts(module_id, qty, len_mm, wid_mm) VALUES (:m, 1, 100, 100)", m=mid)


def _supplier(wid: int, table: str, name: str) -> None:
    # board_materials keys on code (and has a sku); hardware_materials on sku alone
    cols, vals = ("code, sku", ":c, :c") if table == "board_materials" else ("sku", ":c")
    _sql(f"INSERT INTO {table}({cols}, description, supplier, workspace_id)"
         f" VALUES ({vals}, 'd', :s, :w)", c=f"C{uuid.uuid4().hex[:6]}", s=name, w=wid)


def _stats(slug: str | None):
    params = {} if slug is None else {"workspace_slug": slug}
    return TestClient(app).get("/public/stats", params=params)


def test_counts_only_this_workspaces_live_rows_and_answers_without_a_login():
    slug, wid = _workspace()
    other_slug, other = _workspace()
    _item_with_parts(wid, 3)
    _item_with_parts(wid, 5, deleted=True)   # a soft-deleted item's parts are not tracked
    _item_with_parts(other, 7)               # another workspace's rows are not counted
    _supplier(wid, "board_materials", "Plyco")
    _supplier(wid, "hardware_materials", "Plyco")    # the same name twice counts once
    _supplier(wid, "hardware_materials", "Hettich")
    _supplier(other, "board_materials", "Elsewhere")

    r = _stats(slug)   # a fresh client: no cookie
    assert r.status_code == 200, r.text
    assert r.json() == {"projects_live": 2, "parts_tracked": 3, "suppliers": 2}
    assert _stats(other_slug).json() == {"projects_live": 1, "parts_tracked": 7, "suppliers": 1}


def test_an_unknown_slug_answers_zeros_and_a_missing_slug_is_422():
    r = _stats("no-such-workspace")
    assert (r.status_code, r.json()) == (200, {"projects_live": 0, "parts_tracked": 0, "suppliers": 0})
    assert _stats(None).status_code == 422
