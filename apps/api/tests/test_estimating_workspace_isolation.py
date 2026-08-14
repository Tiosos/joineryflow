"""Cross-workspace estimating access must not leak (no existence disclosure).

Estimating was the only module without an isolation suite, despite being the
largest surface in the app (32 routes, 8 tables, a new auth role) and the one
holding commercial data — customer contacts, quoted prices, win/loss reasons.

Both workspaces' users are `admin` on purpose: admin holds every action on
`estimating` and `it_management`, so a route that blocks here can only be
blocking on workspace scope. A lower-privileged caller would 403 first and
mask the thing under test.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _seed_two_workspaces(truncate_all):
    """Workspace A holds a full estimate tree; workspace B holds only a user."""
    truncate_all()
    from app.auth.passwords import hash_password
    from app.db import SessionLocal

    s = SessionLocal()
    try:
        wid_a = s.execute(
            text("INSERT INTO workspace(slug,name) VALUES('esta','A') RETURNING id")
        ).scalar()
        uid_a = s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name,
                                     password_hash, auth_role)
                VALUES (:w, 'a@est.test', 'A', :p, 'admin') RETURNING id
                """
            ),
            {"w": wid_a, "p": hash_password("pw")},
        ).scalar()
        cid_a = s.execute(
            text(
                """
                INSERT INTO customer(workspace_id, name, email, created_by)
                VALUES (:w, 'Confidential Client', 'client@a.test', :u)
                RETURNING customer_id
                """
            ),
            {"w": wid_a, "u": uid_a},
        ).scalar()
        eid_a = s.execute(
            text(
                """
                INSERT INTO estimate(workspace_id, customer_id, estimate_no,
                                     title, created_by)
                VALUES (:w, :c, 'EST-2026-001', 'Hidden job', :u)
                RETURNING estimate_id
                """
            ),
            {"w": wid_a, "c": cid_a, "u": uid_a},
        ).scalar()
        rid_a = s.execute(
            text(
                """
                INSERT INTO estimate_revision(estimate_id, rev_no, status,
                                              created_by)
                VALUES (:e, 1, 'draft', :u)
                RETURNING revision_id
                """
            ),
            {"e": eid_a, "u": uid_a},
        ).scalar()
        s.execute(
            text("UPDATE estimate SET current_revision_id = :r WHERE estimate_id = :e"),
            {"r": rid_a, "e": eid_a},
        )
        lid_a = s.execute(
            text(
                """
                INSERT INTO estimate_line(revision_id, seq, description, qty)
                VALUES (:r, 1, 'Hidden line', 1)
                RETURNING line_id
                """
            ),
            {"r": rid_a},
        ).scalar()
        s.execute(
            text(
                """
                INSERT INTO workspace_labour_rate(workspace_id, stage_key,
                                                  hourly_rate, updated_by)
                VALUES (:w, 'CNC', 123.45, :u)
                """
            ),
            {"w": wid_a, "u": uid_a},
        )

        wid_b = s.execute(
            text("INSERT INTO workspace(slug,name) VALUES('estb','B') RETURNING id")
        ).scalar()
        s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name,
                                     password_hash, auth_role)
                VALUES (:w, 'b@est.test', 'B', :p, 'admin')
                """
            ),
            {"w": wid_b, "p": hash_password("pw")},
        )
        s.commit()
        return {
            "cid_a": cid_a, "eid_a": eid_a, "rid_a": rid_a, "lid_a": lid_a,
            "wid_a": wid_a, "wid_b": wid_b,
        }
    finally:
        s.close()


def _login_b(client: TestClient):
    r = client.post(
        "/auth/login",
        json={"workspace_slug": "estb", "email": "b@est.test", "password": "pw"},
    )
    assert r.status_code == 200, r.text


# ── Customers ─────────────────────────────────────────────────────────────────

def test_get_customer_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    assert client.get(f"/customers/{ids['cid_a']}").status_code == 404


def test_list_customers_excludes_other_workspace(client, truncate_all):
    _seed_two_workspaces(truncate_all)
    _login_b(client)
    r = client.get("/customers")
    assert r.status_code == 200
    assert r.json() == []


def test_patch_customer_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    r = client.patch(f"/customers/{ids['cid_a']}", json={"name": "Renamed"})
    assert r.status_code == 404


def test_archive_customer_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    assert client.post(f"/customers/{ids['cid_a']}/archive").status_code == 404


# ── Estimates ─────────────────────────────────────────────────────────────────

def test_get_estimate_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    assert client.get(f"/estimates/{ids['eid_a']}").status_code == 404


def test_list_estimates_excludes_other_workspace(client, truncate_all):
    _seed_two_workspaces(truncate_all)
    _login_b(client)
    r = client.get("/estimates")
    assert r.status_code == 200
    assert r.json()["estimates"] == []


def test_patch_estimate_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    r = client.patch(f"/estimates/{ids['eid_a']}", json={"title": "Renamed"})
    assert r.status_code == 404


def test_revise_estimate_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    assert client.post(f"/estimates/{ids['eid_a']}/revise").status_code == 404


def test_estimate_no_sequence_does_not_leak_across_workspaces(client, truncate_all):
    """B's first estimate is EST-…-001 even though A already holds that number.

    `uq_estimate_no` is per-workspace, so a shared counter would collide *and*
    disclose how many estimates the other workspace has.
    """
    _seed_two_workspaces(truncate_all)
    _login_b(client)
    cust = client.post("/customers", json={"name": "B Client"})
    assert cust.status_code == 201, cust.text
    r = client.post(
        "/estimates",
        json={"customer_id": cust.json()["customer_id"], "title": "B job"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["estimate_no"].endswith("-0001")


# ── Revisions ─────────────────────────────────────────────────────────────────

def test_get_revision_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    r = client.get(f"/estimates/{ids['eid_a']}/revisions/{ids['rid_a']}")
    assert r.status_code == 404


def test_patch_revision_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    r = client.patch(f"/revisions/{ids['rid_a']}", json={"markup_pct": 99})
    assert r.status_code == 404


@pytest.mark.parametrize(
    "action", ["send", "accept", "reject", "expire", "withdraw", "convert"]
)
def test_revision_transitions_cross_workspace_return_404(client, truncate_all, action):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    r = client.post(f"/revisions/{ids['rid_a']}/{action}")
    assert r.status_code == 404, f"{action} -> {r.status_code} {r.text}"


def test_revision_status_unchanged_after_foreign_transition_attempt(client, truncate_all):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    client.post(f"/revisions/{ids['rid_a']}/send")
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        status = s.execute(
            text("SELECT status FROM estimate_revision WHERE revision_id = :r"),
            {"r": ids["rid_a"]},
        ).scalar()
    finally:
        s.close()
    assert status == "draft"


def test_quote_pdf_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    assert client.get(f"/revisions/{ids['rid_a']}/quote.pdf").status_code == 404


# ── Lines ─────────────────────────────────────────────────────────────────────

def test_create_line_on_foreign_revision_is_blocked(client, truncate_all):
    """Blocked, but with `409 NOT_FOUND` rather than a 404.

    The line routes funnel every `ValueError` from `_assert_draft` through one
    409 mapping, so the not-found case inherits the conflict status. It leaks
    nothing and writes nothing; the code is just inconsistent with the 404 the
    revision and estimate routes return. Asserted as-is so a future fix is a
    deliberate edit rather than a silent behaviour change.
    """
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    r = client.post(
        f"/revisions/{ids['rid_a']}/lines", json={"description": "Injected"}
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NOT_FOUND"

    from app.db import SessionLocal
    s = SessionLocal()
    try:
        n = s.execute(
            text("SELECT COUNT(*) FROM estimate_line WHERE revision_id = :r"),
            {"r": ids["rid_a"]},
        ).scalar()
    finally:
        s.close()
    assert n == 1, "foreign workspace must not append a line"


def test_patch_line_cross_workspace_is_blocked(client, truncate_all):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    r = client.patch(f"/lines/{ids['lid_a']}", json={"description": "Renamed"})
    assert r.status_code == 404, r.text

    from app.db import SessionLocal
    s = SessionLocal()
    try:
        desc = s.execute(
            text("SELECT description FROM estimate_line WHERE line_id = :l"),
            {"l": ids["lid_a"]},
        ).scalar()
    finally:
        s.close()
    assert desc == "Hidden line"


def test_delete_line_cross_workspace_leaves_the_row(client, truncate_all):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    assert client.delete(f"/lines/{ids['lid_a']}").status_code == 404
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        n = s.execute(
            text("SELECT COUNT(*) FROM estimate_line WHERE line_id = :l"),
            {"l": ids["lid_a"]},
        ).scalar()
    finally:
        s.close()
    assert n == 1


def test_add_part_to_foreign_line_is_blocked(client, truncate_all):
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    r = client.post(
        f"/lines/{ids['lid_a']}/parts",
        json={"material_type": "BOARD", "material_id": 1, "qty": 1},
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "NOT_FOUND"
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        n = s.execute(
            text("SELECT COUNT(*) FROM estimate_line_part WHERE line_id = :l"),
            {"l": ids["lid_a"]},
        ).scalar()
    finally:
        s.close()
    assert n == 0


# ── Labour rates ──────────────────────────────────────────────────────────────

def test_labour_rates_are_workspace_scoped(client, truncate_all):
    """A's CNC rate must not appear for B, and B's edit must not touch A's."""
    ids = _seed_two_workspaces(truncate_all)
    _login_b(client)
    r = client.get("/it/labour-rates")
    assert r.status_code == 200, r.text
    assert all(float(row["hourly_rate"]) != 123.45 for row in r.json())

    client.patch(
        "/it/labour-rates",
        json={"rates": [{"stage_key": "CNC", "hourly_rate": 10}]},
    )
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        rate_a = s.execute(
            text(
                """
                SELECT hourly_rate FROM workspace_labour_rate
                 WHERE workspace_id = :w AND stage_key = 'CNC'
                """
            ),
            {"w": ids["wid_a"]},
        ).scalar()
    finally:
        s.close()
    assert float(rate_a) == 123.45
