"""Regression test for the po_line_items.line_number race in add_line().

add_line() computed `SELECT COALESCE(MAX(line_number), 0) + 1` against
po_line_items without locking the parent purchase_orders row, so two
concurrent POST /orders/{po_id}/lines calls on the same order could both
read the same MAX(line_number) and insert a duplicate — which the
UNIQUE (po_id, line_number) constraint (migration 0002) turns into an
unhandled 500 (the route has no IntegrityError handling at all).

The fix locks the purchase_orders row (_lock_order_for_update, mirroring
estimating's lock_revision_for_update) for the rest of the transaction, so
a concurrent add_line() on the same order serializes instead of racing.
"""
from __future__ import annotations

import threading
import time
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app
from app.orders import queries as q
from app.orders.schemas import CreateOrderLineIn



pytestmark = pytest.mark.usefixtures("truncate_after")


def _bootstrap() -> dict:
    suffix = uuid.uuid4().hex[:8]
    slug = f"olr-{suffix}"
    email = f"u-{suffix}@x.test"
    s = SessionLocal()
    try:
        wid = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'OLR') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = s.execute(
            text(
                """INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                   VALUES (:w, :e, 'Buyer', :p, 'purchase_officer') RETURNING id"""
            ),
            {"w": wid, "e": email, "p": hash_password("pw")},
        ).scalar()
        vendor = s.execute(
            text(
                "INSERT INTO vendors(name, category, workspace_id)"
                " VALUES('Vendor', 'Board', :w) RETURNING vendor_id"
            ),
            {"w": wid},
        ).scalar()
        s.commit()
    finally:
        s.close()
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    r = c.post("/orders", json={
        "vendor_id": vendor, "description": "widgets", "category": "Board",
    })
    assert r.status_code == 201, r.text
    return {"client": c, "wid": wid, "uid": uid, "po_id": r.json()["po_id"]}


def test_concurrent_add_line_serializes_instead_of_duplicating_line_number():
    ctx = _bootstrap()
    po_id, wid, uid = ctx["po_id"], ctx["wid"], ctx["uid"]

    lock_acquired = threading.Event()

    def worker_a():
        s = SessionLocal()
        try:
            q.add_line(
                s, po_id=po_id, workspace_id=wid, actor_id=uid,
                payload=CreateOrderLineIn(
                    item_description="A", quantity=Decimal("1"),
                    unit_price=Decimal("10"),
                ),
            )
            lock_acquired.set()
            time.sleep(0.4)  # hold the order row lock so B is forced to wait
            s.commit()
        finally:
            s.close()

    t = threading.Thread(target=worker_a)
    t.start()
    assert lock_acquired.wait(timeout=2), "worker A never reached add_line"

    s2 = SessionLocal()
    try:
        start = time.monotonic()
        q.add_line(
            s2, po_id=po_id, workspace_id=wid, actor_id=uid,
            payload=CreateOrderLineIn(
                item_description="B", quantity=Decimal("1"),
                unit_price=Decimal("10"),
            ),
        )
        elapsed = time.monotonic() - start
        s2.commit()
    finally:
        s2.close()
    t.join(timeout=2)

    assert elapsed >= 0.3, (
        f"add_line for B did not block on A's lock (elapsed={elapsed:.3f}s) "
        "— the race is back"
    )

    check = SessionLocal()
    try:
        rows = check.execute(
            text(
                "SELECT line_number FROM po_line_items"
                " WHERE po_id = :o ORDER BY line_number"
            ),
            {"o": po_id},
        ).scalars().all()
    finally:
        check.close()
    assert rows == [1, 2], f"expected distinct sequential line_numbers, got {rows}"
