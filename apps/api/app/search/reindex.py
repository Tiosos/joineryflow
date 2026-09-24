"""Full rebuild with no search downtime (spec §4.3; plan task C3).

    python -m app.search.reindex        # or: make reindex

Builds every document into a fresh `{index}_{timestamp}`, applies SETTINGS,
atomically swaps it with the live index, then drops the old data (which the
swap left under the temporary name). Search answers from the old index until
the swap. The outbox is not touched: rows written during the rebuild are still
applied by the worker afterwards, and applying a current document twice is
harmless.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import documents
from .index import SearchIndex

log = logging.getLogger("jf.search.reindex")

CHUNK = 1000


def reindex(db: Session, index: SearchIndex) -> int:
    """Returns the number of documents written."""
    live = index.index
    tmp = f"{live}_{int(time.time() * 1000)}"
    index.ensure(live)  # swap needs both sides to exist
    index.ensure(tmp)
    written = 0
    for kind in documents.KINDS:
        table, pk = documents.SOURCE_TABLES[kind]
        ids = [r[0] for r in db.execute(text(f"SELECT {pk} FROM {table} ORDER BY {pk}"))]
        for i in range(0, len(ids), CHUNK):
            docs = list(documents.load(db, kind, ids[i:i + CHUNK]).values())
            if docs:
                index.wait(index.upsert(docs, uid=tmp))
                written += len(docs)
    index.swap(live, tmp)
    index.drop(tmp)
    return written


if __name__ == "__main__":  # pragma: no cover
    from ..db import SessionLocal
    from .index import get_index

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    db = SessionLocal()
    try:
        log.info("reindexed %d documents", reindex(db, get_index()))
    finally:
        db.close()
