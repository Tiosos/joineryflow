# Production images — design (Phase 0 §1)

**Status: implemented and verified 2026-11-08** on local branch `feat/prod-images`
(**not pushed**). PR #181 merged the design on 2026-11-06. Building the images and
running all 17 §8 checks against them found **three further design defects** — per-check
results and the evidence are in §10.2. A second review the same day found **one more
runtime defect (C17)** and **one CI-breaking suggestion in Q15**; both are corrected here
and in the local implementation — see §10.3. Nothing in this branch has been pushed.

**Revised 2026-11-03** — every claim below re-checked against the tree at `db6564b`
(the commit that carries the §2 health split). **Reviewed again 2026-11-06 before merging
PR #181**; that review found one blocking defect (C14) and one unverifiable assertion
(C10), both corrected below. Twelve things the original sketch did not know about are
recorded here; the full trail of corrections is in §10.

It replaces the sketch in `2026-10-27-phase0-checklist.md` §1 with something that
survives contact with the repository:

| Found | Consequence |
| --- | --- |
| CI runs the whole pytest suite **inside** the api image (`ci.yml:42-75`) | The image cannot simply drop pytest — it needs a second target |
| `Makefile:6` runs `alembic` with `-w /db`, and `app/meta.py:27` probes `/db/alembic.ini` | The api image must contain `db/`, so its build context is the **repo root**, not `apps/api` |
| `printing/templates/print.css:7,13,19,25` loads fonts from `../../../seed/fonts/` | The runtime image needs the fonts, which today arrive only through a dev-only volume mount — **decided: move them into `apps/api`** (D3) |
| `docker-compose.yml:39` starts `search-worker` from the same image with a different command | Two Dockerfiles, **three** container roles |
| `tracking/page.tsx:97` reads `NEXT_PUBLIC_PROCUREMENT_UI_READY`, and `ci.yml:239` exports `.env` before `pnpm build` for exactly that reason | The web build **does** need one build-time value (D5), which the first draft denied |
| `apps/api/tests/` is inside the directory `COPY apps/api /code` copies | The runtime image would ship the test suite unless the context excludes it (D6) |
| `USER 10001` has no writable home, and fontconfig wants a cache there | Every PDF render risks a font-cache rebuild unless `HOME`/`XDG_CACHE_HOME` are pinned (C10) |
| `apps/web/pnpm-workspace.yaml` carries `ignoredBuiltDependencies` | It has to be copied **before** `pnpm install`, or the install runs with different settings than CI (C13) |
| `docker-compose.yml:45-50` mounts source at `/code` and runs `pnpm dev` | The web image needs its own `dev` target, or `make up` boots the production stage and the dev stack dies (C14) |
| `app/main.py` imports weasyprint at process start | The four WeasyPrint system libraries have to be in **every** stage, not just `runtime`, or the `dev` target CI runs pytest in cannot even import the app (C4, C15) |
| Host pnpm symlinks are absolute paths, and corepack re-resolves pnpm at container start | The dev service needs an anonymous `node_modules` volume, and the runtime `CMD` must not go through `pnpm` at all (C14, C16) |
| `COPY --from=build /code/.next` lands as root while the process is `USER 10001` | `/app/.next/cache` must be chowned, or the first ISR / image-optimisation write fails with `EACCES` (C17) |

---

## 1. What we are building

| Role | Built from | Command | Image contents it needs |
| --- | --- | --- | --- |
| `api` | `apps/api/Dockerfile` | `uvicorn app.main:app …` | `app/` (incl. `printing/fonts`), `db/` (alembic), WeasyPrint libs |
| `search-worker` | **same image** | `python -m app.search.worker` | same; keeps the Meili master key (§7.1) |
| `web` | `apps/web/Dockerfile` | `next start` | `.next`, `public/`, production `node_modules` |

One extra role appears only during an upgrade: a one-shot `alembic upgrade head`
container from the api image (§4, Q2 gate 3). It runs the same image, so no third
Dockerfile.

Three images are built from two Dockerfiles because `docker-compose.yml:39-43` already
runs `search-worker` from the api image with `command: python -m app.search.worker`. The
runtime target's `CMD` is uvicorn; the worker overrides it. Nothing in the image is
worker-specific.

---

## 2. Constraints, with the code that imposes them

**C1 — CI runs tests inside the api image.** `ci.yml:42-50` bakes the `api` target from
`docker-compose.yml`, then `up -d db meili api`, then three commands *inside* that
container: `-w /db alembic upgrade head` (`ci.yml:65`), `python -m seed.hartwood_joinery`
(`ci.yml:72`) and `pytest -q -n auto --dist loadfile` (`ci.yml:75`). So the image CI
builds must contain pytest, the `seed` package and `db/`. Deleting the dev dependencies
from the image breaks CI before it proves anything about production. The e2e job builds
`api` and `search-worker` the same way (`ci.yml:172-181`).

**C2 — `db/` belongs in the image.** `Makefile:6` is `docker compose exec -w /db api
alembic upgrade head`, and the readiness probe added in #179 reads the alembic script
directory out of the image (`app/meta.py:27-31`, which probes `/db/alembic.ini` first). A
production image without `db/` would answer `schema_match: "skipped"` and, on an upgrade,
would have nothing to migrate with. `db/alembic.ini` sets `script_location = alembic`
(relative to the ini file), so the whole `db/` tree travels together.

**C3 — the build context becomes the repository root.** Because of C2 the api image can
no longer be built with `build: ./apps/api`. It has to be
`build: { context: ., dockerfile: apps/api/Dockerfile }`. There is **no root
`.dockerignore`** today, so that context would ship `.git`, `apps/web/node_modules` and
every `__pycache__` to the daemon. A root `.dockerignore` is part of this change, not an
optional tidy-up.

**C4 — the four WeasyPrint libraries are load-bearing, and belong in every stage.**
The original `apps/api/Dockerfile:2-5` installs
`libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-liberation`. Dropping any of them
does not fail the build; it fails months later when a quote PDF renders without text.
Keep all four, and add a PDF smoke test (§8) rather than trusting the list.

**Verified 2026-11-08:** putting them only in the `runtime` stage (as the first draft of
this design did) breaks the `dev` target outright. `app/main.py` imports weasyprint at
process start, and `libpango` is what pulls in `libgobject-2.0-0`; without it the api dev
container dies with `OSError: cannot load library 'libgobject-2.0-0'` and CI's pytest
never runs. The fix is a shared `base` stage carrying the apt layer, with `deps`, `dev`
and `runtime` all descending from it — one apt layer, no duplication, no stage left out.
See C15.

**C5 — PDF fonts live outside `apps/api`.** `printing/templates/print.css:7,13,19,25`
resolves to `<workdir>/seed/fonts/*.woff2`; in dev that path exists only because
`docker-compose.yml:23` bind-mounts `./seed:/code/seed`. The production image has no such
mount, so today's Dockerfile would produce a PDF with every font silently substituted.

