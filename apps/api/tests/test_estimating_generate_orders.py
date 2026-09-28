"""PO generation from a won quote — `order_preview` / `generate_orders`.

Sources from the revision's own line breakdown, not the converted project's
items (which lose the CUSTOM/BENCHTOP catalog link — only BOARD keeps a real
`board_material_id`) and not the Material Summary (Q585: "no
create-order-from-line in v1" for that surface). Groups by each material's
live `default_supplier_id` (migration 0029's real vendor FK, not the
free-text `default_supplier` the quote itself snapshots), consolidating
identical materials into one PO line with a summed quantity.
"""
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
        s.execute(text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _bootstrap(role: str = "estimator"):
    suffix = uuid.uuid4().hex[:8]
    slug = f"go-{suffix}"
    email = f"u-{suffix}@t"
    s = SessionLocal()
    try:
        wid = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'T') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
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
                    "INSERT INTO stages(stage_key, label, sort_order)"
                    " VALUES (:k, :l, :so) ON CONFLICT (stage_key) DO NOTHING"
                ),
                {"k": sk, "l": label, "so": sort},
            )

        vendor_a = s.execute(
            text(
                "INSERT INTO vendors(name, category, workspace_id)"
                " VALUES ('Vendor A', 'Board', :w) RETURNING vendor_id"
            ),
            {"w": wid},
        ).scalar()

        suffix2 = uuid.uuid4().hex[:6]
        board_id = s.execute(
            text(
                """
                INSERT INTO board_materials
                    (workspace_id, sku, code, description,
                     cost_per_sheet, unit_cost, default_supplier_id)
                VALUES (:w, :sku, :code, 'Test Board', 50.00, 50.00, :sup)
                RETURNING material_id
                """
            ),
            {"w": wid, "sku": f"TBOARD-{suffix2}", "code": f"TBOARD-{suffix2}", "sup": vendor_a},
        ).scalar()
        hw_id = s.execute(
            text(
                """
                INSERT INTO hardware_materials
                    (workspace_id, sku, description, cost_per_unit, default_supplier_id)
                VALUES (:w, :sku, 'Test Hinge', 8.00, :sup)
                RETURNING material_id
                """
            ),
            {"w": wid, "sku": f"THW-{suffix2}", "sup": vendor_a},
        ).scalar()
        # No default_supplier_id — exercises the `unassigned` path.
        unassigned_board_id = s.execute(
            text(
                """
                INSERT INTO board_materials
                    (workspace_id, sku, code, description, cost_per_sheet, unit_cost)
                VALUES (:w, :sku, :code, 'Orphan Board', 30.00, 30.00)
                RETURNING material_id
                """
            ),
            {"w": wid, "sku": f"TORPHAN-{suffix2}", "code": f"TORPHAN-{suffix2}"},
        ).scalar()
        s.commit()
    finally:
        s.close()

    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    return {
        "client": c, "wid": wid, "uid": uid, "slug": slug, "vendor_a": vendor_a,
        "board_id": board_id, "hw_id": hw_id,
        "unassigned_board_id": unassigned_board_id,
    }


def _login_as(slug: str, role: str) -> TestClient:
    """A second user in the SAME workspace — no role has `write` on
    `estimating` without also having `approve` (only estimator/manager/admin
    do), so testing the approve-gate needs a lesser-privileged user looking
    at a quote someone else already built, not one building their own."""
    suffix = uuid.uuid4().hex[:8]
    email = f"u2-{suffix}@t"
    s = SessionLocal()
    try:
        s.execute(
            text(
                "INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)"
                " VALUES ((SELECT id FROM workspace WHERE slug = :s), :e, 'U2', :p, :r)"
            ),
            {"s": slug, "e": email, "p": hash_password("pw"), "r": role},
        )
        s.commit()
    finally:
        s.close()
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    return c


def _advance_to_won(c: TestClient, rid: int) -> None:
    for _ in range(10):
        assert c.post(f"/revisions/{rid}/advance").status_code == 200
    assert c.post(f"/revisions/{rid}/accept").status_code == 200


