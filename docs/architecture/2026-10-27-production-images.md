# Production images — design (Phase 0 §1)

**Status: proposed. No Dockerfile has been changed yet.** This document exists so the
shape of the images can be reviewed on its own; the code change is a separate step
after the decisions in §6 are settled.

It replaces the sketch in `2026-10-27-phase0-checklist.md` §1 with something that
survives contact with the repository. Four things the sketch did not know about turned
up while checking the code, and each one changes the design:

| Found | Consequence |
| --- | --- |
| CI runs the whole pytest suite **inside** the api image (`ci.yml:41-82`) | The image cannot simply drop pytest — it needs a second target |
| `Makefile:6` runs `alembic` with `-w /db`, and `app/meta.py` probes `/db/alembic.ini` | The api image must contain `db/`, so its build context is the **repo root**, not `apps/api` |
| `printing/templates/print.css:7` loads fonts from `../../../seed/fonts/` | The runtime image needs the fonts, which today arrive only through a dev-only volume mount — **decided: move them into `apps/api`** (D3) |
| `docker-compose.yml:36` starts `search-worker` from the same image with a different command | Two Dockerfiles, **three** container roles |

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

---

## 2. Constraints, with the code that imposes them

**C1 — CI runs tests inside the api image.** `ci.yml:41-49` bakes the `api` target from
`docker-compose.yml`, then `up -d db meili api`, then `docker compose exec -T api pytest
-q -n auto --dist loadfile` (line 82). So the image CI builds must contain pytest, the
`seed` package (line 73: `python -m seed.hartwood_joinery`) and `db/` (line 64:
`-w /db alembic upgrade head`). Deleting the dev dependencies from the image breaks CI
before it proves anything about production.

**C2 — `db/` belongs in the image.** `Makefile:6` is `docker compose exec -w /db api
alembic upgrade head`, and the readiness probe added in #179 reads the alembic script
directory out of the image (`app/meta.py`, which probes `/db/alembic.ini` first). A
production image without `db/` would answer "schema head unknown" and, on an upgrade,
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

**C5 — PDF fonts live outside `apps/api`.** `printing/templates/print.css:7` resolves to
`<workdir>/seed/fonts/Inter-Regular.woff2`; in dev that path exists only because
`docker-compose.yml:23` bind-mounts `./seed:/code/seed`. The production image has no such
mount, so today's Dockerfile would produce a PDF with every font silently substituted.

One detail that decides the fix: WeasyPrint resolves the `@font-face` URL against the
template's `base_url`, which `printing/engine.py` sets to `templates/` — not against the
CSS file's own location. Both happen to be the same directory here, so the relative path
is simply one level up from `templates/`.

**Decided (D3): move the fonts to `apps/api/app/printing/fonts/` and change the four
`url()` entries from `../../../seed/fonts/X` to `../fonts/X`.** Fonts are application
assets; `seed/` holds a dev dataset, and shipping a directory named `seed` inside a
customer's runtime image invites someone to run it. After the move the runtime image
needs no `seed/` at all, and `COPY apps/api /code` carries the fonts.

**C6 — non-root needs a writable upload root.** `files/store.py:62` reads
`FILE_STORE_ROOT` from the environment with default `/uploads`; compose sets it to
`/uploads` and mounts the `uploads` volume there. Under `USER 10001` that directory has
to be owned by 10001, or uploads fail with a permission error at the first customer file.
A named Docker volume inherits the ownership of the directory it replaces, so
`mkdir /uploads && chown 10001:10001 /uploads` in the image is enough for named volumes;
a customer using a bind mount has to chown it once. That belongs in the deployment notes
(§8 of the checklist), not only here.

**C7 — almost nothing is baked into the web build.** `lib/session-cookie.ts` documents
that the proxy runs in the Node.js runtime and reads `process.env.SESSION_COOKIE_NAME`
at runtime, so a cookie rename no longer requires a rebuild. The only variable actually
inlined at build time is `NEXT_PUBLIC_PROCUREMENT_UI_READY` (`.env.example:26`), and it
is the same for every customer. So the web image needs **no build-time environment at
all** — one ARG is not needed, and a customer cannot be handed a stale-flag image by
accident.

