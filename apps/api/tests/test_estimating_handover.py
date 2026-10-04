"""Tests for the handover review screen (Q490) and Contract Value at
handover (Q491)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app



pytestmark = pytest.mark.usefixtures("truncate_after")


def _bootstrap(role: str = "estimator"):
    suffix = uuid.uuid4().hex[:8]
    slug = f"ho-{suffix}"
    email = f"u-{suffix}@t"
    s = SessionLocal()
    try:
        wid = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'T') RETURNING id"),
            {"s": slug},
        ).scalar()
        s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, :r)
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
        )
        s.commit()
    finally:
        s.close()
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    return c


def _make_won_estimate_with_two_lines(c: TestClient) -> dict:
    cust = c.post("/customers", json={"name": f"C-{uuid.uuid4().hex[:6]}"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "Kitchen"}).json()
    rid = est["current_revision_id"]
    l1 = c.post(f"/revisions/{rid}/lines", json={"description": "Pantry", "qty": 1}).json()
    l2 = c.post(f"/revisions/{rid}/lines", json={"description": "Island", "qty": 1}).json()
    for _ in range(10):
        c.post(f"/revisions/{rid}/advance")
    r = c.post(f"/revisions/{rid}/accept")
    assert r.status_code == 200, r.text
    return {"estimate_id": est["estimate_id"], "revision_id": rid,
            "line_ids": [l1["line_id"], l2["line_id"]]}


def test_handover_preview_lists_lines_and_proposed_value():
    c = _bootstrap()
    won = _make_won_estimate_with_two_lines(c)
    r = c.get(f"/revisions/{won['revision_id']}/handover-preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "WON"
    assert body["already_converted_project_id"] is None
    assert {l["line_id"] for l in body["lines"]} == set(won["line_ids"])
    assert float(body["proposed_contract_value"]) >= 0


def test_convert_defaults_to_all_lines_and_quote_total():
    c = _bootstrap()
    won = _make_won_estimate_with_two_lines(c)
    preview = c.get(f"/revisions/{won['revision_id']}/handover-preview").json()
    r = c.post(f"/revisions/{won['revision_id']}/convert")
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["items_created"] == 2
    assert float(result["contract_value"]) == float(preview["proposed_contract_value"])

    contract = c.get(f"/projects/{result['project_id']}/contract").json()
    assert float(contract["original_value"]) == float(result["contract_value"])
    assert float(contract["current_value"]) == float(contract["original_value"])
    assert contract["variations"] == []


def test_convert_excludes_deselected_lines():
    c = _bootstrap()
    won = _make_won_estimate_with_two_lines(c)
    r = c.post(f"/revisions/{won['revision_id']}/convert",
               json={"include_line_ids": [won["line_ids"][0]]})
    assert r.status_code == 200, r.text
    assert r.json()["items_created"] == 1


def test_convert_rejects_unknown_line_id():
    c = _bootstrap()
    won = _make_won_estimate_with_two_lines(c)
    r = c.post(f"/revisions/{won['revision_id']}/convert",
               json={"include_line_ids": [999999]})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "UNKNOWN_LINE_IDS"


def test_convert_accepts_explicit_contract_value_override():
    c = _bootstrap()
    won = _make_won_estimate_with_two_lines(c)
    r = c.post(f"/revisions/{won['revision_id']}/convert",
               json={"contract_value": "12345.67"})
    assert r.status_code == 200, r.text
    assert float(r.json()["contract_value"]) == 12345.67


def test_convert_still_requires_won_status():
    c = _bootstrap()
    cust = c.post("/customers", json={"name": f"C-{uuid.uuid4().hex[:6]}"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "Job"}).json()
    r = c.post(f"/revisions/{est['current_revision_id']}/convert")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "BAD_STATUS"
