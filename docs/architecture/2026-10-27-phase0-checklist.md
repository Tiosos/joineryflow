# Phase 0 — Productionisation Checklist

> Status: **ready to execute**. Companion document: `docs/architecture/2026-10-27-scalable-architecture.md` (PR #172).
> Goal: give the system a production path that can carry all later architecture work. **Until this step is done, Phases 1–3 have nothing to land on.**
> Scope: 2–4 weeks (excluding the wait for the decisions in section 0)

---

## 0. Prerequisite decisions (these block 4 items below — please answer first)

| # | Question | Why it blocks |
| --- | --- | --- |
| ~~D1~~ | ~~Self-hosted or cloud-hosted?~~ **DECIDED 2026-10-27: customer self-hosted, one deployment per customer.** | Resolved. See §0.1 for what it fixes and what it costs |
| D2 | Production domain and where TLS terminates (reverse proxy, or is Next exposed directly?) | Determines `COOKIE_SECURE`, `API_URL`, and whether the web tier needs its own TLS |
| D3 | Who runs migrations: the pipeline automatically, or a human after review? | Determines the shape of the pipeline in §4 (automatic migration vs approval gate) |
| ~~D4~~ | ~~Expected go-live date for the second customer~~ **Partly resolved by D1** | With one deployment per customer, the multi-tenant items in §7 stop blocking customer two — see §7.0. What remains open is *when*, which now drives capacity rather than security |

> Until D2 is settled, §3 keeps one open slot (secret injection); §1–§2 and §6 can start (they are independent of deployment shape).

### 0.1 What D1 fixes — and what it costs

**Decided: each customer hosts their own deployment, on their own premises or in their own cloud account. One deployment serves one workspace.**

This resolves things in both directions, and both need writing down.

**What it settles:**

| Settled | How |
| --- | --- |
| Backup approach | Self-managed WAL archiving inside the customer's environment — **not** managed snapshots. §5 is now specified |
| Secret injection | No cloud secret manager of ours. The customer owns the env file. §3 is now specified |
| Data residency | **Resolved by definition** — customer data never leaves the customer's environment. The open question from the review closes here |
| The two multi-tenant leaks | Downgraded from launch blockers to Phase 1 — see §7.0. This is the single biggest relief D1 buys |

**What it costs — say these out loud before committing to it:**

| Cost | Detail |
| --- | --- |
| Operational cost is linear in customers | Customer N means N Postgres instances, N sets of containers, N upgrade windows. Customer three is the turning point; past that, revisit shared hosting |
| You cannot reach the environment | CI cannot deploy into it (and should not hold credentials that could). §9 becomes "produce artifacts here, run the upgrade there" |
| Telemetry may not leave | Sentry SaaS exports stack traces and request context off-site — possibly unacceptable to a customer who self-hosts precisely to keep data in. §6.2 has to offer a self-hosted or local-only option |
| Support needs version visibility | With N environments you will be asked "which version is that customer on?". There is no version endpoint today (`main.py` has only `/health`), so §9 adds one |
| Backup becomes a shared responsibility | You provide the tooling; the customer runs it and owns the storage target. **Who is accountable for RTO/RPO has to be written down per customer**, or it will be assumed to be you |

**Keep the option to converge later.** Per-customer deployment is designed to be *capable* of becoming shared, not to foreclose it. Concretely: never hard-code a single-tenant assumption into the code. The `public_workspace_slug` config field in `2026-10-27-public-stats.md` is deliberately a config field rather than a baked-in slug for this reason.

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

**Change** (D1 settled: customer self-hosted, so *the customer owns this file* — there is no secret manager of ours to inject from):

1. **The image must not contain `.env`** — that is the hard rule. The file lives on the customer's host (e.g. `/opt/joineryflow/.env`, `chmod 600`), and `docker-compose.prod.yml` points `env_file` at it. Mounting a host-owned file is fine; baking one into an image is not
2. Ship a **production `.env.example`** covering every variable with a comment on where the value comes from. Today `Settings` has 8 fields and reads `.env` (`SettingsConfigDict(env_file=".env")`), and `.env.example` is the only guide a customer has
3. Add `scripts/check-env.sh`: assert every required variable is set *and non-empty* before `compose up`. Worth it because a missing field makes `Settings()` raise `ValidationError` at import — the container crash-loops, and on a customer's box that reads as "JoineryFlow is broken" rather than "you forgot to set `DATABASE_URL`"
4. `COOKIE_SECURE=true` (`.env.example:12` already notes it must be true anywhere https is used, otherwise session cookies travel in the clear)
5. `MEILI_API_KEY` distinct from `MEILI_MASTER_KEY` (see §7.1)
6. `API_URL`: in compose it is `http://api:8000`; in production set the real address per D2 (the web tier inlines it at build time, so changing it means rebuilding)

**Acceptance**:
- Inside the production image, `ls .env` → does not exist
- `scripts/check-env.sh` with `DATABASE_URL` unset exits non-zero and names the variable
- After login, `curl -I` shows `Set-Cookie` with `Secure; HttpOnly; SameSite`

**Consequence to accept**: the customer holds the secrets, so **you cannot read them**. When something breaks you will be asking the customer to paste redacted config. Design error messages to be diagnosable from logs alone — this is another reason §6.1 (structured logging) matters more under self-hosting than under cloud hosting.

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

**Change** (D1 settled: no managed snapshots exist in a customer's own environment, so this is self-managed WAL archiving):

#### 5.1 Three volumes, three different answers

`docker-compose.yml:51-54` declares `dbdata`, `uploads` and `meilidata`. They are not equally important:

| Volume | What's in it | Back it up? |
| --- | --- | --- |
| `dbdata` | Postgres data directory | **Yes** — PITR, below |
| `uploads` | Every stored file (`FILE_STORE_ROOT=/uploads`, `docker-compose.yml:17,24`) | **Yes**, and with a consistency rule — see 5.2 |
| `meilidata` | Meilisearch index | **No.** It is a derived index: `make reindex` (`Makefile:10`) rebuilds it from Postgres. Run it once after any restore and save the storage |

The `meilidata` answer is the cheap win here: skipping it removes a volume from every backup, every restore and every drill.

#### 5.2 The consistency rule — the database and the file volume are not independent

This is the part most likely to be got wrong, and it is not obvious.

`store_bytes` writes bytes **before** it writes the row: `store.put(...)` then `insert_blob_or_existing(...)` (`app/files/uploads.py:73-79`). So a file exists on disk slightly before it exists in `file_blob`. That fixes which way a restore may drift:

| If the file volume is restored… | Result |
| --- | --- |
| **older** than the database | Rows point at bytes that aren't there. `stream_blob` checks `store.exists(...)` and raises `404 "file not found"` (`uploads.py:99-100`) — **visible to users as lost files** |
| **newer** than the database | Orphaned files on disk with no row. Invisible, harmless, just wasted space |

**Rule: the file volume's restore point must be at or after the database's. When in doubt, let the files be newer.** Do not aim for "the same moment" and hope.

Add `scripts/check-files.sh` to prove it after a restore: for every `storage_key` in `file_blob`, the bytes must exist in the store. Report orphaned files (bytes with no row) as a count — do not delete them automatically.

#### 5.3 The mechanism

| Item | Action |
| --- | --- |
| PITR | `wal_level=replica` + an `archive_command` writing to a target **inside the customer's environment but not on the database host** (second machine, NAS, or their object storage); daily `pg_basebackup` |
| Logical backup | Daily `pg_dump -Fc`, same rule about location. Belt and braces next to PITR, not instead of it |
| File volume | Copy or snapshot `uploads` on the same schedule. Note it is a named volume, so the script must resolve its path (`docker volume inspect`) rather than assume a bind mount |
| After any restore | `make reindex` to rebuild Meilisearch; then `scripts/check-files.sh` |
| Restore drill | `scripts/restore-drill.sh`: restore dbdata + uploads to a random point in time → `make reindex` → run `tests/e2e/smoke.spec.ts` → print elapsed time |
| Makefile | Add `backup`, `restore-drill` and `check-files` targets |

#### 5.4 Who is accountable — settle this per customer, in writing

Under customer self-hosting **you supply the tooling and the customer runs it**. That split is fine, but if nobody writes down who owns RTO/RPO it will default to you by assumption, and you will find out during an incident.

Per customer, record: backup schedule, where the target is, who monitors that the job ran, who is allowed to restore, and the agreed RTO/RPO.

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

## 7. Multi-tenant security (downgraded by D1 — read §7.0 first)

### 7.0 What D1 does to this section

**The two leaks below stop being launch blockers.** With one deployment per customer, a deployment contains one workspace, so "another tenant's data" mostly isn't there to leak. They move from Phase 0 to **Phase 1**.

**Do not delete them.** Three reasons:

1. **The codebase is shared.** One commit ships to every customer. A leak that is unreachable today becomes reachable the moment any environment holds a second workspace — which is exactly what `--workspace-slug` imports and staging data tend to produce.
2. **Converging on shared hosting reverses this instantly.** Customer three or four is when that gets revisited. If the leaks are still open then, they revert to blockers on someone else's schedule.
3. **The relief comes from topology, not from correctness.** That is worth stating plainly: D1 didn't fix these, it made them unreachable. Change the topology and the bugs are exactly as real as they are today.

Keep **7.3** in Phase 0 regardless — it is a regression test, it is cheap, and it holds behaviour that already works.

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

#### 9.1 Under D1 the pipeline splits in two — CI cannot reach the customer's host

This is the biggest shape difference from a cloud deployment. CI must not hold credentials that can log into a customer's machine, and in practice often cannot reach one at all (no inbound access, sometimes no outbound internet either).

| Stage | Where it runs | What it does |
| --- | --- | --- |
| **Build and publish** | GitHub Actions | Build the prod images, tag with an immutable version, push to a registry the customer can pull from. Also publish a release note |
| **Upgrade** | On the customer's host, by the customer (or by you in an agreed window) | `scripts/upgrade.sh <version>`: pull → `alembic upgrade head` → replace containers → poll `/health/ready` → on failure, re-tag back to the previous version |

**Image delivery is an open question the customer has to answer**: a registry they can reach, or an offline bundle (`docker save` / `load`) for air-gapped sites. Air-gapped changes the artefact format, so ask before building the pipeline.

#### 9.2 Add a version endpoint — you will be asked which version a customer is on

There is no version endpoint today (`main.py` exposes only `/health`, line 111). With N environments this becomes a daily support question. Add `GET /version` (or extend `/health`) returning the image tag plus the Alembic head, and surface it in the support-facing docs.

This also makes the release check honest: after an upgrade, assert the running version is the one you intended, not just that something is answering 200.

**Acceptance**:
- Rehearse one release
- Rehearse one rollback (**a rollback that has never been rehearsed is not a rollback**)
- `GET /version` on a freshly upgraded environment reports the expected tag and migration head

---

## Suggested execution order

```
Can start now (nothing open blocks these)
  ├─ 1.1 API image
  ├─ 1.2 Web image
  ├─ 2   Health check split, plus the /version endpoint (§9.2)
  ├─ 5   Backup and restore (+ drill)      <- D1 settled it: self-managed WAL, §5
  ├─ 6.1 Structured logging
  ├─ 7.3 File download ownership test
  └─ 8   Configuration split

Once D2 is settled (domain / where TLS terminates)
  ├─ 3   Configuration and secrets        <- COOKIE_SECURE, API_URL
  ├─ 6.2 Error reporting                  <- self-hosted option matters here (§0.1)
  └─ 6.3 Metrics

Once D3 is settled (who runs migrations)
  ├─ 4   Migration and release order
  └─ 9   Deploy pipeline (+ release/rollback drills)

Moved to Phase 1 by D1 — no longer blockers, see §7.0
  ├─ 7.1 Meilisearch tenant tokens
  └─ 7.2 /public/stats
```

---

## Acceptance summary (the criteria for "Phase 0 is done")

| # | Criterion | Now |
| --- | --- | --- |
| 1 | Production images contain no dev dependencies and the process is not root | ❌ |
| 2 | A failing `pnpm install` fails the build | ❌ (swallowed by `|| true`) |
| 3 | With the DB down, `/health/ready` returns non-200 | ❌ (`/health` does not query the DB) |
| 4 | Production does not mount `.env` and `COOKIE_SECURE=true` | ❌ |
| 5 | Backups exist **and a restore drill has succeeded once**, with RTO/RPO recorded — database **and** `uploads`, consistent per §5.2 | ❌ (no backups) |
| 6 | One 500 can be traced end to end by `request_id` | ❌ (no structured logging) |
| 7 | Releases are one-click rollbackable, and rollback has been rehearsed | ❌ (no deploy workflow) |
| 8 | Any running environment reports its version and migration head | ❌ (only `/health`, no version) |
| 9 | No dev-only flags such as `fsync=off` in production config | ❌ (only one dev compose file exists) |
| ~~10~~ | ~~Credentials for tenant A cannot reach tenant B's search results~~ | ❌ (master key) — **moved to Phase 1 by D1**, §7.0 |

Row 10 is struck through rather than deleted on purpose: it is deferred, not fixed, and the reason it is safe to defer is a deployment decision that can be reversed.
