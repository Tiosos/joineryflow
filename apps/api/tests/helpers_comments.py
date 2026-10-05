"""Helpers shared by the comment, module/revision comment and comment-count tests."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app


ROLES = ("manager", "drafter", "editor", "purchase_officer", "viewer")


def _workspace() -> dict:
    slug = f"cm-{uuid.uuid4().hex[:8]}"
    s = SessionLocal()
    try:
        s.execute(text("INSERT INTO status_options(status_key, sort_order)"
                       " VALUES('CLEAR',1) ON CONFLICT DO NOTHING"))
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'CM') RETURNING id"),
                        {"s": slug}).scalar()
        uids = {}
        for role in ROLES:
            uids[role] = s.execute(
                text("""INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
                        VALUES(:w,:e,:n,:p,:r) RETURNING id"""),
                {"w": wid, "e": f"{role}@{slug}.test", "n": role.title(),
                 "p": hash_password("pw"), "r": role}).scalar()
        pid = s.execute(text("""INSERT INTO projects(project_code,name,workspace_id)
                                VALUES(:c,:c,:w) RETURNING project_id"""),
                        {"c": slug.upper(), "w": wid}).scalar()
        aid = s.execute(text("INSERT INTO area(project_id, name) VALUES(:p,'Level 1') RETURNING area_id"),
                        {"p": pid}).scalar()
        rid = s.execute(text("INSERT INTO room(area_id, rm_no) VALUES(:a,'R01') RETURNING room_id"),
                        {"a": aid}).scalar()
        iid = s.execute(text("""INSERT INTO items(num, project_id, description, status)
                                VALUES (nextval('joinery_number_seq'), :p, 'Vanity', 'CLEAR')
                                RETURNING item_id"""), {"p": pid}).scalar()
        rp = s.execute(text("""INSERT INTO items(num, project_id, description, status, row_type,
                                                 parent_item_id, related_part_type_key)
                               VALUES (nextval('joinery_number_seq'), :p, 'Top', 'CLEAR',
                                       'related_part', :par, 'benchtop')
                               RETURNING item_id"""), {"p": pid, "par": iid}).scalar()
        s.commit()
    finally:
        s.close()
    return {"slug": slug, "wid": wid, "pid": pid, "aid": aid, "rid": rid,
            "iid": iid, "rp": rp, "uid": uids}


def _client(ws: dict, role: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": ws["slug"],
                                    "email": f"{role}@{ws['slug']}.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return c


def _sql(query, **params):
    s = SessionLocal()
    try:
        return s.execute(text(query), params).all()
    finally:
        s.close()


def _inbox(ws, role, **params):
    r = _client(ws, role).get("/notifications", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _restrict(ws, role, grants):
    """Make `role`'s user governed by the DB alone, holding only `grants`
    (list of (module, action)). Returns the group id so a test can change it."""
    s = SessionLocal()
    try:
        gid = s.execute(text("""INSERT INTO permission_group(workspace_id, name, is_system)
                                VALUES (:w, :n, false) RETURNING group_id"""),
                        {"w": ws["wid"], "n": f"only-{role}-{uuid.uuid4().hex[:4]}"}).scalar()
        for module, action in grants:
            s.execute(text("INSERT INTO group_module_grant(group_id, module, action)"
                           " VALUES (:g, :m, :a)"), {"g": gid, "m": module, "a": action})
        s.execute(text("INSERT INTO user_group_membership(user_id, group_id, project_id)"
                       " VALUES (:u, :g, NULL)"), {"u": ws["uid"][role], "g": gid})
        s.commit()
    finally:
        s.close()
    return gid


def _set_grants(gid, grants):
    s = SessionLocal()
    try:
        s.execute(text("DELETE FROM group_module_grant WHERE group_id = :g"), {"g": gid})
        for module, action in grants:
            s.execute(text("INSERT INTO group_module_grant(group_id, module, action)"
                           " VALUES (:g, :m, :a)"), {"g": gid, "m": module, "a": action})
        s.commit()
    finally:
        s.close()


def _extend(ws: dict) -> dict:
    """Add a module (and one on the related part), and a drawing with one draft
    revision, to a `_workspace()`."""
    s = SessionLocal()
    try:
        ws["mid"] = s.execute(text("""INSERT INTO modules(item_id, module_no, name)
                                      VALUES (:i, 'M01', 'Base') RETURNING module_id"""),
                              {"i": ws["iid"]}).scalar()
        ws["rp_mid"] = s.execute(text("""INSERT INTO modules(item_id, module_no, name)
                                         VALUES (:i, 'M01', 'Top') RETURNING module_id"""),
                                 {"i": ws["rp"]}).scalar()
        blob = s.execute(text("""INSERT INTO file_blob(workspace_id, sha256, mime, byte_size,
                                                       original_filename, storage_key, uploaded_by)
                                 VALUES (:w, :h, 'application/pdf', 10, 'a.pdf', 'k', :u)
                                 RETURNING file_blob_id"""),
                         {"w": ws["wid"], "h": ws["slug"], "u": ws["uid"]["drafter"]}).scalar()
        ws["did"] = s.execute(text("""INSERT INTO shop_drawing(project_id, title, created_by)
                                      VALUES (:p, 'Vanity plan', :u) RETURNING drawing_id"""),
                              {"p": ws["pid"], "u": ws["uid"]["drafter"]}).scalar()
        ws["vid"] = s.execute(text("""INSERT INTO shop_drawing_revision(
                                          drawing_id, rev_no, file_blob_id, status, uploaded_by)
                                      VALUES (:d, 1, :b, 'draft', :u) RETURNING revision_id"""),
                              {"d": ws["did"], "b": blob, "u": ws["uid"]["drafter"]}).scalar()
        ws["num"] = s.execute(text("SELECT num FROM items WHERE item_id = :i"),
                              {"i": ws["iid"]}).scalar()
        s.commit()
    finally:
        s.close()
    return ws


_ID = {"module": "mid", "revision": "vid", "item": "iid", "project": "pid"}


def _t(ws, kind):
    return {"object_type": kind, "object_id": ws[_ID[kind]]}


@pytest.fixture(name="ws")
def module_revision_ws(truncate_all):
    truncate_all()
    return _extend(_workspace())


def post_module(c, ws, body="Hello", kind="module", **extra):
    return c.post("/comments", json={**_t(ws, kind), "body": body, **extra})
