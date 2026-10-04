"""Integration tests for the estimating module — sub-project #9a."""
from __future__ import annotations


import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import SessionLocal

from .helpers_estimating import (  # noqa: F401
    _bootstrap,
    _make_estimate,
)

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



def _advance_to_submitted(c: TestClient, rid: int) -> dict:
    """Walk the 12-stage lifecycle's 10 forward steps (OPPORTUNITY ->
    SUBMITTED) — the sequence `POST /revisions/{rid}/send` used to do in one
    call before Q487/488's tender lifecycle replaced the 6-state machine."""
    r = None
    for _ in range(10):
        r = c.post(f"/revisions/{rid}/advance")
        assert r.status_code == 200, r.text
        if r.json()["status"] == "SUBMITTED":
            break
    return r.json()


def test_create_estimate_assigns_est_number_and_draft_rev():
    c, *_ = _bootstrap()
    est = _make_estimate(c)
    assert est["estimate_no"].startswith("EST-")
    assert est["current_revision_id"] is not None
    assert est["revisions"][0]["rev_no"] == 1
    assert est["revisions"][0]["status"] == "OPPORTUNITY"


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
    assert body["from"] == "OPPORTUNITY" and body["to"] == "WON"


def test_send_empty_revision_409():
    c, *_ = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    # advance to MGMT_APPROVAL (9 steps); the 10th, into SUBMITTED, is the
    # one that checks for at least one line.
    for _ in range(9):
        assert c.post(f"/revisions/{rid}/advance").status_code == 200
    r = c.post(f"/revisions/{rid}/advance")
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
    rev = _advance_to_submitted(c, rid)
    assert rev["status"] == "SUBMITTED"
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
    _advance_to_submitted(c, rid)
    r = c.post(f"/estimates/{est['estimate_id']}/revise")
    assert r.status_code == 201, r.text
    new_rev = r.json()
    assert new_rev["rev_no"] == 2
    assert new_rev["status"] == "ESTIMATING"
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
    _advance_to_submitted(c, rid)
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


def test_convert_line_with_two_parts_does_not_collide_on_seq():
    """Fixed later. Every part's `seq` in `convert_to_project()` was
    hardcoded to 1, not incremented per part in the module — harmless while
    no seed/test fixture had more than one part per line, but
    `uq_parts_module_seq (module_id, seq)` rejects a second part with the
    same seq, so any WON quote line with two or more parts raised a raw
    IntegrityError/500 instead of converting. Found live-testing PO
    generation (a line quoting two different board materials). Two
    estimate_line_part rows on the same line, even referencing the same
    catalog material twice, reproduce it."""
    c, _wid, _uid, board_id, _hw = _bootstrap()
    rid = _make_estimate(c, title="TwoParts")["current_revision_id"]
    lid = c.post(f"/revisions/{rid}/lines",
                 json={"description": "Carcass", "qty": 1}).json()["line_id"]
    c.post(f"/lines/{lid}/parts",
           json={"material_type": "BOARD", "material_id": board_id, "qty": 2})
    c.post(f"/lines/{lid}/parts",
           json={"material_type": "BOARD", "material_id": board_id, "qty": 1})
    _advance_to_submitted(c, rid)
    c.post(f"/revisions/{rid}/accept")
    r = c.post(f"/revisions/{rid}/convert")
    assert r.status_code == 200, r.text
    assert r.json()["parts_created"] == 2


def test_convert_rejected_when_catalog_row_archived():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    rid = _make_estimate(c, title="ArchTest")["current_revision_id"]
    lid = c.post(f"/revisions/{rid}/lines",
                 json={"description": "Box", "qty": 1}).json()["line_id"]
    c.post(f"/lines/{lid}/parts",
           json={"material_type": "BOARD", "material_id": board_id, "qty": 1})
    _advance_to_submitted(c, rid)
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
    _advance_to_submitted(c, rid)
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
    _advance_to_submitted(c, rid)
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
    _advance_to_submitted(c, rid)
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
    _advance_to_submitted(c, rid)
    r = c.patch(f"/revisions/{rid}", json={"expires_at": "2026-12-31"})
    assert r.status_code == 200, r.text
    assert r.json()["expires_at"] == "2026-12-31"


