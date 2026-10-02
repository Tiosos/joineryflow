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


# ----------------------------------------------------------------------------
# Per-line selection — a run can cover part of a quote and a later run the rest
# (migration 0048: `estimate_line.orders_generated_at` is the guard, not the
# revision's flag)
# ----------------------------------------------------------------------------

def _sql_scalar(sql: str, **params):
    s = SessionLocal()
    try:
        return s.execute(text(sql), params).scalar()
    finally:
        s.close()


def _line_flags(c: TestClient, estimate_id: int, rid: int) -> dict[int, dict]:
    est = c.get(f"/estimates/{estimate_id}").json()
    rev = next(r for r in est["revisions"] if r["revision_id"] == rid)
    return {l["line_id"]: l for l in rev["lines"]}


def _board_qty(c: TestClient, po_id: int) -> float:
    po = c.get(f"/orders/{po_id}").json()
    return float(next(l for l in po["lines"] if l["material_table"] == "board_materials")["quantity"])


def _po_count(wid: int) -> int:
    return _sql_scalar(
        "SELECT count(*) FROM purchase_orders po JOIN vendors v ON v.vendor_id = po.vendor_id"
        " WHERE v.workspace_id = :w", w=wid)


def _two_line_quote():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx, second_board_line=True)
    _convert(c, quote["revision_id"])
    return ctx, c, quote, quote["line_ids"][0], quote["line_ids"][1]


def test_a_partial_run_covers_only_its_lines_and_a_later_run_takes_the_rest():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]

    r = c.post(f"/revisions/{rid}/generate-orders", json={"include_line_ids": [l1]})
    assert r.status_code == 200, r.text
    first_po = r.json()["po_ids"][0]
    assert _board_qty(c, first_po) == 2.0
    flags = _line_flags(c, quote["estimate_id"], rid)
    assert flags[l1]["orders_generated_at"] is not None
    assert flags[l2]["orders_generated_at"] is None

    # No ids: every line still to order — just line 2, its own PO, not line 1 again.
    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 200, r.text
    assert r.json()["orders_created"] == 1
    second_po = r.json()["po_ids"][0]
    assert second_po != first_po
    assert _board_qty(c, second_po) == 3.0
    assert len(c.get(f"/orders/{second_po}").json()["lines"]) == 1   # no hardware: that was line 1's
    assert _po_count(ctx["wid"]) == 2

    # Everything is covered now: the old once-per-quote answer.
    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ORDERS_ALREADY_GENERATED"
    assert _po_count(ctx["wid"]) == 2


def test_a_line_an_earlier_run_covered_cannot_be_ordered_again():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    assert c.post(f"/revisions/{rid}/generate-orders",
                  json={"include_line_ids": [l1]}).status_code == 200
    before = _po_count(ctx["wid"])

    r = c.post(f"/revisions/{rid}/generate-orders", json={"include_line_ids": [l1, l2]})

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == {"code": "LINES_ALREADY_GENERATED", "line_ids": [l1]}
    assert _po_count(ctx["wid"]) == before, "a refused run creates nothing"
    assert _line_flags(c, quote["estimate_id"], rid)[l2]["orders_generated_at"] is None
    # ...and line 2 is still there to order.
    assert c.post(f"/revisions/{rid}/generate-orders",
                  json={"include_line_ids": [l2]}).status_code == 200


def test_an_empty_selection_is_refused_and_leaves_the_quote_orderable():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]

    r = c.post(f"/revisions/{rid}/generate-orders", json={"include_line_ids": []})

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "NO_LINES_SELECTED"
    assert _sql_scalar("SELECT orders_generated_at FROM estimate_revision WHERE revision_id = :r",
                       r=rid) is None
    assert _po_count(ctx["wid"]) == 0
    assert c.post(f"/revisions/{rid}/generate-orders").status_code == 200


