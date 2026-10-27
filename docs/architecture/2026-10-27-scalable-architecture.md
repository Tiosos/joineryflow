# JoineryFlow Scalable Architecture Design and Long-Term Roadmap

> **Status: draft proposal (not approved).** This is the output of an external architecture review and is **not a rule**. Until the team accepts it, it changes nothing binding in `CLAUDE.md` (the rulebook) or in Plan V1. Items that are accepted should land separately as ADRs, in `CLAUDE.md`, or in Plan V1 — not live here indefinitely.
>
> **Subject**: `Tiosos/joineryflow` (Python/FastAPI + Next.js 16, a joinery production system replacing FileMaker)
> **Basis**: hands-on inspection of `apps/api`, `apps/web`, `db/alembic`, and `tests/` (2026-10-27, HEAD = `main`, migration head `0089_variation_fields`), plus `CLAUDE.md`, `docs/REVIEW-2026-10.md`, and Plan V1
> **Purpose**: architectural judgement and an executable route for "what next" — not a generic best-practice list
>
> **Relationship to existing documents**
> - With `CLAUDE.md`: this document only describes the current shape and makes suggestions; it adds no hard rules. Where this document and `CLAUDE.md` conflict, **`CLAUDE.md` wins**, and the conflict should be escalated (RULE ZERO).
> - With Plan V1 (`docs/plan-v1/`): Plan V1 is the **customer target spec and roadmap**; this document is an **evolvability assessment of the code tree**. Different perspectives, not substitutes. `ALIGNMENT.md` §3 still has to be read before building anything.
> - With `docs/REVIEW-2026-10.md`: that one is a defect list (handled item by item); this one covers structural / long-term issues. The two do not overlap.

---

## 0. Conclusions first: six points

| # | Point | In one sentence |
| --- | --- | --- |
| **1** | **Do not split into microservices. Build a modular monolith that is divisible, then don't divide it** | ~107 tables are tightly coupled and `items` is the de facto god table, so splitting services hits cross-service joins and distributed transactions immediately; meanwhile the 1,690 tests that run against a real database are the monolith's most valuable asset, and splitting halves their value |
| **2** | **The real risk is not performance — it is the missing production path** | Measured: 1,000-item list 137 ms, 5,000 items 715 ms — nowhere near a bottleneck. But both Dockerfiles are dev images (dev dependencies, not multi-stage, running as root), and there is **no deploy pipeline, no monitoring, no backup** |
| **3** | **The most brittle coupling is using SQL strings as interfaces** | `row_types` is depended on at 47 call sites; `open_orders_sql` and `FROM_VISIBLE` are imported across modules and then concatenated. Neither the type checker nor the compiler can police this — only tests can. This is what has to be eliminated before anything is split |
| **4** | **There is no Application layer; business rules are stuck to the HTTP layer** | `routes.py` totals 9,580 lines and every `commit()` lives in a route. Rules therefore cannot be reused by workers / CLI / background jobs, and every new non-HTTP entry point means rewriting the business logic again |
| **5** | **Promote the outbox from "search-only" to a system-level integration pattern** | Search already does it right (DB trigger writes outbox + separate worker + `FOR UPDATE SKIP LOCKED`). It is the only real decoupling example in the tree and should be extended to PDF generation, CV import, and E3 data migration |
| **6** | **Turn rules from "documentation" into "CI gates"** | `CLAUDE.md` has 323 rules enforced by self-discipline, while AI pair-programming contributed 43% of commits (226 commits / 25 days). The pace will only increase, so guardrails only matter once they are automated |

> **Addition (multi-tenant SaaS is the confirmed target)**: multi-tenancy does **not** change point 1 above — more tenants does not mean more services. It does add one **must-complete-before-launch** P0 item: the Meilisearch master key and the unauthenticated `/public/stats` are tolerable with a single customer but become cross-tenant information leaks once there are several (see §decision 5.2; the file store was verified as already sharded by workspace with ownership checks on every download path, so it is not on that list).

---

## 1. Current state assessment

### 1.1 Objective scale