One detail that decides the fix: WeasyPrint resolves the `@font-face` URL against the
template's `base_url`, which `printing/engine.py:28,34` sets to `TEMPLATES_DIR` — not
against the CSS file's own location. Both happen to be the same directory here, so the
relative path is simply one level up from `templates/`.

**Decided (D3): move the fonts to `apps/api/app/printing/fonts/` and change the four
`url()` entries from `../../../seed/fonts/X` to `../fonts/X`.** Fonts are application
assets; `seed/` holds a dev dataset, and shipping a directory named `seed` inside a
customer's runtime image invites someone to run it. After the move the runtime image
needs no `seed/` at all, and `COPY apps/api /code` carries the fonts.

**C6 — non-root needs a writable upload root.** `files/store.py:62` reads
`FILE_STORE_ROOT` from the environment with default `/uploads`; compose sets it to
`/uploads` (`docker-compose.yml:17`) and mounts the `uploads` volume there. Under
`USER 10001` that directory has to be owned by 10001, or uploads fail with a permission
error at the first customer file. A named Docker volume inherits the ownership of the
directory it replaces, so `mkdir /uploads && chown 10001:10001 /uploads` in the image is
enough for named volumes; a customer using a bind mount has to chown it once. That
belongs in the deployment notes (§8 of the checklist), not only here.

**C7 — the web build needs exactly one value, and it is not a secret.** Three variables
matter, and they do not behave the same way:

| Variable | When it is read | Evidence |
| --- | --- | --- |
| `SESSION_COOKIE_NAME` | **runtime** | `proxy.ts` runs in the Node.js runtime and `lib/session-cookie.ts:19-22` documents that the read is no longer inlined |
| `API_URL` | **runtime** | read at module scope in 20 server components (`dashboard/page.tsx:12`, `api/[...proxy]/route.ts:3`, …); not a `NEXT_PUBLIC_` name, so nothing inlines it |
| `NEXT_PUBLIC_PROCUREMENT_UI_READY` | **build time** | `tracking/page.tsx:97`; `ci.yml:239` exports `.env` before `pnpm build` and says so: *"NEXT_PUBLIC_* values are inlined at build time"* |

So the image takes **one** `ARG` (D5). Without it the flag resolves to `undefined`,
`tracking/page.tsx:97` compares against `"1"`, and the Procurement entry point silently
disappears from every production deployment — the same class of silent absence this
section exists to remove. The default is `1`, matching `.env.example:19`.

**Documentation defect found while checking this:** `.env.example:6-7` still says a
cookie rename *"requires a web rebuild, since Next inlines env reads in middleware"*.
That was true under the Edge-runtime `middleware`; it is false now that the file is
`proxy.ts` in the Node runtime. The code is right and the comment is stale — PR A should
fix the comment, since a customer reading it would rebuild for nothing.

**C8 — `pip install -e .` with a bare `pyproject.toml`.** Today's Dockerfile copies
`pyproject.toml` alone and installs editable; the resulting `jf-api` distribution
contains no packages (the source arrives afterwards via `COPY . .` / a bind mount) and
the install exists purely to populate the virtualenv. This is worth knowing because the
obvious "improvement" — copy the source first, then install — makes setuptools discover
several top-level packages (`app`, `tests`, …) and fail the build. Keep the current
order; it is deliberate even though it does not look like it.

**C9 — the web build needs no reachable api.** This is what makes a single-stage build
possible in an environment where no api container exists. Checked by walking every page
that fetches: the two that fetch without `cookies()` — `items/[id]/page.tsx` and
`items/[id]/label/page.tsx` — are dynamic-segment routes with no `generateStaticParams`,
so they render on demand and never at build time. `app/page.tsx` only redirects, and
`app/(public)/login/page.tsx` is a client component that fetches in `useEffect`. CI is
consistent with this: its build step exports `API_URL=http://localhost:8000`, but that
same export is what the subsequent `next start` inherits — the build itself would not
fail without it.

**C10 — UID 10001 has no writable home, and fontconfig caches fonts there.** The
`python:3.12-slim` image declares no `HOME`, so with a numeric `USER 10001` the process
starts with `HOME` unset or pointing at a root-owned path — either way fontconfig has no
writable cache directory. It falls back, warns on stderr, and each worker rebuilds its
font cache; WeasyPrint pays that cost per process, and there are two workers.
`ENV HOME=/tmp XDG_CACHE_HOME=/tmp/.cache` makes the behaviour deterministic regardless of
which of the two it is. (The earlier wording claimed the base image sets `HOME=/root`;
that was an assumption, not something we verified, and Docker is not available in the
environment this review ran in. The fix is the same either way.)

**C11 — `COPY apps/api /code` would ship the test suite.** `apps/api/` contains `tests/`,
`perf_ids.txt` and the Dockerfile itself. The runtime image should carry `app/` and
`pyproject.toml`, not a second copy of the suite (D6). Excluding it from the build context
is safe for CI because CI's container sees the source through the bind mount
(`docker-compose.yml:21`), not through the image.

**C12 — the `dev` targets deliberately contain no application source.** Both images'
`deps` and `dev` stages install dependencies only; the source arrives from the bind
mounts (`./apps/api:/code` and `./apps/web:/code`). That is what makes the dev images
cheap and cache-stable, but it means `docker run <api-dev image> pytest` finds nothing.
Worth stating plainly, because the next person to debug CI will try exactly that.

**C13 — `pnpm-workspace.yaml` changes how `pnpm install` behaves.** It carries
`ignoredBuiltDependencies: [sharp, unrs-resolver]`, which is the pnpm 10 build-script
allow-list. If the file is absent when `pnpm install` runs, the install uses different
settings than CI does (CI runs from `apps/web`, where the file is present). Copy it with
`package.json` and the lockfile, before the install — not with the later `COPY apps/web ./`.

**C14 — the web image needs a `dev` target too, or `make up` breaks.** This is the one
blocking defect found in the 2026-11-06 review. The dev compose service is
`docker-compose.yml:45-50`: `build: ./apps/web`, `volumes: ["./apps/web:/code"]`,
`command: pnpm dev`. A multi-stage Dockerfile builds its **last** stage when no `target`
is given. If that last stage is `runtime`, the container starts with `WORKDIR /app`,
`NODE_ENV=production` and `--prod`-only `node_modules` — while the source is mounted at
`/code`. `next dev` then runs in `/app` with no `app/` directory, no `next.config.ts` and
no `tailwindcss`; the dev stack is dead on the first `make up`.

It does not get caught by CI either: `ci.yml:172-181` bakes only `api` and
`search-worker`; the e2e job builds and starts web **on the runner**
(`ci.yml:238-272`), never as this image. So the failure would surface on a developer's
machine, not in a check.

**Fix:** give the web Dockerfile a `deps` stage (`WORKDIR /code`, full dependency set, no
source) and a `dev` stage inheriting it, and set `target: dev` in the dev compose file —
exactly the shape the api image already uses (C12). The production compose file overrides
`target: runtime`.

