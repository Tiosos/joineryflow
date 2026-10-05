"""Quote builders shared by the generate-orders, coverage and dismissal tests."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .helpers import log_in


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
    return log_in(slug, email)


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


def _advance_to_won(c: TestClient, rid: int) -> None:
    for _ in range(10):
        assert c.post(f"/revisions/{rid}/advance").status_code == 200
    assert c.post(f"/revisions/{rid}/accept").status_code == 200


def _convert(c: TestClient, rid: int) -> int:
    r = c.post(f"/revisions/{rid}/convert")
    assert r.status_code == 200, r.text
    return r.json()["project_id"]