def test_patch_revision_expires_at_blocked_before_submitted_409():
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


# Revision transitions — reject / expire / withdraw ----------------

def _send_revision(c: TestClient, board_id: int) -> int:
    """Create estimate, add a line+part, advance it to SUBMITTED. Returns rid."""
    rid = _make_estimate(c)["current_revision_id"]
    lid = c.post(
        f"/revisions/{rid}/lines",
        json={"description": "Cabinet", "qty": 1},
    ).json()["line_id"]
    c.post(
        f"/lines/{lid}/parts",
        json={"material_type": "BOARD", "material_id": board_id, "qty": 1},
    )
    rev = _advance_to_submitted(c, rid)
    assert rev["status"] == "SUBMITTED"
    return rid


def test_reject_revision_sets_status_and_stores_reason():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    rid = _send_revision(c, board_id)
    r = c.post(f"/revisions/{rid}/reject", json={"lost_reason": "Too expensive"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "LOST"
    assert body["lost_reason"] == "Too expensive"


def test_reject_requires_lost_reason():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    rid = _send_revision(c, board_id)
    r = c.post(f"/revisions/{rid}/reject", json={})
    assert r.status_code == 422


def test_expire_revision_sets_status():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    rid = _send_revision(c, board_id)
    r = c.post(f"/revisions/{rid}/expire", json={"lost_reason": "Quote lapsed"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "LOST"


def test_withdraw_revision_sets_status():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    rid = _send_revision(c, board_id)
    r = c.post(f"/revisions/{rid}/withdraw", json={"lost_reason": None})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "WITHDRAWN"


# Remove operations — part / hardware / line -----------------------

def test_remove_part_from_line():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    _lid, pid = _seed_line_with_part(c, board_id)
    r = c.delete(f"/estimate-parts/{pid}")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    r2 = c.patch(f"/estimate-parts/{pid}", json={"qty": "1"})
    assert r2.status_code == 404


def test_remove_hardware_from_line():
    c, _wid, _uid, _board, hw_id = _bootstrap()
    _lid, hid = _seed_line_with_hardware(c, hw_id)
    r = c.delete(f"/hardware/{hid}")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    r2 = c.patch(f"/hardware/{hid}", json={"qty": "1"})
    assert r2.status_code == 404


def test_delete_line_removes_it():
    c, _wid, _uid, board_id, _hw = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    lid = c.post(
        f"/revisions/{rid}/lines",
        json={"description": "To delete", "qty": 1},
    ).json()["line_id"]
    r = c.delete(f"/lines/{lid}")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    est_id = c.get("/estimates").json()["estimates"][0]["estimate_id"]
    detail = c.get(f"/estimates/{est_id}").json()
    line_ids = [ln["line_id"] for ln in detail["revisions"][0]["lines"]]
    assert lid not in line_ids


# Labour upsert ---------------------------------------------------

def test_upsert_labour_adds_then_removes():
    c, _wid, _uid, _board, _hw = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    lid = c.post(
        f"/revisions/{rid}/lines",
        json={"description": "Cabinet", "qty": 1},
    ).json()["line_id"]

    r = c.post(f"/lines/{lid}/labour", json={"stage_key": "CNC", "hours": 3.5})
    assert r.status_code == 200, r.text
    assert any(l["stage_key"] == "CNC" for l in r.json()["labour"])

    r2 = c.post(f"/lines/{lid}/labour", json={"stage_key": "CNC", "hours": 0})
    assert r2.status_code == 200, r2.text
    assert not any(l["stage_key"] == "CNC" for l in r2.json()["labour"])
