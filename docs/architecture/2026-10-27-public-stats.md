# `GET /public/stats` — the second cross-tenant leak, and three ways to close it

> Status: **proposal**, actionable. Companion to `2026-10-27-scalable-architecture.md` §decision 5.2 (leak #2) and `2026-10-27-phase0-checklist.md` §7.2.
> Scope: docs only. No code in this PR.
> Every claim below cites the file and line it came from.

---

## 1. What the endpoint is

`app/public/routes.py:19` — one route, no authentication, docstring says *"returns only non-sensitive numeric totals"*. It answers with three counts for whatever `workspace_slug` the caller asks for:

| Field | Counts |
| --- | --- |
| `projects_live` | every project in the workspace |
| `parts_tracked` | parts of live joinery items in the workspace |
| `suppliers` | distinct supplier names across nine material tables |

**It has exactly one caller**, the login page's brand panel: `apps/web/app/(public)/login/page.tsx:46`.

And that caller passes a **hard-coded constant**:

```tsx
// apps/web/app/(public)/login/page.tsx:5
const WORKSPACE_SLUG = "hartwood-joinery";
```

The login form below it is labelled *"Single-tenant — fixed for now"* (`login/page.tsx:230`).

**This is the whole finding.** The `workspace_slug` parameter is flexibility that nothing uses. The one caller always asks for the same workspace. That unused parameter *is* the entire attack surface — remove it and the leak goes with it.

## 2. Severity, calibrated

Let me be precise, because my earlier wording overstated this and I'd rather correct it in writing.

**It is not an exposed credential.** No key, no session, no PII crosses the wire — three integers come back. No names, no money, no ids (`public/routes.py:13-17`).

**What it becomes with a second customer:** anyone who knows or guesses a slug reads that customer's project count, part count and supplier count, and confirms they are a customer. That is commercial information, not personal data — real, worth fixing before a second tenant, but not an incident today.

**It is a weak existence oracle, not a reliable one.** An unknown slug answers all zeros (`routes.py:91`), and so does a real workspace that happens to be empty. So "zeros" does not prove non-existence.

**No rate limit.** `rate|throttle|slowapi|limiter` returns zero hits across `apps/api/app` and `apps/api/pyproject.toml`. The endpoint is unauthenticated and uncached.

**The project already accepted this, knowingly.** `docs/REVIEW-2026-10.md` A4 is marked *"checked, intentional, no change"*, and it lists the accepted limits — including, verbatim:

> *the login page hard-codes `hartwood-joinery`, so a second customer needs a different approach to this panel*

That is exactly the trigger we have now reached. This plan is that different approach; it does not contradict A4, it discharges the condition A4 itself named.

## 3. What is *not* a leak — checked, please don't fix these

Two things look related and are not:

| Checked | Finding |
| --- | --- |
| `POST /auth/login` also takes `workspace_slug` (`auth/routes.py:22-42`) | **No tenant-existence oracle.** Unknown workspace, inactive user and wrong password all fall into the same branch and raise the same `401 "invalid credentials"` (`auth/routes.py:36-38`). Nothing to change. |
| `workspace.slug` guessability | `citext NOT NULL UNIQUE` (`db/alembic/versions/0004_auth.py:19`). Enumeration means guessing company names, not scanning sequential ids. Renaming it would break the login form for no security gain. |

## 4. Options

| | Option | Change | Cost | Verdict |
| --- | --- | --- | --- | --- |
| **A** | **Drop the parameter; tenant comes from server config** | ~15 lines across 3 files + test rewrite | Low | **Recommended** |
| **B** | **Delete the endpoint; brand panel goes static** | Delete module, route, fetch, panel numbers, test file | Low | Good if the three numbers aren't worth an unauthenticated endpoint |
| **C** | Keep it; add rate limiting + an unguessable public id | New rate-limit dependency, new column, login form changes | High | **Rejected** — costs more than the leak is worth |

Option C is rejected on arithmetic: there is no rate-limiting infrastructure in the tree at all, and `slug` is what users log in with, so making it unguessable means adding a second identifier and changing the login form. Both are bigger changes than the leak.

**Recommendation: A**, unless the team decides the three numbers are not worth maintaining any unauthenticated endpoint for, in which case **B** is cleaner still. Section 5 gives A; section 6 gives B.

## 5. Option A — remove the parameter (recommended)

### 5.1 `apps/api/app/config.py`

`Settings` currently has no workspace field at all (`config.py` is 14 lines). Add one:

```python
public_workspace_slug: str = ""
```

Default empty rather than required, on purpose: a required field makes `Settings()` raise at import, which would fail every API test for anyone who hasn't updated their local `.env`. An empty value degrades to a brand panel showing "—", which is cosmetic, not unsafe. Production must set it — that belongs in the prod env file, next to the other Phase 0 secrets work.

### 5.2 `apps/api/app/public/routes.py`

```python
from ..config import settings

@router.get("/stats", response_model=WorkspaceStatsOut)
def workspace_stats(db: Session = Depends(get_db)) -> WorkspaceStatsOut:
    """Aggregate counts for the configured workspace — login page brand panel.

    No authentication required, and no workspace parameter either: the tenant
    comes from server config, so a caller cannot ask for another one.
    """
    slug = settings.public_workspace_slug
    if not slug:
        return WorkspaceStatsOut(projects_live=0, parts_tracked=0, suppliers=0)
    row = db.execute(
        text(...),                     # unchanged SQL
        {"slug": slug},
    ).mappings().first()
    ...
```

The query body does not change — only where `slug` comes from.

### 5.3 `apps/web/app/(public)/login/page.tsx`

```tsx
fetch("/api/public/stats", { cache: "no-store" })
```

Keep `WORKSPACE_SLUG` — the login form still needs it for `POST /api/auth/login` (`login/page.tsx:62`). Only the stats call drops it.

### 5.4 Why old clients don't break

FastAPI ignores query parameters that aren't in the signature. A cached browser still sending `?workspace_slug=other` gets `200` with the configured tenant's counts — not a `422`. Worth asserting in a test so nobody "helpfully" re-adds the parameter later.

### 5.5 Tests — `apps/api/tests/test_public_stats.py`

The existing file **pins the leak as a feature**. Line 73:

```python
assert _stats(other_slug).json() == {"projects_live": 1, "parts_tracked": 7, "suppliers": 1}
```

That assertion is "a second workspace's counts are readable". It has to go — and its removal is the clearest statement of what this change is for.

Rewrite:

```python
def _stats(slug: str | None = None):
    params = {} if slug is None else {"workspace_slug": slug}
    return TestClient(app).get("/public/stats", params=params)


def test_counts_only_the_configured_workspace(monkeypatch):
    slug, wid = _workspace()
    other_slug, other = _workspace()
    monkeypatch.setattr(settings, "public_workspace_slug", slug)
    _item_with_parts(wid, 3)
    _item_with_parts(wid, 5, deleted=True)   # soft-deleted parts not tracked
    _item_with_parts(other, 7)               # another workspace never counted
    _supplier(wid, "board_materials", "Plyco")
    _supplier(wid, "hardware_materials", "Plyco")    # same name counts once
    _supplier(wid, "hardware_materials", "Hettich")
    _supplier(other, "board_materials", "Elsewhere")

    r = _stats()                     # no cookie, no slug
    assert r.status_code == 200, r.text
    assert r.json() == {"projects_live": 2, "parts_tracked": 3, "suppliers": 2}


def test_a_client_supplied_slug_is_ignored(monkeypatch):
    slug, wid = _workspace()
    other_slug, other = _workspace()
    monkeypatch.setattr(settings, "public_workspace_slug", slug)
    _item_with_parts(wid, 3)
    _item_with_parts(other, 7)

    assert _stats(other_slug).json()["parts_tracked"] == 3   # not 7


def test_unset_config_answers_zeros(monkeypatch):
    monkeypatch.setattr(settings, "public_workspace_slug", "")
    assert _stats().json() == {"projects_live": 0, "parts_tracked": 0, "suppliers": 0}
```

`test_an_unknown_slug_answers_zeros_and_a_missing_slug_is_422` (line 76) is deleted: both halves describe behaviour that no longer exists. The `422` half in particular — with no required parameter there is nothing to omit.

### 5.6 e2e — nothing breaks

`tests/e2e/screenshot-login.spec.ts` asserts only that "Welcome back" is visible and writes screenshots; it does not compare them. And the fetch already swallows failure (`.catch(() => null)`, `login/page.tsx:49`), so the panel degrades to "—". No spec asserts on the three numbers.

## 6. Option B — delete the endpoint

If the three numbers aren't worth an unauthenticated endpoint:

1. Delete `apps/api/app/public/` and its two `include_router` lines (`main.py:12`, `main.py:58`)
2. Delete the `useEffect` fetch and `stats` state (`login/page.tsx:43-50`), and the three-number block (`login/page.tsx:120-142`) — replace with static copy or nothing
3. Delete `apps/api/tests/test_public_stats.py`
4. Update `docs/software-spec/SOFTWARE-SPEC.md:219` and `:1290`, which both describe the endpoint

Saves a public surface and one SQL query per login-page view. **Costs** the brand panel its live numbers — a product decision, not an engineering one.

## 7. If D1 lands on shared-hosting SaaS

Option A assumes one deployment serves one tenant. If instead several customers share one deployment, the login page has to know which tenant it is *before* anyone logs in, which means resolving the tenant from the `Host` header (subdomain per tenant) rather than from config.

The good news: **the route shape is the same** — the tenant comes from request context instead of a client parameter. The work is the resolver plus a middleware, and it is the same resolver the rest of multi-tenant onboarding needs.

This is deliberately not specified here, because it is blocked on **D1 (self-hosted vs cloud)**. Specifying it before D1 is decided means specifying it twice.

## 8. What this does not fix

- **No rate limiting.** The endpoint stays unauthenticated. It is one indexed-count query per call, so the risk is low, but if it ever matters, put a short cache in front of it at the CDN/ingress rather than adding a dependency to the API.
- **Nothing about logged-in users.** Cross-tenant access by an authenticated user is workspace isolation, which is already centralised and already probed. Different problem, already handled.

## 9. Acceptance

| # | Test | Expected |
| --- | --- | --- |
| 1 | `test_counts_only_the_configured_workspace` | Only the configured workspace's rows, soft-deleted parts excluded, a supplier name counted once |
| 2 | `test_a_client_supplied_slug_is_owned_by_no_one` | `?workspace_slug=<other>` still returns the configured workspace's counts |
| 3 | `test_unset_config_answers_zeros` | Empty config → all zeros, no 500 |
| 4 | Fresh client, no cookie | `200` — the login page still works unauthenticated |
| 5 | Panel renders | Numbers appear in prod; "—" when config is unset |
| 6 | The old assertion at `test_public_stats.py:73` | Gone |

Acceptance is **not** "nobody can read another tenant's counts" in the abstract — it is test 2, which is falsifiable: pass another tenant's slug and assert you still get your own numbers.
