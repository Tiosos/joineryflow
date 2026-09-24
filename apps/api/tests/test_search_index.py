"""Contract tests for the SearchIndex implementations (plan task A2).

The same assertions run against `FakeIndex` always and against a real
Meilisearch when `MEILI_URL` is set (`@pytest.mark.meili`), so the fake cannot
quietly drift from the behaviour the worker and routes rely on.
"""
import os
import uuid

import pytest

from app.search.index import (
    FakeIndex, MeiliIndex, SearchQuery, SearchUnavailable, build_filter,
)


def _doc(i, ws=1, type_="item", title="Kitchen island bench", codes=None,
         project_id=7, archived=False):
    return {
        "id": f"{type_}-{i}", "type": type_, "entity_id": i, "workspace_id": ws,
        "project_id": project_id, "codes": codes or [str(297800 + i)],
        "title": title, "subtitle": "ALF-001", "body": "", "status": "LIVE",
        "archived": archived, "updated_at": 0, "url": f"/items/{i}",
    }


def _real():
    url = os.environ.get("MEILI_URL")
    if not url:
        pytest.skip("MEILI_URL not set")
    idx = MeiliIndex(url, os.environ.get("MEILI_API_KEY", ""),
                     f"test_{uuid.uuid4().hex[:8]}")
    idx.ensure()
    return idx


@pytest.fixture(params=["fake", pytest.param("meili", marks=pytest.mark.meili)])
def index(request):
    if request.param == "fake":
        yield FakeIndex()
        return
    idx = _real()
    yield idx
    idx.drop(idx.index)


def _q(q, **kw):
    kw.setdefault("workspace_id", 1)
    kw.setdefault("types", ["item", "order"])
    return SearchQuery(q=q, **kw)


def _put(index, docs):
    index.wait(index.upsert(docs))


def test_upsert_then_search_finds_by_code(index):
    _put(index, [_doc(30), _doc(31, title="Vanity")])
    hits = index.search(_q("297830")).hits
    assert [h["id"] for h in hits] == ["item-30"]


def test_workspace_filter_is_unconditional(index):
    _put(index, [_doc(1, ws=1), _doc(2, ws=2)])
    assert {h["id"] for h in index.search(_q("Kitchen")).hits} == {"item-1"}
    assert {h["id"] for h in index.search(_q("Kitchen", workspace_id=2)).hits} == {"item-2"}


def test_type_and_project_filters(index):
    _put(index, [_doc(1), _doc(2, type_="order"), _doc(3, project_id=8)])
    assert {h["id"] for h in index.search(_q("Kitchen", types=["order"])).hits} == {"order-2"}
    assert {h["id"] for h in index.search(_q("Kitchen", project_id=8)).hits} == {"item-3"}


def test_archived_hidden_unless_asked(index):
    _put(index, [_doc(1), _doc(2, archived=True)])
    assert {h["id"] for h in index.search(_q("Kitchen")).hits} == {"item-1"}
    assert {h["id"] for h in index.search(_q("Kitchen", include_archived=True)).hits} == {"item-1", "item-2"}


def test_type_counts(index):
    _put(index, [_doc(1), _doc(2), _doc(3, type_="order")])
    assert index.search(_q("Kitchen")).type_counts == {"item": 2, "order": 1}


def test_delete(index):
    _put(index, [_doc(1), _doc(2)])
    index.wait(index.delete(["item-1"]))
    assert {h["id"] for h in index.search(_q("Kitchen")).hits} == {"item-2"}


def test_ensure_is_idempotent(index):
    index.ensure()
    index.ensure()


@pytest.mark.meili
def test_real_typo_tolerance_on_title_not_on_codes():
    """Spec §3.2, binding: a misspelt word matches; a near-miss number does not."""
    idx = _real()
    try:
        _put(idx, [_doc(30)])
        assert [h["id"] for h in idx.search(_q("kitchn")).hits] == ["item-30"]
        assert idx.search(_q("297831")).hits == []
    finally:
        idx.drop(idx.index)


def test_fake_outage_raises():
    f = FakeIndex()
    f.down = True
    with pytest.raises(SearchUnavailable):
        f.search(_q("x"))
    assert f.healthy() is False


def test_real_unreachable_raises_unavailable():
    idx = MeiliIndex("http://127.0.0.1:9", "", "x", timeout=0.5)
    with pytest.raises(SearchUnavailable):
        idx.search(_q("x"))
    assert idx.healthy() is False


# --- build_filter: the one producer of filter expressions ------------------

def test_filter_always_carries_workspace():
    f = build_filter(_q("x", workspace_id=5, types=["item"]))
    assert f == "workspace_id = 5 AND type IN [item] AND archived = false"


def test_filter_drops_unknown_types():
    f = build_filter(_q("x", types=["item", "item] OR workspace_id = 2 OR type IN [x"]))
    assert "OR" not in f and f.startswith("workspace_id = 1 AND type IN [item]")


def test_filter_rejects_no_types():
    with pytest.raises(ValueError):
        build_filter(_q("x", types=["nope"]))


def test_filter_rejects_non_integer_ids():
    with pytest.raises(ValueError):
        build_filter(_q("x", project_id="1 OR workspace_id = 2"))  # type: ignore[arg-type]
