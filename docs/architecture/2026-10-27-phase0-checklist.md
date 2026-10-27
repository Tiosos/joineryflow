# Phase 0 — Productionisation Checklist

> Status: **ready to execute**. Companion document: `docs/architecture/2026-10-27-scalable-architecture.md` (PR #172).
> Goal: give the system a production path that can carry all later architecture work. **Until this step is done, Phases 1–3 have nothing to land on.**
> Scope: 2–4 weeks (excluding the wait for the decisions in section 0)

---

## 0. Prerequisite decisions (these block 4 items below — please answer first)

| # | Question | Why it blocks |
| --- | --- | --- |
| ~~D1~~ | ~~Self-hosted or cloud-hosted?~~ **DECIDED 2026-10-27: customer self-hosted, one deployment per customer.** | Resolved. See §0.1 for what it fixes and what it costs |
| ~~D2~~ | ~~Production domain and where TLS terminates~~ **DECIDED 2026-10-27 (Q1): single hostname, TLS terminated by the customer's existing reverse proxy.** | Resolved — §0.3 lists what follows, including the request-body limit and the ports that must not be published |
| ~~D3~~ | ~~Who runs migrations~~ **DECIDED 2026-10-27 (Q2): automatic, gated by a mandatory backup and an explicit confirmation for destructive revisions.** | Resolved — §4 is now specified |
| ~~D4~~ | ~~Expected go-live date for the second customer~~ **Partly resolved by D1** | With one deployment per customer, the multi-tenant items in §7 stop blocking customer two — see §7.0. What remains open is *when*, which now drives capacity rather than security |

> Until D2 is settled, §3 keeps one open slot (secret injection); §1–§2 and §6 can start (they are independent of deployment shape).
> **Every question still open across all four documents is collected in §0.2** — including the ones raised further down (image delivery §9.1, RTO/RPO §5, telemetry §6.2).

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

### 0.2 Consolidated open-questions register — everything still unanswered, in one place

D1 closed one question and changed the shape of several others. What follows is the complete remainder: every item from this document, from `2026-10-27-scalable-architecture.md` §7, and from `2026-10-27-public-stats.md`, gathered so that nothing has to be recovered by reading four files. **Nothing in this table has been decided on anyone's behalf** — each row names what it blocks so the order can be chosen deliberately.

| # | Question | Where it lands | What it blocks | Needed by |
| --- | --- | --- | --- | --- |
| ~~**Q1** (= D2)~~ | ~~Production domain, and where TLS terminates~~ **DECIDED: single hostname, TLS terminated by the customer's existing reverse proxy** | §0.3 | Resolved. Sets `COOKIE_SECURE=true`, keeps `API_URL` container-internal, and adds proxy requirements (body size, read timeout, forwarded headers) | Settled |
| ~~**Q2** (= D3)~~ | ~~Who runs migrations~~ **DECIDED: automatic, behind a mandatory backup gate and an explicit confirmation for destructive revisions** | §0.3, §4 | Resolved. §4 is written; §2 gains a schema-version check and §5 supplies the dump the gate depends on | Settled |
| **Q3** (= D4) | When does the second customer go live? | §0 / ops | No longer a security gate (one deployment per customer). It now sets **operational capacity**: N customers means N environments to upgrade, monitor and keep on a supported version | Before customer two |
| **Q4** | Image delivery: a registry the customer can pull from, or an offline bundle (`docker save` / `load`) for air-gapped sites? | §9.1 | The artefact format the pipeline produces. Air-gapped delivery is not a flag you add later — ask before building §9 | Before §9 |
| **Q5** | RTO and RPO per customer, and who is accountable for hitting them | §5 | Backup here is a shared responsibility: we ship the tooling, the customer runs it and owns the storage target. Unwritten, accountability is assumed to be ours | Before the first go-live |
| **Q6** | Is telemetry allowed to leave the customer's environment? | §6.2 | Sentry SaaS exports stack traces and request context off-site. A customer who self-hosts precisely to keep data in may refuse it; §6.2 then needs a self-hosted or local-only option | Before §6 |
| **Q7** | Who performs the upgrade, and in what window — the customer, or us under an agreed arrangement? | §9.1 | Whether `upgrade.sh` is a customer-facing script or an internal runbook, whether we need access to the host, and whether a rollback window has to be staffed | Before the first upgrade |
| **Q8** | Billing model: per seat, per project count, or a flat price per workspace? | Roadmap §7 (Q3) | The design of the quota tables. Per-customer hosting carries a real per-customer infrastructure cost, which sits awkwardly with a pure per-seat price — decide the two together | Before any quota work |
| **Q9** | `/public/stats`: Option A (tenant comes from server config, remove the `workspace_slug` parameter) or Option B (drop the endpoint entirely)? | `2026-10-27-public-stats.md` §5–§6 | B is cleaner still, but it costs the login page its live counts — a product decision, not an engineering one | Before §7.2 starts |
| **Q10** | Formal acceptance of the two cross-tenant leaks as Phase 1 risk | §7.0 | D1 made them **unreachable, not fixed**. Someone should sign that risk explicitly, and it has to be closed before any move back to shared hosting | Now — it is one line |
| **Q11** | `tests/e2e/` spec count: 76 on disk vs 66 in `CLAUDE.md:125` | Roadmap §7 (Q1) | Documentation accuracy only. Second half of the question: should `CLAUDE.md` drop the concrete number the way it already does for pytest counts? | Low |

**Two of these block Phase 0 work (Q1, Q2).** The rest set the shape of individual sections or of the commercial model, and none of them prevents §1, §2 or §6 from starting this week.

**Interactions worth noticing before answering:**

- **Q4, Q5 and Q7 are the same conversation.** They are all "what does support look like when we cannot reach the environment" — decide them together, not in three separate threads.
- **Q6 and Q5 pull against each other.** No telemetry off-site (Q6) and a tight RTO (Q5) both require the customer to operate more of the stack themselves, or to grant us access. Expect both answers to move together.
- **Q8 is the one that outlives Phase 0.** Everything else here is about shipping safely; the billing model decides what the quota tables look like, and getting it wrong is expensive to unwind once tables exist.

### 0.3 Q1 and Q2, settled 2026-10-27

#### Q1 — one hostname; TLS ends at the customer's existing reverse proxy

**Decided**: a single external hostname (for example `jf.customer.com`). TLS terminates at the reverse proxy / gateway / WAF the customer already runs. The api and Meilisearch stay inside the compose network and are never published.

**Why this is the low-risk answer** — the evidence that made it obvious:

- **The browser never talks to the api.** `apps/web/app/api/[...proxy]/route.ts:15-27` forwards every `/api/**` request server-side to `API_URL` and copies the upstream response headers back — `Set-Cookie` included. So the session cookie is issued into the browser's relationship with the *web* hostname: host-only and `SameSite=Lax` (`apps/api/app/auth/sessions.py:95-96`).
- **A separate api hostname would break login, not merely complicate it.** Cross-site XHR does not carry a `Lax` cookie, so every authenticated request would arrive anonymous. Repairing that means `SameSite=None; Secure` plus CORS, and then Chrome/Safari third-party cookie policy applies — a worse position than we are in now.
- **"Expose Next directly" was never available.** Next's standalone server speaks HTTP; something has to terminate TLS in front of it either way. The real question was only *who owns that point*.

**What follows, concretely**:

| Item | Setting |
| --- | --- |
| `COOKIE_SECURE` | `true` (already §3) |
| `API_URL` | **stays `http://api:8000`** — container-internal. It is read by two server components (`apps/web/app/items/[id]/label/page.tsx:14`, `apps/web/app/(app)/tracking/page.tsx:25`) and by the proxy route; no public address is needed for either |
| Published ports | Only the proxy's 80/443. `docker-compose.prod.yml` must **not** publish 5432 or 8000 — dev compose publishes `5432/8000/3000` (see §8) |
| Request body size | Must be raised at the proxy. The proxy route reads the whole body into memory (`await req.arrayBuffer()`, `route.ts:20`) and uploads pass through it; nginx's default `client_max_body_size 1m` answers 413 before the application sees the request |
| Proxy read timeout | PDF and export routes are inherently slow (`docs/REVIEW-2026-10.md` §C: a 300-line PDF ≈ 3.3 s). Raise `proxy_read_timeout` for those paths rather than globally, and keep a ceiling |
| Forwarded headers | Nothing reads `request.url` / `base_url` today, so `X-Forwarded-Proto` is not *required* yet — but add `--proxy-headers` to uvicorn now, so the first feature that builds an absolute URL does not emit `http://` links behind https |
| WebSockets / SSE | Not used. A plain HTTP reverse proxy is sufficient |

**Consequence to accept**: we do not control the proxy. Certificate renewal, TLS policy and any WAF rule are the customer's, so an outage in their tier looks like an outage in ours and we have no lever on it. Ask for the proxy config to be part of the install checklist, and make `GET /version` reachable so "is it up on your side?" is answerable without shell access.

#### Q2 — migrations run automatically, behind a mandatory backup and an explicit confirmation for destructive ones

**Decided**: `scripts/upgrade.sh` runs `alembic upgrade head` by default. It is *gated*, not interactive by default — three gates, any of which can abort the upgrade.

**What the 89 revisions actually contain** (scanned, not assumed):

| Property | Count | Consequence |
| --- | --- | --- |
| Linear chain, single head | 89 | `alembic upgrade head` is unambiguous |
| `upgrade()` contains a DROP (column or table) | **7** | Data loss is real and irreversible |
| `upgrade()` contains data DML (UPDATE / INSERT / DELETE) | **36** | Backfills — duration depends on table size, and they hold locks while they run |
| `downgrade()` implemented | 88 of 89 | Downgrades exist, **but they do not restore dropped data** — they recreate empty columns |

That last row is the one that decides the design: **rolling back a migration is a database restore, not `alembic downgrade`.** Which is why the backup gate is mandatory rather than polite.

**The three gates**:

1. **Back up first, or stop.** Before migrating, run `pg_dump -Fc` to the target from §5 and record the dump path in the upgrade log. If the dump fails, abort and leave the running version untouched.
2. **Destructive revisions ask.** Scan the pending revisions for `drop_column` / `drop_table` / bulk DML. If any is present, print what will be dropped or rewritten — naming the revision ids — and require an explicit `--yes`. Without it the script exits non-zero and says which revisions stopped it.
3. **Prove the schema landed.** After migrating, assert that `alembic_version` equals the head compiled into the image. `/health/ready` carries this check (§2) so that "new image, old schema" reads as *unhealthy* instead of silently serving 500s, and `GET /version` (§9.2) exposes both the image tag and the schema head.

`--skip-migrate` remains available for whoever wants to migrate by hand — but gate 3 then keeps the deployment unhealthy until the schema matches, so a half-upgrade cannot go unnoticed.

**Consequence to accept**: the gate is a script, not a reviewer. Nobody reads the SQL before it runs; what we buy is a guaranteed restore point and a loud stop on the seven dangerous revisions. If a customer additionally wants a human to sign off, that is **Q7** (who runs the upgrade), not Q2.

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
| `GET /health/ready` | `SELECT 1` through `db.get_db()`; **plus `alembic_version` == the head compiled into the image** (Q2 gate 3, §0.3); Meili optional (`GET /search/health` already exists) | Deciding whether to admit traffic |

**Keep `/health`**: `README.md:40` documents `http://localhost:3000/api/health -> {"ok":true}` and existing e2e specs may depend on it (`tests/e2e/smoke.spec.ts`) — **do not delete it**; make it equivalent to live.

**Acceptance**: stop the db container → `/health/ready` returns non-200 while `/health/live` still returns 200.

**Add the schema check (Q2 gate 3)**: `/health/ready` should also compare `SELECT version_num FROM alembic_version` against the head stored in the image. Without it, "new image + old schema" answers 200 on liveness and then 500s on every request that touches a new column — and nobody notices until a user reports it.

---

## 3. Configuration and secrets

**Current state**: `Settings` in `apps/api/app/config.py` has only 8 fields and reads `.env` (`SettingsConfigDict(env_file=".env")`); `docker-compose.yml` mounts the file into containers with `env_file: .env`.

**Change** (D1 settled: customer self-hosted, so *the customer owns this file* — there is no secret manager of ours to inject from):

1. **The image must not contain `.env`** — that is the hard rule. The file lives on the customer's host (e.g. `/opt/joineryflow/.env`, `chmod 600`), and `docker-compose.prod.yml` points `env_file` at it. Mounting a host-owned file is fine; baking one into an image is not
2. Ship a **production `.env.example`** covering every variable with a comment on where the value comes from. Today `Settings` has 8 fields and reads `.env` (`SettingsConfigDict(env_file=".env")`), and `.env.example` is the only guide a customer has
3. Add `scripts/check-env.sh`: assert every required variable is set *and non-empty* before `compose up`. Worth it because a missing field makes `Settings()` raise `ValidationError` at import — the container crash-loops, and on a customer's box that reads as "JoineryFlow is broken" rather than "you forgot to set `DATABASE_URL`"
4. `COOKIE_SECURE=true` (`.env.example:12` already notes it must be true anywhere https is used, otherwise session cookies travel in the clear)
5. `MEILI_API_KEY` distinct from `MEILI_MASTER_KEY` (see §7.1)
6. `API_URL`: **keep `http://api:8000`**. Q1 settled on a single hostname with the api inside the compose network (§0.3), so this stays a container-internal address — no public api URL exists. It is read server-side only: by the proxy route and by two server components. (The web tier inlines it at build time, so if a customer ever needs a different address it means a rebuild, not a restart.)

**Acceptance**:
- Inside the production image, `ls .env` → does not exist
- `scripts/check-env.sh` with `DATABASE_URL` unset exits non-zero and names the variable
- After login, `curl -I` shows `Set-Cookie` with `Secure; HttpOnly; SameSite`

**Consequence to accept**: the customer holds the secrets, so **you cannot read them**. When something breaks you will be asking the customer to paste redacted config. Design error messages to be diagnosable from logs alone — this is another reason §6.1 (structured logging) matters more under self-hosting than under cloud hosting.

---

## 4. Migration and release order

**Current state**: `make migrate` = `docker compose exec -w /db api alembic upgrade head`. 89 migrations, ~107 tables; `sqlalchemy.url` in `db/alembic.ini` comes from `${DATABASE_URL}`.

**Change** (Q2 settled — automatic and gated, §0.3 gives the reasoning):

```
scripts/upgrade.sh <version>
  0. scripts/check-env.sh                     -> abort on any missing variable
  1. pull the new image                       (do not switch traffic yet)
  2. pg_dump -Fc to the §5 target             -> GATE 1: abort if the dump fails
  3. scan pending revisions for drop_column / drop_table / bulk DML
       if any found: print the ids and what will be lost, require --yes   GATE 2
  4. alembic upgrade head                     -> abort on failure
  5. replace the web / api containers
  6. poll /health/ready until 200             -> GATE 3: includes the schema check
  7. on failure: re-tag to the previous version, then restore the dump from step 2
```

**Why the dump is gate 1 and not a nice-to-have.** Of the 89 revisions, **7 drop a column or a table** and **36 run data DML**. A `downgrade` exists for 88 of them, but a downgrade rebuilds *structure*, not *contents* — a dropped column comes back empty. So the only real rollback is the dump taken one minute earlier. Running `alembic downgrade` on a customer's production database and calling it a rollback would destroy more than it saves.

**Key constraint** (unchanged): `CLAUDE.md` requires that changes land only behind **data-preserving migrations** (Q435). The order is therefore **migrate first, switch traffic second**, and migrations must stay forward-compatible for one version so the old code can still run if we roll back.

**Acceptance**:
- Rehearse: migration succeeded + release succeeded
- Rehearse: **the dump fails → the upgrade aborts and the running version is untouched**
- Rehearse: **a destructive revision is pending → the script stops, names the revision, and does not migrate**
- Rehearse: migration succeeded but the schema head does not match → `/health/ready` returns non-200
- Rehearse **one rollback from the pre-migration dump** — this is the drill everyone skips, and it is the only one that proves gate 1 was worth building

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

**`upgrade.sh` reuses this** (Q2 gate 1, §0.3): the same `pg_dump -Fc` invocation and the same target are used before every migration. One artefact to verify rather than two, and the restore point a customer needs after a bad upgrade is the thing they already know how to find.

#### 5.4 Who is accountable — settle this per customer, in writing

Under customer self-hosting **you supply the tooling and the customer runs it**. That split is fine, but if nobody writes down who owns RTO/RPO it will default to you by assumption, and you will find out during an incident.

Per customer, record: backup schedule, where the target is, who monitors that the job ran, who is allowed to restore, and the agreed RTO/RPO. (→ **Q5** in §0.2: the numbers and the named owner. **Q7** is the same question for the upgrade path.)

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

**Answer Q6 (§0.2) before choosing a vendor**: if telemetry is not allowed to leave the customer's environment at all, this section needs a self-hosted or local-only option rather than a SaaS DSN, and scrubbing does not rescue it — the data still leaves.

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

**Downgrading these is a risk decision, and it needs an owner (Q10 in §0.2).** D1 made them unreachable; it did not fix them. Someone should accept that explicitly, and the acceptance should carry the condition that closes it: *if we ever move back to shared hosting, both items revert to launch blockers before the second workspace lands anywhere.*

> **Correction**: the first version of the companion document listed "single-root file store" as a leak. **That was wrong.** Verified against the code: the layout is already sharded by workspace (`app/files/store.py` docstring: `<root>/<workspace_slug>/<sha256[0:2]>/<sha256>`), and all three download paths **do** check ownership — `files/routes.py:153`, `files/uploads.py:94` (`WHERE file_blob_id = :b AND workspace_id = :w`), `orders/attachments.py:83` (`_order_exists`). This item is downgraded from "fix this" to "add a test to hold it in place".

### 7.1 Meilisearch: replace the master key — **real work**

**Current state**: `.env.example:21-24` — the `MEILI_API_KEY` the API uses *is* the master key, with the comment stating "scoped keys are out of scope for v1".

**Isolation today (clarified)**: the application layer actually has two filters — `app/search/index.py:96 build_filter` builds from `me.workspace_id`, its comment saying "The workspace clause is unconditional", and `readable_types` in `app/search/routes.py` then filters types by module `read` permission. **So the main line of defence does exist.** The problem is that the search engine enforces nothing: the master key can read the whole index, so any call path that bypasses `build_filter` is a total leak.

**Change**: move to Meilisearch **tenant tokens**, pushing the `workspace_id` filter down into the engine so that "forgot the filter" degrades from "leak" to "no data returned".

**Acceptance**: using a token issued for tenant A against Meili directly returns none of tenant B's documents (as an automated test).

### 7.2 `/public/stats` — **real work, but moderate severity**

**Current state**: `app/public/routes.py:19` has no auth; the comment says "No authentication required". Any `workspace_slug` returns three counts (projects, parts, suppliers).

**Clarification**: what leaks is **three numbers**, not customer data itself. Acceptable with one customer; with several, it means anyone can enumerate other customers' project and supplier counts, and can distinguish "a workspace with data" from "a slug that does not exist".

**Change**: the full work-up is in `2026-10-27-public-stats.md`. In short:

| Option | What it is | Cost |
| --- | --- | --- |
| **A — recommended** | The tenant comes from server config (`public_workspace_slug`); delete the `workspace_slug` request parameter. ~15 lines | None functionally. The parameter is used by exactly one caller, which always asks for the same workspace (`apps/web/app/(public)/login/page.tsx:5`) |
| **B** | Delete the endpoint; make the login-page brand panel static copy | Zero public surface, but the panel loses its live counts — a product decision |

**Q9 in §0.2 is this choice.** The finding underneath it: the parameter is flexibility nothing uses, so *the parameter is the entire attack surface*.

**Acceptance**: no caller can ask for another tenant's counts; `tests/test_public_stats.py:73` — which pins the leak as a feature — is deleted and replaced by a test asserting the response comes from config.

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
| `ports: ["5432:5432", "8000:8000"]`, everything exposed | **Only the web tier is published** (and only to the proxy). Under Q1 neither 5432 nor 8000 is reachable from outside the compose network |
| `env_file: .env` | Environment variables / injected secrets |
| `uvicorn app.main:app ...` | add `--proxy-headers`, so absolute URLs built later respect `X-Forwarded-Proto` |

**Also ship a proxy configuration snippet** (`deploy/proxy/`), because Q1 puts TLS in the customer's hands and three defaults there will break the app before anyone suspects the proxy:

| Setting | Why |
| --- | --- |
| `client_max_body_size` (nginx default `1m`) | Uploads pass through the web tier's proxy route, which buffers the whole body; the default answers 413 before the app sees the request |
| `proxy_read_timeout` (nginx default `60s`) | PDF and export routes are slow by nature (review §C: 300-line PDF ≈ 3.3 s). Raise it for those paths, keep a ceiling |
| `X-Forwarded-Proto` / `X-Forwarded-For` | Nothing reads them today; add them now so the first absolute-URL feature does not emit `http://` links behind https |

**Acceptance**: `grep -c "fsync=off" docker-compose.prod.yml` → **0**; from outside the host, `nc -zv <host> 5432` and `8000` both fail while `443` answers.

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

**Image delivery is an open question the customer has to answer (Q4 in §0.2)**: a registry they can reach, or an offline bundle (`docker save` / `load`) for air-gapped sites. Air-gapped changes the artefact format, so ask before building the pipeline — bolting it on afterwards is a rewrite, not a flag.

**Who runs the upgrade row of that table is Q7**, and it is not a detail: customer-run means `upgrade.sh` has to be documented for someone who did not write it, while us-run means we need host access and a staffed rollback window.

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