**Verified 2026-11-08 — the first version of this fix was still incomplete.** A `dev`
target alone is not enough. The bind mount at `/code` shadows the image's
`/code/node_modules`, so `pnpm dev` had been using the **host's** `apps/web/node_modules`.
On Windows that fails: pnpm's host links are absolute
`/c/Users/.../node_modules/.pnpm/...` paths that do not exist inside a Linux container,
and `next dev` dies with `Cannot find module '/code/node_modules/next/dist/bin/next'`.

The correction is an **anonymous volume** in the dev compose service:

```yaml
    volumes:
      - ./apps/web:/code
      - /code/node_modules
```

Docker seeds that volume from the image on first creation, so the container uses the
Linux-correct `node_modules` the `deps` stage installed. This also removes the old
assumption that `make up` requires a local `pnpm install` on the host — a small win on
every platform, and the difference between working and not working on Windows. If
`apps/web/package.json` changes, the anonymous volume has to be recreated
(`docker compose down -v` for the dev stack, or a fresh `up --build --renew-anon-volumes`).

**C15 — the WeasyPrint apt layer must be shared across stages.** See C4. The evidence
is the `dev` container's startup failure; `deps`/`dev` are not merely "dependency only"
stages, they are the environment CI imports the whole application in.

**C16 — the runtime `CMD` must not go through corepack.** The first draft used
`CMD ["pnpm", "start"]`. Under `USER 10001` corepack tries to re-resolve the pinned pnpm
at container start; with no writable `HOME` it attempts
`mkdir '/.cache/node/corepack/v1'` and exits with `EACCES`. The build-time copy lives in
`/root/.cache` (root-owned), and even a writable cache would leave a production container
needing network access at startup. Call the bundled binary directly instead:

```dockerfile
CMD ["node", "node_modules/next/dist/bin/next", "start"]
```

`pnpm` remains a build-time tool only, which is what a production image should want.
The same reasoning applies to the `HEALTHCHECK`: it uses `node -e` and never touches a
package manager.

**C17 — the web runtime needs a writable `.next/cache`.** Found in the second review
(2026-11-08), after the 17 checks had already passed. `COPY --from=build /code/.next`
lands as **root**, while the process runs as `USER 10001`; `touch
/app/.next/cache/.probe` inside the running container returns `Permission denied`.
Nothing in today's app writes there — no `next/image`, and server-side fetches default to
no-store — which is exactly why all 17 checks stayed green. The first ISR page, image
optimisation call or persistent fetch cache would fail with `EACCES`, on a customer's box,
with no build-time warning. `RUN mkdir -p /app/.next/cache && chown -R 10001:10001
/app/.next/cache` **after** the COPY is the whole fix. This is the same class of bug as
C6 (upload root) and C10 (fontconfig cache): a non-root process inherits root-owned
directories from the build.

---

## 3. Proposed `apps/api/Dockerfile`

```dockerfile
# Build context is the repository root:
#   docker build -f apps/api/Dockerfile .
# db/ has to be in the image: Makefile runs `alembic -w /db`, and app/meta.py
# reads the schema head from /db/alembic.ini (C2).

# ---- base: WeasyPrint system libraries, shared by every stage (C4/C15) ----
FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

# ---- deps: runtime dependencies only ----
FROM base AS deps
ENV PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /code
# pyproject.toml on its own, on purpose: see C8.
COPY apps/api/pyproject.toml /code/pyproject.toml
RUN pip install -e .

# ---- dev: adds the test toolchain. CI runs the suite in this target (C1). ----
FROM deps AS dev
RUN pip install -e ".[dev]"

# ---- runtime ----
FROM base AS runtime
COPY --from=deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPYCACHEPREFIX=/tmp/pycache \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache
WORKDIR /code
COPY apps/api /code
COPY db /db
# Upload root and font cache, writable by the unprivileged user (C6, C10).
RUN mkdir -p /uploads /tmp/.cache && chown -R 10001:10001 /uploads /tmp/.cache
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live').status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips=*", "--workers", "2"]
```

**Notes on the choices**

- **Four stages, default last.** `base → deps → dev → runtime`: `base` carries the apt
  layer every stage needs (C15), `deps` the venv, `dev` the test toolchain. The runtime
  image inherits the dependency layer and never sees pytest, so the "no pytest in
  production" rule is structural rather than a `pip uninstall` that someone can drop.
  `runtime` is last so a bare `docker build` produces the production shape — fail-safe.
- **`dev` does not re-copy `pyproject.toml`.** It inherits it from `deps`; repeating the
  `COPY` in the first draft was redundant and would only invalidate the layer twice.
- **`--proxy-headers` needs `--forwarded-allow-ips`.** Uvicorn trusts forwarded headers
  only from `127.0.0.1` by default, so without the second flag the reverse proxy decided
  in Q1 would have its `X-Forwarded-*` silently ignored and the flag would look applied
  while doing nothing. `*` is acceptable here because the only thing that can reach
  `:8000` is the proxy on the compose network.
- **Two workers, not four.** `--workers` forks the process; the search outbox is drained
  by a separate container, and there is no in-process scheduler, so forking is safe —
  but each worker carries WeasyPrint and its own font cache. Two is the low-memory
  default; a customer with more CPU raises it in their compose override. (D4.)
- **`PYTHONPYCACHEPREFIX`** keeps `.pyc` writes out of `/code` and `/db`, so both can be
  read-only at runtime.
- **`HOME`/`XDG_CACHE_HOME`** give fontconfig a writable cache inside the image (C10).
  `/tmp` is used deliberately: nothing there needs to survive a restart, and it needs no
  volume.
