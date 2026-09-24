"""GET /search and GET /search/health (spec §5; plan tasks D1, D2).

Search is not an RBAC module and adds no row to the matrix: a result type is
visible when the role can `read` the module that owns it (Q576). Types the
role cannot read are dropped silently, never 403'd, so nothing about their
existence leaks. The filter itself is built by `index.build_filter` from
`me.workspace_id`, enum-checked types and integers only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.permissions import has_permission
from ..auth.rbac import current_user, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from .index import TYPES, SearchIndex, SearchQuery, SearchUnavailable, get_index

router = APIRouter(tags=["search"])

# The module whose `read` grant makes a type visible (spec §3).
TYPE_MODULE: dict[str, str] = {
    "project": "tracking", "item": "tracking", "related_part": "tracking",
    "cutlist": "list", "order": "orderbook", "supplier": "orderbook",
    "drawing": "shop_dwgs", "sample": "isample", "customer": "estimating",
    "estimate": "estimating", "material": "catalog",
}
assert set(TYPE_MODULE) == set(TYPES)

HIT_FIELDS = ("type", "entity_id", "title", "subtitle", "codes", "status",
              "archived", "url", "project_code")

_index: SearchIndex | None = None


def search_index() -> SearchIndex:
    """FastAPI dependency; tests override it with a FakeIndex."""
    global _index
    if _index is None:
        _index = get_index()
    return _index


def readable_types(auth_role: str) -> list[str]:
    return [t for t in TYPES if has_permission(auth_role, TYPE_MODULE[t], "read")]


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail={"code": "SEARCH_UNAVAILABLE"})


@router.get("/search")
def search(
    q: str = Query(..., max_length=200),
    types: str | None = Query(None, description="comma-separated"),
    project_id: int | None = None,
    include_archived: bool = False,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=1000),
    me: AuthUser = Depends(current_user),
    index: SearchIndex = Depends(search_index),
):
    q = q.strip()
    if not q:
        raise HTTPException(status_code=422, detail={"code": "EMPTY_QUERY"})
    allowed = readable_types(me.auth_role)
    wanted = [t for t in (types.split(",") if types else allowed) if t in allowed]
    empty = {"hits": [], "total": 0, "type_counts": {}}
    if not wanted:
        return empty

    base = dict(q=q, workspace_id=me.workspace_id, project_id=project_id,
                include_archived=include_archived)
    try:
        result = index.search(SearchQuery(types=wanted, limit=limit, offset=offset, **base))
        counts = result.type_counts
        if set(wanted) != set(allowed):
            # Chips show counts for every readable type, not just the one picked.
            counts = index.search(SearchQuery(types=allowed, limit=0, **base)).type_counts
    except SearchUnavailable:
        raise _unavailable()
    return {
        "hits": [{k: h.get(k) for k in HIT_FIELDS} for h in result.hits],
        "total": result.total,
        "type_counts": counts,
    }


@router.get("/search/health")
def search_health(
    _: AuthUser = Depends(require_permission("it_management", "read")),
    db: Session = Depends(get_db),
    index: SearchIndex = Depends(search_index),
):
    depth, oldest = db.execute(text(
        "SELECT count(*), min(enqueued_at) FROM search_outbox")).one()
    return {
        "meili": "ok" if index.healthy() else "down",
        "outbox_depth": depth,
        "oldest_enqueued_at": oldest.isoformat() if oldest else None,
    }
