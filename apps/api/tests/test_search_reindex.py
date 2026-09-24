"""Full reindex (plan task C3; spec §4.3)."""
import os
import uuid

import pytest
from sqlalchemy import text

from app.search import documents as D
from app.search.index import FakeIndex, MeiliIndex, SearchQuery
from app.search.reindex import reindex

from .search_helpers import make_tree


def test_source_tables_match_installed_triggers(db):
    """documents.SOURCE_TABLES and migration 0033's triggers must agree, or a
    reindex and the outbox would disagree about what exists."""
    rows = db.execute(text("""
        SELECT c.relname, encode(t.tgargs, 'escape')
          FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
         WHERE t.tgname LIKE 'search_enqueue_%' AND c.relname <> 'estimate_revision'""")).all()
    installed = {}
    for table, args in rows:
        kind, pk = args.split("\\000")[:2]
        installed[kind] = (table, pk)
    assert installed == D.SOURCE_TABLES


def test_reindex_replaces_live_contents(db, workspace_id):
    tree = make_tree(db, workspace_id)
    index = FakeIndex()
    index.upsert([{"id": "item-0", "type": "item", "workspace_id": workspace_id}])  # stale
    n = reindex(db, index)
    assert n > 0
    assert "item-0" not in index.docs
    assert f"item-{tree['item']}" in index.docs
    assert list(index.indexes) == ["jf_search"]  # temporary index dropped


@pytest.mark.meili
def test_real_reindex_swaps_and_drops_temp(db, workspace_id):
    tree = make_tree(db, workspace_id)
    live = f"test_{uuid.uuid4().hex[:8]}"
    idx = MeiliIndex(os.environ["MEILI_URL"], os.environ.get("MEILI_API_KEY", ""), live)
    try:
        idx.ensure()
        idx.wait(idx.upsert([{"id": "item-0", "type": "item", "workspace_id": workspace_id,
                              "codes": ["STALE"], "title": "stale", "archived": False}]))
        reindex(db, idx)
        q = SearchQuery(q="Island bench", workspace_id=workspace_id, types=["item"])
        assert [h["id"] for h in idx.search(q).hits] == [f"item-{tree['item']}"]
        stale = SearchQuery(q="STALE", workspace_id=workspace_id, types=["item"])
        assert idx.search(stale).hits == []
        uids = [i["uid"] for i in idx._call("GET", "/indexes", params={"limit": 1000})["results"]]
        assert not [u for u in uids if u.startswith(f"{live}_")]
    finally:
        idx.drop(live)