def _make_quote(
    ctx: dict, *, second_board_line: bool = False, include_unassigned: bool = False,
) -> dict:
    c = ctx["client"]
    cust = c.post("/customers", json={"name": f"C-{uuid.uuid4().hex[:6]}"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "Kitchen"}).json()
    rid = est["current_revision_id"]

    l1 = c.post(f"/revisions/{rid}/lines", json={"description": "Pantry", "qty": 1}).json()
    c.post(f"/lines/{l1['line_id']}/parts",
           json={"material_type": "BOARD", "material_id": ctx["board_id"], "qty": 2})
    c.post(f"/lines/{l1['line_id']}/hardware",
           json={"material_type": "HARDWARE", "material_id": ctx["hw_id"], "qty": 6})

    line_ids = [l1["line_id"]]
    if second_board_line:
        # Same SKU on a different line — proves consolidation (2 + 3 = 5).
        l2 = c.post(f"/revisions/{rid}/lines", json={"description": "Island", "qty": 1}).json()
        c.post(f"/lines/{l2['line_id']}/parts",
               json={"material_type": "BOARD", "material_id": ctx["board_id"], "qty": 3})
        line_ids.append(l2["line_id"])
    if include_unassigned:
        l3 = c.post(f"/revisions/{rid}/lines", json={"description": "Orphan", "qty": 1}).json()
        c.post(f"/lines/{l3['line_id']}/parts",
               json={"material_type": "BOARD", "material_id": ctx["unassigned_board_id"], "qty": 1})
        line_ids.append(l3["line_id"])

    _advance_to_won(c, rid)
    return {"estimate_id": est["estimate_id"], "revision_id": rid, "line_ids": line_ids}


def _convert(c: TestClient, rid: int) -> int:
    r = c.post(f"/revisions/{rid}/convert")
    assert r.status_code == 200, r.text
    return r.json()["project_id"]


# ----------------------------------------------------------------------------
# order-preview
# ----------------------------------------------------------------------------

def test_order_preview_groups_by_supplier_and_consolidates_qty():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx, second_board_line=True)
    r = c.get(f"/revisions/{quote['revision_id']}/order-preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["converted_project_id"] is None
    assert body["orders_generated_at"] is None
    assert len(body["groups"]) == 1
    group = body["groups"][0]
    assert group["supplier_id"] == ctx["vendor_a"]
    assert group["supplier_name"] == "Vendor A"
    by_key = {(l["material_type"], l["material_id"]): l for l in group["lines"]}
    assert float(by_key[("BOARD", ctx["board_id"])]["qty"]) == 5.0  # 2 + 3 consolidated
    assert float(by_key[("HARDWARE", ctx["hw_id"])]["qty"]) == 6.0
    assert body["unassigned"] == []


def test_order_preview_unassigned_supplier_surfaced():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx, include_unassigned=True)
    r = c.get(f"/revisions/{quote['revision_id']}/order-preview")
    body = r.json()
    assert len(body["unassigned"]) == 1
    assert body["unassigned"][0]["material_id"] == ctx["unassigned_board_id"]


def test_order_preview_requires_approve_permission():
    ctx = _bootstrap()
    quote = _make_quote(ctx)
    drafter = _login_as(ctx["slug"], "drafter")
    r = drafter.get(f"/revisions/{quote['revision_id']}/order-preview")
    assert r.status_code == 403


def test_order_preview_cross_workspace_404():
    ctx = _bootstrap()
    quote = _make_quote(ctx)
    other = _bootstrap()
    r = other["client"].get(f"/revisions/{quote['revision_id']}/order-preview")
    assert r.status_code == 404


# ----------------------------------------------------------------------------
# generate-orders
# ----------------------------------------------------------------------------

def test_generate_orders_requires_converted():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx)
    r = c.post(f"/revisions/{quote['revision_id']}/generate-orders")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NOT_CONVERTED"


def test_generate_orders_defaults_to_lines_actually_converted():
    """Fixed later. generate_orders() used to default (no include_line_ids)
    to EVERY line in the revision, not the subset actually included at
    Convert — so a line the PM deliberately excluded from the project still
    got its materials purchase-ordered. `included_at_convert` (migration
    0041) now records the real set, and the default reads that instead."""
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx, second_board_line=True)
    # Convert ONLY line 1 — line 2's extra board qty (3) never becomes part
    # of the project.
    r = c.post(f"/revisions/{quote['revision_id']}/convert",
               json={"include_line_ids": [quote["line_ids"][0]]})
    assert r.status_code == 200, r.text
    assert r.json()["items_created"] == 1

    r = c.post(f"/revisions/{quote['revision_id']}/generate-orders")
    assert r.status_code == 200, r.text
    po = c.get(f"/orders/{r.json()['po_ids'][0]}").json()
    board_line = next(l for l in po["lines"] if l["material_table"] == "board_materials")
    # Only line 1's qty (2) — line 2 was never converted, so its extra 3
    # must not be included even though no include_line_ids was passed here.
    assert float(board_line["quantity"]) == 2.0


def test_order_preview_after_convert_reflects_only_converted_lines():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx, second_board_line=True)
    c.post(f"/revisions/{quote['revision_id']}/convert",
           json={"include_line_ids": [quote["line_ids"][0]]})
    r = c.get(f"/revisions/{quote['revision_id']}/order-preview")
    assert r.status_code == 200, r.text
    group = r.json()["groups"][0]
    board_line = next(l for l in group["lines"] if l["material_type"] == "BOARD")
    assert float(board_line["qty"]) == 2.0