| Dimension | Measured |
| --- | --- |
| Backend | `apps/api/app`: 44 module directories, 40,056 lines of Python; `routes.py` 9,580 lines, `queries.py` 13,829 lines, `schemas.py` 4,486 lines |
| Database | 89 Alembic migrations (`0001`→`0089`), roughly **107 tables + 5 views**, all bare DDL |
| Frontend | `apps/web`: 300 TS/TSX files, 38,590 lines, 28 `page.tsx`; `useState` 896 occurrences, `useEffect` 262 |
| Tests | 157 `test_*.py`, **1,690 test functions**, all against real Postgres with real migrations; `tests/e2e/` has **76 `*.spec.ts`** (measured with `ls`; ⚠️ `CLAUDE.md:125` says 66, see §7) |
| Delivery | 2 Dockerfiles (both dev-grade), 1 `docker-compose.yml` (dev-grade), 2 GitHub workflows (**0 deploys**) |
| Team | 3 contributors (117 / 97 / 12), of which Claude is 43% |

### 1.2 Current layering: two and a half layers

```
HTTP routes.py  ──►  queries.py  ──►  Postgres (text() bare SQL)
     │                    │
     │ business rules     │ cross-module sharing of SQL string fragments
     │ + commit           │
     └────────────────────┴──── no Application / Domain layer in between
```

- **Zero** `service.py` / `repo.py` / `models.py` / `router.py`; the convention is `routes.py + queries.py + schemas.py`
- **No ORM entity layer**: `relationship` / `joinedload` / `declarative_base` — zero hits. `app/db.py` has only `create_engine` + `sessionmaker`
- Transaction boundaries live in routes: 29 `commit()` calls in `estimating/routes.py`, 14 in `items/routes.py`; helper layers flush but do not commit (explicit comment at `auth/audit.py:6-8`)

### 1.3 What is already right — do not touch it

These are genuine assets and are the easiest things to break during refactoring:

1. **Search outbox** (`0033_search_outbox`): a PL/pgSQL trigger writes `search_outbox`; business code is completely untouched (zero hits for `INSERT INTO search_outbox` inside `app`); the worker claims batches with `FOR UPDATE SKIP LOCKED` and deletes rows only after the Meili task actually succeeds. **This is the only real decoupling example in the whole project.**
2. **Workspace isolation + the automatic probe**: `workspace_scope.py` centrally provides `project_in_workspace` / `user_in_workspace` / `vendor_in_workspace`; `test_workspace_isolation_probe.py` walks the paths of `app.openapi()`, so **new routes are covered automatically and 5xx counts as a failure**. This is the real foundation for multi-customer SaaS.
3. **RBAC is genuinely centralised**: a `require_permission()` factory plus a DB-driven engine, using a separate short transaction so it cannot be caught by a business rollback (`rbac.py:20-28`).
4. **The file store has a Protocol abstraction**: `files/store.py:16-21`, with a comment stating an S3 implementation can replace it without touching routes.
5. **Test density**: 1,690 tests, real database and real migrations, xdist with a separate database per worker, downgrades tested too. Far above comparable projects, and the safety net for every refactor here.
6. **No N+1 in performance**: statement count is identical at 14 items and at 1,000 items.

### 1.4 Five structural risks (in priority order)

| Level | Risk | Evidence | Consequence |
| --- | --- | --- | --- |
| **P0** | Productionisation gap | Dockerfiles install dev dependencies, no multi-stage, running as root; `docker-compose.yml` is a dev file (`--reload`, source mounts) and its `db` service sets `fsync=off` (commented as a warning, but reusing the same compose file hits it); 0 deploy workflows; grep for `sentry\|prometheus\|grafana\|/metrics` — zero hits; grep for `pg_dump\|wal-g` — zero hits | Incident on day one; no evidence when it happens; no way back for the data |
| **P1** | SQL strings used as interfaces | `row_types.py` imported by 24 modules, 47 call sites; `notifications/queries.py:12` imports `tasks.queries.FROM_VISIBLE` and then f-string-concatenates it; `home/queries.py:24-27` assembles SQL fragments from 6 modules in one file | Renaming one column silently breaks other places; **this is the first thing to break when splitting services** |
| **P1** | An import cycle already exists | `orders/queries.py:31` ←→ `catalog/routes.py:26`; the graph confirms `catalog ↔ orders` is a cycle, worked around at `orders/queries.py:212` with a deferred import inside a function | The boundary is already broken; modules cannot be physically isolated |
| **P2** | No Application layer | Business rules and `commit()` live in routes; `get_db` only `close()`s and never calls `rollback()` explicitly, relying on implicit rollback when the connection closes | Rules cannot be reused by workers/CLI; transactional semantics on the error path are implicit |
| **P2** | No frontend data layer; contracts are hand-written | 21 hand-written `*-types.ts` (3,084 lines), no OpenAPI generation; `apiCall` in `lib/api.ts` hard-codes `cache:"no-store"`, plus 3 duplicated fetch wrappers; contract correctness rests on tsc + 76 e2e specs | Backend field change → silent frontend error; no dedup for repeated fetches |