def _link_supplier(table: str, id_col: str, material_id: int, vendor_id: int) -> None:
    """What the Catalog's Supplier link does, by SQL — the estimator these tests log
    in as cannot write the catalog."""
    s = SessionLocal()
    try:
        s.execute(
            text(f"UPDATE {table} SET default_supplier_id = :v WHERE {id_col} = :m"),
            {"v": vendor_id, "m": material_id},
        )
        s.commit()
    finally:
        s.close()


def _orphan_only_quote():
    """A converted quote whose single line uses only a material with no supplier."""
    ctx = _bootstrap()
    c = ctx["client"]
    cust = c.post("/customers", json={"name": f"C-{uuid.uuid4().hex[:6]}"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "Orphans"}).json()
    rid = est["current_revision_id"]
    line = c.post(f"/revisions/{rid}/lines", json={"description": "Orphan", "qty": 1}).json()
    c.post(f"/lines/{line['line_id']}/parts",
           json={"material_type": "BOARD", "material_id": ctx["unassigned_board_id"], "qty": 2})
    _advance_to_won(c, rid)
    _convert(c, rid)
    return ctx, c, est["estimate_id"], rid, line["line_id"]


def test_a_run_with_nothing_orderable_is_refused_and_writes_nothing():
    """It used to answer 200 with no orders and stamp the line covered, so linking a
    supplier afterwards could never be acted on."""
    ctx, c, eid, rid, line = _orphan_only_quote()

    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "NOTHING_ORDERABLE"
    assert r.json()["detail"]["unassigned_count"] == 1

    assert _po_count(ctx["wid"]) == 0
    assert _line_flags(c, eid, rid)[line]["orders_generated_at"] is None
    assert _sql_scalar(
        "SELECT orders_generated_at FROM estimate_revision WHERE revision_id = :r", r=rid
    ) is None
    assert _sql_scalar(
        "SELECT count(*) FROM audit_log WHERE event = 'estimate.generate_orders'"
        " AND target = :t", t=str(rid)) == 0
    # the explicit selection answers the same way
    r = c.post(f"/revisions/{rid}/generate-orders", json={"include_line_ids": [line]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "NOTHING_ORDERABLE"
    # and the preview still offers the line, with nothing grouped
    pv = c.get(f"/revisions/{rid}/order-preview").json()
    assert pv["groups"] == [] and len(pv["unassigned"]) == 1
    assert [l["selected"] for l in pv["lines"]] == [True]


def test_a_line_with_only_unassigned_materials_can_be_ordered_once_a_supplier_is_linked():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx, include_unassigned=True)
    _convert(c, quote["revision_id"])
    rid = quote["revision_id"]
    pantry, orphan = quote["line_ids"]
    eid = quote["estimate_id"]

    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 200, r.text
    assert r.json()["orders_created"] == 1
    assert r.json()["uncovered_line_ids"] == [orphan]
    flags = _line_flags(c, eid, rid)
    assert flags[pantry]["orders_generated_at"] is not None
    assert flags[orphan]["orders_generated_at"] is None

    # nothing more can be ordered until the supplier is linked ...
    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "NOTHING_ORDERABLE"

    # ... and then the same line orders, in its own PO
    _link_supplier("board_materials", "material_id", ctx["unassigned_board_id"], ctx["vendor_a"])
    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 200, r.text
    assert r.json()["orders_created"] == 1 and r.json()["uncovered_line_ids"] == []
    assert _line_flags(c, eid, rid)[orphan]["orders_generated_at"] is not None
    assert _po_count(ctx["wid"]) == 2

    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ORDERS_ALREADY_GENERATED"


def _mixed_quote(ctx, *, shared_line: bool = False):
    """A converted quote whose line 'Mixed' uses a supplied board AND a board with no
    supplier. With `shared_line`, a second line 'Plain' uses the supplied board alone."""
    c = ctx["client"]
    cust = c.post("/customers", json={"name": "Mixed"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "Mixed"}).json()
    rid = est["current_revision_id"]
    mixed = c.post(f"/revisions/{rid}/lines", json={"description": "Mixed", "qty": 1}).json()
    c.post(f"/lines/{mixed['line_id']}/parts",
           json={"material_type": "BOARD", "material_id": ctx["board_id"], "qty": 2})
    c.post(f"/lines/{mixed['line_id']}/parts",
           json={"material_type": "BOARD", "material_id": ctx["unassigned_board_id"], "qty": 1})
    plain = None
    if shared_line:
        plain = c.post(f"/revisions/{rid}/lines", json={"description": "Plain", "qty": 1}).json()
        c.post(f"/lines/{plain['line_id']}/parts",
               json={"material_type": "BOARD", "material_id": ctx["board_id"], "qty": 3})
    _advance_to_won(c, rid)
    _convert(c, rid)
    return est["estimate_id"], rid, mixed["line_id"], plain["line_id"] if plain else None


def test_a_line_with_any_unassigned_material_is_held_back_whole():
    """Ordering part of a line would either lose the rest (if the line counted as
    covered) or order that part twice on the next run (if it did not). So the line
    waits, whole, until every material on it has a supplier."""
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)

    pv = c.get(f"/revisions/{rid}/order-preview").json()
    assert pv["groups"] == [] and len(pv["unassigned"]) == 1
    assert [(l["selected"], l["held_back"]) for l in pv["lines"]] == [(True, True)]

    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "NOTHING_ORDERABLE"
    assert _po_count(ctx["wid"]) == 0
    assert _line_flags(c, eid, rid)[mixed]["orders_generated_at"] is None


