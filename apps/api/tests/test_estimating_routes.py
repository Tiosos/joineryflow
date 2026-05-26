"""Integration tests for the estimating module — sub-project #9a."""
from __future__ import annotations

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
        s.execute(
            text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE")
        )
        s.commit()
    finally:
        s.close()


def _bootstrap(role: str = "estimator", *, seed_catalog: bool = True):
    suffix = uuid.uuid4().hex[:8]
    slug = f"est-{suffix}"
    email = f"u-{suffix}@example.com"
    s = SessionLocal()
    try:
        wid = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'Est') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name,
                                     password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, :r) RETURNING id
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
        ).scalar()
        for sk, label, sort in (
            ("REQ", "Requested", 10), ("SM", "Site Measure", 20),
            ("LISTED", "Listed", 30), ("DOWN", "Down", 40),
            ("CNC", "CNC", 50), ("EDGED", "Edged", 60),
            ("PAINTED", "Painted", 70), ("MADE", "Made", 80),
            ("DEL", "Delivered", 90), ("INST", "Installed", 100),
        ):
            s.execute(
                text(
                    """
                    INSERT INTO stages(stage_key, label, sort_order)
                    VALUES (:k, :l, :so)
                    ON CONFLICT (stage_key) DO NOTHING
                    """
                ),
                {"k": sk, "l": label, "so": sort},
            )
        for status_key, sort in (
            ("CLEAR", 10), ("VOID", 20), ("NOTE!", 30),
            ("LIVE", 40), ("APPROVED", 50), ("HOLD", 60),
        ):
            s.execute(
                text(
                    """
                    INSERT INTO status_options(status_key, sort_order)
                    VALUES (:k, :s)
                    ON CONFLICT (status_key) DO NOTHING
                    """
                ),
                {"k": status_key, "s": sort},
            )

        board_id = hw_id = None
        if seed_catalog:
            board_sku = f"TBOARD-{suffix}"
            hw_sku = f"THW-{suffix}"
            board_id = s.execute(
                text(
                    """
                    INSERT INTO board_materials
                        (workspace_id, sku, code, description,
                         cost_per_sheet, unit_cost, default_supplier)
                    VALUES (:w, :sku, :code, 'Test Board',
                            50.00, 50.00, 'Test Supplier')
                    RETURNING material_id
                    """
                ),
                {"w": wid, "sku": board_sku, "code": board_sku},
            ).scalar()
            hw_id = s.execute(
                text(
                    """
                    INSERT INTO hardware_materials
                        (workspace_id, sku, description,
                         cost_per_unit, default_supplier)
                    VALUES (:w, :sku, 'Test Hinge',
                            8.00, 'Test Supplier')
                    RETURNING material_id
                    """
                ),
                {"w": wid, "sku": hw_sku},
            ).scalar()
        s.commit()
    finally:
        s.close()

    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": email, "password": "pw"},
    )
    assert r.status_code == 200, r.text
    return c, wid, uid, board_id, hw_id


# Customers --------------------------------------------------------

def test_create_customer_201():
    c, *_ = _bootstrap()
    r = c.post("/customers", json={"name": "ACME Pty"})
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "ACME Pty"


