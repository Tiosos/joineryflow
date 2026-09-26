"""Regression test for the estimate_line.seq race in create_line().

create_line() computed `SELECT COALESCE(MAX(seq), 0) + 1` and inserted
without locking the parent revision, so two concurrent POST /revisions/{rid}
/lines calls on the same draft could both read the same MAX(seq) and insert
duplicate seq values. The fix locks the revision row (the same
lock_revision_for_update() helper other estimating mutations already use)
for the rest of the transaction, so a concurrent create_line() on the same
revision blocks instead of racing.
"""
from __future__ import annotations

import threading
import time
from decimal import Decimal

from sqlalchemy import text

from app.db import SessionLocal
from app.estimating import queries as q

from .test_estimating_routes import _bootstrap, _make_estimate


def test_concurrent_create_line_serializes_instead_of_duplicating_seq():
    c, wid, uid, *_ = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]

    lock_acquired = threading.Event()

    def worker_a():
        s = SessionLocal()
        try:
            q.create_line(
                s, revision_id=rid, workspace_id=wid, actor_id=uid,
                payload={"description": "A", "qty": Decimal("1"),
                         "unit": "EA", "notes": None},
            )
            lock_acquired.set()
            time.sleep(0.4)  # hold the revision row lock so B is forced to wait
            s.commit()
        finally:
            s.close()

    t = threading.Thread(target=worker_a)
    t.start()
    assert lock_acquired.wait(timeout=2), "worker A never reached create_line"

    s2 = SessionLocal()
    try:
        start = time.monotonic()
        q.create_line(
            s2, revision_id=rid, workspace_id=wid, actor_id=uid,
            payload={"description": "B", "qty": Decimal("1"),
                     "unit": "EA", "notes": None},
        )
        elapsed = time.monotonic() - start
        s2.commit()
    finally:
        s2.close()
    t.join(timeout=2)

    assert elapsed >= 0.3, (
        f"create_line for B did not block on A's lock (elapsed={elapsed:.3f}s) "
        "— the race is back"
    )

    check = SessionLocal()
    try:
        rows = check.execute(
            text(
                "SELECT seq FROM estimate_line WHERE revision_id = :r ORDER BY seq"
            ),
            {"r": rid},
        ).scalars().all()
    finally:
        check.close()
    assert rows == [1, 2], f"expected distinct sequential seqs, got {rows}"