def test_a_held_back_line_orders_once_with_all_its_materials_after_the_link():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    _link_supplier("board_materials", "material_id", ctx["unassigned_board_id"], ctx["vendor_a"])

    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["orders_created"] == 1 and body["lines_created"] == 2
    assert body["unassigned"] == [] and body["uncovered_line_ids"] == []
    assert _line_flags(c, eid, rid)[mixed]["orders_generated_at"] is not None
    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ORDERS_ALREADY_GENERATED"


def test_a_material_shared_with_a_held_back_line_is_ordered_for_the_covered_line_only():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, plain = _mixed_quote(ctx, shared_line=True)

    pv = c.get(f"/revisions/{rid}/order-preview").json()
    held = {l["line_id"]: l["held_back"] for l in pv["lines"]}
    assert held == {mixed: True, plain: False}

    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["orders_created"] == 1 and body["uncovered_line_ids"] == [mixed]
    assert _board_qty(c, body["po_ids"][0]) == 3.0  # Plain's 3, not Mixed's 2 as well
    flags = _line_flags(c, eid, rid)
    assert flags[plain]["orders_generated_at"] is not None
    assert flags[mixed]["orders_generated_at"] is None

    # once linked, the held line orders in full — the shared board for its own 2
    _link_supplier("board_materials", "material_id", ctx["unassigned_board_id"], ctx["vendor_a"])
    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 200, r.text
    assert r.json()["lines_created"] == 2 and r.json()["uncovered_line_ids"] == []
    po = c.get(f"/orders/{r.json()['po_ids'][0]}").json()
    qty = {l["material_id"]: float(l["quantity"]) for l in po["lines"]}
    assert qty == {ctx["board_id"]: 2.0, ctx["unassigned_board_id"]: 1.0}


def _archive(table: str, id_col: str, material_id: int) -> None:
    s = SessionLocal()
    try:
        s.execute(
            text(f"UPDATE {table} SET archived_at = now() WHERE {id_col} = :m"),
            {"m": material_id},
        )
        s.commit()
    finally:
        s.close()


