"""Estimate-number allocation keeps numeric order and serializes creators."""
from datetime import datetime, timezone

from sqlalchemy import text

from app.db import SessionLocal
from app.estimating import queries as q

from .conftest import truncate_fixture
from .helpers_concurrency import finish_after_waiting
from .helpers_estimating import _bootstrap, _make_estimate

_cleanup = truncate_fixture()


def test_concurrent_estimates_receive_distinct_numbers():
    c, wid, uid, *_ = _bootstrap(seed_catalog=False)
    customer = c.post("/customers", json={"name": "Concurrent customer"}).json()["customer_id"]
    payload = {"customer_id": customer, "title": "Concurrent job"}
    with SessionLocal() as first:
        a = q.create_estimate(first, workspace_id=wid, actor_id=uid, payload=payload)
        b = finish_after_waiting(first, lambda db: q.create_estimate(db, workspace_id=wid, actor_id=uid, payload=payload))
    with SessionLocal() as db:
        numbers = db.execute(text("SELECT estimate_no FROM estimate WHERE estimate_id=ANY(:ids)"), {"ids": [a, b]}).scalars().all()
    prefix = f"EST-{datetime.now(timezone.utc).year}-"
    assert set(numbers) == {prefix + "0001", prefix + "0002"}


def test_numbering_continues_numerically_after_9999():
    c, _wid, *_ = _bootstrap(seed_catalog=False)
    first = _make_estimate(c)
    prefix = f"EST-{datetime.now(timezone.utc).year}-"
    with SessionLocal() as db:
        db.execute(text("UPDATE estimate SET estimate_no=:n WHERE estimate_id=:i"), {"n": prefix + "9999", "i": first["estimate_id"]})
        db.commit()
    assert _make_estimate(c)["estimate_no"] == prefix + "10000"
    assert _make_estimate(c)["estimate_no"] == prefix + "10001"


def test_custom_non_numeric_numbers_do_not_reset_the_allocator():
    c, wid, uid, *_ = _bootstrap(seed_catalog=False)
    first = _make_estimate(c)
    prefix = f"EST-{datetime.now(timezone.utc).year}-"
    with SessionLocal() as db:
        q.create_estimate(db, workspace_id=wid, actor_id=uid, payload={
            "customer_id": db.execute(text("SELECT customer_id FROM estimate WHERE estimate_id=:i"), {"i": first["estimate_id"]}).scalar_one(),
            "title": "Custom", "estimate_no": prefix + "ZZZZ"})
        db.commit()
    assert _make_estimate(c)["estimate_no"] == prefix + "0002"
