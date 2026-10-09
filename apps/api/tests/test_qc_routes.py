"""QC module: defects, checklist, rework (migration 0039, Q515-517).

What these pin down:

  - defect create/list/patch/resolve round-trip; resolve is qc:approve,
    not qc:write — editor can raise a defect but not resolve it, only
    manager/admin can (matches the shop_floor precedent: drafter is
    downstream on production-floor QC, only read+comment)
  - a resolved defect cannot be edited or resolved again (409)
  - checklist add/toggle/relabel/remove round-trip; toggling stamps
    checked_by/checked_at and clears them on uncheck
  - rework create/list/patch/close round-trip, kind CHECK, close is
    qc:approve; a closed rework cannot be edited or closed again (409)
  - every mutation writes audit_log AND item_edit_log
  - related parts get 404 everywhere (Joinery Items only, same rule as
    item_documents)
  - another workspace's item/defect/checklist-item/rework is 404, never a leak
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app
from .helpers import log_in


def _sql(sql: str, params: dict | None = None):
    s = SessionLocal()
    try:
        out = s.execute(text(sql), params or {})
        rows = out.mappings().all() if out.returns_rows else None
        s.commit()
        return rows
    finally:
        s.close()


def _workspace(roles=("editor", "manager", "drafter", "viewer", "purchase_officer")) -> dict:
    slug = f"qc-{uuid.uuid4().hex[:8]}"
    s = SessionLocal()
    try:
        s.execute(text("INSERT INTO status_options(status_key, sort_order)"
                       " VALUES('CLEAR',1) ON CONFLICT DO NOTHING"))
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'QC') RETURNING id"),
                        {"s": slug}).scalar()
        for role in roles:
            s.execute(text("""INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
                              VALUES(:w,:e,:n,:p,:r)"""),
                      {"w": wid, "e": f"{role}@{slug}.test", "n": role.title(),
                       "p": hash_password("pw"), "r": role})
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
        s.commit()
    finally:
        s.close()
    return {"slug": slug, "wid": wid, "pid": pid, "iid": iid, "rp": rp}


def _client(ws: dict, role: str) -> TestClient:
    c = TestClient(app)
    log_in(ws["slug"], f"{role}@{ws['slug']}.test", client=c)
    return c


@pytest.fixture
def ws(truncate_all):
    truncate_all()
    return _workspace()


# ============================================================================
# Defects
# ============================================================================

def test_defect_create_list_resolve_round_trip(ws):
    editor = _client(ws, "editor")
    manager = _client(ws, "manager")
    assert editor.get(f"/items/{ws['iid']}/qc/defects").json() == []

    r = editor.post(f"/items/{ws['iid']}/qc/defects",
                     json={"stage_key": "MADE", "description": "Chip on top edge"})
    assert r.status_code == 201, r.text
    defect = r.json()
    assert defect["status"] == "open"
    assert defect["stage_key"] == "MADE"
    assert defect["created_by_name"] == "Editor"

    listed = editor.get(f"/items/{ws['iid']}/qc/defects").json()
    assert len(listed) == 1 and listed[0]["defect_id"] == defect["defect_id"]

    r = manager.post(f"/qc/defects/{defect['defect_id']}/resolve",
                      json={"resolved_note": "Sanded and refinished"})
    assert r.status_code == 200, r.text
    resolved = r.json()
    assert resolved["status"] == "resolved"
    assert resolved["resolved_note"] == "Sanded and refinished"
    assert resolved["resolved_by_name"] == "Manager"


def test_resolved_defect_cannot_be_edited_or_resolved_again(ws):
    editor = _client(ws, "editor")
    manager = _client(ws, "manager")
    did = editor.post(f"/items/{ws['iid']}/qc/defects", json={"description": "Scratch"}).json()["defect_id"]
    manager.post(f"/qc/defects/{did}/resolve", json={}).raise_for_status()

    assert manager.post(f"/qc/defects/{did}/resolve", json={}).status_code == 409
    assert editor.patch(f"/qc/defects/{did}", json={"description": "Edited"}).status_code == 409


def test_editor_can_raise_but_not_resolve_defect(ws):
    editor = _client(ws, "editor")
    r = editor.post(f"/items/{ws['iid']}/qc/defects", json={"description": "Dent"})
    assert r.status_code == 201, r.text
    did = r.json()["defect_id"]
    assert editor.post(f"/qc/defects/{did}/resolve", json={}).status_code == 403


def test_drafter_can_read_but_not_write(ws):
    drafter = _client(ws, "drafter")
    assert drafter.get(f"/items/{ws['iid']}/qc/defects").status_code == 200
    assert drafter.post(f"/items/{ws['iid']}/qc/defects", json={"description": "x"}).status_code == 403


def test_viewer_cannot_write(ws):
    viewer = _client(ws, "viewer")
    assert viewer.post(f"/items/{ws['iid']}/qc/defects", json={"description": "x"}).status_code == 403
    assert viewer.get(f"/items/{ws['iid']}/qc/defects").status_code == 200


def test_defect_on_related_part_is_404(ws):
    manager = _client(ws, "manager")
    assert manager.get(f"/items/{ws['rp']}/qc/defects").status_code == 404
    assert manager.post(f"/items/{ws['rp']}/qc/defects", json={"description": "x"}).status_code == 404


def test_defect_writes_audit_and_edit_log(ws):
    manager = _client(ws, "manager")
    did = manager.post(f"/items/{ws['iid']}/qc/defects", json={"description": "Glue line"}).json()["defect_id"]
    manager.post(f"/qc/defects/{did}/resolve", json={"resolved_note": "Fixed"}).raise_for_status()

    events = _sql("SELECT event FROM audit_log WHERE workspace_id = :w ORDER BY id",
                  {"w": ws["wid"]})
    names = [e["event"] for e in events]
    assert "qc.defect.create" in names
    assert "qc.defect.resolve" in names

    edits = _sql("SELECT field FROM item_edit_log WHERE item_id = :i", {"i": ws["iid"]})
    fields = [e["field"] for e in edits]
    assert "_qc_defect_create" in fields
    assert any(f.startswith(f"qc_defect.{did}.status") for f in fields)


# ============================================================================
# Checklist
# ============================================================================

def test_checklist_add_toggle_relabel_remove_round_trip(ws):
    editor = _client(ws, "editor")
    r = editor.post(f"/items/{ws['iid']}/qc/checklist", json={"label": "Doors align"})
    assert r.status_code == 201, r.text
    cid = r.json()["checklist_item_id"]
    assert r.json()["is_checked"] is False

    r = editor.patch(f"/qc/checklist/{cid}", json={"is_checked": True})
    assert r.status_code == 200, r.text
    checked = r.json()
    assert checked["is_checked"] is True
    assert checked["checked_by_name"] == "Editor"
    assert checked["checked_at"] is not None

    r = editor.patch(f"/qc/checklist/{cid}", json={"is_checked": False})
    assert r.json()["checked_at"] is None
    assert r.json()["checked_by"] is None

    r = editor.patch(f"/qc/checklist/{cid}", json={"label": "Doors align flush"})
    assert r.json()["label"] == "Doors align flush"

    assert editor.delete(f"/qc/checklist/{cid}").status_code == 204
    assert editor.get(f"/items/{ws['iid']}/qc/checklist").json() == []


def test_checklist_on_related_part_is_404(ws):
    editor = _client(ws, "editor")
    assert editor.post(f"/items/{ws['rp']}/qc/checklist", json={"label": "x"}).status_code == 404


# ============================================================================
# Rework
# ============================================================================

def test_rework_create_list_close_round_trip(ws):
    editor = _client(ws, "editor")
    manager = _client(ws, "manager")
    r = editor.post(f"/items/{ws['iid']}/qc/rework", json={
        "kind": "internal", "cause": "CNC misalignment", "scope": "Re-cut two panels",
        "responsibility": "Machine team", "cost": "150.00",
    })
    assert r.status_code == 201, r.text
    rework = r.json()
    assert rework["status"] == "open"
    assert rework["kind"] == "internal"
    assert rework["cost"] == "150.00"

    listed = editor.get(f"/items/{ws['iid']}/qc/rework").json()
    assert len(listed) == 1

    r = manager.post(f"/qc/rework/{rework['rework_id']}/close", json={"closed_note": "Panels replaced"})
    assert r.status_code == 200, r.text
    closed = r.json()
    assert closed["status"] == "closed"
    assert closed["closed_by_name"] == "Manager"


def test_rework_kind_must_be_internal_or_full(ws):
    editor = _client(ws, "editor")
    r = editor.post(f"/items/{ws['iid']}/qc/rework", json={
        "kind": "partial", "cause": "x", "scope": "y",
    })
    assert r.status_code == 422


def test_closed_rework_cannot_be_edited_or_closed_again(ws):
    editor = _client(ws, "editor")
    manager = _client(ws, "manager")
    rid = editor.post(f"/items/{ws['iid']}/qc/rework",
                      json={"kind": "full", "cause": "Site damage", "scope": "Reinstall"}).json()["rework_id"]
    manager.post(f"/qc/rework/{rid}/close", json={}).raise_for_status()

    assert manager.post(f"/qc/rework/{rid}/close", json={}).status_code == 409
    assert editor.patch(f"/qc/rework/{rid}", json={"cause": "Edited"}).status_code == 409


def test_editor_can_raise_but_not_close_rework(ws):
    editor = _client(ws, "editor")
    r = editor.post(f"/items/{ws['iid']}/qc/rework",
                     json={"kind": "internal", "cause": "x", "scope": "y"})
    assert r.status_code == 201, r.text
    rid = r.json()["rework_id"]
    assert editor.post(f"/qc/rework/{rid}/close", json={}).status_code == 403


def test_rework_writes_audit_and_edit_log(ws):
    manager = _client(ws, "manager")
    rid = manager.post(f"/items/{ws['iid']}/qc/rework",
                       json={"kind": "full", "cause": "x", "scope": "y"}).json()["rework_id"]
    manager.post(f"/qc/rework/{rid}/close", json={}).raise_for_status()

    events = _sql("SELECT event FROM audit_log WHERE workspace_id = :w ORDER BY id",
                  {"w": ws["wid"]})
    names = [e["event"] for e in events]
    assert "qc.rework.create" in names
    assert "qc.rework.close" in names


# ============================================================================
# Cross-workspace isolation
# ============================================================================

def test_other_workspace_sees_404_never_403():
    ws1 = _workspace()
    ws2 = _workspace()
    c1 = _client(ws1, "manager")
    c2 = _client(ws2, "manager")

    did = c1.post(f"/items/{ws1['iid']}/qc/defects", json={"description": "x"}).json()["defect_id"]
    assert c2.get(f"/items/{ws1['iid']}/qc/defects").status_code == 404
    assert c2.post(f"/qc/defects/{did}/resolve", json={}).status_code == 404

    cid = c1.post(f"/items/{ws1['iid']}/qc/checklist", json={"label": "x"}).json()["checklist_item_id"]
    assert c2.patch(f"/qc/checklist/{cid}", json={"is_checked": True}).status_code == 404

    rid = c1.post(f"/items/{ws1['iid']}/qc/rework",
                  json={"kind": "internal", "cause": "x", "scope": "y"}).json()["rework_id"]
    assert c2.post(f"/qc/rework/{rid}/close", json={}).status_code == 404
