"""The outbox worker (plan task C2; spec §4.2), against FakeIndex."""
import os

import pytest
from sqlalchemy import create_engine, text

from app.search.index import FakeIndex, SearchUnavailable
from app.search.worker import process_batch

from .search_helpers import make_tree


def _drain(db, index):
    while process_batch(db, index):
        pass


def _pending(db, kind, eid):
    return db.execute(text("SELECT count(*) FROM search_outbox"
                           " WHERE entity_type = :k AND entity_id = :e"),
                      {"k": kind, "e": eid}).scalar()


@pytest.fixture
def tree(db, workspace_id):
    return make_tree(db, workspace_id)


def test_batch_indexes_and_consumes_rows(db, tree):
    index = FakeIndex()
    _drain(db, index)
    assert f"item-{tree['item']}" in index.docs
    assert f"project-{tree['project']}" in index.docs
    assert f"cutlist-{tree['cutlist']}" in index.docs
    assert _pending(db, "item", tree["item"]) == 0


def test_repeated_writes_collapse_to_one_document(db, tree):
    for n in range(3):
        db.execute(text("UPDATE items SET description = :d WHERE item_id = :i"),
                   {"d": f"Bench v{n}", "i": tree["item"]})
    index = FakeIndex()
    _drain(db, index)
    assert index.docs[f"item-{tree['item']}"]["title"] == "Bench v2"


def test_deleted_row_deletes_its_document(db, tree):
    index = FakeIndex()
    _drain(db, index)
    db.execute(text("UPDATE items SET deleted = true WHERE item_id = :i"), {"i": tree["item"]})
    _drain(db, index)
    assert f"item-{tree['item']}" not in index.docs


def test_rows_survive_an_outage(db, tree):
    """The no-loss guarantee Q575 chose the outbox for."""
    index = FakeIndex()
    index.down = True
    with pytest.raises(SearchUnavailable):
        process_batch(db, index)
    assert _pending(db, "item", tree["item"]) == 1
    index.down = False
    _drain(db, index)
    assert f"item-{tree['item']}" in index.docs


class _Racing(FakeIndex):
    """Commits a fresh outbox row from another connection mid-pass."""

    def __init__(self):
        super().__init__()
        self.raced_id = None

    def upsert(self, docs, uid=None):
        if self.raced_id is None:
            eng = create_engine(os.environ["DATABASE_URL"], future=True)
            with eng.begin() as c:
                self.raced_id = c.execute(text(
                    "INSERT INTO search_outbox(entity_type, entity_id)"
                    " VALUES ('project', 987654321) RETURNING outbox_id")).scalar()
            eng.dispose()
        return super().upsert(docs, uid)


def test_row_committed_mid_pass_survives(db, tree):
    index = _Racing()
    process_batch(db, index, limit=10_000)
    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    try:
        with eng.begin() as c:
            left = c.execute(text("SELECT count(*) FROM search_outbox WHERE outbox_id = :i"),
                             {"i": index.raced_id}).scalar()
            c.execute(text("DELETE FROM search_outbox WHERE outbox_id = :i"),
                      {"i": index.raced_id})
    finally:
        eng.dispose()
    assert left == 1


def test_empty_outbox_is_a_no_op(db):
    index = FakeIndex()
    _drain(db, index)
    assert process_batch(db, index) == 0
