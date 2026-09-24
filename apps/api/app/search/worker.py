"""Drain search_outbox into the index (spec §4.2; plan task C2).

    python -m app.search.worker

One pass (`process_batch`):

1. lock up to `limit` outbox rows (`FOR UPDATE SKIP LOCKED`, so several
   workers could share the queue — compose runs one);
2. de-duplicate by (kind, id) and load each row's *current* document;
3. upsert what exists, delete what does not, and **wait for Meilisearch to
   report the tasks succeeded**;
4. delete exactly the outbox ids it locked.

Step 4 deletes by locked id, never by entity: a write committed while this
pass is between steps 2 and 4 has its own outbox row, which survives and is
picked up next pass. If step 3 raises, the caller rolls back and every locked
row stays — nothing is lost while Meilisearch is down (Q575).

Waiting for task *success* (rather than only Meili's enqueue acknowledgement)
is stricter than spec §4.2 asked, and deliberate: an accepted task can still
fail, and the outbox row is the only record that a document is owed.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import documents
from .index import SearchIndex, SearchUnavailable

log = logging.getLogger("jf.search.worker")

BATCH = 500
IDLE_SLEEP = 1.0
BACKOFF_MAX = 60.0


def process_batch(db: Session, index: SearchIndex, limit: int = BATCH) -> int:
    """One pass. Returns the number of outbox rows consumed. Does not commit —
    the caller owns the transaction, so a raise leaves every row in place."""
    rows = db.execute(text("""
        SELECT outbox_id, entity_type, entity_id FROM search_outbox
         ORDER BY outbox_id LIMIT :n FOR UPDATE SKIP LOCKED"""), {"n": limit}).all()
    if not rows:
        return 0

    by_kind: dict[str, set[int]] = defaultdict(set)
    for _, kind, eid in rows:
        by_kind[kind].add(eid)

    upserts: list[dict] = []
    deletes: list[str] = []
    for kind, ids in by_kind.items():
        found = documents.load(db, kind, sorted(ids))
        upserts.extend(found.values())
        for eid in ids - found.keys():
            deletes.extend(documents.doc_ids(kind, eid))

    if upserts:
        index.wait(index.upsert(upserts))
    if deletes:
        index.wait(index.delete(deletes))

    db.execute(text("DELETE FROM search_outbox WHERE outbox_id = ANY(:ids)"),
               {"ids": [r[0] for r in rows]})
    return len(rows)


def run(session_factory, index: SearchIndex) -> None:  # pragma: no cover - loop
    backoff = 1.0
    while True:
        try:
            index.ensure()
            break
        except SearchUnavailable as e:
            log.warning("search index unavailable at start-up (%s); retry in %.0fs", e, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)

    backoff = 1.0
    while True:
        db = session_factory()
        try:
            n = process_batch(db, index)
            db.commit()
            backoff = 1.0
            if n:
                log.info("indexed %d outbox rows", n)
            else:
                time.sleep(IDLE_SLEEP)
        except SearchUnavailable as e:
            db.rollback()
            log.warning("search index unavailable (%s); retry in %.0fs", e, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)
        except Exception:
            db.rollback()
            log.exception("search worker pass failed; retry in %.0fs", backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)
        finally:
            db.close()


if __name__ == "__main__":  # pragma: no cover
    from ..db import SessionLocal
    from .index import get_index

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    run(SessionLocal, get_index())
