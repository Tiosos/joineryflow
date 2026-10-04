"""Helpers shared by the estimating route and race tests."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app


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


def _make_estimate(c: TestClient, title: str = "Job") -> dict:
    cust = c.post("/customers", json={"name": f"C-{uuid.uuid4().hex[:6]}"}).json()
    r = c.post(
        "/estimates",
        json={"customer_id": cust["customer_id"], "title": title},
    )
    assert r.status_code == 201, r.text
    return r.json()
