# Production deployment (Phase 0 §8 / PR B)

Customer self-hosted, one deployment per customer (D1). TLS terminates at the
customer's own reverse proxy (Q1). This directory is the customer-facing half of
the release; the images themselves come from CI (§9, not built yet).

```
deploy/
  .env.prod.example          template — copy, fill, chmod 600, never commit
  proxy/nginx.conf.snippet   nginx snippet (not a complete config)
  proxy/README.md            why the three proxy defaults break the app
  README.md                  this file
docker-compose.prod.yml      the production stack (repo root)
scripts/check-env.sh         pre-flight validation of the env file
```

## Decisions recorded 2026-11-08

| # | Question | Decision |
| --- | --- | --- |
| 1 | Where does the proxy run? | Configurable. `JF_WEB_BIND` defaults to `127.0.0.1` for a same-host proxy; set it to the host's internal IP when the proxy is on another machine and firewall the port to that proxy only. `JF_WEB_PORT` (default `3000`) changes the **host** port if something already owns 3000 — the container and its healthcheck stay on 3000, and the proxy's `upstream` must be updated to match. |
| 2 | How are images named for both delivery modes (Q4)? | Variable registry prefix: `${JF_REGISTRY:-joineryflow}/{api,web}:${JF_VERSION}`. Registry mode sets `JF_REGISTRY=registry.customer.com/joineryflow`; offline mode leaves the default and pre-loads the same tags with `docker load`. One compose file, two delivery paths. |
| 3 | How is the production env delivered? | A separate `deploy/.env.prod.example`. The dev `.env.example` has `COOKIE_SECURE=false` and a published dev password — a customer must never copy it. |
| 4 | Who performs the upgrade (Q7)? | **The customer.** `scripts/upgrade.sh` (§9, still to be written) must be documented for someone who did not write it: clear prompts, self-diagnosing errors, and a rollback path that does not require us to reach the host. |

## First install

Work from the directory that holds `docker-compose.prod.yml` and the filled
`.env` (the example below assumes `/opt/joineryflow/`).

```bash
cp deploy/.env.prod.example /opt/joineryflow/.env
chmod 600 /opt/joineryflow/.env
# edit: replace every __SET_ME__, set JF_VERSION to the release tag
scripts/check-env.sh /opt/joineryflow/.env
```

**`--env-file` is mandatory on every compose command below.** It supplies the
`${...}` interpolation values; `env_file:` then injects the same file into the
containers. `JF_VERSION` is declared with `:?`, so forgetting `--env-file` (or
running from a source checkout with its dev `.env`) fails loudly instead of
starting with dev credentials.

Get the images, depending on delivery mode:

```bash
# registry mode
docker compose --env-file .env -f docker-compose.prod.yml pull api web

# offline mode (air-gapped): load the two runtime images AND the two base
# images postgres:16 / getmeili/meilisearch:v1.54.0 from the release bundle
docker load -i joineryflow-images-<version>.tar
```

Then bring up the data services and migrate **before** switching traffic on
(Q2: migrate first, switch second):

```bash
docker compose --env-file .env -f docker-compose.prod.yml up -d db meili
docker compose --env-file .env -f docker-compose.prod.yml run --rm -w /db api alembic upgrade head
docker compose --env-file .env -f docker-compose.prod.yml up -d
```

> **BLOCKER — Q12 (open).** The migration above creates the schema but not its
> starting rows. The only seeding tool is `python -m seed.hartwood_joinery`, a
> **dev** seed with a published password and demo data, and it is also the only
> thing that fills `stages` (10 rows) and `status_options` (6 rows). A customer
> install can neither run it as-is nor do without it. Creating the first
> workspace, first admin and reference rows needs a production-safe path before
> the first go-live. This is recorded in the checklist §0.2 and is **not** solved
> by PR B.

Finally merge `deploy/proxy/nginx.conf.snippet` into the customer's proxy and
run the checks in `deploy/proxy/README.md`.

## Why `/health/ready` is not a compose startup gate

The api image's `HEALTHCHECK` probes `/health/live` (process alive). `web`
depends on `api: service_healthy` for that reason. Using `/health/ready` here
would deadlock a first install: readiness requires `alembic_version` to equal
the image's schema head, which is false on an empty unmigrated database — so api
would never become healthy and web would never start. Readiness is polled by
`upgrade.sh` **after** migration (Q2 gate 3), not by compose. This is also why
the migration above runs as a one-shot container before `up -d`.

## What is deliberately different from dev

| dev (`docker-compose.yml`) | prod (`docker-compose.prod.yml`) |
| --- | --- |
| `fsync=off`, `synchronous_commit=off`, `full_page_writes=off` | none of them |
| source bind mounts, `--reload`, `next dev`, `target: dev` | no mounts, code in the image, `target: runtime` images |
| 5432 / 8000 / 3000 all published | only web, bound to `127.0.0.1` by default |
| `env_file: .env` from the repo | host-owned `.env` at `JF_ENV_FILE` |
| `MEILI_ENV: development` | `MEILI_ENV: production` (requires a ≥16-byte master key) |
| no restart policy | `restart: unless-stopped` on all five services |
| `search-worker` uses the dev image (no healthcheck) | `healthcheck: disable: true` — the api **runtime** image's `/health/live` probe would otherwise be inherited by a worker that never listens on 8000 |

> **Operational caveat:** the worker currently has no liveness signal of its own.
> `restart: unless-stopped` recovers a crash, but not a worker stuck in a retry
> loop. A heartbeat in `app/search/worker.py` is still owed before the first
> customer install; until then, watch the search outbox / Meili index age as the
> practical signal.

## Acceptance

```bash
grep -c "fsync=off" docker-compose.prod.yml          # must be 0
scripts/check-env.sh <env-with-DATABASE_URL-unset>   # non-zero, names DATABASE_URL
JF_VERSION=1.0.0 docker compose --env-file .env -f docker-compose.prod.yml config
```

From **outside** the host, `nc -zv <host> 5432` and `8000` must fail while 443
(the customer's proxy) answers. After login, `curl -I` must show `Set-Cookie`
with `Secure; HttpOnly; SameSite`. No `.env` may exist inside either image.

## Still open for §9 (deploy pipeline)

- Q4 was decided as **both** registry and offline bundle. CI must therefore
  produce two artefacts: immutable tags pushed to a reachable registry, and a
  `docker save` bundle containing both runtime images, both base images,
  `docker-compose.prod.yml`, `deploy/`, `scripts/`, a release manifest and
  checksums. `upgrade.sh` must support `pull` and `load` paths.
- Q7 (customer-run) means the upgrade script is a customer-facing document, not
  an internal runbook. No host credentials in CI.
- Q5 (RTO/RPO and named owner) and Q6 (telemetry leaving the environment) are
  still open in checklist §0.2; neither blocks this PR.