- **`APP_VERSION`** is the build arg `GET /version` reports (#179, `config.py:13`). It
  stays `dev` unless the release pipeline passes it, so a locally built image cannot
  claim to be a release.
- **`uvicorn[standard]` is already a dependency** (`pyproject.toml:16`) — no gunicorn, no
  process supervisor. The container runs one process; restart policy is the
  orchestrator's job.

---

## 4. Proposed `apps/web/Dockerfile`

```dockerfile
# Build context is the repository root:
#   docker build -f apps/web/Dockerfile .

# ---- deps: full dependency set, no source (C12/C14) ----
FROM node:22-slim AS deps
ENV NEXT_TELEMETRY_DISABLED=1
# No pnpm version here on purpose: corepack reads packageManager from
# package.json, which is the one pin CI and the image share (D7).
RUN corepack enable
WORKDIR /code
# pnpm-workspace.yaml carries ignoredBuiltDependencies; without it the install
# runs with different settings than CI (C13).
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

# ---- dev: what the dev compose file builds (C14) ----
# WORKDIR stays /code, NODE_ENV stays development; source and node_modules
# arrive from the ./apps/web:/code bind mount.
FROM deps AS dev
ENV NODE_ENV=development

# ---- build: the production bundle ----
FROM deps AS build
COPY apps/web ./
# The one build-time value (C7). Default matches .env.example:19.
ARG NEXT_PUBLIC_PROCUREMENT_UI_READY=1
ENV NEXT_PUBLIC_PROCUREMENT_UI_READY=${NEXT_PUBLIC_PROCUREMENT_UI_READY}
RUN pnpm build

# ---- runtime ----
FROM node:22-slim AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /app
COPY --from=build /code/package.json /code/pnpm-lock.yaml /code/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --prod
COPY --from=build /code/.next ./.next
COPY --from=build /code/public ./public
# Next writes ISR / fetch / image-optimisation caches under .next/cache at
# runtime. The COPY above lands as root, so UID 10001 would hit EACCES the
# first time a cache is written (C17). This must come after the COPY.
RUN mkdir -p /app/.next/cache && chown -R 10001:10001 /app/.next/cache
USER 10001
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/api/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
# Not `pnpm start`: see C16.
CMD ["node", "node_modules/next/dist/bin/next", "start"]
```

**Notes on the choices**

- **`node:22`, not `node:20`.** CI builds and typechecks on Node 22 (`ci.yml:111,218`),
  so 22 is the version everything is actually tested against. Node 20 is also the version
  currently in the Dockerfile, which means the image and CI disagree today.
- **`pnpm install --frozen-lockfile`, no `|| true`.** The current image swallows install
  failures (`apps/web/Dockerfile:5`), which is how a broken dependency reaches
  production looking healthy. With `--frozen-lockfile` a package.json/lockfile mismatch
  fails the build — that is the whole point (§1.2 acceptance).
- **Re-install in the runtime stage rather than `COPY --from=build node_modules`.** pnpm's
  `node_modules` is a store plus symlinks; copying it across stages mostly works and then
  fails in ways that look like application bugs. The second install is slower and honest.
- **No `next.config.ts` in the runtime image, on purpose.** It only sets
  `allowedDevOrigins` (dev-only), and `next start` reads the build's own
  `required-server-files.json`. Copying a `.ts` config into a `--prod` image would add a
  loader path that CI never exercises. **Revisit if the config ever gains a
  runtime-affecting key** (`basePath`, `distDir`, `images`) — at that point the build and
  the runtime would diverge silently, which is the failure mode this note exists to
  prevent.
- **The healthcheck goes through the app's own proxy route** (`/api/health` → the api's
  `/health`, `api/[...proxy]/route.ts`), not a synthetic endpoint: it exercises the Next
  server *and* the hop to the api. It uses the built-in `fetch`, so no `curl` in the
  image. Note that this makes the web container report unhealthy while the api is down —
  that is a readiness signal, not liveness. Do not wire it to an automatic restart, or
  api downtime will flap the web tier too.
- **`output: "standalone"` is not in this change.** It would cut the runtime image
  substantially, but it changes how static assets and `next start` behave and would need
  the full e2e suite to prove. Separate PR, after this one is on `main` (D2).
- **`.next/cache` is chowned after the COPY (C17).** A `standalone` build would change
  where that directory lives, so PR C must re-check ownership rather than assume this
  line still applies.
- **Four targets, `runtime` last.** `dev` and `build` both branch off `deps`, so neither
  repeats the install. `runtime` is last so a bare `docker build` stays production-shaped.
  `dev` is reachable only because compose names it explicitly — see C14 for why that is
  mandatory and not cosmetic.
- **The flag must also be present at runtime.** The build `ARG` covers the inlined path
  (C7). `docker-compose.prod.yml` must keep `NEXT_PUBLIC_PROCUREMENT_UI_READY` in its
  `env_file` / `environment` as well, so that a future refactor which reads it in a
  server component at runtime does not silently resolve to `undefined`. Do not strip
  `NEXT_PUBLIC_*` when writing the production env whitelist.

**Resolved during the re-check (was V2):** the pnpm 10 build-script question is already
answered in the tree — `apps/web/pnpm-workspace.yaml` lists `sharp` and `unrs-resolver`
under `ignoredBuiltDependencies`. Nothing to add; just copy the file before installing
(C13).

---

## 5. Repository changes the images require

**`docker-compose.yml`** (the dev file — it stays the dev file):

```yaml
  api:
    build:
      context: .                       # C2/C3: db/ has to be in the image
      dockerfile: apps/api/Dockerfile
      target: dev                      # C1: CI runs pytest in here
  search-worker:
    build:
      context: .
      dockerfile: apps/api/Dockerfile
      target: dev
  web:
    build:
      context: .
      dockerfile: apps/web/Dockerfile
      target: dev                      # C14: `pnpm dev` must run in /code, not /app
    volumes:
      - ./apps/web:/code
      - /code/node_modules             # C14: keep the image's Linux node_modules
```

Setting `target: dev` in the compose file is what keeps CI untouched: `docker/bake-action`
reads the same file (`ci.yml:42-50`), so it builds `dev` without any workflow edit. The
production file written in §8 of the checklist overrides `target: runtime` for all three
services. The alternative — leaving the default as `dev` and overriding in production
only — also works but makes a bare `docker build` produce a test-bearing image.

Because the `dev` targets carry no source (C12, C14), the dev file's bind mounts stop
being a convenience and become load-bearing. They must not be removed — and the web one
must keep pointing at `/code`, because that is the `dev` stage's `WORKDIR`. The
`/code/node_modules` anonymous volume is equally load-bearing: it is what keeps those
Linux-correct dependencies visible under the source mount (C14).

**New root `.dockerignore`** (C3, C11):

```
.git
.env
**/node_modules
**/.next
**/.venv
**/__pycache__
**/*.pyc
.pytest_cache
apps/api/tests
apps/api/perf_ids.txt
legacy
docs
tests
.github
New system pictures
```

`apps/web/.dockerignore` already exists and can stay — but note it stops applying once the
web build context becomes the repository root; the root file has to carry those rules.

**No `seed/` in the production api image at all.** With the fonts moved (D3) there is
nothing left in `seed/` that belongs in front of a customer — it is a dev dataset with a
fixed roster of staff accounts and a published password (Q12) — so the runtime image
simply does not copy it. The `dev` target keeps getting it through the compose bind mount,
which is how CI seeds.

---

## 6. Decisions

Settled, recorded here so the Dockerfiles have one source of truth.

| # | Decision | Outcome |
| --- | --- | --- |
| **D1** | Keep a `dev` target with pytest, or move CI off the image | **Keep the target.** CI keeps proving the image we ship; `build.target: dev` in compose selects it without a workflow edit |
| **D2** | `output: "standalone"` now or later | **Later, its own PR.** The size win is real, the risk is asset handling, and e2e is the only thing that can settle it |
| **D3** | PDF fonts: copy `seed/fonts` into the image, or move them | **Move to `apps/api/app/printing/fonts/`**, four `url()` entries become `../fonts/X`. Nothing named `seed` ships to a customer |
| **D4** | `--workers` default | **2**, with `--proxy-headers` and `--forwarded-allow-ips=*`. Forking is safe (no in-process scheduler); WeasyPrint makes each worker expensive |
| **D5** | Build-time env for the web image | **One `ARG`: `NEXT_PUBLIC_PROCUREMENT_UI_READY`, default `1`.** It is inlined at build; `SESSION_COOKIE_NAME` and `API_URL` stay runtime-only |
| **D6** | Does the runtime api image carry `tests/`? | **No.** `apps/api/tests` and `perf_ids.txt` leave via `.dockerignore`; CI keeps its tests through the bind mount (C11, C12) |
| **D7** | Where the pnpm version is pinned | **`apps/web/package.json`'s `packageManager` field**, exact **`pnpm@10.34.9`** (settled 2026-11-03, verified 2026-11-06). The image and a developer's shell read it via corepack. CI still installs pnpm with `pnpm/action-setup@v4` and `version: 10` — a **major range** — so all three coincide today but are **not** guaranteed to stay in step. See the CI caveat in Q15 |

