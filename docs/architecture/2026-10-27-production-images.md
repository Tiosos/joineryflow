# Production images — design (Phase 0 §1)

**Status: proposed. No Dockerfile has been changed yet.** This document exists so the
shape of the images can be reviewed on its own; the code change is a separate step
after the decisions in §6 are settled.

**Revised 2026-11-03** — every claim below re-checked against the tree at `db6564b`
(the commit that carries the §2 health split). Eight things the original sketch did not
know about are recorded here; four of them came from that re-check and are listed in
§10 with the evidence that corrected them.

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
| `USER 10001` has no home directory, and fontconfig wants a writable cache | Every PDF render rebuilds the font cache unless `HOME`/`XDG_CACHE_HOME` are set (C10) |
| `apps/web/pnpm-workspace.yaml` carries `ignoredBuiltDependencies` | It has to be copied **before** `pnpm install`, or the install runs with different settings than CI (C13) |

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

**C4 — the four WeasyPrint libraries are load-bearing.** `apps/api/Dockerfile:2-5`
installs `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-liberation`. Dropping any
of them does not fail the build; it fails months later when a quote PDF renders without
text. Keep all four, and add a PDF smoke test (§8) rather than trusting the list.

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

**C10 — UID 10001 has no home directory, and fontconfig writes a cache.** `python:3.12-slim`
declares no `HOME`, so a numeric `USER 10001` starts with `HOME=/root` inherited from the
base image's environment — unwritable. fontconfig then falls back, warns on stderr, and
each worker rebuilds its font cache; WeasyPrint pays that cost per process, and there are
two workers. `ENV HOME=/tmp XDG_CACHE_HOME=/tmp/.cache` is the whole fix. It is cheap and
it removes a class of "PDFs are slow on the customer's box and nobody knows why".

**C11 — `COPY apps/api /code` would ship the test suite.** `apps/api/` contains `tests/`,
`perf_ids.txt` and the Dockerfile itself. The runtime image should carry `app/` and
`pyproject.toml`, not a second copy of the suite (D6). Excluding it from the build context
is safe for CI because CI's container sees the source through the bind mount
(`docker-compose.yml:21`), not through the image.

**C12 — the `dev` target deliberately contains no application source.** `deps` and `dev`
install dependencies only; the source arrives from `./apps/api:/code`. That is what makes
the dev image cheap and cache-stable, but it means `docker run <dev image> pytest` finds
nothing. Worth stating plainly, because the next person to debug CI will try exactly that.

**C13 — `pnpm-workspace.yaml` changes how `pnpm install` behaves.** It carries
`ignoredBuiltDependencies: [sharp, unrs-resolver]`, which is the pnpm 10 build-script
allow-list. If the file is absent when `pnpm install` runs, the install uses different
settings than CI does (CI runs from `apps/web`, where the file is present). Copy it with
`package.json` and the lockfile, before the install — not with the later `COPY apps/web ./`.

---

## 3. Proposed `apps/api/Dockerfile`

```dockerfile
# Build context is the repository root:
#   docker build -f apps/api/Dockerfile .
# db/ has to be in the image: Makefile runs `alembic -w /db`, and app/meta.py
# reads the schema head from /db/alembic.ini (C2).

# ---- deps: runtime dependencies only ----
FROM python:3.12-slim AS deps
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
FROM python:3.12-slim AS runtime
# All four WeasyPrint libraries from the current image; see C4.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-liberation \
 && rm -rf /var/lib/apt/lists/*
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

- **Three targets, default last.** `deps → dev → runtime` means the runtime image
  inherits the dependency layer and never sees pytest, so the "no pytest in production"
  rule is structural rather than a `pip uninstall` that someone can drop. `runtime` is
  last so a bare `docker build` produces the production shape — fail-safe.
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
FROM node:22-slim AS build
ENV NEXT_TELEMETRY_DISABLED=1
# No pnpm version here on purpose: corepack reads packageManager from
# package.json, which is the one pin CI and the image share (D7).
RUN corepack enable
WORKDIR /code
# pnpm-workspace.yaml carries ignoredBuiltDependencies; without it the install
# runs with different settings than CI (C13).
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web ./
# The one build-time value (C7). Default matches .env.example:19.
ARG NEXT_PUBLIC_PROCUREMENT_UI_READY=1
ENV NEXT_PUBLIC_PROCUREMENT_UI_READY=${NEXT_PUBLIC_PROCUREMENT_UI_READY}
RUN pnpm build

FROM node:22-slim AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /app
COPY --from=build /code/package.json /code/pnpm-lock.yaml /code/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --prod
COPY --from=build /code/.next ./.next
COPY --from=build /code/public ./public
USER 10001
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/api/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
CMD ["pnpm", "start"]
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
```