---

## 2. Target architecture: bounded contexts, divisible but not divided

### 2.1 Target layering

```
┌─ Interface layer ─────────────────────────────────────────┐
│  routes.py  — auth, parameter validation, call use case,   │
│               map response. Nothing else.                  │
└───────────────────────┬────────────────────────────────────┘
┌─ Application layer (new — the project's biggest gap) ──────┐
│  use cases: business rules, transaction boundaries,         │
│  orchestration, emitting domain events                     │
└───────────────────────┬────────────────────────────────────┘
┌─ Domain / data access ─────────────────────────────────────┐
│  queries.py (existing asset, kept) + explicit data-service  │
│  interfaces                                                │
└───────────────────────┬────────────────────────────────────┘
┌─ Infrastructure ───────────────────────────────────────────┐
│  Postgres / Meili / FileStore / outbox worker               │
└────────────────────────────────────────────────────────────┘
```

**Key trade-off**: do not introduce an ORM. The current `text()` bare SQL is a proven performance advantage for this team (no N+1, DB time ≤ 37 ms). What is missing is **structure**, not **abstraction**.

### 2.2 Context map (proposed boundaries)

| Context | Existing modules | Type | Evolution strategy |
| --- | --- | --- | --- |
| **Item & Production** (core domain) | `items` `parts` `cutlists` `related_parts` `hardware_lines` | Core | Stays in the main database; never extracted |
| **Project & Tracking** (core domain) | `projects` `areas` `order_tabs` `project_*` | Core | Same as above |
| **Estimating / Tender** | `estimating`, `catalog` (partly) | Core | Extract the Application layer first; do not split yet |
| **Procurement** | `orders` `purchase_orders` `procurement_v1` `suppliers` | Supporting | The cycle with `catalog` must be broken |
| **Shop Floor / Cut Floor** | `shop_floor` `cut_floor` `qc` | Supporting | Floor kiosk; most likely to need offline / separate deployment later |
| **Catalog** | `catalog` `cv` `importers` | Supporting | The nine tables are deliberately not unified (existing invariant — respect it) |
| **Search** | `search` + worker | Generic | **Already a separate process**; the template for splitting |
| **Files / Printing** | `files` `printing` `shop_drawings` | Generic | CPU-heavy (PDF 3.3 s / 300 lines) — **the best first candidate to extract** |

### 2.3 Dependency rules (must be checkable in CI, not just written down)

1. Contexts may communicate **only** through explicit interfaces; importing internal symbols from another context's `queries.py` is forbidden
2. Importing any module's private `_q_*` files is forbidden
3. The generic layer (`db` `auth` `files` `search`) must not depend back on business contexts
4. **Freeze first, then converge**: use import-linter to fix "the current state" as the baseline contract, forbid new violations, and retire the existing ones one at a time

---

## 3. Six key decisions for extensibility

### Decision 1: keep a single process, but keep it ready to split

**Rationale**: peak load is far below the measured 5,000 items / 715 ms (single-workspace baseline). None of the costs of a distributed system (network failure, idempotency, eventual consistency, distributed tracing) buy anything right now.

**Note**: multi-tenant SaaS is the confirmed target, but **more tenants ≠ more services**. Multi-tenancy is a data and isolation problem, solved by decision 5; whether to split services is a deployment and team problem. **Do not go and split microservices just because you are building SaaS** — at a joinery company's volumes, a shared process plus strong tenant isolation is the optimal answer.

