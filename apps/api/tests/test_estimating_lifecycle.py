"""Tests for the 12-stage tender lifecycle (Plan V1 §5, Q487/488/548)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.estimating.queries import TENDER_STAGE_ORDER
from app.main import app



pytestmark = pytest.mark.usefixtures("truncate_after")


def _bootstrap(role: str = "estimator"):
    suffix = uuid.uuid4().hex[:8]
    slug = f"tl-{suffix}"
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


def _make_estimate(c: TestClient) -> dict:
    cust = c.post("/customers", json={"name": f"C-{uuid.uuid4().hex[:6]}"}).json()
    r = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "Job"})
    assert r.status_code == 201, r.text
    return r.json()


def test_new_estimate_starts_at_opportunity():
    c = _bootstrap()
    est = _make_estimate(c)
    assert est["revisions"][0]["status"] == "OPPORTUNITY"


def test_advance_walks_all_ten_stages_to_submitted():
    c = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    c.post(f"/revisions/{rid}/lines", json={"description": "L", "qty": 1})
    seen = []
    for _ in range(10):
        r = c.post(f"/revisions/{rid}/advance")
        assert r.status_code == 200, r.text
        seen.append(r.json()["status"])
    assert seen == list(TENDER_STAGE_ORDER[1:])
    assert seen[-1] == "SUBMITTED"


def test_advance_from_submitted_is_illegal():
    c = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    c.post(f"/revisions/{rid}/lines", json={"description": "L", "qty": 1})
    for _ in range(10):
        c.post(f"/revisions/{rid}/advance")
    r = c.post(f"/revisions/{rid}/advance")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "BAD_TRANSITION"


@pytest.mark.parametrize("n_advances", [0, 1, 5, 9])
def test_withdraw_legal_from_any_pre_submitted_stage(n_advances):
    c = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    for _ in range(n_advances):
        c.post(f"/revisions/{rid}/advance")
    r = c.post(f"/revisions/{rid}/withdraw", json={"lost_reason": None})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "WITHDRAWN"


def test_accept_reject_only_legal_from_submitted():
    c = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    r = c.post(f"/revisions/{rid}/accept")
    assert r.status_code == 409
    r = c.post(f"/revisions/{rid}/reject", json={"lost_reason": "no"})
    assert r.status_code == 409


def test_expire_and_reject_are_distinct_audit_events():
    c = _bootstrap()
    rid1 = _make_estimate(c)["current_revision_id"]
    c.post(f"/revisions/{rid1}/lines", json={"description": "L", "qty": 1})
    for _ in range(10):
        c.post(f"/revisions/{rid1}/advance")
    c.post(f"/revisions/{rid1}/reject", json={"lost_reason": "price"})

    rid2 = _make_estimate(c)["current_revision_id"]
    c.post(f"/revisions/{rid2}/lines", json={"description": "L", "qty": 1})
    for _ in range(10):
        c.post(f"/revisions/{rid2}/advance")
    c.post(f"/revisions/{rid2}/expire", json={"lost_reason": "lapsed"})

    s = SessionLocal()
    try:
        events = {
            r["target"]: r["event"]
            for r in s.execute(
                text(
                    "SELECT target, event FROM audit_log "
                    "WHERE event IN ('estimate.reject', 'estimate.expire')"
                )
            ).mappings()
        }
    finally:
        s.close()
    assert events[str(rid1)] == "estimate.reject"
    assert events[str(rid2)] == "estimate.expire"
    # Both land on the same status (Q548) despite the different audit event.
    s = SessionLocal()
    try:
        statuses = s.execute(
            text("SELECT revision_id, status FROM estimate_revision WHERE revision_id IN (:a,:b)"),
            {"a": rid1, "b": rid2},
        ).all()
    finally:
        s.close()
    assert {status for _, status in statuses} == {"LOST"}


def test_revise_after_won_starts_at_estimating():
    c = _bootstrap()
    est = _make_estimate(c)
    eid, rid = est["estimate_id"], est["current_revision_id"]
    c.post(f"/revisions/{rid}/lines", json={"description": "L", "qty": 1})
    for _ in range(10):
        c.post(f"/revisions/{rid}/advance")
    r = c.post(f"/revisions/{rid}/accept")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "WON"

    r = c.post(f"/estimates/{eid}/revise")
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "ESTIMATING"


def test_new_revision_blocked_while_one_is_unlocked():
    c = _bootstrap()
    est = _make_estimate(c)
    r = c.post(f"/estimates/{est['estimate_id']}/revise")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "DRAFT_EXISTS"


def test_send_route_no_longer_exists():
    """`/send` was retired in favour of the generic `/advance` (the one
    sequential step with real business logic, MGMT_APPROVAL -> SUBMITTED,
    fires through transition_revision's target=="SUBMITTED" branch instead
    of a dedicated entry point)."""
    c = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    r = c.post(f"/revisions/{rid}/send")
    assert r.status_code == 404
