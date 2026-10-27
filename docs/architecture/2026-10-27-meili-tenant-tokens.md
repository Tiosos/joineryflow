# Scoping Meilisearch with tenant tokens

> Status: **proposal**, actionable. Expands leak #1 of `2026-10-27-scalable-architecture.md` §decision 5.2, and item 7.1 of the Phase 0 checklist (that file is still in review — PR #173, not on `main` yet).
> Scope: `apps/api/app/search/index.py`, `apps/api/app/config.py`, `.env.example`, one new test file. **`routes.py` does not change.**
> Effort: half a day to a day, including the test.

---

## 0. One-paragraph summary

Today the API queries Meilisearch with the master key, so the engine enforces nothing: `build_filter` in the application layer is the only thing keeping tenant A out of tenant B's results. Sign a short-lived **Meilisearch tenant token** per search request, carrying `searchRules: {"*": {"filter": "workspace_id = N"}}`, and send the search with that token instead. The engine then applies the workspace clause itself, so a code path that forgets `build_filter` returns nothing instead of everything. Because `SearchQuery` already carries `workspace_id`, the change is confined to `MeiliIndex` — no route has to know.

---

## 1. What the code does today

| Fact | Evidence |
| --- | --- |
| The API holds one key and it is the master key | `.env.example:20-24` — "The master key is also used as the api's key in dev; **scoped keys are out of scope for v1**"; `MEILI_API_KEY=jf-dev-meili-master-key` |
| That key is baked into an httpx client at construction | `app/search/index.py:134-140` — `headers={"Authorization": f"Bearer {api_key}"}` |
| Workspace filtering is application-layer only | `app/search/index.py:96-119` `build_filter` — "The workspace clause is unconditional" |
| Types are filtered separately by RBAC | `app/search/routes.py:60-77` `readable_types` |
| **The browser never talks to Meilisearch** | `docker-compose.yml:26-27` — "No host port: only the api and the search-worker talk to it — the browser never does"; the `meili` service exposes no host port |
| Only the worker and the reindex script create/swap indexes | `app/search/worker.py:77` (`index.ensure()`), `app/search/reindex.py:32-44`. The API process calls only `search()` and `healthy()` |
| Image is `getmeili/meilisearch:v1.54.0` | `docker-compose.yml:29` |

### An honest framing of the risk

Because the browser never reaches Meilisearch, this is **not** an exposure-of-credentials-to-the-internet problem. The master key never leaves the server. What it is: a **defence-in-depth** problem. Any code path that reaches Meili without going through `build_filter` returns every tenant's documents, and nothing downstream catches it. With one customer that is a bug; with several, it is a cross-tenant disclosure.

That also means the value ordering below is the right one: the biggest win is making the engine enforce the workspace clause, not merely shrinking the key's permissions.

---

## 2. Two facts that shape the design

Both verified against upstream, not from memory:

1. **The master key cannot sign a tenant token.** The official SDK says so in its own docstring: *"It's not possible to create a token from the master key."* A dedicated key with the `search` action is required.
2. **A tenant token only authorises the search endpoint.** Meilisearch docs: *"Tenant tokens only restrict the search endpoint. They do not apply to admin operations such as indexing, settings updates, or API key management."* So the worker keeps using the master key — unchanged.

Token construction (mirrors `meilisearch/client.py::generate_tenant_token` exactly): header `{"typ":"JWT","alg":"HS256"}`, payload `{"apiKeyUid": <uuid>, "searchRules": {...}, "exp": <epoch seconds>}`, signature `HMAC-SHA256(secret = the signing key's own value, "<header>.<payload>")`, base64url without padding. The official SDK builds this with `hmac` + `hashlib` and **no JWT dependency** — so this project can too.

---

## 3. The change

### 3.1 Create the search-only key (ops, once per environment)

```bash
curl -X POST "$MEILI_URL/keys" \
  -H "Authorization: Bearer $MEILI_MASTER_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary '{
    "description": "JF search: signs tenant tokens",
    "actions": ["search"],
    "indexes": ["*"],
    "expiresAt": null
  }'
# -> {"key": "...", "uid": "...", ...}   put both in the environment
```

`GET /keys` (admin) returns `uid`, `key`, `actions`, `indexes` — so both values can be recovered later, and the uid can be looked up at startup if you prefer not to store it.

### 3.2 `config.py` — three fields

```python
    meili_url: str = "http://meili:7700"
    meili_api_key: str = ""          # unchanged: admin/master, used by the worker and reindex
    meili_search_key: str = ""       # new: search-only; signs tenant tokens
    meili_search_key_uid: str = ""   # new: its uid (required in the token payload)
    meili_tenant_token_ttl: int = 300  # new: seconds
```

### 3.3 `index.py` — the token, ~15 lines, no new dependency