**Prepare the preconditions for splitting first** (these are worth having anyway):
- All cross-context calls go through explicit interfaces, not SQL strings
- Transaction boundaries for all writes converge in the Application layer
- All cross-context side effects go through an outbox, not synchronous calls

### Decision 2: extract an Application layer and rescue the business rules from HTTP

Pilot in order of **rate of change**, not size: `estimating` (4,591 lines, already has a facade) → `orders` → `items`.

Acceptance criteria for each step:
- No `db.commit()` remains in routes
- The new use-case functions can be called from tests **without starting HTTP**
- All 1,690 tests are green (a hard gate)

### Decision 3: kill the SQL-string coupling with data-service interfaces

Turn the SQL fragments that are imported across modules — `row_types.joinery_items_only()`, `orders.queries.open_orders_sql`, `tasks.queries.FROM_VISIBLE` — into **explicit functions owned by the owning context** (e.g. `items.read.visible_items(...)`, `orders.read.open_orders(...)`). Callers receive **data**, not **concatenable SQL text**.

- Benefit: renaming a column changes from "silently breaking 47 call sites" to "an import-time / type-check error"
- Cost: moderate. Pilot on `orders ↔ catalog`, the one pair already confirmed to be in a cycle

### Decision 4: promote the outbox to a system-level integration pattern

The `search_outbox` pattern (trigger → outbox table → separate worker → `SKIP LOCKED`) is proven. Extend it to:

| Scenario | Now | After |
| --- | --- | --- |
| Quote PDF | 300 lines 3.3 s, 800 lines 12 s, synchronous and blocking (caching exists via `0062`) | Asynchronous generation + notification, cache as fallback |
| CV import | 3-stage wizard, synchronous | Background job + progress query |
| E3 data migration | CLI, dry run via rollback | Reuse the same job table |
| Notifications | The single write point is a hard-coded INSERT at `comments/queries.py:328` | Domain event → outbox → notification service |

Note: the search outbox is **identity-based** (stores only ids; the worker looks them up). A general job outbox needs to be **payload-based** (stores the full payload). Do not put both in one table.

### Decision 5: multi-tenancy — the target is SaaS; after verification only two cross-tenant leaks remain

> **Correction record (2026-10-27)**: the first version of this document listed "single-root file store" as leak #2. **That judgement was wrong.** Verified against the code: the layout is already sharded by workspace (`app/files/store.py` docstring: `<root>/<workspace_slug>/<sha256[0:2]>/<sha256>`), and all three download paths **do** check ownership — `files/routes.py:153`, `files/uploads.py:94`, `orders/attachments.py:83`. Downgraded from "fix this" to "add a test to hold it in place". Lesson: every other assertion here must be checked against the code before being cited.

**Multi-customer SaaS is the confirmed target.** The good news is that `workspace` is already the de facto tenant, and the data-plane foundation is stronger than in most projects: `workspace_scope.py` centrally provides `project_in_workspace` / `user_in_workspace` / `vendor_in_workspace` (cross-tenant is always a 404), and `test_workspace_isolation_probe.py` walks the paths of `app.openapi()` — **new routes are covered automatically and 5xx counts as a failure**. This is the most mature engineering asset in the project; do not start over.

#### 5.1 Isolation model: keep shared schema + `workspace_id`

| Option | Assessment |
| --- | --- |
| **shared schema + `workspace_id`** (current) | ✅ Adopt. The 89 migrations apply atomically to all tenants; per-customer data volume is small; the central helper and the automatic probe already exist |
| schema-per-tenant | ❌ Very expensive to adopt now: ~107 tables have DDL only and **no ORM metadata**, and every migration would have to iterate all schemas |
| database-per-tenant | ❌ Same as above, plus connection management complexity |

**Move to separate databases only on a clear signal**: a large customer's contract demands physical isolation, one tenant's data volume makes maintenance windows unacceptable, or tenant-level PITR is required. Keeping that door open takes only two things: never hard-code schema names in SQL, and keep `workspace_id` present on every tenant table (both are already true).

#### 5.2 Verified cross-tenant risks (P0, in parallel with Phase 0 productionisation)

