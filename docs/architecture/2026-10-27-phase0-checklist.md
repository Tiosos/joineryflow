# Phase 0 — Productionisation Checklist

> Status: **ready to execute**. Companion document: `docs/architecture/2026-10-27-scalable-architecture.md` (PR #172).
> Goal: give the system a production path that can carry all later architecture work. **Until this step is done, Phases 1–3 have nothing to land on.**
> Scope: 2–4 weeks (excluding the wait for the decisions in section 0)

---

## 0. Prerequisite decisions (these block 4 items below — please answer first)

| # | Question | Why it blocks |
| --- | --- | --- |
| D1 | **Self-hosted (customer premises / own servers) or cloud-hosted?** | Determines the backup approach (self-managed WAL archiving vs managed snapshots), the image registry location, and how secrets are injected |
| D2 | Production domain and where TLS terminates (reverse proxy, or is Next exposed directly?) | Determines `COOKIE_SECURE`, `API_URL`, and whether the web tier needs its own TLS |
| D3 | Who runs migrations: the pipeline automatically, or a human after review? | Determines the shape of the pipeline in §4 (automatic migration vs approval gate) |
| D4 | Expected go-live date for the second customer | Determines whether the multi-tenant items in §7 are "do now" or "schedule at the end of this phase" |

> Until D1/D2 are settled, §1–§3 and §6 can start (they are independent of deployment shape); §4 and §5 have to wait.

---

## 1. Production images

### 1.1 `apps/api/Dockerfile`

**Current state** (`apps/api/Dockerfile`, all 7 lines): installs `.[dev]` (including pytest / pytest-xdist), `COPY . .` bakes tests together with source, no `USER` (runs as root), no `CMD`.

**Change**:

```dockerfile
# ---- build ----
FROM python:3.12-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY apps/api/pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"    # dev deps only needed to build/verify here
RUN pip uninstall -y pytest pytest-xdist pytest-asyncio

# ---- runtime ----
FROM python:3.12-slim AS runtime
# WeasyPrint's PDF rendering needs these (the current Dockerfile already installs them — keep every one)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-liberation \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /code
COPY apps/api /code
COPY db /db
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live').status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**Key points**: `uvicorn[standard]` is already in `pyproject.toml`, so **no need to add gunicorn**. Not one of the WeasyPrint system libraries may be dropped, or quote PDFs will fail silently.

**Acceptance**:
- `docker run --rm <img> pip list | grep -c pytest` → **0**
- `docker run --rm <img> id -u` → **10001** (not 0)
- With the container up, `curl /health/live` → 200

### 1.2 `apps/web/Dockerfile`

**Current state** (`apps/web/Dockerfile`, all 7 lines): `RUN pnpm install || true` — **install failures are swallowed**; no `pnpm build`; no `CMD`; runs as root.

**Change**:

```dockerfile
FROM node:20-slim AS build
RUN corepack enable
WORKDIR /code
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile      # drop the || true: if it cannot install, it must fail
COPY apps/web .
RUN pnpm build

FROM node:20-slim AS runtime
RUN corepack enable
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /code/package.json /code/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --prod
COPY --from=build /code/.next ./.next
COPY --from=build /code/public ./public
USER 10001
EXPOSE 3000
CMD ["pnpm", "start"]
```

**Prerequisite for `--frozen-lockfile`**: `apps/web/pnpm-lock.yaml` must exist and be committed. If it is missing, add the lockfile first (otherwise CI and production builds are not reproducible).

**Acceptance**:
- Deliberately break a dependency version in `package.json` → **the build must fail** (today it passes silently)
- `docker run --rm <img> node -e "console.log(process.getuid())"` → **10001**
- The runtime image contains no `devDependencies`

**Optional slimming (verify first)**: `apps/web/next.config.ts` currently has no `output` setting. Adding `output: "standalone"` shrinks the image significantly but changes how static assets and `next start` behave. **Validate on a branch with all e2e specs green before merging**, and keep it separate from the other changes in this batch.

---

## 2. Split the health check

**Current state**: `apps/api/app/main.py` ends with a single `/health` returning `{"ok": true}` and **not touching the database** — if the DB is down it still returns 200, so orchestration has nothing to go on.

**Change**: split into two endpoints with separate meanings.

| Endpoint | Checks | Used for |
| --- | --- | --- |
| `GET /health/live` | Process is alive (keep today's `{"ok": true}`) | Deciding whether to restart the container |
| `GET /health/ready` | `SELECT 1` through `db.get_db()`; Meili optional (`GET /search/health` already exists) | Deciding whether to admit traffic |

**Keep `/health`**: `README.md:40` documents `http://localhost:3000/api/health -> {"ok":true}` and existing e2e specs may depend on it (`tests/e2e/smoke.spec.ts`) — **do not delete it**; make it equivalent to live.

**Acceptance**: stop the db container → `/health/ready` returns non-200 while `/health/live` still returns 200.

---

## 3. Configuration and secrets

**Current state**: `Settings` in `apps/api/app/config.py` has only 8 fields and reads `.env` (`SettingsConfigDict(env_file=".env")`); `docker-compose.yml` mounts the file into containers with `env_file: .env`.

**Change**:

1. In production **do not mount `.env`** — inject everything as environment variables (D1 decides between a secret manager and the orchestrator's secrets)
2. `COOKIE_SECURE=true` (`.env.example:12` already notes it must be true anywhere https is used, otherwise session cookies travel in the clear)
3. `MEILI_API_KEY` distinct from `MEILI_MASTER_KEY` (see §7.1)
4. `API_URL`: in compose it is `http://api:8000`; in production set the real address per D2 (the web tier inlines it at build time, so changing it means rebuilding)

**Acceptance**:
- Inside the production image, `ls .env` → does not exist
- After login, `curl -I` shows `Set-Cookie` with `Secure; HttpOnly; SameSite`

---

## 4. Migration and release order

**Current state**: `make migrate` = `docker compose exec -w /db api alembic upgrade head`. 89 migrations, ~107 tables; `sqlalchemy.url` in `db/alembic.ini` comes from `${DATABASE_URL}`.

**Change** (depends on D3):

```
1. Build and push the new image (do not switch traffic yet)
2. alembic upgrade head        <- separate step; abort on failure
3. Rolling replacement of the web / api containers
4. Poll /health/ready until all return 200
5. On failure -> roll back to the previous image tag; per Q435 ("preserve data"),
   migrations never do a destructive downgrade
```

**Key constraint**: `CLAUDE.md` requires that changes land only behind **data-preserving migrations** (Q435). The release order must therefore be **migrate first, switch traffic second**, and migrations must be forward-compatible for one version (both old and new code can run) — otherwise a rollback hits a schema incompatibility.

**Acceptance**:
- Rehearse once: "migration succeeded + release succeeded"
- Rehearse once: "migration failed → release aborted, traffic still on the old version"

---

## 5. Backup and restore (only counts once rehearsed)

**Current state**: `pg_dump` / `wal-g` / `barman` — **zero hits** repo-wide; the Makefile has no backup / restore target.

**Change**:

| Item | Action |
| --- | --- |
| PITR | Production Postgres with `wal_level=replica` + WAL archiving; a daily base backup |
| Logical backup | Daily `pg_dump -Fc` to **off-site** storage (a different machine from the database) |
| Restore drill | New `scripts/restore-drill.sh`: pull the latest backup → start a temporary instance → restore to a random point in time → run `make test` or `tests/e2e/smoke.spec.ts` → print elapsed time |
| Makefile | Add `backup` and `restore-drill` targets |

**Acceptance (hard)**: **the restore drill succeeds once, and the measured RTO/RPO are written into `docs/`.** An untested backup is not a backup.

**Note**: the `db` service in `docker-compose.yml` sets `fsync=off -c synchronous_commit=off -c full_page_writes=off` (the comment already warns "never with real data"). The production config must be a separate file with those three flags removed — see §8.

---

## 6. Observability (minimum set)

**Current state**: the API has no structured logging at its core (only `app/search/worker.py` and `app/search/reindex.py` do); `sentry` / `prometheus` / `/metrics` — zero hits.

**Do these in order; do not ship the whole suite at once** (consistent with `CLAUDE.md` §2 Simplicity First):

### 6.1 Structured logging (no new dependency, best value for effort)

Add middleware in `app/main.py` emitting one JSON line per request:

```
{"ts","request_id","method","path","status","duration_ms","user_id","workspace_id"}
```

- Also write `request_id` into a response header, so a user reporting a problem can give you an id
- **Never** log request bodies (they contain passwords, uploads, customer data)
- Emit one ERROR line with the `request_id` wherever an exception is handled

### 6.2 Error reporting

Wire up Sentry (or equivalent). **Scrubbing must be configured**: production data includes customer projects, suppliers, and amounts, so stack traces and request context must not carry those fields out.

### 6.3 Metrics

Add `/metrics` (Prometheus format). Two options:

| Option | Assessment |
| --- | --- |
| `prometheus-fastapi-instrumentator` | One dependency gets you HTTP latency / error rate / QPS — **recommended**, avoids the traps of hand-written counters |
| Hand-written middleware + in-memory counters | Zero dependencies, but with `--workers 4` the counters are split across processes and need extra handling |

**Acceptance**:
- Trigger one 500 → the log can be joined to the error report by `request_id`
- p95 latency and the 5xx rate are visible (the only basis for deciding "should Phase 2 optimisation start")

**Do not do yet**: distributed tracing. A monolith plus one worker does not justify it.

---

## 7. Multi-tenant security (must be done before SaaS launch)

> **Correction**: the first version of the companion document listed "single-root file store" as a leak. **That was wrong.** Verified against the code: the layout is already sharded by workspace (`app/files/store.py` docstring: `<root>/<workspace_slug>/<sha256[0:2]>/<sha256>`), and all three download paths **do** check ownership — `files/routes.py:153`, `files/uploads.py:94` (`WHERE file_blob_id = :b AND workspace_id = :w`), `orders/attachments.py:83` (`_order_exists`). This item is downgraded from "fix this" to "add a test to hold it in place".

### 7.1 Meilisearch: replace the master key — **real work**

**Current state**: `.env.example:21-24` — the `MEILI_API_KEY` the API uses *is* the master key, with the comment stating "scoped keys are out of scope for v1".

**Isolation today (clarified)**: the application layer actually has two filters — `app/search/index.py:96 build_filter` builds from `me.workspace_id`, its comment saying "The workspace clause is unconditional", and `readable_types` in `app/search/routes.py` then filters types by module `read` permission. **So the main line of defence does exist.** The problem is that the search engine enforces nothing: the master key can read the whole index, so any call path that bypasses `build_filter` is a total leak.

**Change**: move to Meilisearch **tenant tokens**, pushing the `workspace_id` filter down into the engine so that "forgot the filter" degrades from "leak" to "no data returned".

**Acceptance**: using a token issued for tenant A against Meili directly returns none of tenant B's documents (as an automated test).

### 7.2 `/public/stats` — **real work, but moderate severity**

**Current state**: `app/public/routes.py:19` has no auth; the comment says "No authentication required". Any `workspace_slug` returns three counts (projects, parts, suppliers).

**Clarification**: what leaks is **three numbers**, not customer data itself. Acceptable with one customer; with several, it means anyone can enumerate other customers' project and supplier counts, and can distinguish "a workspace with data" from "a slug that does not exist".

**Change (pick one)**:
- Make the slug unguessable (random suffix) + rate limiting; or
- Remove the endpoint before multi-customer launch and turn the login-page branding panel into static copy

**Acceptance**: requesting with a slug that does not exist or is not yours → no distinguishing information returned.

### 7.3 File download ownership — **add a test to hold current behaviour**

The three paths already check ownership (see the correction above). Add a test asserting that "every route returning a file stream filters by `workspace_id`", so a future download route cannot skip it. The existing probe pattern (`helpers_probe.py` walking `app.openapi()`) can be reused.

---

## 8. Configuration split

Add `docker-compose.prod.yml`, fully separate from dev — **do not reuse the same file**.

| dev (`docker-compose.yml`, keep) | prod (new) |
| --- | --- |
| `postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off` | **all removed** |
| `uvicorn --reload` + `pnpm dev` | `uvicorn --workers 4` + `pnpm start` |
| Source mount `./apps/api:/code` | **no mount**; the code is in the image |
| `ports: ["5432:5432", "8000:8000"]`, everything exposed | Only required ports; the DB is not exposed |
| `env_file: .env` | Environment variables / injected secrets |

**Acceptance**: `grep -c "fsync=off" docker-compose.prod.yml` → **0**.

---

## 9. Deploy pipeline

Add `.github/workflows/deploy.yml` (today `.github/workflows/` has only `ci.yml` and `ci-docs-only.yml`, **no deploy at all**).

**Job-name caution**: the header comment of `ci-docs-only.yml` states that its four job names must match `ci.yml`'s, otherwise docs-only PRs get stuck on required checks. **Do not reuse those four names for deploy jobs**, to avoid conflicting with branch protection rules.

Steps follow the order in §4.

**Acceptance**:
- Rehearse one release
- Rehearse one rollback (**a rollback that has never been rehearsed is not a rollback**)

---

## Suggested execution order

```
Can start in parallel (independent of D1-D4)
  ├─ 1.1 API image
  ├─ 1.2 Web image
  ├─ 2   Health check split
  ├─ 6.1 Structured logging
  └─ 7.3 File download ownership test

Once D1/D2 are settled
  ├─ 3   Configuration and secrets
  ├─ 5   Backup and restore (+ drill)
  ├─ 6.2 Error reporting
  ├─ 6.3 Metrics
  └─ 8   Configuration split

Once D3 is settled
  ├─ 4   Migration and release order
  └─ 9   Deploy pipeline (+ release/rollback drills)

D4 decides whether 7.1 / 7.2 are immediate or scheduled for the end of this phase
```

---

## Acceptance summary (the criteria for "Phase 0 is done")

| # | Criterion | Now |
| --- | --- | --- |
| 1 | Production images contain no dev dependencies and the process is not root | ❌ |
| 2 | A failing `pnpm install` fails the build | ❌ (swallowed by `|| true`) |
| 3 | With the DB down, `/health/ready` returns non-200 | ❌ (`/health` does not query the DB) |
| 4 | Production does not mount `.env` and `COOKIE_SECURE=true` | ❌ |
| 5 | Backups exist **and a restore drill has succeeded once**, with RTO/RPO recorded | ❌ (no backups) |
| 6 | One 500 can be traced end to end by `request_id` | ❌ (no structured logging) |
| 7 | Releases are one-click rollbackable, and rollback has been rehearsed | ❌ (no deploy workflow) |
| 8 | Credentials for tenant A cannot reach tenant B's search results | ❌ (master key) |
| 9 | No dev-only flags such as `fsync=off` in production config | ❌ (only one dev compose file exists) |