def test_an_archived_material_that_is_linked_still_orders_from_its_supplier():
    """The quote priced it before it was archived; treating the row as missing sent it
    to 'unassigned' with a stale snapshot even though it has a supplier."""
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx)
    _convert(c, quote["revision_id"])
    _archive("board_materials", "material_id", ctx["board_id"])
    rid = quote["revision_id"]

    pv = c.get(f"/revisions/{rid}/order-preview").json()
    assert pv["unassigned"] == [] and len(pv["groups"]) == 1
    flags = {l["material_id"]: l["archived"] for l in pv["groups"][0]["lines"]}
    assert flags == {ctx["board_id"]: True, ctx["hw_id"]: False}

    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 200, r.text
    assert r.json()["orders_created"] == 1 and r.json()["lines_created"] == 2


def test_an_archived_material_with_no_supplier_is_still_unassigned_with_its_live_sku():
    ctx, c, eid, rid, line = _orphan_only_quote()
    _archive("board_materials", "material_id", ctx["unassigned_board_id"])
    pv = c.get(f"/revisions/{rid}/order-preview").json()
    assert pv["groups"] == [] and len(pv["unassigned"]) == 1
    assert pv["unassigned"][0]["archived"] is True
    assert pv["unassigned"][0]["sku"].startswith("TORPHAN-")


def test_a_line_that_references_no_catalog_material_is_covered_by_a_run():
    """Nothing on it can ever be ordered, so it must not stay pending forever."""
    ctx = _bootstrap()
    c = ctx["client"]
    cust = c.post("/customers", json={"name": "Labour"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "Labour"}).json()
    rid = est["current_revision_id"]
    plain = c.post(f"/revisions/{rid}/lines", json={"description": "Labour only", "qty": 1}).json()
    stocked = c.post(f"/revisions/{rid}/lines", json={"description": "Stocked", "qty": 1}).json()
    c.post(f"/lines/{stocked['line_id']}/parts",
           json={"material_type": "BOARD", "material_id": ctx["board_id"], "qty": 1})
    _advance_to_won(c, rid)
    _convert(c, rid)

    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 200, r.text
    assert r.json()["orders_created"] == 1 and r.json()["uncovered_line_ids"] == []
    flags = _line_flags(c, est["estimate_id"], rid)
    assert flags[plain["line_id"]]["orders_generated_at"] is not None
    assert flags[stocked["line_id"]]["orders_generated_at"] is not None


def test_the_audit_row_names_the_lines_a_run_covered_and_the_ones_it_left():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx, include_unassigned=True)
    _convert(c, quote["revision_id"])
    rid = quote["revision_id"]
    pantry, orphan = quote["line_ids"]
    assert c.post(f"/revisions/{rid}/generate-orders").status_code == 200
    payload = _sql_scalar(
        "SELECT payload FROM audit_log WHERE event = 'estimate.generate_orders'"
        " AND target = :t ORDER BY id DESC LIMIT 1", t=str(rid))
    assert payload["included_line_ids"] == [pantry]
    assert payload["uncovered_line_ids"] == [orphan]


def test_the_revision_timestamp_is_the_latest_run_and_each_run_is_audited():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    c.post(f"/revisions/{rid}/generate-orders", json={"include_line_ids": [l1]})
    first = _sql_scalar("SELECT orders_generated_at FROM estimate_revision WHERE revision_id = :r", r=rid)
    c.post(f"/revisions/{rid}/generate-orders")
    second = _sql_scalar("SELECT orders_generated_at FROM estimate_revision WHERE revision_id = :r", r=rid)
    assert first is not None and second > first

    s = SessionLocal()
    try:
        rows = s.execute(
            text("SELECT payload FROM audit_log WHERE event = 'estimate.generate_orders'"
                 " AND target = :t ORDER BY id"), {"t": str(rid)}).scalars().all()
    finally:
        s.close()
    assert [p["included_line_ids"] for p in rows] == [[l1], [l2]]