**C8 — `pip install -e .` with a bare `pyproject.toml`.** Today's Dockerfile copies
`pyproject.toml` alone and installs editable; the resulting `jf-api` distribution
contains no packages (the source arrives afterwards via `COPY . .` / a bind mount) and
the install exists purely to populate the virtualenv. This is worth knowing because the
obvious "improvement" — copy the source first, then install — makes setuptools discover
several top-level packages (`app`, `tests`, …) and fail the build. Keep the current
order; it is deliberate even though it does not look like it.

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
COPY apps/api/pyproject.toml /code/pyproject.toml
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
    PYTHONPYCACHEPREFIX=/tmp/pycache
WORKDIR /code
COPY apps/api /code
COPY db /db
# Upload root, writable by the unprivileged user (C6).
RUN mkdir -p /uploads && chown 10001:10001 /uploads
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
- **`APP_VERSION`** is the build arg `GET /version` reports (#179). It stays `dev` unless
  the release pipeline passes it, so a locally built image cannot claim to be a release.
- **`uvicorn[standard]` is already a dependency** (`pyproject.toml`) — no gunicorn, no
  process supervisor. The container runs one process; restart policy is the
  orchestrator's job.

---

## 4. Proposed `apps/web/Dockerfile`

```dockerfile
FROM node:22-slim AS build
ENV NEXT_TELEMETRY_DISABLED=1
# pnpm is pinned rather than "whatever corepack picks today": the lockfile is
# lockfileVersion 9.0 and a future pnpm major would be free to reject it.
RUN corepack enable && corepack prepare pnpm@10.34.9 --activate
WORKDIR /code
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web ./
RUN pnpm build

FROM node:22-slim AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && corepack prepare pnpm@10.34.9 --activate
WORKDIR /app
COPY --from=build /code/package.json /code/pnpm-lock.yaml ./
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

- **`node:22`, not `node:20`.** CI already builds and typechecks on Node 22
  (`ci.yml:111`), so 22 is the version everything is actually tested against. Node 20 is
  also the version currently in the Dockerfile, which means the image and CI disagree
  today.
- **`pnpm install --frozen-lockfile`, no `|| true`.** The current image swallows install
  failures (`apps/web/Dockerfile:5`), which is how a broken dependency reaches
  production looking healthy. With `--frozen-lockfile` a package.json/lockfile mismatch
  fails the build — that is the whole point (§1.2 acceptance).
- **No build-time env needed** (C7), so there is no `ARG` and no risk of baking one
  customer's flag into every image.
- **The healthcheck goes through the app's own proxy route** (`/api/health`), not a
  synthetic endpoint: it exercises the Next server *and* the hop to the api, which is the
  thing that actually breaks in production. It uses the built-in `fetch`, so no `curl`
  in the image.
- **`output: "standalone"` is not in this change.** It would cut the runtime image
  substantially, but it changes how static assets and `next start` behave and would need
  the full e2e suite to prove. Separate PR, after this one is on `main` (D2).

**To verify during implementation (V2):** the pnpm 10 default is to block dependency
build scripts unless they are allow-listed. If the build log reports that `sharp` (or
another native dependency) was skipped, add `pnpm.onlyBuiltDependencies` to
`apps/web/package.json` rather than passing `--ignore-scripts` behaviour around. Watch
the first build log; do not pre-empt it.

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
reads the same file (`ci.yml:46-49`), so it builds `dev` without any workflow edit. The
production file written in §8 overrides `target: runtime`. The alternative — leaving the
default as `dev` and overriding in production only — also works but makes a bare
`docker build` produce a test-bearing image.

**New root `.dockerignore`** (C3); `apps/web/.dockerignore` already exists and can stay:

```
.git
**/node_modules
**/.next
**/.venv
**/__pycache__
**/*.pyc
.pytest_cache
```

**No `seed/` in the production api image at all.** With the fonts moved (D3) there is
nothing left in `seed/` that belongs in front of a customer — it is a dev dataset with
eight known passwords (Q12) — so the runtime image simply does not copy it. The `dev`
target keeps getting it through the compose bind mount, which is how CI seeds.

---

## 6. Decisions

All four settled; recorded here so the Dockerfiles have one source of truth.

| # | Decision | Outcome |
| --- | --- | --- |
| **D1** | Keep a `dev` target with pytest, or move CI off the image | **Keep the target.** CI keeps proving the image we ship; `build.target: dev` in compose selects it without a workflow edit |
| **D2** | `output: "standalone"` now or later | **Later, its own PR.** The size win is real, the risk is asset handling, and e2e is the only thing that can settle it |
| **D3** | PDF fonts: copy `seed/fonts` into the image, or move them | **Move to `apps/api/app/printing/fonts/`**, four `url()` entries become `../fonts/X`. Nothing named `seed` ships to a customer |
| **D4** | `--workers` default | **2**, with `--proxy-headers` and `--forwarded-allow-ips=*`. Forking is safe (no in-process scheduler); WeasyPrint makes each worker expensive |

---

## 7. New open questions this raised

**Q12 — how does a brand-new customer database get its starting rows?**
The only seeding tool is `python -m seed.hartwood_joinery` (`seed/hartwood_joinery.py`),
and it is a **dev** seed: one workspace, eight staff users with the password
`hartwood-dev`, demo projects and items. It is also the only thing that populates the
reference tables the rest of the schema depends on (`stages`, `status_options`,
`status_symbols`). So a customer install cannot run it as-is (it would log in with a
known password) and cannot run without it (nothing else fills those tables). This is not
a Dockerfile problem — D3 already settled that the image carries no `seed/` — but §1 is
where it surfaces, and it blocks the first customer install. Options: a separate `seed/reference.py` for
the lookup tables only, plus a first-run "create workspace + first admin" step; or move
the reference rows into a migration so an empty database is a usable one. **Blocks the
first customer install, not this PR.**

**Q13 — do the images need to be reproducible (pinned digests)?**
`python:3.12-slim` and `node:22-slim` float. Pinning by digest makes an image rebuildable
byte-for-byte, which matters if a customer ever asks "is this image the one we audited?";
it also means a base-image security fix requires a commit. Not urgent, but it is much
cheaper to decide before the release pipeline (§9) is built than after.

**Q14 — image tags and where they are pushed** is **Q4** in the register
(registry vs offline bundle). It does not change anything in these Dockerfiles.

---

## 8. Acceptance

Run against the built images, not against a compose-up dev stack:

| Check | Expected |
| --- | --- |
| `docker run --rm <api-runtime> pip list \| grep -ci pytest` | `0` |
| `docker run --rm <api-runtime> id -u` | `10001` |
| `docker run --rm <api-runtime> python -c "import weasyprint; from weasyprint import HTML; print(len(HTML(string='<p>x</p>').write_pdf()))"` | prints a byte count > 1000 (proves C4) |
| `docker run --rm <api-runtime> test -f /code/app/printing/fonts/Inter-Regular.woff2` | exit 0 (proves C5) |
| Render a quote PDF in the container and open it | Inter / JetBrains Mono actually embedded, not substituted |
| `docker run --rm <api-runtime> test -f /db/alembic.ini` | exit 0 (proves C2) |
| Start api + db, `curl /health/ready` | 200 after migrations (already covered by #179) |
| Start api only, `curl /version` | `{"app_version": "…", …}` |
| `docker run --rm <web-runtime> node -e "console.log(process.getuid())"` | `10001` |
| `docker run --rm <web-runtime> ls node_modules \| grep -c "typescript"` | `0` (no devDependencies) |
| Start web + api, `curl -I localhost:3000` and one authenticated e2e spec | 200 / pass |
| Deliberately corrupt a version in `apps/web/package.json` | **build fails** (proves `|| true` is gone) |

The last one is the acceptance test that matters most: the current image cannot fail.

---

## 9. Suggested sequence

1. **PR A** — `apps/api/Dockerfile` and `apps/web/Dockerfile` (multi-stage, targets),
   root `.dockerignore`, compose build blocks with `context: .` / `target: dev`, and the
   font move with its four `url()` edits. CI stays green because `dev` is what CI builds.
   This PR alone proves C1, C2, C3, C8 and the "install failures fail the build"
   acceptance.
2. **PR B** — `docker-compose.prod.yml` with `target: runtime` (part of checklist §8):
   this is where the runtime image first gets exercised.
3. **PR C (optional, later)** — `output: "standalone"` slimming, behind a full green e2e
   run.

Nothing here touches §7.1 (Meili tenant tokens) or §7.2 (`/public/stats`); both are
Phase 1 following the D1 decision.
