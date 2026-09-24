"""The search index behind a small protocol (spec §5).

`MeiliIndex` talks to Meilisearch over plain HTTP (httpx); `FakeIndex` is the
in-memory stand-in the test suite uses, so only tests marked `meili` need a
running container. Callers pass *structured* filters — never a filter string —
and `build_filter` is the one place a Meilisearch filter expression is made.
That keeps workspace isolation in a single, separately tested function.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

# The closed set of document types (spec §3). `build_filter` only ever emits
# values from this tuple, so no caller-supplied string reaches a filter.
TYPES: tuple[str, ...] = (
    "project", "item", "related_part", "cutlist", "order", "supplier",
    "drawing", "sample", "customer", "estimate", "material",
)

SETTINGS: dict = {
    # Order matters: an exact code outranks a description that mentions it.
    "searchableAttributes": ["codes", "title", "subtitle", "body"],
    "filterableAttributes": ["workspace_id", "type", "project_id", "archived", "status"],
    "sortableAttributes": ["updated_at"],
    # Binding (spec §3.2): joinery_number_seq is shared (Q541), so a number one
    # keystroke off is a different record and must never match.
    "typoTolerance": {"disableOnAttributes": ["codes"]},
}


class SearchUnavailable(Exception):
    """Meilisearch could not be reached or answered with a server error."""


@dataclass
class SearchQuery:
    q: str
    workspace_id: int
    types: list[str]
    project_id: int | None = None
    include_archived: bool = False
    limit: int = 20
    offset: int = 0


@dataclass
class SearchResult:
    hits: list[dict]
    total: int
    type_counts: dict[str, int] = field(default_factory=dict)


def build_filter(query: SearchQuery) -> str:
    """The only producer of Meilisearch filter expressions.

    Every value is either an int (coerced here, so a crafted string fails
    loudly) or a member of `TYPES`. The workspace clause is unconditional.
    """
    types = [t for t in query.types if t in TYPES]
    if not types:
        raise ValueError("no searchable types")
    parts = [
        f"workspace_id = {int(query.workspace_id)}",
        "type IN [" + ", ".join(types) + "]",
    ]
    if query.project_id is not None:
        parts.append(f"project_id = {int(query.project_id)}")
    if not query.include_archived:
        parts.append("archived = false")
    return " AND ".join(parts)


class SearchIndex(Protocol):
    def ensure(self, uid: str | None = None) -> None: ...
    def upsert(self, docs: list[dict], uid: str | None = None) -> int: ...
    def delete(self, ids: list[str], uid: str | None = None) -> int: ...
    def wait(self, task_uid: int) -> None: ...
    def search(self, query: SearchQuery) -> SearchResult: ...
    def swap(self, a: str, b: str) -> None: ...
    def drop(self, uid: str) -> None: ...
    def healthy(self) -> bool: ...


class MeiliIndex:
    def __init__(self, url: str, api_key: str, index: str, timeout: float = 5.0):
        self.index = index
        self._http = httpx.Client(
            base_url=url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=timeout,
        )

    def _call(self, method: str, path: str, **kw) -> dict:
        try:
            r = self._http.request(method, path, **kw)
        except httpx.TransportError as e:
            raise SearchUnavailable(str(e)) from e
        if r.status_code >= 500:
            raise SearchUnavailable(f"{r.status_code} {r.text[:200]}")
        r.raise_for_status()
        return r.json() if r.content else {}

    def _task(self, body: dict) -> int:
        return body["taskUid"]

    def ensure(self, uid: str | None = None) -> None:
        """Create the index if absent, then apply SETTINGS (idempotent)."""
        uid = uid or self.index
        try:
            self._call("GET", f"/indexes/{uid}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                raise
            self.wait(self._task(self._call(
                "POST", "/indexes", json={"uid": uid, "primaryKey": "id"})))
        self.wait(self._task(self._call(
            "PATCH", f"/indexes/{uid}/settings", json=SETTINGS)))

    def upsert(self, docs: list[dict], uid: str | None = None) -> int:
        return self._task(self._call(
            "POST", f"/indexes/{uid or self.index}/documents",
            params={"primaryKey": "id"}, json=docs))

    def delete(self, ids: list[str], uid: str | None = None) -> int:
        return self._task(self._call(
            "POST", f"/indexes/{uid or self.index}/documents/delete-batch", json=ids))

    def wait(self, task_uid: int, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while True:
            t = self._call("GET", f"/tasks/{task_uid}")
            if t["status"] == "succeeded":
                return
            if t["status"] in ("failed", "canceled"):
                raise SearchUnavailable(f"task {task_uid} {t['status']}: {t.get('error')}")
            if time.monotonic() > deadline:
                raise SearchUnavailable(f"task {task_uid} timed out")
            time.sleep(0.05)

    def search(self, query: SearchQuery) -> SearchResult:
        body = self._call("POST", f"/indexes/{self.index}/search", json={
            "q": query.q,
            "filter": build_filter(query),
            "limit": query.limit,
            "offset": query.offset,
            "facets": ["type"],
            # Every query word must match. Meili's default ("last") drops
            # trailing words until something matches, so "EST-2026-0001"
            # (tokenised EST / 2026 / 0001) returned EST-2026-0002 too — the
            # same wrong-record hazard the codes typo rule exists for.
            "matchingStrategy": "all",
        })
        return SearchResult(
            hits=body["hits"],
            total=body.get("estimatedTotalHits", len(body["hits"])),
            type_counts=body.get("facetDistribution", {}).get("type", {}),
        )

    def swap(self, a: str, b: str) -> None:
        self.wait(self._task(self._call(
            "POST", "/swap-indexes", json=[{"indexes": [a, b]}])))

    def drop(self, uid: str) -> None:
        self.wait(self._task(self._call("DELETE", f"/indexes/{uid}")))

    def healthy(self) -> bool:
        try:
            return self._call("GET", "/health").get("status") == "available"
        except (SearchUnavailable, httpx.HTTPError):
            return False


class FakeIndex:
    """In-memory `SearchIndex`. Matching is case-insensitive substring over the
    searchable fields — enough to test plumbing, not relevance."""

    def __init__(self, index: str = "jf_search"):
        self.index = index
        self.indexes: dict[str, dict[str, dict]] = {index: {}}
        self.down = False
        self._tasks = 0

    def _check(self) -> None:
        if self.down:
            raise SearchUnavailable("fake is down")

    def _next(self) -> int:
        self._tasks += 1
        return self._tasks

    @property
    def docs(self) -> dict[str, dict]:
        return self.indexes[self.index]

    def ensure(self, uid: str | None = None) -> None:
        self._check()
        self.indexes.setdefault(uid or self.index, {})

    def upsert(self, docs: list[dict], uid: str | None = None) -> int:
        self._check()
        store = self.indexes.setdefault(uid or self.index, {})
        for d in docs:
            store[d["id"]] = d
        return self._next()

    def delete(self, ids: list[str], uid: str | None = None) -> int:
        self._check()
        store = self.indexes.setdefault(uid or self.index, {})
        for i in ids:
            store.pop(i, None)
        return self._next()

    def wait(self, task_uid: int) -> None:
        self._check()

    def search(self, query: SearchQuery) -> SearchResult:
        self._check()
        build_filter(query)  # same validation as the real path
        needle = query.q.lower()
        allowed = set(query.types) & set(TYPES)

        def visible(d: dict) -> bool:
            return (
                d["workspace_id"] == query.workspace_id
                and d["type"] in allowed
                and (query.project_id is None or d.get("project_id") == query.project_id)
                and (query.include_archived or not d.get("archived"))
            )

        def matches(d: dict) -> bool:
            hay = " ".join([*d.get("codes", []), d.get("title") or "",
                            d.get("subtitle") or "", d.get("body") or ""])
            return needle in hay.lower()

        found = [d for d in self.docs.values() if visible(d) and matches(d)]
        counts: dict[str, int] = {}
        for d in found:
            counts[d["type"]] = counts.get(d["type"], 0) + 1
        return SearchResult(
            hits=found[query.offset:query.offset + query.limit],
            total=len(found),
            type_counts=counts,
        )

    def swap(self, a: str, b: str) -> None:
        self._check()
        self.indexes[a], self.indexes[b] = self.indexes.get(b, {}), self.indexes.get(a, {})

    def drop(self, uid: str) -> None:
        self._check()
        self.indexes.pop(uid, None)

    def healthy(self) -> bool:
        return not self.down


def get_index() -> SearchIndex:
    """The configured index — the worker's and the routes' single source."""
    from ..config import settings

    return MeiliIndex(settings.meili_url, settings.meili_api_key, settings.search_index)