```python
import base64
import hashlib
import hmac
import time


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def tenant_token(*, key_uid: str, key: str, workspace_id: int,
                 ttl_seconds: int = 300) -> str:
    """A Meilisearch tenant token pinning every index to one workspace.

    Same construction as the official SDK's `generate_tenant_token`: HS256,
    the signing secret is the key's own value, `exp` in epoch seconds. The
    master key cannot sign a tenant token -- `key` must carry the `search`
    action.
    """
    header = {"typ": "JWT", "alg": "HS256"}
    # "*" rather than the live index uid: reindex builds `{index}_{ts}` and
    # swaps it in, and a token issued against one uid would not cover the
    # other. The workspace clause is what isolates tenants, not the uid.
    payload = {
        "apiKeyUid": key_uid,
        "searchRules": {"*": {"filter": f"workspace_id = {int(workspace_id)}"}},
        "exp": int(time.time()) + ttl_seconds,
    }
    head = _b64url(json.dumps(header, separators=(",", ":")).encode())
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{head}.{body}"
    sig = hmac.new(key.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(sig)}"
```

### 3.4 `index.py` — per-request `Authorization`

`MeiliIndex.__init__` keeps the admin header as the client default; `search()` overrides it for that one call.

```python
class MeiliIndex:
    def __init__(self, url, api_key, index, timeout=5.0, *,
                 search_key: str = "", search_key_uid: str = "",
                 token_ttl: int = 300):
        self.index = index
        self._search_key = search_key
        self._search_key_uid = search_key_uid
        self._token_ttl = token_ttl
        self._admin = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(
            base_url=url.rstrip("/"), headers=self._admin, timeout=timeout)

    def _call(self, method, path, *, headers: dict | None = None, **kw) -> dict:
        try:
            r = self._http.request(
                method, path, headers=self._admin if headers is None else headers, **kw)
        except httpx.TransportError as e:
            raise SearchUnavailable(str(e)) from e
        ...  # unchanged

    def search(self, query: SearchQuery) -> SearchResult:
        headers = None
        if self._search_key and self._search_key_uid:
            headers = {"Authorization": "Bearer " + tenant_token(
                key_uid=self._search_key_uid,
                key=self._search_key,
                workspace_id=query.workspace_id,
                ttl_seconds=self._token_ttl)}
        body = self._call("POST", f"/indexes/{self.index}/search",
                          headers=headers, json={
            "q": query.q,
            "filter": build_filter(query),   # kept: see §4
            ...                              # unchanged
        })
```

`build_filter` stays. The engine ANDs the token's rule with the request filter, so both layers apply; removing the application one would make task-visibility and RBAC behaviour depend on the engine.

### 3.5 `get_index()`

```python
def get_index() -> SearchIndex:
    from ..config import settings

    return MeiliIndex(
        settings.meili_url, settings.meili_api_key, settings.search_index,
        search_key=settings.meili_search_key,
        search_key_uid=settings.meili_search_key_uid,
        token_ttl=settings.meili_tenant_token_ttl,
    )
```

### 3.6 Worth doing in the same pass: the API stops needing the master key