---

## 7. New open questions this raised

**Q12 — how does a brand-new customer database get its starting rows?**
The only seeding tool is `python -m seed.hartwood_joinery`, and it is a **dev** seed: one
workspace, a fixed roster of staff accounts all with the password `hartwood-dev`, demo
projects and items. It is also the only thing that populates the reference tables the rest
of the schema depends on — `stages` (10 rows) and `status_options` (6 rows), inserted at
`seed/hartwood_joinery.py:205-230`. So a customer install cannot run it as-is (it would
create accounts with a published password) and cannot run without it (nothing else fills
those tables). This is not a Dockerfile problem — D3 already settled that the image
carries no `seed/` — but §1 is where it surfaces, and it blocks the first customer
install. Options: a separate `seed/reference.py` for the lookup tables only, plus a
first-run "create workspace + first admin" step; or move the reference rows into a
migration so an empty database is a usable one. **Blocks the first customer install, not
this PR.**

*Correction to the earlier wording:* `status_symbols` is **not** seeded — the table is
created at `db/alembic/versions/0001_tracking_port.py:81` and no seed or migration inserts
rows into it. It is a cosmetic per-item flag (`docs/archive/2026-04-25-pm-workbench.md:403`),
so an empty table is not what blocks a first install; `stages` and `status_options` are.

**Q13 — do the images need to be reproducible (pinned digests)?**
`python:3.12-slim` and `node:22-slim` float. Pinning by digest makes an image rebuildable
byte-for-byte, which matters if a customer ever asks "is this the image the one we
audited?"; it also means a base-image security fix requires a commit. Not urgent, but it
is much cheaper to decide before the release pipeline (§9) is built than after.

**Q14 — image tags and where they are pushed** is **Q4** in the register
(registry vs offline bundle). It does not change anything in these Dockerfiles.

**Q15 — one pnpm version, in one place. DECIDED 2026-11-03: the `packageManager` field.**
The problem it settles: the draft pinned `pnpm@10.34.9` in the Dockerfile, CI pins
`version: 10` (`ci.yml:105,212`) and `apps/web/package.json` declares nothing — three
sources, two of them ranges. `"packageManager": "pnpm@10.34.9"` in
`apps/web/package.json` is now the pin the **image** and a **developer's shell** read
(corepack and pnpm both honour it); the Dockerfile needs no version of its own.

**CI is the exception, and an earlier version of this section got it wrong.** CI does not
use corepack — it installs pnpm with `pnpm/action-setup@v4` and an explicit `version: 10`,
a major range. All three resolve to 10.34.9 today (verified 2026-11-08: the image's
corepack, `corepack pnpm` on the host, and even the host's pnpm 11.6.0 invoked from
`apps/web/` all report 10.34.9), but they do so **independently**. A 10.35.0 release would
move CI while the image stays pinned. "Cannot drift by construction" was too strong; the
honest statement is "coincide today".

Two implementation notes:

- **The exact version — settled 2026-11-06: `pnpm@10.34.9`.** `npm view 'pnpm@10' version`
  shows it exists and is the latest 10.x; the lockfile is `lockfileVersion: 9.0`, the pnpm
  10 lineage. The number in the first draft was right — it was simply never checked.
- **Keep `version: 10` in CI. Do not just drop it.** The previous wording here suggested
  "drop the `version` input so the action reads `packageManager`; both work" — **that would
  break CI**. `pnpm/action-setup@v4` defaults `package_json_file` to `package.json` at
  `GITHUB_WORKSPACE` (the repo root), and this repo has **no root `package.json`**; the
  field lives in `apps/web/package.json`. With `version` removed the action finds no
  `packageManager` and fails with `No pnpm version is specified`. It also throws
  `Multiple versions of pnpm specified` if a `version` input and a *visible*
  `packageManager` ever disagree. Exactly two safe configurations exist: keep
  `version: 10` (current state), or remove `version` **and** add
  `package_json_file: apps/web/package.json` to both action steps. Keep the first — the
  lockfile is 9.0 and a pnpm 10.x patch drift does not invalidate it.

---

## 8. Acceptance

Run against the built images, not against a compose-up dev stack — with one deliberate
exception: the C14 check has to prove that `make up` still works.