| # | Risk | Evidence | Assessment |
| --- | --- | --- | --- |
| **1** | **Meilisearch uses the master key** | `.env.example:21-24`, comment verbatim: "The master key is also used as the api's key in dev; **scoped keys are out of scope for v1**" | **Needs fixing.** The application layer already has two filters — `app/search/index.py:96 build_filter` builds from `me.workspace_id` (its comment says "The workspace clause is unconditional"), and `readable_types` in `app/search/routes.py` then filters types by module `read` permission. But **the engine side enforces nothing**: the master key can read the whole index, so any path that bypasses `build_filter` is a total leak. Move to **tenant tokens** so the `workspace_id` filter is enforced by the engine, downgrading "forgot the filter" from "leak" to "no data returned" |
| **2** | **`GET /public/stats?workspace_slug=` is unauthenticated** | `app/public/routes.py:19`, comment verbatim: "No authentication required"; `docs/REVIEW-2026-10.md` A4 accepted this risk | **Needs fixing, but severity is moderate.** What leaks is **three counts** (projects, parts, suppliers), not customer data itself. Acceptable with one customer; with several, anyone can enumerate other customers' counts, and can distinguish "a workspace with data" from "a slug that does not exist". Options: add a random suffix to the slug + rate limiting, or remove the endpoint before multi-customer launch |
| ~~3~~ | ~~Single-root file store~~ | ~~`FILE_STORE_ROOT=/uploads`~~ | **Not a real issue after verification; no change needed.** The layout is already sharded by workspace, and all three download paths check `workspace_id` (`files/routes.py:153`, `files/uploads.py:94`, `orders/attachments.py:83`). Only add a test to hold the current behaviour so a future download route cannot forget the check |

#### 5.3 Defence in depth (evaluate in Phase 2 — not now)

Postgres **RLS** can act as a second line behind the application-layer filtering: `SET LOCAL app.workspace_id` on connect, with policies of `workspace_id = current_setting('app.workspace_id')`.

- Benefit: downgrades "forgot the workspace filter" from data leak to query error
- Cost: a policy is needed on every tenant table; today there is a single connection pool with a single role, which has to change
- **Recommendation**: run a feasibility trial on one module before deciding whether to roll it out everywhere. The main line of defence stays `workspace_scope` + the automatic probe

#### 5.4 Gap list

- [ ] Workspace self-service provisioning and onboarding (today it is `make seed`; `CLAUDE.md:137`; `seed_system_groups()` must be automated inside the provisioning flow, see `CLAUDE.md:171`)
- [ ] Subscription / quota / billing model
- [ ] **Tenant-level backup and restore** (the whole repo has no `pg_dump` and no PITR; under shared schema the minimum is "export by workspace + restore by workspace")
- [ ] Tenant-level data export (customers taking their data with them) and deletion (contract termination / compliance)
- [ ] Tenant-level configuration isolation (`workspace.at_risk_days` was introduced by `0085`; extend along that pattern)

> **Existing scaffolding**: the E3 importer already does "load one workspace's data in" (`python -m app.importers.tracking_grid FILE.xlsx … --workspace-slug`, with dry-run rollback semantics). Tenant onboarding imports can reuse it directly instead of being written from scratch.

### Decision 6: two high-return frontend items

1. **OpenAPI → TS type generation**: the 21 hand-written `*-types.ts` (3,084 lines) can be generated, turning contract drift from "relying on tsc and luck" into "a CI failure". The backend already exposes `app.openapi()` (the probe test uses it), so the foundation exists.
2. **A unified data-fetching layer**: 262 bare `useEffect` calls and 3 duplicated fetch wrappers → one hook layer with dedup, invalidation, and error conventions. No need to bring in TanStack Query (the current constraint explicitly rules it out); a thin in-house layer is fine, but **converge on `lib/api.ts` first**.

---

## 4. Long-term roadmap

### Phase 0 — Productionisation (2–4 weeks, highest priority)