Setting `target: dev` in the compose file is what keeps CI untouched: `docker/bake-action`
reads the same file (`ci.yml:42-50`), so it builds `dev` without any workflow edit. The
production file written in §8 of the checklist overrides `target: runtime`. The
alternative — leaving the default as `dev` and overriding in production only — also works
but makes a bare `docker build` produce a test-bearing image.

Because `dev` carries no source (C12), the bind mounts at `docker-compose.yml:21,42,49`
stop being a convenience and become load-bearing. They must not be removed from the dev
file.

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
| **D7** | Where the pnpm version is pinned | **`package.json`'s `packageManager` field** (settled 2026-11-03). CI and the image then read the same pin through corepack, so they cannot drift. Exact version **`pnpm@10.34.9`**, verified 2026-11-06 — see Q15 |

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
sources, two of them ranges. Adding `"packageManager": "pnpm@<exact>"` to
`apps/web/package.json` makes CI, the image and a developer's shell agree by construction,
because `corepack enable` reads that field; the Dockerfile then needs no version at all.

Two details still to settle at implementation time, neither of them a design question:

- **The exact version — settled 2026-11-06: `pnpm@10.34.9`.** `npm view 'pnpm@10' version`
  shows it exists and is the latest 10.x, which is what CI's `version: 10` resolves to
  today; the lockfile is `lockfileVersion: 9.0`, the pnpm 10 lineage. The number in the
  first draft was right after all — it was simply never checked, which is why this
  question existed. Write `"packageManager": "pnpm@10.34.9"`.
- **CI's `pnpm/action-setup@v4` step.** It takes `version: 10` explicitly. Leave it or
  drop the `version` input so the action reads `packageManager`; both work, but only the
  second removes the last duplicated pin.

---

## 8. Acceptance

Run against the built images, not against a compose-up dev stack:

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
| `docker run --rm <web-runtime> node -e "console.log(process.getuid())"` | `10001` |
| `docker run --rm <web-runtime> ls node_modules \| grep -c "typescript"` | `0` (no devDependencies) |
| Build with `--build-arg NEXT_PUBLIC_PROCUREMENT_UI_READY=0`, log in, open `/tracking` | the Procurement entry point is **absent**; rebuild with the default and it is **present** (proves D5 is wired) |
| Start web + api, `curl -I localhost:3000` and one authenticated e2e spec | 200 / pass |
| Deliberately corrupt a version in `apps/web/package.json` | **build fails** (proves `|| true` is gone) |

The last one is the acceptance test that matters most: the current image cannot fail. The
one above it is the second: an image that quietly loses a feature is the failure mode a
green build does not catch.

---

## 9. Suggested sequence

1. **PR A** — `apps/api/Dockerfile` and `apps/web/Dockerfile` (multi-stage, targets),
   root `.dockerignore`, compose build blocks with `context: .` / `target: dev`, the font
   move with its four `url()` edits, and the stale `.env.example:6-7` comment (C7).
   CI stays green because `dev` is what CI builds.
   This PR alone proves C1, C2, C3, C8, C11 and the "install failures fail the build"
   acceptance.
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