| Check | Expected |
| --- | --- |
| `docker run --rm <api-runtime> pip list \| grep -ci pytest` | `0` |
| `docker run --rm <api-runtime> id -u` | `10001` |
| `docker run --rm <api-runtime> test ! -d /code/tests` | exit 0 (proves D6) |
| `docker run --rm <api-runtime> python -c "import weasyprint; from weasyprint import HTML; print(len(HTML(string='<p>x</p>').write_pdf()))"` | prints a byte count > 1000 (proves C4) |
| the same command with `2>` captured | **empty stderr** — no fontconfig warnings (proves C10) |
| `docker run --rm <api-runtime> test -f /code/app/printing/fonts/Inter-Regular.woff2` | exit 0 (proves C5) |
| Render a quote PDF in the container and open it | Inter / JetBrains Mono actually embedded, not substituted |
| `docker run --rm <api-runtime> test -f /db/alembic.ini` | exit 0 (proves C2) |
| Start api + db, `curl /health/ready` | 200 after migrations (already covered by #179) |
| Start api only, `curl /version` | `{"version": "dev", "schema_head": "…", …}` |
| `docker run --rm <web-runtime> node -e "console.log(process.getuid())"`; plus `docker run --rm --entrypoint sh <web-runtime> -c 'touch /app/.next/cache/.probe'` | `10001`; exit 0 (proves C17) |
| `docker run --rm <web-runtime> ls node_modules \| grep -c "typescript"` | `0` (no devDependencies) |
| Build with `--build-arg NEXT_PUBLIC_PROCUREMENT_UI_READY=0`, log in, open `/tracking` | the Procurement entry point is **absent**; rebuild with the default and it is **present** (proves D5 is wired) |
| Start web + api, `curl -I localhost:3000` and one authenticated e2e spec | 200 / pass |
| Deliberately corrupt a version in `apps/web/package.json` | **build fails** (proves `|| true` is gone) |
| `docker build -f apps/web/Dockerfile --target build .` with no api or db container running | build succeeds (proves C9) |
| `make up`, then `curl -s -o /dev/null -w '%{http_code}' localhost:3000/login` | `200`, and `docker compose logs web` shows `next dev` (proves C14 — the dev stack is not broken by the new last stage) |

The last one is the acceptance test that matters most: the current image cannot fail. The
one above it is the second: an image that quietly loses a feature is the failure mode a
green build does not catch.

**Three methods that produce false results if done the obvious way** (all three were hit
during the 2026-11-08 run):

- **Row 7 — use the application's own stylesheet path.** Rendering with
  `weasyprint.CSS(filename=...)` passed via `stylesheets=[...]` resolves the `@font-face`
  URL against the CSS *file* URL rather than the template's `base_url`, so the fonts are
  not found and the PDF falls back to Liberation Mono — a **false FAIL**. The application
  loads the stylesheet through `<link rel="stylesheet" href="print.css">` in
  `templates/_base.html`; reproduce that (`HTML(string=..., base_url=TEMPLATES_DIR)` with
  the link in the markup) and inspect `/BaseFont` in the PDF with `pypdf`.
- **Row 13 — diff the compiled chunk, not `page.js`.** `.next/server/app/(app)/tracking/page.js`
  is a ~1 KB re-export stub and is byte-identical between the two builds. The flag lands
  in `.next/server/chunks/ssr/[root-of-the-server]__*.js` as
  `procurementReady:!0` (ARG=1) versus `procurementReady:!1` (ARG=0).
- **Row 14 — run the e2e spec against the runtime image, not `next dev`.** On the dev
  stack `POST /auth/login` succeeds and sets the cookie, but `smoke.spec.ts` stays on
  `/login?` — the click-before-hydration race `ci.yml` already warns about. Against
  `next start` the same spec passes in 2.8 s. Row 17 is the *only* check that belongs on
  the dev stack.

---

## 9. Suggested sequence

1. **PR A** — `apps/api/Dockerfile` (`base`/`deps`/`dev`/`runtime`) and
   `apps/web/Dockerfile` (`deps`/`dev`/`build`/`runtime`), root `.dockerignore`, compose
   build blocks with `context: .` / `target: dev` for all three services **plus the web
   `/code/node_modules` anonymous volume**, the `packageManager` pin (Q15), the font move
   with its four `url()` edits, the direct-`next` `CMD` (C16), the `.next/cache` chown
   (C17), and the stale `.env.example:6-7` comment (C7). CI stays green because `dev` is
   what CI builds. All of this is already implemented and verified on the local
   `feat/prod-images` branch (§10.2, §10.3) — **not pushed**. Before merging, re-run
   `make up` and the §8 table; the defects in §10.2/§10.3 were invisible until a
   container was actually started. **Leave `ci.yml` alone** — Q15's "drop `version`"
   suggestion was wrong and has been removed.
2. **PR B** — `docker-compose.prod.yml` with `target: runtime` (part of checklist §8):
   this is where the runtime image first gets exercised, and where C6/C10 stop being
   theoretical.
3. **PR C (optional, later)** — `output: "standalone"` slimming, behind a full green e2e
   run.

Nothing here touches §7.1 (Meili tenant tokens) or §7.2 (`/public/stats`); both are
Phase 1 following the D1 decision.

---

## 10. Verification log — what the 2026-11-03 re-check changed

Each row is a claim in the first draft that the tree disagreed with, and what replaced it.

| # | First draft said | The tree says | Now |
| --- | --- | --- | --- |
| 1 | The web image needs **no** build-time environment | `NEXT_PUBLIC_PROCUREMENT_UI_READY` is inlined at build (`ci.yml:239`, `tracking/page.tsx:97`) | **C7 rewritten, D5 added**: one `ARG`, default `1` |
| 2 | `docker-compose.yml:36` starts `search-worker` | it is line `39` | citation fixed |
| 3 | `.env.example:26` is the Procurement flag | it is line `19` | citation fixed |
| 4 | CI's pytest is at `ci.yml:82` | it is line `75`; migrations `:65`, seed `:72` | citations fixed |
| 5 | Q12: the seed is the only thing filling `stages` / `status_options` / `status_symbols` | `status_symbols` is filled by nothing at all, and is cosmetic | Q12 corrected |
| 6 | "verify during implementation: pnpm may block build scripts" | `apps/web/pnpm-workspace.yaml` already lists them as ignored | replaced by C13 (copy it before install) |

Four further items were **added** rather than corrected, because the first draft did not
consider them: C9 (the build needs no api — what makes the single-stage build possible),
C10 (fontconfig under a numeric UID), C11/D6 (the test suite riding along in `COPY
apps/api`), and C12 (the `dev` target is source-less by design).

Two claims were re-verified and stand unchanged: the four `url()` entries in `print.css`
and their resolution against `TEMPLATES_DIR` (C5), and `FILE_STORE_ROOT` defaulting to
`/uploads` at `files/store.py:62` (C6).

### 10.1 Review before merging PR #181 — 2026-11-06

One blocking defect, one unverifiable assertion, two gaps in verification, and one count:

| Severity | Finding | What changed |
| --- | --- | --- |
| **Blocking** | The web Dockerfile had only `build` and `runtime` stages while the dev compose file named no `target`. Compose builds the last stage, so `make up` would run `pnpm dev` in `/app` (`NODE_ENV=production`, `--prod` deps) with the source mounted at `/code`. CI would not catch it — `ci.yml:172-181` bakes only `api` and `search-worker`, and e2e builds web on the runner | **C14 added**, web Dockerfile gains `deps` + `dev` stages, compose gains `target: dev`, two acceptance rows added, §9 PR A now requires `make up` |
| Accuracy | C10 asserted the base image sets `HOME=/root`. Docker was not available to verify it, and the official image declares no `HOME` | **C10 reworded** to the observable fact (no writable cache dir for a numeric UID); the `HOME`/`XDG_CACHE_HOME` fix is unchanged and is now justified without the assumption |
| Gap | C9 asserted `next build` needs no reachable api but had no acceptance command | **row added** to §8: build `--target build` with no api/db running |
| Gap | Nothing proved the production env whitelist keeps the Procurement flag | **note added** to §4: prod compose must keep `NEXT_PUBLIC_PROCUREMENT_UI_READY` in `env_file`/`environment` |
| Count | The PR body said "14 acceptance commands"; the table already had 15 | corrected in the PR body — it now has **17** |

**Not verified in this review:** none of the §8 commands were executed — there was no
Docker daemon in the environment at the time. That gap was closed on 2026-11-08; see
§10.2.

### 10.2 Acceptance run — 2026-11-08

Docker Desktop 4.94.0 / Engine 29.8.2 on Windows, local branch `feat/prod-images`.
All five images (`api:dev`, `api:runtime`, `web:dev`, `web:build`, `web:runtime`, plus a
`web:flag0` variant) were built from the repository root, then all 17 rows were run.

| # | Result | Evidence |
| --- | --- | --- |
| 1 | PASS | `pip list \| grep -ci pytest` → `0` |
| 2 | PASS | `id -u` → `10001` |
| 3 | PASS | `/code` contains `Dockerfile`, `app`, `pyproject.toml` — no `tests/` |
| 4 | PASS | WeasyPrint rendered 2150–2151 bytes |
| 5 | PASS | stderr empty on PDF render |
| 6 | PASS | `/code/app/printing/fonts/Inter-Regular.woff2` present |
| 7 | PASS | linked stylesheet embeds `/RQQJXR+Inter` and `/KTPBXU+JetBrains-Mono` (see method note in §8) |
| 8 | PASS | `/db/alembic.ini` present |
| 9 | PASS | after `alembic upgrade head` (→ `0089`) and seed: `{"ok":true,...,"schema_match":true}`, HTTP 200 |
| 10 | PASS | api alone: `{"version":"dev","schema_head":"0089","db_schema":null}` |
| 11 | PASS (C17 added later) | `process.getuid()` → `10001`; the `.next/cache` writability assertion was added in §10.3 and re-run there |
| 12 | PASS | runtime `node_modules` has no `typescript` |
| 13 | PASS | ssr chunk `procurementReady:!0` (default) vs `!1` (`ARG=0`) |
| 14 | PASS | runtime stack `curl -I /login` → 200; `smoke.spec.ts` (login → six tabs → logout) `1 passed (2.8s)` |
| 15 | PASS | corrupting `next` to `16.2.5` → `ERR_PNPM_OUTDATED_LOCKFILE`, build exit 1 |
| 16 | PASS | `--target build` succeeded with no api/db container running |
| 17 | PASS | `make up` → `/login` 200, web log `▲ Next.js 16.2.4 … Ready in 741ms` |

**Three design defects the run exposed.** None were hypothetical; each stopped a container.
All are fixed in the local implementation and in §2–§5 above.

| # | Symptom | Root cause | Fix |
| --- | --- | --- | --- |
| 1 | api dev container: `OSError: cannot load library 'libgobject-2.0-0'`; CI's pytest would never start | WeasyPrint apt layer was in `runtime` only, but `app/main.py` imports weasyprint on startup in **every** target | shared `base` stage (C4, C15) |
| 2 | web dev container: `Cannot find module '/code/node_modules/next/dist/bin/next'` | bind mount shadowed the image's `node_modules`; on Windows the host's pnpm links are absolute `/c/Users/...` paths | anonymous `/code/node_modules` volume (C14) |
| 3 | web runtime container exited 1: `EACCES: mkdir '/.cache/node/corepack/v1'` | `CMD ["pnpm","start"]` re-resolves corepack as UID 10001; build-time cache is in root-owned `/root/.cache` | call `next` directly, no package manager at runtime (C16) |

**Also confirmed empirically:** `USER 10001` in `python:3.12-slim` gets `HOME=/` (not
`/root`) and no `XDG_CACHE_HOME` — so the C10 rewording was right and the original claim
was wrong. `corepack` resolved `pnpm v10.34.9` from `packageManager` in both the image and
the host (D7). `expected_schema_head()` returned `0089` from `/db/alembic.ini` even with
no database reachable (C2).

**Environment caveats, not design issues:** on Git Bash, `docker compose exec -w /db`
needs `MSYS_NO_PATHCONV=1` or Docker reports `Cwd must be an absolute path`; and
Playwright's output-directory cleanup tripped the host's bulk-delete guard, so the spec
was run with `--output` pointed at a fresh directory. Neither changes any conclusion.

**What this does not prove:** the production compose file (`docker-compose.prod.yml`,
PR B) was not exercised; the runtime stack here was assembled manually from the two
runtime images. C6 (upload ownership under a named volume) and the §5 restore drill are
still unverified.

### 10.3 Second review — 2026-11-08 (before opening PR A)

A read-through of the whole `feat/prod-images` diff, plus checks the 17-row table did not
cover. No code was changed during the review itself; the two fixes were applied
afterwards.

**Checks that were added, not repeated:**

| Check | Result |
| --- | --- |
| `docker buildx bake -f docker-compose.yml --print api` | resolves `context: .`, `dockerfile: apps/api/Dockerfile`, `target: dev` — the workflow's bake step will read the new build blocks |
| `pytest -q tests/test_public_stats.py` inside the **dev** service | `2 passed` — C1 holds; the 17-row table never ran pytest |
| `docker compose ps` | all five dev services Up; `search-worker` stable for 30 min |
| `docker compose up --help \| grep renew-anon` | `-V, --renew-anon-volumes` exists, so the C14 rebuild advice is executable |
| §3/§4 Dockerfile snippets vs the real files (normalised diff) | byte-identical after the C17 edit |
| Full-tree grep for `seed/fonts` | only `print.css` (new `../fonts/` paths) and historical archive docs remain |

**Two findings, both fixed:**

| # | Severity | Finding | Fix |
| --- | --- | --- | --- |
| 1 | **High (documentation)** | §7 Q15 advised dropping `version: 10` from `pnpm/action-setup@v4` so it would read `packageManager`. That fails: the action defaults `package_json_file` to a **root** `package.json`, which this repo does not have, and throws `No pnpm version is specified`. D7 and the checklist also overstated "cannot drift" — CI uses pnpm via the action, not corepack | Q15 rewritten with the action's source-level behaviour and the two safe configurations; D7, the checklist row and the header note now say the three versions *coincide today* rather than being drift-proof. **No `ci.yml` change was made — `version: 10` stays** |
| 2 | **Medium (runtime)** | `/app/.next/cache` is root-owned; `touch` as UID 10001 returns `Permission denied`. Invisible today (no `next/image`, fetches default to no-store), but ISR / image optimisation would fail on a customer's box | `RUN mkdir -p /app/.next/cache && chown -R 10001:10001 /app/.next/cache` after the `.next` COPY, in both the implementation and §4's snippet; recorded as C17 and added to §8 row 11 |

**Re-verification after the chown:** the web runtime image was rebuilt;
`docker run --rm --entrypoint sh jf-verify/web:runtime -c 'id -u; touch
/app/.next/cache/.probe'` printed `10001` and `C17_WRITABLE=PASS`, with `ls -ld` showing
the directory owned by `10001:10001`. The runtime web container came up `healthy`,
`/login` returned 200, and `smoke.spec.ts` passed again. Row 11's expected result was
updated accordingly.

**One environment trap worth recording:** the review ran
`pytest tests/test_public_stats.py` inside the dev service to prove C1. pytest truncates
workspace-scoped tables (`ci.yml:67-70` documents this), which deleted the seeded users;
the next e2e run then failed with `POST /auth/login → 401 invalid credentials`. That was
**not** a regression from the chown — re-running `python -m seed.hartwood_joinery`
restored login to 200 and the spec passed again. If pytest and an e2e run share a
database, re-seed between them.

**Still open, deliberately not in scope for these two fixes:** the web runtime has no
explicit `HOME` (harmless now that C16 removed corepack from the startup path, but it is
inconsistent with the api image); `.dockerignore` does not exclude local-only directories
such as `.workbuddy-ai/` or `test-results/` (they enter the build context but are never
`COPY`ed into an image); and `docs/archive/2026-05-02-pdf-generation.md` still describes
`seed/fonts/` — a historical record, left as-is.

---

## 11. PR B — the production compose file (2026-11-08, branch `feat/prod-compose`)

PR A made the images; PR B is the first thing that **runs** them with real
configuration. It also closes checklist §3 items 2–3 and §8. The full
customer-facing write-up is `deploy/README.md`; this section records the
decisions and the reasoning that is not obvious from the files.

### 11.1 Decisions taken before writing anything

| # | Question | Decision | Why |
| --- | --- | --- | --- |
| 1 | Where is the proxy? | `JF_WEB_BIND` (default `127.0.0.1`) and `JF_WEB_PORT` (default `3000`, host side only) | Same-host proxy is the safe default; the two variables cover the other-host and port-conflict cases without publishing 3000 to the world. The port variable was added **during verification**: a second local stack could not start because the dev stack already owned 3000 — a collision a customer can hit too. The container and its healthcheck stay on 3000; only the proxy's `upstream` needs to follow |
| 2 | How are images named (Q4 = both)? | `${JF_REGISTRY:-joineryflow}/{api,web}:${JF_VERSION}` | One compose file serves a registry pull and a `docker load` from an offline bundle; the tag is identical in both modes |
| 3 | Production env template | New `deploy/.env.prod.example` | The dev `.env.example` has `COOKIE_SECURE=false` and a published password — copying it would be a security incident, not a shortcut |
| 4 | Who upgrades (Q7)? | The customer | Shapes §9: `upgrade.sh` becomes a customer-facing document; CI holds no host credentials |

`JF_VERSION` is declared with `:?` in all three `image:` lines. That is a
deliberate second purpose beyond "no `:dev` in production": forgetting
`--env-file`, or running the prod file from a source checkout, would otherwise
interpolate the **dev** `.env` (weak password, `COOKIE_SECURE=false`). With `:?`
the command fails immediately instead.

### 11.2 Files

| File | Purpose |
| --- | --- |
| `docker-compose.prod.yml` | Five services, runtime images, no source mounts, no db/api/meili ports, `restart: unless-stopped`, `MEILI_ENV=production`, three named volumes |
| `deploy/.env.prod.example` | Every variable, source noted, `__SET_ME__` placeholders, comments on their own line so the checker never mangles a `#` inside a secret |
| `scripts/check-env.sh` | Pre-flight: non-empty required keys, no placeholders, `COOKIE_SECURE=true`, ≥16-byte Meili key, `APP_VERSION` == `JF_VERSION`; parses rather than sources the file |
| `deploy/proxy/nginx.conf.snippet` | `client_max_body_size 25m`; 120 s read timeout **only** on the three `*.pdf` routes; `X-Forwarded-*` on every path; 60 s global ceiling |
| `deploy/proxy/README.md` | Why each nginx default breaks the app, and the verification steps |
| `deploy/README.md` | First install, both delivery modes, dev/prod diff, decisions, Q12 blocker |

### 11.3 Why `/health/ready` is not a compose startup gate

`web` depends on `api: condition: service_healthy`, and the api image's
`HEALTHCHECK` probes `/health/live`. That is deliberate. Readiness additionally
requires `alembic_version` to equal the image's schema head (Q2 gate 3); on a
brand-new empty database it is false, so making readiness the compose gate would
leave api permanently unhealthy and web would never start — a first-install
deadlock. The one-shot migration container runs **before** `up -d`, and
`upgrade.sh` polls readiness afterwards.

### 11.4 What this PR does not solve

- **Q12 is a real first-install blocker.** Migration creates the schema but not
  its starting rows (`stages`, `status_options`) or the first workspace/admin.
  The only seed is a dev dataset with a published password. `deploy/README.md`
  marks the step explicitly rather than pretending the install is complete.
- `nginx -t` could not be run — nginx is not installed in this environment. The
  snippet must be syntax-checked when merged into a customer's config.
- The external `nc -zv <host> 5432/8000` checks need a real host; locally,
  `docker compose config` expansion (only web has `ports:`) and `docker inspect`
  of the running containers were used instead (§11.5).
- `docker-compose.prod.yml` is not yet exercised by CI; §9 does not exist yet,
  so there is no `upgrade.sh` to consume it. A local end-to-end run was done —
  see §11.5.

### 11.5 Verification of PR B (2026-11-08, local)

Ran the real production file as an isolated compose project (`jf-prod-verify`)
using the PR A runtime images tagged `joineryflow/{api,web}:1.0.0`, with
`JF_WEB_PORT=13001` to avoid the dev stack's 3000. `--env-file` pointed at the
**local dev `.env`**, so this run validates structure and runtime behaviour only —
`GET /version` reported `dev` and `COOKIE_SECURE` was false; neither is a
statement about the production template.

| Check | Result |
| --- | --- |
| `docker compose config --quiet` | OK with `JF_VERSION` set; missing `JF_VERSION` fails with a named error |
| `grep -c "fsync=off" docker-compose.prod.yml` | `0` |
| config expansion: published ports | only web, `127.0.0.1:3000`; db/meili/api/search-worker have none |
| `scripts/check-env.sh` (5 paths) | template → exit 1 with 4 named placeholders; filled → 0; `DATABASE_URL` removed → exit 1 naming it; `COOKIE_SECURE=false` → exit 1; missing file → exit 2 |
| `up -d db meili` → db healthcheck | `healthy` |
| one-shot `run --rm -w /db api alembic upgrade head` | reached `0089` |
| `up -d` all five services | api `healthy`, db `healthy`, meili Up, search-worker Up, web `healthy` |
| `GET /health/ready` (inside api) | `{"ok":true,"db":true,"schema_match":true}` |
| `GET /version` | `{"version":"dev","schema_head":"0089","db_schema":["0089"]}` |
| **C6 — `/uploads` named volume** | `uid=10001`, directory `10001:10001`, `touch` succeeds → **PASS** (previously unverified) |
| `docker inspect PortBindings` | web `{"3000/tcp":[{"HostIp":"127.0.0.1","HostPort":"13001"}]}`; api `{}`; db `{}` |
| host-side HTTP | `/login` 200, `/api/health` 200 |

**Two defects were found by this run.**

1. The first attempt failed with `bind: Only one usage of each socket address`
   because the dev stack already owned `127.0.0.1:3000`. Only `JF_WEB_BIND` was
   configurable, so the host port was fixed. `JF_WEB_PORT` (default 3000, host
   side only) was added to compose, the env template, the nginx snippet's
   upstream note and the deployment docs; the container and its `HEALTHCHECK`
   still use 3000. A customer with another service on 3000 would have hit the
   same wall.
2. `search-worker` came up **unhealthy**. It shares the api **runtime** image,
   whose `HEALTHCHECK` probes `127.0.0.1:8000/health/live` — but the worker runs
   `python -m app.search.worker` and never listens on 8000, so every probe
   failed with a connection error. The dev stack uses the `dev` target (no
   `HEALTHCHECK`), which is why PR A's 17 checks never saw it. Fixed with
   `healthcheck: { disable: true }` on that service; after recreation it reports
   plain `Up`. A meaningful worker liveness signal needs an in-code heartbeat
   and is out of scope here — `restart: unless-stopped` covers crashes only, not
   a stuck retry loop. **Revisit this before the first customer install.**

**Not verified:** `nginx -t` (nginx absent), external `nc` against a real host,
and `Set-Cookie: Secure` behind an actual TLS proxy. Q12 still blocks a genuine
first install.