def test_revision_detail_lines_carry_the_per_line_flags():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    flags = _line_flags(c, quote["estimate_id"], rid)
    assert flags[l1]["included_at_convert"] is True
    assert flags[l1]["orders_generated_at"] is None

    c.post(f"/revisions/{rid}/generate-orders", json={"include_line_ids": [l1]})
    flags = _line_flags(c, quote["estimate_id"], rid)
    assert flags[l1]["orders_generated_at"] is not None
    assert flags[l2]["orders_generated_at"] is None


def test_preview_lists_the_lines_and_follows_the_selection():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]

    r = c.get(f"/revisions/{rid}/order-preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [(l["line_id"], l["selected"]) for l in body["lines"]] == [(l1, True), (l2, True)]
    board = next(x for x in body["groups"][0]["lines"] if x["material_type"] == "BOARD")
    assert float(board["qty"]) == 5.0

    # Narrowed to line 2: the groups are for exactly that selection.
    r = c.get(f"/revisions/{rid}/order-preview", params={"include_line_ids": [l2]})
    body = r.json()
    assert [(l["line_id"], l["selected"]) for l in body["lines"]] == [(l1, False), (l2, True)]
    assert [x["material_type"] for x in body["groups"][0]["lines"]] == ["BOARD"]
    assert float(body["groups"][0]["lines"][0]["qty"]) == 3.0


def test_preview_after_a_partial_run_marks_the_covered_line_and_selects_the_rest():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    c.post(f"/revisions/{rid}/generate-orders", json={"include_line_ids": [l1]})

    body = c.get(f"/revisions/{rid}/order-preview").json()

    by_id = {l["line_id"]: l for l in body["lines"]}
    assert by_id[l1]["orders_generated_at"] is not None and by_id[l1]["selected"] is False
    assert by_id[l2]["orders_generated_at"] is None and by_id[l2]["selected"] is True
    assert float(next(x for x in body["groups"][0]["lines"]
                      if x["material_type"] == "BOARD")["qty"]) == 3.0


def test_preview_refuses_a_covered_or_unknown_line_like_generate_does():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    c.post(f"/revisions/{rid}/generate-orders", json={"include_line_ids": [l1]})

    r = c.get(f"/revisions/{rid}/order-preview", params={"include_line_ids": [l1]})
    assert r.status_code == 409
    assert r.json()["detail"] == {"code": "LINES_ALREADY_GENERATED", "line_ids": [l1]}

    r = c.get(f"/revisions/{rid}/order-preview", params={"include_line_ids": [999999]})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "UNKNOWN_LINE_IDS"


def test_concurrent_runs_cannot_order_the_same_line_twice():
    """Two runs naming the same line serialize on the revision lock, so the second
    sees the first's flag instead of both passing the check and making two POs."""
    import threading
    import time

    from app.estimating import queries as q

    ctx, c, quote, l1, l2 = _two_line_quote()
    rid, wid, uid = quote["revision_id"], ctx["wid"], ctx["uid"]
    holding = threading.Event()

    def worker_a():
        s = SessionLocal()
        try:
            q.generate_orders(s, revision_id=rid, workspace_id=wid, actor_id=uid,
                              include_line_ids=[l1])
            holding.set()
            time.sleep(0.4)     # hold the revision lock so B is forced to wait
            s.commit()
        finally:
            s.close()

    t = threading.Thread(target=worker_a)
    t.start()
    assert holding.wait(timeout=5), "run A never finished generating"

    s2 = SessionLocal()
    try:
        start = time.monotonic()
        with pytest.raises(ValueError) as exc:
            q.generate_orders(s2, revision_id=rid, workspace_id=wid, actor_id=uid,
                              include_line_ids=[l1])
        elapsed = time.monotonic() - start
        s2.rollback()
    finally:
        s2.close()
    t.join(timeout=5)

    assert elapsed >= 0.3, f"run B did not wait for run A's lock ({elapsed:.3f}s)"
    assert "LINES_ALREADY_GENERATED" in str(exc.value)
    assert _po_count(wid) == 1