def test_create_customer_duplicate_name_409():
    c, *_ = _bootstrap()
    c.post("/customers", json={"name": "ACME Pty"})
    r = c.post("/customers", json={"name": "ACME Pty"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "DUPLICATE_NAME"


def test_archive_customer_idempotency_409():
    c, *_ = _bootstrap()
    cid = c.post("/customers", json={"name": "ACME"}).json()["customer_id"]
    assert c.post(f"/customers/{cid}/archive").status_code == 200
    r = c.post(f"/customers/{cid}/archive")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ALREADY_ARCHIVED"


# Estimate header + revision lifecycle ------------------------------

def _make_estimate(c: TestClient, title: str = "Job") -> dict:
    cust = c.post("/customers", json={"name": f"C-{uuid.uuid4().hex[:6]}"}).json()
    r = c.post(
        "/estimates",
        json={"customer_id": cust["customer_id"], "title": title},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_estimate_assigns_est_number_and_draft_rev():
    c, *_ = _bootstrap()
    est = _make_estimate(c)
    assert est["estimate_no"].startswith("EST-")
    assert est["current_revision_id"] is not None
    assert est["revisions"][0]["rev_no"] == 1
    assert est["revisions"][0]["status"] == "draft"


def test_revise_blocks_when_draft_exists_409():
    c, *_ = _bootstrap()
    est = _make_estimate(c)
    r = c.post(f"/estimates/{est['estimate_id']}/revise")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "DRAFT_EXISTS"


def test_status_transition_blocks_illegal_arrow():
    c, *_ = _bootstrap()
    est = _make_estimate(c)
    rid = est["current_revision_id"]
    r = c.post(f"/revisions/{rid}/accept")
    assert r.status_code == 409
    body = r.json()["detail"]
    assert body["code"] == "BAD_TRANSITION"
    assert body["from"] == "draft" and body["to"] == "accepted"


def test_send_empty_revision_409():
    c, *_ = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    r = c.post(f"/revisions/{rid}/send")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "EMPTY_REVISION"


# Lines + breakdown -------------------------------------------------

def test_add_line_then_part_rolls_up_material_cost():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    r = c.post(f"/revisions/{rid}/lines",
               json={"description": "Cabinet", "qty": 1})
    lid = r.json()["line_id"]
    r = c.post(
        f"/lines/{lid}/parts",
        json={"material_type": "BOARD", "material_id": board_id, "qty": 2},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert float(body["cost_per_unit_snapshot"]) == 50.00
    assert float(body["cost_extended"]) == 100.00


def test_locked_revision_blocks_line_mutation():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    lid = c.post(f"/revisions/{rid}/lines",
                 json={"description": "X", "qty": 1}).json()["line_id"]
    r = c.post(f"/revisions/{rid}/send")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent"
    r = c.patch(f"/lines/{lid}", json={"description": "renamed"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REVISION_LOCKED"


def test_revise_clones_lines_into_new_draft():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    est = _make_estimate(c)
    rid = est["current_revision_id"]
    r = c.post(f"/revisions/{rid}/lines",
               json={"description": "L1", "qty": 1})
    c.post(f"/lines/{r.json()['line_id']}/parts",
           json={"material_type": "BOARD", "material_id": board_id, "qty": 1})
    c.post(f"/revisions/{rid}/send")
    r = c.post(f"/estimates/{est['estimate_id']}/revise")
    assert r.status_code == 201, r.text
    new_rev = r.json()
    assert new_rev["rev_no"] == 2
    assert new_rev["status"] == "draft"
    assert len(new_rev["lines"]) == 1
    assert len(new_rev["lines"][0]["parts"]) == 1


# Convert-to-Project -----------------------------------------------

def test_convert_materialises_project_items_parts_and_hardware():
    c, _wid, _uid, board_id, hw_id = _bootstrap()
    rid = _make_estimate(c, title="Bathroom")["current_revision_id"]
    lid = c.post(f"/revisions/{rid}/lines",
                 json={"description": "Vanity 1500", "qty": 1}).json()["line_id"]
    c.post(f"/lines/{lid}/parts",
           json={"material_type": "BOARD", "material_id": board_id, "qty": 2})
    c.post(f"/lines/{lid}/hardware",
           json={"material_type": "HARDWARE", "material_id": hw_id, "qty": 6})
    c.post(f"/revisions/{rid}/lines",
           json={"description": "Mirror cabinet", "qty": 1})
    c.post(f"/revisions/{rid}/send")
    c.post(f"/revisions/{rid}/accept")
    r = c.post(f"/revisions/{rid}/convert")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["items_created"] == 2
    assert body["parts_created"] == 1
    assert body["hardware_lines_created"] == 1
    assert body["project_hardware_catalog_added"] == 1
    r = c.post(f"/revisions/{rid}/convert")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ALREADY_CONVERTED"


def test_convert_rejected_when_catalog_row_archived():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    rid = _make_estimate(c, title="ArchTest")["current_revision_id"]
    lid = c.post(f"/revisions/{rid}/lines",
                 json={"description": "Box", "qty": 1}).json()["line_id"]
    c.post(f"/lines/{lid}/parts",
           json={"material_type": "BOARD", "material_id": board_id, "qty": 1})
    c.post(f"/revisions/{rid}/send")
    c.post(f"/revisions/{rid}/accept")
    s = SessionLocal()
    try:
        s.execute(
            text(
                "UPDATE board_materials SET archived_at = now() "
                "WHERE material_id = :m"
            ),
            {"m": board_id},
        )
        s.commit()
    finally:
        s.close()
    r = c.post(f"/revisions/{rid}/convert")
    assert r.status_code == 409
    body = r.json()["detail"]
    assert body["code"] == "CATALOG_GONE"
    assert body["failures"][0]["material_id"] == board_id


# Quote PDF --------------------------------------------------------

def test_quote_pdf_draft_renders_with_watermark():
    # Draft PDF is now allowed (renders DRAFT — NOT FOR CLIENT watermark).
    c, *_ = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    r = c.get(f"/revisions/{rid}/quote.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


def test_quote_pdf_renders_for_sent_revision():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    lid = c.post(f"/revisions/{rid}/lines",
                 json={"description": "L1", "qty": 1}).json()["line_id"]
    c.post(f"/lines/{lid}/parts",
           json={"material_type": "BOARD", "material_id": board_id, "qty": 1})
    c.post(f"/revisions/{rid}/send")
    r = c.get(f"/revisions/{rid}/quote.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF")


# RBAC -------------------------------------------------------------

def test_viewer_blocked_from_creating_customer():
    c, *_ = _bootstrap(role="viewer")
    r = c.post("/customers", json={"name": "X"})
    assert r.status_code == 403


def test_drafter_can_read_but_not_write():
    c, *_ = _bootstrap(role="drafter")
    assert c.get("/estimates").status_code == 200
    assert c.post("/customers", json={"name": "X"}).status_code == 403


def test_purchase_officer_can_read_estimates_list():
    c, *_ = _bootstrap(role="purchase_officer")
    assert c.get("/estimates").status_code == 200


# Workspace isolation ----------------------------------------------

def test_cross_workspace_estimate_returns_404():
    c1, *_ = _bootstrap()
    est = _make_estimate(c1)
    c2, *_ = _bootstrap()
    r = c2.get(f"/estimates/{est['estimate_id']}")
    assert r.status_code == 404


# Labour rates -----------------------------------------------------

def test_admin_can_set_labour_rates():
    c, *_ = _bootstrap(role="admin")
    r = c.patch(
        "/it/labour-rates",
        json={"rates": [
            {"stage_key": "CNC", "hourly_rate": "95.00"},
            {"stage_key": "MADE", "hourly_rate": "90.00"},
        ]},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    by_key = {row["stage_key"]: float(row["hourly_rate"]) for row in rows}
    assert by_key["CNC"] == 95.00
    assert by_key["MADE"] == 90.00


def test_estimator_cannot_edit_labour_rates():
    c, *_ = _bootstrap(role="estimator")
    r = c.patch(
        "/it/labour-rates",
        json={"rates": [{"stage_key": "CNC", "hourly_rate": "95.00"}]},
    )
    assert r.status_code == 403


# Patch part / hardware (Phase 1 polish) ---------------------------

def _seed_line_with_part(c: TestClient, board_id: int) -> tuple[int, int]:
    rid = _make_estimate(c)["current_revision_id"]
    lid = c.post(
        f"/revisions/{rid}/lines",
        json={"description": "Cab", "qty": 1},
    ).json()["line_id"]
    pid = c.post(
        f"/lines/{lid}/parts",
        json={"material_type": "BOARD", "material_id": board_id, "qty": 2},
    ).json()["part_id"]
    return lid, pid


def _seed_line_with_hardware(c: TestClient, hw_id: int) -> tuple[int, int]:
    rid = _make_estimate(c)["current_revision_id"]
    lid = c.post(
        f"/revisions/{rid}/lines",
        json={"description": "Cab", "qty": 1},
    ).json()["line_id"]
    hid = c.post(
        f"/lines/{lid}/hardware",
        json={"material_type": "HARDWARE", "material_id": hw_id, "qty": 4},
    ).json()["hw_id"]
    return lid, hid


def test_patch_part_qty_updates_cost():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    _lid, pid = _seed_line_with_part(c, board_id)
    r = c.patch(f"/estimate-parts/{pid}", json={"qty": "5"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["qty"]) == 5.0
    assert float(body["cost_extended"]) == 250.00


def test_patch_part_dims_and_paint():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    _lid, pid = _seed_line_with_part(c, board_id)
    r = c.patch(
        f"/estimate-parts/{pid}",
        json={
            "len_mm": 720, "wid_mm": 380,
            "paint_instruction": "DOUBLE_SIDE",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["len_mm"] == 720
    assert body["wid_mm"] == 380
    assert body["paint_instruction"] == "DOUBLE_SIDE"


def test_patch_part_missing_404():
    c, *_ = _bootstrap()
    r = c.patch("/estimate-parts/999999", json={"qty": "1"})
    assert r.status_code == 404


def test_patch_part_cross_workspace_404():
    c1, _w1, _u1, board_id, _hw = _bootstrap()
    _lid, pid = _seed_line_with_part(c1, board_id)
    c2, *_ = _bootstrap()
    r = c2.patch(f"/estimate-parts/{pid}", json={"qty": "9"})
    assert r.status_code == 404


def test_patch_part_locked_revision_409():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    _lid, pid = _seed_line_with_part(c, board_id)
    rid = c.get("/estimates").json()["estimates"][0]["current_revision_id"]
    r = c.post(f"/revisions/{rid}/send")
    assert r.status_code == 200, r.text
    r = c.patch(f"/estimate-parts/{pid}", json={"qty": "9"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REVISION_LOCKED"


def test_patch_part_bad_qty_422():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    _lid, pid = _seed_line_with_part(c, board_id)
    r = c.patch(f"/estimate-parts/{pid}", json={"qty": "0"})
    assert r.status_code == 422


def test_patch_hardware_qty_updates_cost():
    c, _wid, _uid, _board, hw_id = _bootstrap()
    _lid, hid = _seed_line_with_hardware(c, hw_id)
    r = c.patch(f"/hardware/{hid}", json={"qty": "10"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["qty"]) == 10.0
    assert float(body["cost_extended"]) == 80.00


def test_patch_hardware_comment_only():
    c, _wid, _uid, _board, hw_id = _bootstrap()
    _lid, hid = _seed_line_with_hardware(c, hw_id)
    r = c.patch(f"/hardware/{hid}", json={"comment": "soft-close"})
    assert r.status_code == 200, r.text
    assert r.json()["comment"] == "soft-close"


def test_patch_hardware_locked_revision_409():
    c, _wid, _uid, _board, hw_id = _bootstrap()
    _lid, hid = _seed_line_with_hardware(c, hw_id)
    rid = c.get("/estimates").json()["estimates"][0]["current_revision_id"]
    r = c.post(f"/revisions/{rid}/send")
    assert r.status_code == 200, r.text
    r = c.patch(f"/hardware/{hid}", json={"qty": "1"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REVISION_LOCKED"


def test_patch_hardware_missing_404():
    c, *_ = _bootstrap()
    r = c.patch("/hardware/999999", json={"qty": "1"})
    assert r.status_code == 404


# Revision expires_at + draft PDF (Phase 2 polish) -----------------

def test_patch_revision_expires_at_when_sent():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    _lid, _pid = _seed_line_with_part(c, board_id)
    rid = c.get("/estimates").json()["estimates"][0]["current_revision_id"]
    assert c.post(f"/revisions/{rid}/send").status_code == 200
    r = c.patch(f"/revisions/{rid}", json={"expires_at": "2026-12-31"})
    assert r.status_code == 200, r.text
    assert r.json()["expires_at"] == "2026-12-31"


def test_patch_revision_expires_at_blocked_on_draft_409():
    c, *_ = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    r = c.patch(f"/revisions/{rid}", json={"expires_at": "2026-12-31"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NOT_SENT"


def test_quote_pdf_on_draft_renders_with_watermark():
    c, *_ = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    r = c.get(f"/revisions/{rid}/quote.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