| Item | Action | Acceptance |
| --- | --- | --- |
| Production images | Dockerfiles become multi-stage, non-root, prod dependencies only; `next build` + `next start` / uvicorn workers | Image contains no dev dependencies; process is not root |
| Configuration split | `docker-compose.yml` (dev) and `docker-compose.prod.yml` fully separated, **`fsync=off` and friends removed** | No dev-only dangerous flag appears in any prod config |
| Deploy pipeline | New deploy workflow (build → push image → migrate → health check → rollback) | One-click rollback |
| Backup | PITR (WAL archiving) + periodic `pg_dump`, **and a restore drill** | The restore drill succeeds once (an untested backup is not a backup) |
| Observability | Structured logging + error reporting + `/metrics` + key alerts | An incident can be located within 5 minutes |
| **Two multi-tenant security items** | Meili moves to tenant tokens; `/public/stats` hardened or removed; plus a test locking in the workspace check on file downloads | Credentials for tenant A cannot reach any of tenant B's data (as an automated test, not a manual check) |

**Until this step is done, none of the later architecture work has anything to stand on.** (The two multi-tenant items are "must be done before SaaS launch", not "can be done later" — see §decision 5.2. Item-by-item changes are in the companion checklist `2026-10-27-phase0-checklist.md`.)

### Phase 1 — Boundaries and contracts (1–2 months)

- Ship OpenAPI → TS type generation and delete the hand-written types
- Land import-linter and freeze the current dependency graph as the baseline contract
- **Break the `catalog ↔ orders` cycle** (the only confirmed import cycle)
- Eliminate cross-module SQL string sharing: pilot on `orders↔catalog`, then extend to `row_types` / `FROM_VISIBLE` / `open_orders_sql`
- Converge frontend fetch wrappers onto `lib/api.ts`
- **Workspace self-service provisioning + onboarding** (replacing the manual `make seed` flow, with `seed_system_groups()` automated) plus subscription / quota tables and migrations

### Phase 2 — Extract the Application layer (2–4 months)

- Extract use cases in the order `estimating` → `orders` → `items`
- Move every `commit()` out of routes; introduce an explicit unit of work
- `get_db` calls `rollback()` explicitly; drop the "implicit rollback when the connection closes" behaviour
- Background PDF / CV import / E3 migration (general job outbox)
- Move notifications to domain-event driven
- **Tenant-level data export / deletion** (contract termination and compliance), reusing the E3 importer's import scaffolding for the reverse capability
- RLS feasibility trial (one module; decide on full rollout after the trial, see §decision 5.3)

### Phase 3 — Selective extraction (trigger-driven, 6–12 months)

**Extract only on a clear signal**, not on a timetable:

| Trigger | Extract what | Why it is the safest |
| --- | --- | --- |
| PDF / optimisation compute becomes a CPU bottleneck | `/optimise` in `printing` and `cut_floor` | Naturally stateless, pure functions, no shared writes |
| Search throughput becomes a bottleneck, or search needs to scale independently | `search` + worker | Already a separate process; the pattern exists (**note**: a second customer is by itself **not** a trigger for extraction — see §decision 5.1) |
| The Shop Floor kiosk needs on-site offline capability | `shop_floor` `qc` | Read/write set overlaps little with the main flow |
| Team growth requires independent releases | See the context boundaries in §2.2 | Boundaries already converged in Phase 1 |

**Prerequisite before any extraction**: add SQLAlchemy Core `Table` metadata (today ~107 tables have DDL only, no model metadata). Without metadata, "split the database by module" cannot even start.

---

## 5. Engineering governance: make the guardrails automatic

The project moves very fast (226 commits / 25 days, 43% with AI pair-programming). The 323 rules in `CLAUDE.md` are currently enforced by self-discipline — that is not sustainable at this pace with AI in the loop. Convert the rules into CI gates one by one:

| Existing rule (documentation) | Convert to (CI) |
| --- | --- |
| "workspace isolation everywhere" | Already ✅ automatic probe (exemplary — keep it) |
| "dynamic SQL columns must go through an allow-list" | Already ✅ `test_sql_set_columns.py` |
| "PATCH must use `no_null`" | Possible: scan every PATCH schema field against column NOT NULL |
| "reading items must include `not_deleted`" | Already ✅ `test_items_deleted_filter.py` |
| **Module dependency rules** | **Missing ❌** — introduce import-linter |
| **Contract drift** | **Missing ❌** — OpenAPI → TS generation + diff check |
| **Migration safety** | Partial: downgrade tests exist; add a "no destructive DDL" check (Q435 requires data preservation) |

