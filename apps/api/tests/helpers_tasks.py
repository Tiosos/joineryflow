"""Helpers for the task tests (migration 0080): one workspace with a user per role,
a project, a live item, a related part and a cutlist."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

ROLES = ("admin", "manager", "drafter", "editor", "estimator", "purchase_officer", "viewer")


def workspace() -> dict:
    slug = f"tk-{uuid.uuid4().hex[:8]}"
    s = SessionLocal()
    try:
        s.execute(text("INSERT INTO status_options(status_key, sort_order)"
                       " VALUES('CLEAR',1) ON CONFLICT DO NOTHING"))
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'TK') RETURNING id"),
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
        iid = s.execute(text("""INSERT INTO items(num, project_id, description, status)
                                VALUES (nextval('joinery_number_seq'), :p, 'Vanity', 'CLEAR')
                                RETURNING item_id"""), {"p": pid}).scalar()
        rp = s.execute(text("""INSERT INTO items(num, project_id, description, status, row_type,
                                                 parent_item_id, related_part_type_key)
                               VALUES (nextval('joinery_number_seq'), :p, 'Top', 'CLEAR',
                                       'related_part', :par, 'benchtop')
                               RETURNING item_id"""), {"p": pid, "par": iid}).scalar()
        cid = s.execute(text("""INSERT INTO cutlist(project_id, cutlist_no, name)
                                VALUES (:p, nextval('joinery_number_seq'), 'Run 1')
                                RETURNING cutlist_id"""), {"p": pid}).scalar()
        s.commit()
    finally:
        s.close()
    return {"slug": slug, "wid": wid, "pid": pid, "iid": iid, "rp": rp, "cid": cid, "uid": uids}


def client(ws: dict, role: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": ws["slug"],
                                    "email": f"{role}@{ws['slug']}.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return c


def sql(statement: str, **params):
    """Run one committed statement; returns the first column of the first row, if any."""
    s = SessionLocal()
    try:
        r = s.execute(text(statement), params)
        out = r.scalar() if r.returns_rows else None
        s.commit()
        return out
    finally:
        s.close()
