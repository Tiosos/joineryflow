"""Helpers shared by the Material Take route, summary and lock tests."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import TRUNCATE_TABLES


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        s.execute(text("TRUNCATE board_inventory, board_materials, "
                       + ", ".join(TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _sql(sql, **p):
    s = SessionLocal()
    try:
        r = s.execute(text(sql), p)
        out = r.scalar() if r.returns_rows else None
        s.commit()
        return out
    finally:
        s.close()


def _workspace():
    return _sql("INSERT INTO workspace(slug, name) VALUES (:s, 'MT') RETURNING id",
                s=f"mt-{uuid.uuid4().hex[:8]}")


def _client(wid, role):
    email = f"{role}-{uuid.uuid4().hex[:6]}@x.test"
    _sql("INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)"
         " VALUES (:w, :e, 'U', :p, :r)", w=wid, e=email, p=hash_password("pw"), r=role)
    slug = _sql("SELECT slug FROM workspace WHERE id = :w", w=wid)
    c = TestClient(app)
    assert c.post("/auth/login", json={"workspace_slug": slug, "email": email,
                                       "password": "pw"}).status_code == 200
    return c


def _item(wid, *, parts=((2000, 600, 4),), related=False):
    pid = _sql("INSERT INTO projects(project_code, name, workspace_id) VALUES ('MT', :n, :w)"
               " RETURNING project_id", n=f"MT {uuid.uuid4().hex[:6]}", w=wid)  # name is UNIQUE
    iid = _sql("""INSERT INTO items(num, project_id, description, status)
                  VALUES (nextval('joinery_number_seq'), :p, 'Vanity', 'LIVE') RETURNING item_id""", p=pid)
    bid = _sql("INSERT INTO board_materials(code, description, sku, workspace_id)"
               " VALUES (:c, '18mm MDF', :c, :w) RETURNING material_id", c=f"MT-{iid}", w=wid)
    _sql("INSERT INTO board_inventory(workspace_id, material_id, len_mm, wid_mm, qty_on_hand)"
         " VALUES (:w, :b, 2440, 1220, 5)", w=wid, b=bid)
    mid = _sql("INSERT INTO modules(item_id, module_no) VALUES (:i, 1) RETURNING module_id", i=iid)
    for ln, wd, qty in parts:
        _sql("INSERT INTO parts(module_id, qty, len_mm, wid_mm, board_material_id)"
             " VALUES (:m, :q, :l, :d, :b)", m=mid, q=qty, l=ln, d=wd, b=bid)
    rp = None
    if related:
        rp = _sql("""INSERT INTO items(num, project_id, description, status, row_type,
                                       parent_item_id, related_part_type_key)
                     VALUES (nextval('joinery_number_seq'), :p, 'Frame', 'LIVE', 'related_part',
                             :i, 'metal') RETURNING item_id""", p=pid, i=iid)
    return {"item": iid, "module": mid, "board": bid, "related": rp}