Only `worker.py:77` and `reindex.py` call `ensure()`/`swap()`/`drop()`; the API process calls only `search()` and `healthy()` (Meili's `/health` needs no key). So once search goes through a token, the API container's `MEILI_API_KEY` can be **the search-only key**, not the master key — leaving the master key in the worker's environment only.

That is a real reduction in blast radius for a two-line config change, and it is the part that makes "the api holds the master key" stop being true. Recommended, but it is independent of the token work and can ship after it.

---

## 4. Tests

### 4.1 Signing, no Meilisearch needed (runs in the default suite)

```python
def test_tenant_token_is_hs256_and_carries_the_workspace_rule():
    token = tenant_token(key_uid="u", key="s3cret", workspace_id=7, ttl_seconds=60)
    head, body, sig = token.split(".")

    def dec(s):
        return json.loads(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)))

    assert dec(head) == {"typ": "JWT", "alg": "HS256"}
    assert dec(body)["searchRules"] == {"*": {"filter": "workspace_id = 7"}}
    assert dec(body)["apiKeyUid"] == "u"
    assert dec(body)["exp"] > int(time.time())
    expected = hmac.new(b"s3cret", f"{head}.{body}".encode(), hashlib.sha256).digest()
    assert base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4)) == expected
```

### 4.2 The engine actually enforces it (mark `meili`, self-contained)

New `apps/api/tests/test_search_tenant_token.py`. It creates its own key and deletes it afterwards, so it needs no environment change and works in CI:

```python
@pytest.mark.meili
def test_tenant_token_hides_other_workspaces_even_with_no_filter():
    idx = _real()                      # MeiliIndex on the master key (admin)
    key = idx._call("POST", "/keys", json={
        "description": "tenant token test", "actions": ["search"],
        "indexes": ["*"], "expiresAt": None})
    try:
        idx.wait(idx.upsert([_doc(1, ws=1), _doc(2, ws=2)]))
        token = tenant_token(key_uid=key["uid"], key=key["key"], workspace_id=1)

        # Deliberately no filter in the request: the token must supply it.
        r = httpx.post(
            f"{os.environ['MEILI_URL']}/indexes/{idx.index}/search",
            headers={"Authorization": f"Bearer {token}"},
            json={"q": "kitchen"})
        r.raise_for_status()
        assert {h["id"] for h in r.json()["hits"]} == {"item-1"}
    finally:
        idx._call("DELETE", f"/keys/{key['uid']}")
        idx.drop(idx.index)
```

`_doc(i, ws=…)` and `_real()` already exist in `test_search_index.py`. This test is the acceptance criterion from the review — "using a token issued for tenant A returns none of tenant B's documents" — written so it fails if the token is not applied.

### 4.3 What must still pass

The whole existing suite. `FakeIndex` is untouched, and when `meili_search_key` is empty `MeiliIndex` behaves exactly as before, so the 1,690 tests and the dev environment are unaffected. Add one assertion there: search with no search key configured still filters by workspace (that is `test_workspace_filter_is_unconditional` today).

---

## 5. Configuration and operations

`.env.example` — replace the "scoped keys are out of scope for v1" note:

```
# Global Search (sub-project #11).
# meili_api_key is the admin key: only the worker and `make reindex` need it
# (they create, swap and drop indexes). The api container can be given the
# search-only key instead -- it only searches.
# meili_search_key signs a tenant token per request, which is what pins
# results to one workspace in the engine. The master key cannot sign one.
# Create it with: POST /keys {"actions":["search"],"indexes":["*"]}
MEILI_MASTER_KEY=jf-dev-meili-master-key
MEILI_URL=http://meili:7700
MEILI_API_KEY=jf-dev-meili-master-key
MEILI_SEARCH_KEY=
MEILI_SEARCH_KEY_UID=
```

- **Rotation**: create a new key, update the env, delete the old one (`DELETE /keys/{uid}` takes effect immediately). Tenant tokens are short-lived, so old ones expire on their own.
- **Report the state**: add `"tenant_tokens": "on" if (settings.meili_search_key and settings.meili_search_key_uid) else "off"` to `GET /search/health`, so "did production actually turn this on" is answerable without shelling into a container.
- **Fail-open by default**. With no search key configured, search behaves as today. For production, `tenant_tokens: on` belongs in the Phase 0 acceptance list rather than as a hard startup failure, so a misconfiguration cannot take search down for one customer.

---

## 6. Acceptance

| # | Criterion | How it is checked |
| --- | --- | --- |
| 1 | A tenant token issued for workspace 1 returns no workspace-2 documents even when the request carries no filter | 4.2, automated |
| 2 | The token is HS256, signed with the search key, expires | 4.1, automated |
| 3 | `GET /search` still applies RBAC type filtering and task visibility | existing `test_search_routes.py` |
| 4 | `GET /search/health` reports `tenant_tokens: on` in production | manual, once |
| 5 | An expired token is rejected by the engine | manual: issue with `ttl_seconds=1`, sleep, expect 403 |
| 6 | (3.6) The api container has no master key in its environment | `docker compose exec api env \| grep MEILI_API_KEY` differs from `MEILI_MASTER_KEY` |

---

## 7. Alternatives considered

| Option | Verdict |
| --- | --- |
| **Tenant token per request** | ✅ Recommended. Engine-side enforcement, no route changes, no new dependency |
| **One index per workspace** | ❌ Index count grows linearly with customers; Meilisearch has practical limits on index count, and `reindex.py`'s create-then-swap would have to run per index. Physical isolation for a logical problem |
| **Search-only key, no token** | Half a step: shrinks the key's permissions but the engine still enforces no workspace clause. Worth doing (§3.6), not sufficient alone |
| **Sign one token per session and cache it** | Rejected. A cache is state that can go stale across a workspace switch or a key rotation, and HMAC-SHA256 costs microseconds. Sign per request |
| **Postgres RLS** | Same idea on the database side (§decision 5.3), separate work, Phase 2 |

---

## 8. Notes and risks

- **The token does not replace RBAC.** It pins `workspace_id` only. Type visibility (`readable_types`) and task `visibility`/`private_to` stay in the application layer, enforced by `build_filter` and `readable_types`. Do not let anyone read this change as "search is now secure".
- **The API still needs `meili_api_key`** for `healthy()` until §3.6 ships; that call is `GET /health`, which needs no key, so ordering §3.6 first is also fine.
- **`searchRules` uses `"*"`** deliberately — a token scoped to `jf_search` alone would not cover the `{index}_{timestamp}` index during reindex. The workspace clause, not the uid, is what isolates tenants.
- **Do not cache tokens**, and do not log them. `exp` is 300 s; a leaked token is useless within minutes and cannot write.
- **No dependency is added.** The construction matches upstream's own implementation (`hmac` + `hashlib` + base64url). If the team would rather not hand-roll it, `PyJWT` is a single well-scoped dependency and the only change is the last four lines of `tenant_token`.