def test_generate_orders_creates_one_po_per_supplier_with_consolidated_lines():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx, second_board_line=True)
    _convert(c, quote["revision_id"])

    r = c.post(f"/revisions/{quote['revision_id']}/generate-orders")
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["orders_created"] == 1
    assert result["lines_created"] == 2
    assert result["unassigned"] == []
    assert len(result["po_ids"]) == 1

    po = c.get(f"/orders/{result['po_ids'][0]}").json()
    assert po["vendor_id"] == ctx["vendor_a"]
    assert po["category"] == "Board"  # 2 board lines vs 1 hardware — dominant type
    # material_id is only unique PER TABLE (board_materials.material_id and
    # hardware_materials.material_id are separate BIGSERIAL sequences), so
    # the two together are the real key.
    lines_by_key = {(l["material_table"], l["material_id"]): l for l in po["lines"]}
    board_line = lines_by_key[("board_materials", ctx["board_id"])]
    hw_line = lines_by_key[("hardware_materials", ctx["hw_id"])]
    assert float(board_line["quantity"]) == 5.0
    assert float(board_line["unit_price"]) == 50.0
    assert float(hw_line["quantity"]) == 6.0


def test_generate_orders_runs_once_per_revision():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx)
    _convert(c, quote["revision_id"])
    assert c.post(f"/revisions/{quote['revision_id']}/generate-orders").status_code == 200
    r = c.post(f"/revisions/{quote['revision_id']}/generate-orders")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ORDERS_ALREADY_GENERATED"


def test_generate_orders_unassigned_material_does_not_block_the_rest():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx, include_unassigned=True)
    _convert(c, quote["revision_id"])
    r = c.post(f"/revisions/{quote['revision_id']}/generate-orders")
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["orders_created"] == 1  # Vendor A's group still generated
    assert len(result["unassigned"]) == 1
    assert result["unassigned"][0]["material_id"] == ctx["unassigned_board_id"]


def test_generate_orders_include_line_ids_filters():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx, second_board_line=True)
    _convert(c, quote["revision_id"])

    r = c.post(
        f"/revisions/{quote['revision_id']}/generate-orders",
        json={"include_line_ids": [quote["line_ids"][0]]},
    )
    assert r.status_code == 200, r.text
    po = c.get(f"/orders/{r.json()['po_ids'][0]}").json()
    board_line = next(l for l in po["lines"] if l["material_table"] == "board_materials")
    # Only line 1's qty (2), not line 2's extra 3 — line 2 was excluded.
    assert float(board_line["quantity"]) == 2.0
    assert board_line["material_id"] == ctx["board_id"]
    # Line 1 also carries the hardware, so it's still in the generated PO —
    # only line 2's extra board qty was excluded, not a whole material.
    assert len(po["lines"]) == 2


def test_generate_orders_rejects_unknown_line_id():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx)
    _convert(c, quote["revision_id"])
    r = c.post(
        f"/revisions/{quote['revision_id']}/generate-orders",
        json={"include_line_ids": [999999]},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "UNKNOWN_LINE_IDS"


def test_generate_orders_requires_approve_permission():
    ctx = _bootstrap()
    quote = _make_quote(ctx)
    _convert(ctx["client"], quote["revision_id"])
    drafter = _login_as(ctx["slug"], "drafter")
    r = drafter.post(f"/revisions/{quote['revision_id']}/generate-orders")
    assert r.status_code == 403


def test_generate_orders_cross_workspace_404():
    ctx = _bootstrap()
    quote = _make_quote(ctx)
    _convert(ctx["client"], quote["revision_id"])
    other = _bootstrap()
    r = other["client"].post(f"/revisions/{quote['revision_id']}/generate-orders")
    assert r.status_code == 404


def test_generate_orders_audit_and_revision_flag():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx)
    _convert(c, quote["revision_id"])
    c.post(f"/revisions/{quote['revision_id']}/generate-orders")

    s = SessionLocal()
    try:
        flag = s.execute(
            text("SELECT orders_generated_at FROM estimate_revision WHERE revision_id = :r"),
            {"r": quote["revision_id"]},
        ).scalar()
        assert flag is not None
        event = s.execute(
            text(
                "SELECT event FROM audit_log WHERE event = 'estimate.generate_orders'"
                " AND target = :t"
            ),
            {"t": str(quote["revision_id"])},
        ).scalar()
        assert event == "estimate.generate_orders"
    finally:
        s.close()