**ADR recommendation**: record key decisions under `docs/adr/` (why not microservices, why no ORM, outbox choice) so the same debate is not re-run every quarter.

---

## 6. Risk register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 89 migrations / ~107 tables with no ORM metadata | Blocks every future database split | Add Core `Table` definitions within Phase 2 (read-only use is enough) |
| `items` is hard-depended on by 10 modules; lock semantics are duplicated in 7 | Large blast radius for changes | Converge lock checks into a single entry point; the rest call it through an interface |
| 43% AI-authored commits + rules enforced by self-discipline | Architecture decays faster than human review | CI-ifying the guardrails (§5) is the top-priority governance item |
| Single Postgres + single Meili, no HA | Single point of failure; after multi-tenancy it affects every tenant | Phase 0 must at least deliver PITR and a rehearsed restore |
| **Meili master key + unauthenticated `/public/stats`** | Cross-tenant information leak once multiple customers are live | §decision 5.2 — fix in parallel with Phase 0 |
| Coarse tenant-level restore granularity under shared schema | One tenant's accidental deletion forces a whole-database rollback | Build "export/restore by workspace" first (the E3 importer can be reused); do not split databases early just for this |
| e2e runs in 2 shards and is a required check on `main` | A spec that depends on data left by another spec fails under sharding | `CLAUDE.md:152-153` already mandates "create your own data, do not leave it behind"; follow it. This document no longer lists it as a risk |

---

## Appendix: key evidence behind these judgements

| Conclusion | Evidence location |
| --- | --- |
| Two and a half layers, no service layer | `apps/api/app/**/routes.py` — 9,580 lines including `commit()`; `find -name "service*.py"` → 0 |
| No ORM | `app/db.py:5-6`; `relationship\|joinedload\|declarative_base` — zero hits |
| Import cycle | `apps/api/app/orders/queries.py:31` ↔ `apps/api/app/catalog/routes.py:26` |
| SQL strings as interfaces | `app/row_types.py` (imported by 24 modules / 47 call sites); `app/notifications/queries.py:12`; `app/home/queries.py:24-27` |
| Outbox example | `db/alembic/versions/0033_search_outbox.py:86-127`; `app/search/worker.py:44-49` |
| Transaction boundaries in routes | `app/auth/audit.py:6-8` comment; 29 `commit()` calls in `estimating/routes.py` |
| Dev-grade Dockerfiles | `apps/web/Dockerfile` (`pnpm install \|\| true`, no build), `apps/api/Dockerfile` (`pip install -e ".[dev]"`) |
| No operational assets | `sentry\|prometheus\|grafana\|/metrics\|pg_dump\|wal-g` — zero hits repo-wide; `.github/workflows` has 2 files and no deploy |
| Performance baseline | `docs/REVIEW-2026-10.md` §C (1,000 items → 137 ms / 1.5 MB; 5,000 items → 715 ms; PDF 300 lines → 3.3 s) |

---

## 7. Open questions (RULE ZERO: no unilateral decisions)

1. **Number of specs in `tests/e2e/`**: `ls tests/e2e/*.spec.ts` gives **76**, while `CLAUDE.md:125` says **66**. At least one is wrong; confirm and reconcile. (`CLAUDE.md` §1 notes for pytest file counts that "counts drift, so none are recorded here" — please decide whether the e2e line should drop the concrete number too.)
2. **The target shape of production deployment is undecided**: Phase 0 here assumes "containers + one pipeline", but the project does not state whether it is self-hosted (on the customer's premises) or cloud-hosted. This directly determines backup (PITR vs managed snapshots) and the observability choice, so **it needs confirming first**.
3. ~~Whether to move to multi-customer SaaS~~ — **confirmed: the target is SaaS.** §decision 5 is written accordingly (isolation model, verified leaks, gap list). New questions that follow from it:
   - When is the first non-Hartwood customer expected to go live? This decides whether Phase 0's "two multi-tenant security items" happen now or can be scheduled later — **if a second customer is coming within 3 months, it is the first item in P0**.
   - Billing model: per seat, per project count, or a flat price per workspace? This determines how the quota tables are designed.
   - Data residency: must customer data stay in a specific region (for example, only within Australia)? This determines the hosting choice and compounds with open question 2 above (production deployment shape).
