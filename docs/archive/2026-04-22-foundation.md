# Foundation

> Merged from `specs/2026-04-22-foundation-design.md`, `plans/2026-04-22-foundation.md` (October 2026). Each part below is the original text, verbatim, with headings pushed down two levels; use `git log --follow` on the original paths for history. This is a record of intent at one moment, not a description of the current code: see `docs/sub-projects/` and `CLAUDE.md`.


## Design spec

### JoineryFlow — Foundation Design

**Date:** 22/04/2026
**Status:** Approved (pending written-spec review)
**Scope:** Sub-project #1 of the JoineryFlow build. Provides the tech stack, repo scaffold, DB + migrations, auth + RBAC, base chrome, and local dev loop. All user-facing business surfaces (PM Workbench, Drafter Editor, Procurement UI, CV import, PDF) are later sub-projects.

#### 1. Context & Decomposition

`product_spec.md` defines three modules (Project Information Management v1, Shop Floor Ops v2, Cabinet Vision Integration v2). The full build is sequenced as:

1. **Foundation** *(this spec)*
2. PM Project Workbench
3. Drafter Item Editor
4. Procurement module
5. CV CSV import + PDF generation
6. (v2) Shop Floor Ops
7. (v2) Cabinet Vision deep integration + Cut Schedule

Each sub-project gets its own spec → plan → implementation cycle.

Foundation ships no business value on its own. It is the substrate every later module depends on. "Done" means a developer can clone, start the stack, log in as any of the seeded roles, and hit stub pages behind correct RBAC.

#### 2. Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Frontend | **Next.js 15** (App Router) + TypeScript + Tailwind | Closest to the existing `hi-*.jsx` hi-fi files; minimal translation cost. |
| Backend | **FastAPI** (Python 3.12) + SQLAlchemy Core (`text()` queries) + Pydantic v2 | Preserves `procurement_api.py` without rewrite. |
| Database | **Postgres 16** | Stronger constraints, JSON support, citext, modern hosting. Ports the two existing MySQL `.sql` files. |
| Auth | **Self-built**, server-side sessions, httpOnly cookie | Full control; no vendor dependency. |
| Migrations | **Alembic** | Python-native, fits FastAPI repo. |
| Dev env | **docker-compose** (`web`, `api`, `db`) | Local-only for now; production target deferred to a later spec. |
| Monorepo | Single git repo | `apps/web`, `apps/api`, `db/`, `docs/` at root. |

#### 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  docker-compose (local dev)                                  │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  web         │    │  api         │    │  db          │  │
│  │  Next.js 15  │───▶│  FastAPI     │───▶│  Postgres 16 │  │
│  │  :3000       │HTTP│  :8000       │ SQL│  :5432       │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                   ▲                               │
│         └── httpOnly cookie ┘                               │
└─────────────────────────────────────────────────────────────┘
```

**Boundaries**
- `web` owns UI, routing, forms, design system. Default to CSR; use SSR only where meaningful.
- `api` owns data, auth, RBAC, business logic. Later: PDF generation, CV import.
- `db` is the single source of truth; migrations owned by `api`.

**Comms**
- Browser → `web` → `api` over REST, JSON.
- Next.js Route Handlers proxy auth-sensitive requests to FastAPI, attaching the session cookie. Browser never calls FastAPI directly — eliminates CORS, keeps the session cookie httpOnly.

**Session flow**
1. Browser POSTs `/api/auth/login` to Next.js with `{ workspace_slug, email, password }`.
2. Next.js forwards to FastAPI `POST /auth/login`.
3. FastAPI validates, inserts a row in `session`, returns `Set-Cookie: jf_session=<opaque-token>; HttpOnly; SameSite=Lax; Max-Age=1209600`.
4. Next.js passes the cookie through to the browser.
5. Subsequent requests: browser → Next.js → FastAPI, cookie forwarded; FastAPI hashes the token, looks up the session row, loads user + workspace + auth_role, injects into request state.

#### 4. Repo Layout

```
joineryflow/
├── apps/
│   ├── web/                              # Next.js 15 (App Router) + TS + Tailwind
│   │   ├── app/
│   │   │   ├── (auth)/login/page.tsx
│   │   │   ├── (app)/
│   │   │   │   ├── layout.tsx            # HAppChrome
│   │   │   │   ├── dashboard/page.tsx    # HiDashA placeholder
│   │   │   │   ├── tracking/page.tsx
│   │   │   │   ├── list/page.tsx
│   │   │   │   ├── orderbook/page.tsx
│   │   │   │   ├── shop-dwgs/page.tsx
│   │   │   │   └── isample/page.tsx
│   │   │   └── api/[...proxy]/route.ts   # forwards to FastAPI
│   │   ├── components/
│   │   │   ├── chrome/                   # HAppChrome, sidebar, top bar
│   │   │   └── ui/                       # primitives (h-btn, h-card, ...)
│   │   ├── lib/
│   │   │   ├── api-client.ts
│   │   │   └── tokens.ts                 # H palette → Tailwind theme
│   │   ├── tailwind.config.ts
│   │   └── package.json
│   └── api/
│       ├── joineryflow_api/
│       │   ├── main.py                   # FastAPI app factory
│       │   ├── config.py                 # env settings (pydantic-settings)
│       │   ├── db.py                     # engine, session factory
│       │   ├── auth/
│       │   │   ├── routes.py             # /auth/login, /logout, /me
│       │   │   ├── sessions.py           # token create/lookup/extend
│       │   │   ├── passwords.py          # argon2id hash/verify
│       │   │   ├── permissions.py        # static matrix
│       │   │   └── rbac.py               # require_permission dep
│       │   ├── workspaces/
│       │   ├── users/
│       │   └── procurement/              # split from procurement_api.py
│       ├── tests/
│       └── pyproject.toml
├── db/
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       ├── 0001_initial.py           # port of trackingv2_schema.sql
│   │       ├── 0002_procurement.py       # port of procurement_schema.sql
│   │       ├── 0003_material_catalog.py  # 6-table split from spec §5.2
│   │       └── 0004_auth_tables.py       # workspace, app_user, session, audit_log
│   └── seed/
│       └── hartwood_joinery.py           # fixture workspace from spec §12.4
├── legacy/                               # moved from repo root
│   ├── hi-dashboard.jsx
│   ├── hi-login-it.jsx
│   ├── hi-order-dwg-sample.jsx
│   ├── hi-tracking-list.jsx
│   ├── wireframes-hifi.jsx
│   ├── Joinery Workflow Hi-fi.html
│   ├── tracking_dashboard.html
│   ├── procurement_orderbook_dashboard.html
│   ├── drafter_item_editor.html
│   ├── home.html
│   ├── procurement_api.py
│   ├── procurement_schema.sql
│   └── trackingv2_schema.sql
├── docs/
│   ├── superpowers/specs/
│   │   └── 2026-04-22-foundation-design.md
│   ├── product_spec.md                   # moved from root
│   └── trackingv2.md
├── docker-compose.yml
├── .env.example
├── Makefile
├── CLAUDE.md
└── README.md
```

**Notes**
- Root-level prototype files move to `legacy/`; they remain the visual spec, not built code.
- The `H` palette and primitive class list from `wireframes-hifi.jsx` are extracted once into `apps/web/lib/tokens.ts` + `apps/web/app/globals.css`.
- `procurement_api.py` is **split** into `apps/api/joineryflow_api/procurement/` modules (routes, schemas, queries) — not copied verbatim. Ported DB dialect: MySQL → Postgres.

#### 5. Data Model (Foundation only)

Foundation adds only the tables required to authenticate and route by role. Business tables (items, materials, procurement batches) land in later specs.

##### 5.1 New tables

```sql
-- workspace: single-tenant today; workspace_id present for future multi-tenancy.
CREATE TABLE workspace (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug          text UNIQUE NOT NULL,            -- "hartwood-joinery"
  name          text NOT NULL,                   -- "Hartwood Joinery Co."
  plan          text NOT NULL DEFAULT 'studio',
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app_user (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id   uuid NOT NULL REFERENCES workspace(id),
  email          citext NOT NULL,
  password_hash  text NOT NULL,                  -- argon2id
  display_name   text NOT NULL,                  -- "Bill Ma"
  title          text,                           -- "Estimator / Admin"
  avatar_color   text,                           -- key in H palette (e.g. 'accent')
  auth_role      text NOT NULL
    CHECK (auth_role IN ('admin','manager','editor','purchase_officer','viewer')),
  jtbd_role      text
    CHECK (jtbd_role IN ('ceo','pm','drafter','foreman','machine','procurement')),
  status         text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active','invited','suspended')),
  last_active_at timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, email)
);

CREATE TABLE session (
  token_hash    bytea PRIMARY KEY,               -- sha256 of opaque token
  user_id       uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  workspace_id  uuid NOT NULL REFERENCES workspace(id),
  issued_at     timestamptz NOT NULL DEFAULT now(),
  expires_at    timestamptz NOT NULL,
  last_seen_at  timestamptz NOT NULL DEFAULT now(),
  user_agent    text,
  ip            inet
);
CREATE INDEX session_user_id_idx ON session (user_id);
CREATE INDEX session_expires_at_idx ON session (expires_at);

CREATE TABLE audit_log (
  id             bigserial PRIMARY KEY,
  workspace_id   uuid NOT NULL,
  actor_user_id  uuid,                            -- null = system
  action         text NOT NULL,                   -- "auth.login.success", ...
  target_type    text,
  target_id      text,
  detail         jsonb NOT NULL DEFAULT '{}',
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_workspace_time_idx ON audit_log (workspace_id, created_at DESC);
```

##### 5.2 Design rationale

- `session.token_hash` stores `sha256(token)`; the raw token lives only in the cookie. A DB breach cannot replay sessions.
- `citext` on email: case-insensitive uniqueness without app-layer normalization.
- `jsonb` `audit_log.detail` survives schema drift in the future admin log surface.
- `jtbd_role` is separate from `auth_role`. Six operational roles (CEO/PM/Drafter/Foreman/Machine/Procurement) map onto five RBAC tiers with a default mapping but admin-overridable per user.
- `gen_random_uuid()` requires the `pgcrypto` extension — migration `0004` enables it if not present.

##### 5.3 Seeded fixtures

`db/seed/hartwood_joinery.py` inserts the workspace `hartwood-joinery` + the eight staff from `product_spec.md` §12.4. Local-dev password for every seeded user: `hartwood-dev` (documented in `.env.example`, never a production default).

| Seed user | JTBD role | Default auth_role |
|---|---|---|
| Bill Ma | — (estimator / admin) | admin |
| Jules Roh | pm | manager |
| Rin Park | drafter | editor |
| Sam Oduya | foreman | editor |
| Mina Klee | procurement | **purchase_officer** |
| Theo Akkad | — (carpenter) | editor |
| Priya Shah | — (designer) | editor |
| Dan Kowalski | — (site supervisor) | editor |

##### 5.4 Out of scope for Foundation

Password reset flow, email delivery, invitations, SSO, MFA, password policy, rate limiting on login. All are auth features but are scoped to a later module — not blockers for an authenticated stub app.

#### 6. Auth, RBAC & Request Flow

##### 6.1 Password hashing

argon2id via `argon2-cffi`. Parameters from env:
- `ARGON2_TIME_COST=3`
- `ARGON2_MEMORY_KB=65536`
- parallelism = 1

No legacy hashes to support.

##### 6.2 Session token

32 random bytes (`secrets.token_bytes(32)`), base64url-encoded. Raw token goes in the cookie; `sha256(token)` is stored in `session.token_hash`.

- Sliding expiry: `expires_at` extended to `now() + SESSION_TTL_DAYS` on every authenticated request.
- Hard cap: sessions older than `issued_at + SESSION_MAX_DAYS` are rejected even if sliding expiry is fresh.
- Defaults: `SESSION_TTL_DAYS=14`, `SESSION_MAX_DAYS=30`.

##### 6.3 Cookie

```
Set-Cookie: jf_session=<token>; HttpOnly; SameSite=Lax; Path=/;
            Secure (prod only); Max-Age=1209600
```

- `Secure` is toggled off in dev so it works over plain http; `COOKIE_SECURE=false` in `.env.example`.
- `SameSite=Lax` — the app is first-party; no embedded cross-site POSTs needed.

##### 6.4 RBAC model — module × action

**Five auth roles:** `admin`, `manager`, `editor`, `purchase_officer`, `viewer`.

Routes do **not** call `require_role(...)`. They call `require_permission(module, action)` where `action ∈ {read, write, approve, comment}`. A static Python dict in `auth/permissions.py` maps `(auth_role, module) → set[action]`.

**Permission matrix (binding):**

| Tab / module     | admin      | manager    | editor     | purchase_officer                     | viewer |
|---|---|---|---|---|---|
| `dashboard`      | read       | read       | read       | read                                  | read   |
| `tracking`       | read,write | read,write | read,write | **read,comment**                      | read   |
| `list_cutlist`   | read,write | read,write | read,write | read                                  | read   |
| `list_hardware`  | read,write | read,write | read,write | read                                  | read   |
| `orderbook`      | read,write,approve | read,write,approve | read | **read,write,approve**         | read   |
| `shop_dwgs`      | read,write | read,write | read,write | read                                  | read   |
| `isample`        | read,write | read,write | read,write | read                                  | read   |
| `it_management`  | read,write | —          | —          | —                                     | —      |

- Hierarchy is **not** implicit. No "admin includes manager". Every route lists the required `(module, action)`; the matrix answers yes/no. Verbose by design — permission decisions are grep-able.
- `tracking` has a dedicated `comment` action used only by `purchase_officer` to add notes/flags on Tracking items without editing status or fields.

**Default JTBD → auth_role mapping** (applied at seed; admins can override per user):

| JTBD role (spec §2) | Default auth_role |
|---|---|
| CEO | admin |
| PM | manager |
| Drafter | editor |
| Foreman | editor |
| Machine team | editor |
| Procurement | **purchase_officer** |

(Spec §11 previously mapped Procurement → `manager`. This spec supersedes that — `purchase_officer` is the correct default; admins can still elevate a specific Procurement user to `manager` when needed.)

##### 6.5 FastAPI dependencies

```python
# joineryflow_api/auth/rbac.py

def current_user() -> AuthUser:
    """Loads session from cookie, returns AuthUser or raises 401.
       Touches last_seen_at and extends expires_at.
       Rejects if now() > issued_at + SESSION_MAX_DAYS."""

def require_permission(module: str, action: str):
    """Dep factory. Asserts the current user's auth_role grants (module, action)
       per the static matrix, else raises 403."""
```

Usage:

```python
@router.post("/orderbook/purchase-orders/{po_id}/approve")
def approve_po(
    po_id: UUID,
    user: AuthUser = Depends(require_permission("orderbook", "approve")),
    db: Session = Depends(get_db),
):
    ...
```

##### 6.6 Audit events written in Foundation

- `auth.login.success` — detail: `{ workspace_slug, ip, user_agent }`
- `auth.login.failure` — detail: `{ workspace_slug, email_tried, reason }` (reason ∈ `unknown_user | wrong_password | workspace_mismatch | user_suspended`)
- `auth.logout` — detail: `{}`
- `auth.session.expired` — detail: `{ session_age_days }` (written lazily on first failed lookup)
- `user.role_changed` — detail: `{ target_user_id, from, to }`
- `user.status_changed` — detail: `{ target_user_id, from, to }`

Everything else (project.created, po.approved, etc.) is written by its own module.

##### 6.7 Endpoints shipped in Foundation

```
POST   /auth/login          { workspace_slug, email, password } → Set-Cookie
POST   /auth/logout         → clears cookie, deletes session row
GET    /auth/me             → { user, workspace }
GET    /workspace           → workspace info for chrome
GET    /users               admin-only; list workspace users
PATCH  /users/{id}          admin-only; change auth_role or status
```

No other endpoints ship in Foundation. The six tab pages in `apps/web` render stub content gated by `current_user()`.

#### 7. Dev Loop, Config & Testing

##### 7.1 Environment variables

`.env.example` committed, `.env` gitignored.

```
# api
DATABASE_URL=postgresql+psycopg://jf:jf@db:5432/joineryflow
SESSION_COOKIE_NAME=jf_session
SESSION_TTL_DAYS=14
SESSION_MAX_DAYS=30
ARGON2_TIME_COST=3
ARGON2_MEMORY_KB=65536
ALLOW_ORIGINS=http://localhost:3000
COOKIE_SECURE=false            # prod: true

# web
NEXT_PUBLIC_APP_NAME=JoineryFlow
API_INTERNAL_URL=http://api:8000
```

##### 7.2 docker-compose services

- `db` — `postgres:16`, named volume for data, healthcheck on `pg_isready`.
- `api` — builds from `apps/api`, runs `uvicorn joineryflow_api.main:app --host 0.0.0.0 --reload`, depends on db healthcheck.
- `web` — builds from `apps/web`, runs `next dev`, depends on api.

##### 7.3 Makefile

```
make up              # docker-compose up -d
make down            # docker-compose down
make logs            # docker-compose logs -f
make migrate         # alembic upgrade head
make revision m="add x"   # alembic revision --autogenerate -m "..."
make seed            # python -m db.seed.hartwood_joinery
make reset-db        # drop + recreate + migrate + seed
make test            # pytest (api) + (web tests skipped in Foundation)
make e2e             # run the one Playwright smoke test
make fmt             # ruff format + prettier
make lint            # ruff check + eslint + tsc --noEmit
```

##### 7.4 Testing (Foundation scope)

**Backend (`apps/api/tests/`), pytest:**
- Ephemeral Postgres schema per test; transaction-rollback fixture.
- `test_passwords.py` — hash/verify round trip; rejects wrong password; timing-stable verify.
- `test_sessions.py` — create, lookup, sliding extend, hard-cap expiry, revoke on logout.
- `test_permissions.py` — parametrized across `(auth_role, module, action)` against the binding matrix in §6.4.
- `test_auth_routes.py` — `/auth/login` happy path, 401 on bad password, 401 on wrong workspace, 401 on suspended user, `/auth/logout` clears cookie.
- `test_users_admin.py` — admin can `PATCH /users/{id}`; non-admin gets 403; audit row written.

**Frontend (`apps/web/`):**
- No unit tests in Foundation.
- **One Playwright smoke test:** login as `rin.park@hartwood-joinery` (drafter) → land on `/dashboard` → see 6-tab chrome → logout → redirected to `/login`.
- Run locally via `make e2e`; not in CI (no CI in Foundation).

No coverage gate in Foundation. Coverage gates activate when real business logic lands.

##### 7.5 "Foundation done" — acceptance checklist

1. `git clone && cp .env.example .env && make up && make migrate && make seed` → running stack, no manual steps.
2. Visit `http://localhost:3000` → `HiLogin` surface with workspace selector prefilled to `hartwood-joinery`.
3. Log in as each seeded user → correct default tab, 6-tab chrome renders, sidebar shows fixture projects by name (no data yet), logout works.
4. As admin, `PATCH /users/{id}` changes another user's `auth_role`; `user.role_changed` audit row written.
5. `purchase_officer` user hits `/orderbook` → full access. Hits `/tracking` → read-only UI with visible "can comment, cannot edit" hint.
6. All Alembic migrations reversible: `alembic downgrade base` runs clean.
7. `make test` green. `make e2e` green.

#### 8. Explicitly Out of Scope

To prevent scope creep into later sub-projects:

- Project / item / material / cutlist / hardware CRUD.
- Procurement business logic beyond the split-and-port of `procurement_api.py` into Postgres dialect. No new procurement features.
- PDF generation for Cutlist / Hardware List.
- CV CSV import.
- Email delivery, invitations, password reset, MFA, SSO.
- Production deploy config (Vercel / Railway / VPS / cloud).
- CI pipeline.
- Observability (metrics, tracing, error reporting).
- Rate limiting / WAF / CSRF tokens beyond SameSite=Lax cookie.
- Real-time features (WebSocket, SSE, pub/sub).

Each of these belongs to a later spec.

#### 9. Open Questions

None blocking. Spec is ready for a written-spec review pass, then an implementation plan.

#### 10. Reference

- `docs/product_spec.md` — product overview, roles, data-model invariants, design tokens, IA. Authoritative.
- `docs/trackingv2.md` — v1 module build plan.
- `CLAUDE.md` — repo-level guidance for future Claude Code sessions.


## Implementation plan

### JoineryFlow Foundation Implementation Plan

> **Status: shipped.** Migrations `0001`–`0004`. Current state lives in
> `## Foundation dev loop` / `## Auth & RBAC` / `## Web shell` in `CLAUDE.md`;
> the task checkboxes below were never ticked and are not a progress signal
> (see `docs/archive/README.md`).

> **Later change:** The Goal below says *five-role RBAC* and *six-tab IA*: both have since
> grown — 7 auth roles and 11 modules, with a secondary tab row added by #9a.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the JoineryFlow monorepo (Next.js web + FastAPI + Postgres 16) with self-built auth, five-role RBAC, Alembic migrations porting the legacy MySQL schemas, and a signed-in shell showing the six-tab IA — end-to-end verifiable via a Playwright smoke test.

**Architecture:** Three-container docker-compose (db, api, web). Browser talks only to Next.js; Next.js Route Handler proxies to FastAPI. Session is an opaque 32-byte token, sha256 stored in `session.token_hash`, delivered via httpOnly `jf_session` cookie with sliding 14d / hard-cap 30d TTL. RBAC is a static `(auth_role, module) → set[action]` matrix enforced by a `require_permission` FastAPI dependency.

**Tech Stack:** Next.js 15 (App Router, TypeScript, Tailwind), FastAPI + SQLAlchemy Core `text()` + Pydantic v2, Postgres 16 (`citext`, `pgcrypto`), Alembic, argon2-cffi, docker-compose, pytest, Playwright.

---

#### File Structure (locked)

```
apps/
  api/
    app/
      main.py                     # FastAPI entrypoint
      config.py                   # env + settings
      db.py                       # engine, get_db
      auth/
        passwords.py              # argon2id hash/verify
        sessions.py               # create/lookup/revoke + sliding/hard-cap
        permissions.py            # static matrix + has_permission
        rbac.py                   # current_user + require_permission deps
        audit.py                  # write_audit
        schemas.py                # LoginIn, MeOut, ...
        routes.py                 # /auth/login /auth/logout /auth/me
      workspaces/routes.py        # GET /workspace
      users/
        schemas.py
        routes.py                 # GET /users, PATCH /users/{id}
      procurement/
        schemas.py                # ported from legacy procurement_api.py
        queries.py                # SQLAlchemy text() calls
        routes.py                 # mounted under /procurement
    tests/
      conftest.py                 # ephemeral schema + rollback fixture
      test_passwords.py
      test_permissions.py
      test_sessions.py
      test_audit.py
      test_rbac.py
      test_auth_routes.py
      test_users_routes.py
    pyproject.toml
    Dockerfile
  web/
    app/
      layout.tsx
      (public)/login/page.tsx
      (app)/layout.tsx            # HAppChrome wrapper
      (app)/dashboard/page.tsx
      (app)/tracking/page.tsx
      (app)/list/page.tsx
      (app)/shop-dwgs/page.tsx
      (app)/isample/page.tsx
      (app)/orderbook/page.tsx
      (app)/it/page.tsx
      api/[...proxy]/route.ts     # server-side proxy to FastAPI
    components/chrome/
      HAppChrome.tsx
      TopBar.tsx
      TabStrip.tsx
      SideBar.tsx
    lib/
      session.ts                  # cookie read/write helpers
      api.ts                      # server-side fetch wrapper
      tokens.ts                   # H design tokens
    styles/globals.css
    middleware.ts                 # auth gate
    tailwind.config.ts
    tsconfig.json
    next.config.ts
    package.json
    Dockerfile
db/
  alembic/
    env.py
    script.py.mako
    versions/
      0001_tracking_port.py
      0002_procurement_port.py
      0003_material_catalog.py
      0004_auth.py
  alembic.ini
seed/
  hartwood_joinery.py             # workspace + 8 users
legacy/
  trackingv2_schema.sql
  procurement_schema.sql
  procurement_api.py              # original, unchanged, reference only
docs/
  superpowers/specs/2026-04-22-foundation-design.md
  superpowers/plans/2026-04-22-foundation.md
tests/e2e/
  smoke.spec.ts
.env.example
.gitignore
Makefile
README.md
docker-compose.yml
CLAUDE.md
```

---

#### Phase 1 — Repo scaffolding

##### Task 1: Initialize git + .gitignore + README

**Files:**
- Create: `.gitignore`
- Create: `README.md`

- [ ] **Step 1: Initialize git**

```bash
cd "D:/new system test" && git init && git checkout -b main
```

- [ ] **Step 2: Write .gitignore**

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.mypy_cache/
*.egg-info/

# Node
node_modules/
.next/
.turbo/
dist/
build/

# Env / secrets
.env
.env.local
.env.*.local

# Editors
.vscode/
.idea/
.DS_Store

# Playwright
test-results/
playwright-report/
```

- [ ] **Step 3: Write README.md**

```markdown
# JoineryFlow

Web replacement for a legacy FileMaker joinery production system.

Dev: `make up` → http://localhost:3000 (login: rin.park@hartwood.test / hartwood-dev).

See `docs/archive/2026-04-22-foundation.md`.
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore README.md && git commit -m "chore: init repo"
```

---

##### Task 2: Monorepo directories + relocate legacy artifacts

**Files:**
- Create dirs: `apps/api`, `apps/web`, `db/alembic/versions`, `seed/`, `legacy/`, `tests/e2e/`
- Move: existing `trackingv2_schema.sql`, `procurement_schema.sql`, `procurement_api.py` → `legacy/`

- [ ] **Step 1: Create directories**

```bash
mkdir -p apps/api/app/{auth,workspaces,users,procurement} apps/api/tests \
  apps/web/app apps/web/components/chrome apps/web/lib apps/web/styles \
  db/alembic/versions seed legacy tests/e2e
```

- [ ] **Step 2: Move legacy files (if present)**

```bash
for f in trackingv2_schema.sql procurement_schema.sql procurement_api.py; do
  [ -f "$f" ] && git mv "$f" legacy/ || true
done
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "chore: monorepo layout + legacy quarantine"
```

---

##### Task 3: .env.example + Makefile

**Files:**
- Create: `.env.example`
- Create: `Makefile`

- [ ] **Step 1: Write .env.example**

```env
POSTGRES_USER=jf
POSTGRES_PASSWORD=jf
POSTGRES_DB=joineryflow
DATABASE_URL=postgresql+psycopg://jf:jf@db:5432/joineryflow
API_URL=http://api:8000
SESSION_COOKIE_NAME=jf_session
SESSION_SLIDING_DAYS=14
SESSION_HARD_CAP_DAYS=30
```

- [ ] **Step 2: Write Makefile**

```makefile
.PHONY: up down logs migrate seed test e2e fmt

up:        ; docker compose up -d --build
down:      ; docker compose down
logs:      ; docker compose logs -f
migrate:   ; docker compose exec api alembic upgrade head
seed:      ; docker compose exec api python -m seed.hartwood_joinery
test:      ; docker compose exec api pytest -q
e2e:       ; pnpm --dir apps/web exec playwright test
```

- [ ] **Step 3: Commit**

```bash
cp .env.example .env && git add .env.example Makefile && git commit -m "chore: env + make targets"
```

---

##### Task 4: docker-compose + Dockerfiles + pyproject

**Files:**
- Create: `docker-compose.yml`
- Create: `apps/api/Dockerfile`, `apps/api/pyproject.toml`
- Create: `apps/web/Dockerfile`

- [ ] **Step 1: docker-compose.yml**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports: ["5432:5432"]
    volumes: ["dbdata:/var/lib/postgresql/data"]
  api:
    build: ./apps/api
    env_file: .env
    depends_on: [db]
    ports: ["8000:8000"]
    volumes: ["./apps/api:/code", "./db:/db", "./seed:/code/seed"]
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  web:
    build: ./apps/web
    env_file: .env
    depends_on: [api]
    ports: ["3000:3000"]
    volumes: ["./apps/web:/code"]
    command: pnpm dev
volumes:
  dbdata:
```

- [ ] **Step 2: apps/api/pyproject.toml**

```toml
[project]
name = "jf-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlalchemy>=2.0",
  "psycopg[binary]>=3.2",
  "alembic>=1.13",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "argon2-cffi>=23.1",
  "python-multipart>=0.0.12",
]
[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "httpx>=0.27"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: apps/api/Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /code
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"
COPY . .
```

- [ ] **Step 4: apps/web/Dockerfile**

```dockerfile
FROM node:20-slim
RUN corepack enable
WORKDIR /code
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install || true
COPY . .
```

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml apps/api/Dockerfile apps/api/pyproject.toml apps/web/Dockerfile
git commit -m "chore: docker compose + images"
```

---

#### Phase 2 — FastAPI skeleton

##### Task 5: FastAPI `/health` endpoint

**Files:**
- Create: `apps/api/app/__init__.py`, `apps/api/app/config.py`, `apps/api/app/main.py`

- [ ] **Step 1: apps/api/app/config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    session_cookie_name: str = "jf_session"
    session_sliding_days: int = 14
    session_hard_cap_days: int = 30
    class Config: env_file = ".env"

settings = Settings()
```

- [ ] **Step 2: apps/api/app/main.py**

```python
from fastapi import FastAPI

app = FastAPI(title="JoineryFlow API")

@app.get("/health")
def health():
    return {"ok": True}
```

- [ ] **Step 3: Start stack + verify**

```bash
docker compose up -d --build db api
curl -s http://localhost:8000/health
```
Expected: `{"ok":true}`

- [ ] **Step 4: Commit**

```bash
git add apps/api/app && git commit -m "feat(api): health endpoint"
```

---

##### Task 6: Next.js scaffold

**Files:**
- Generate via: `pnpm create next-app@latest apps/web --ts --tailwind --app --no-src-dir --import-alias "@/*" --no-eslint`

- [ ] **Step 1: Scaffold**

```bash
cd "D:/new system test" && pnpm create next-app@latest apps/web \
  --ts --tailwind --app --no-src-dir --import-alias "@/*" --no-eslint --use-pnpm
```

- [ ] **Step 2: Verify dev server**

```bash
docker compose up -d --build web
curl -sI http://localhost:3000
```
Expected: `HTTP/1.1 200 OK`

- [ ] **Step 3: Commit**

```bash
git add apps/web && git commit -m "feat(web): next.js scaffold"
```

---

##### Task 7: db.py engine + get_db

**Files:**
- Create: `apps/api/app/db.py`
- Create: `apps/api/tests/__init__.py`, `apps/api/tests/test_db.py`

- [ ] **Step 1: Write failing test `tests/test_db.py`**

```python
from sqlalchemy import text
from app.db import engine

def test_engine_connects():
    with engine.connect() as c:
        assert c.execute(text("select 1")).scalar() == 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
docker compose exec api pytest tests/test_db.py -q
```
Expected: ImportError (`app.db` missing).

- [ ] **Step 3: Implement db.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import settings

engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: Test passes**

```bash
docker compose exec api pytest tests/test_db.py -q
```
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/db.py apps/api/tests && git commit -m "feat(api): db engine + session factory"
```

---

#### Phase 3 — Alembic + migrations

##### Task 8: Alembic init

**Files:**
- Create: `db/alembic.ini`, `db/alembic/env.py`, `db/alembic/script.py.mako`

- [ ] **Step 1: alembic.ini (minimal)**

```ini
[alembic]
script_location = alembic
sqlalchemy.url = ${DATABASE_URL}

[loggers]
keys = root

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[handler_console]
class = StreamHandler
args = (sys.stderr,)
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 2: db/alembic/env.py**

```python
import os
from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()

run_migrations_online()
```

- [ ] **Step 3: db/alembic/script.py.mako**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}

def upgrade():
    ${upgrades if upgrades else "pass"}

def downgrade():
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Smoke-test**

```bash
docker compose exec api bash -c "cd /db && alembic current"
```
Expected: no errors, no current revision.

- [ ] **Step 5: Commit**

```bash
git add db/ && git commit -m "chore(db): alembic init"
```

---

##### Task 9: Migration 0001 — port `trackingv2_schema.sql` to Postgres

**Files:**
- Create: `db/alembic/versions/0001_tracking_port.py`

- [ ] **Step 1: Open `legacy/trackingv2_schema.sql` and translate each `CREATE TABLE` to Postgres.** Apply the dialect conversions:
  - `INT AUTO_INCREMENT PRIMARY KEY` → `BIGSERIAL PRIMARY KEY`
  - `DATETIME` → `timestamptz`
  - `TINYINT(1)` → `boolean`
  - `VARCHAR(n) CHARACTER SET utf8mb4` → `varchar(n)` or `citext` for emails
  - `JSON` → `jsonb`
  - `ENUM('a','b')` → `text CHECK (col IN ('a','b'))`

- [ ] **Step 2: Write migration skeleton**

```python
"""tracking port

Revision ID: 0001
Revises:
Create Date: 2026-04-22
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(r"""
    -- <<< paste each translated CREATE TABLE here, semicolon-separated >>>
    """)

def downgrade():
    op.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
```

- [ ] **Step 3: Apply + verify**

```bash
docker compose exec api bash -c "cd /db && alembic upgrade head"
docker compose exec db psql -U jf -d joineryflow -c "\dt"
```
Expected: every tracking table listed.

- [ ] **Step 4: Commit**

```bash
git add db/alembic/versions/0001_tracking_port.py
git commit -m "feat(db): port trackingv2 schema to postgres"
```

---

##### Task 10: Migration 0002 — port `procurement_schema.sql`

**Files:**
- Create: `db/alembic/versions/0002_procurement_port.py`

- [ ] **Step 1: Translate `legacy/procurement_schema.sql` the same way as Task 9.**

- [ ] **Step 2: Skeleton**

```python
"""procurement port

Revision ID: 0002
Revises: 0001
"""
from alembic import op
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade():
    op.execute(r"""
    -- <<< translated procurement tables >>>
    """)

def downgrade():
    op.execute("-- intentionally no granular down; see 0001")
```

- [ ] **Step 3: Apply + verify**

```bash
docker compose exec api bash -c "cd /db && alembic upgrade head"
```

- [ ] **Step 4: Commit**

```bash
git add db/alembic/versions/0002_procurement_port.py
git commit -m "feat(db): port procurement schema"
```

---

##### Task 11: Migration 0003 — material catalog (six tables + derivatives)

**Files:**
- Create: `db/alembic/versions/0003_material_catalog.py`

Tables to create (per spec §5.2): `board_materials`, `hardware_materials`, `custom_made`, `benchtop_materials`, `appliances`, `equipment_hire`, plus `project_hardware_catalog`, `project_hardware_catalog_log`, `cut_plan`, `cut_sheet`, `part_slot`, `cut_schedule`.

- [ ] **Step 1: Skeleton**

```python
"""material catalog

Revision ID: 0003
Revises: 0002
"""
from alembic import op
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    op.execute(r"""
    CREATE TABLE board_materials (
      id            BIGSERIAL PRIMARY KEY,
      workspace_id  BIGINT NOT NULL,
      sku           text NOT NULL,
      name          text NOT NULL,
      spec          jsonb NOT NULL DEFAULT '{}'::jsonb,
      unit_cost     numeric(12,2),
      created_at    timestamptz NOT NULL DEFAULT now(),
      UNIQUE (workspace_id, sku)
    );

    CREATE TABLE hardware_materials (LIKE board_materials INCLUDING ALL);
    CREATE TABLE custom_made        (LIKE board_materials INCLUDING ALL);
    CREATE TABLE benchtop_materials (LIKE board_materials INCLUDING ALL);
    CREATE TABLE appliances         (LIKE board_materials INCLUDING ALL);
    CREATE TABLE equipment_hire     (LIKE board_materials INCLUDING ALL);

    CREATE TABLE project_hardware_catalog (
      id            BIGSERIAL PRIMARY KEY,
      workspace_id  BIGINT NOT NULL,
      project_id    BIGINT NOT NULL,
      source_table  text NOT NULL CHECK (source_table IN
        ('board_materials','hardware_materials','custom_made',
         'benchtop_materials','appliances','equipment_hire')),
      source_id     BIGINT NOT NULL,
      qty           numeric(12,3) NOT NULL DEFAULT 0,
      created_at    timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE project_hardware_catalog_log (
      id            BIGSERIAL PRIMARY KEY,
      catalog_id    BIGINT NOT NULL REFERENCES project_hardware_catalog(id) ON DELETE CASCADE,
      action        text NOT NULL,
      actor_id      BIGINT,
      payload       jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at    timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE cut_plan (
      id            BIGSERIAL PRIMARY KEY,
      workspace_id  BIGINT NOT NULL,
      project_id    BIGINT NOT NULL,
      name          text NOT NULL,
      created_at    timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE cut_sheet (
      id            BIGSERIAL PRIMARY KEY,
      cut_plan_id   BIGINT NOT NULL REFERENCES cut_plan(id) ON DELETE CASCADE,
      sheet_no      int NOT NULL,
      material_sku  text NOT NULL,
      UNIQUE (cut_plan_id, sheet_no)
    );

    CREATE TABLE part_slot (
      id            BIGSERIAL PRIMARY KEY,
      cut_sheet_id  BIGINT NOT NULL REFERENCES cut_sheet(id) ON DELETE CASCADE,
      x             numeric(10,2) NOT NULL,
      y             numeric(10,2) NOT NULL,
      w             numeric(10,2) NOT NULL,
      h             numeric(10,2) NOT NULL,
      label         text
    );

    CREATE TABLE cut_schedule (
      id            BIGSERIAL PRIMARY KEY,
      cut_plan_id   BIGINT NOT NULL REFERENCES cut_plan(id) ON DELETE CASCADE,
      scheduled_for date,
      status        text NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned','running','done','cancelled'))
    );
    """)

def downgrade():
    op.execute("""
    DROP TABLE IF EXISTS cut_schedule, part_slot, cut_sheet, cut_plan,
      project_hardware_catalog_log, project_hardware_catalog,
      equipment_hire, appliances, benchtop_materials, custom_made,
      hardware_materials, board_materials CASCADE;
    """)
```

- [ ] **Step 2: Apply + verify six catalog tables exist**

```bash
docker compose exec api bash -c "cd /db && alembic upgrade head"
docker compose exec db psql -U jf -d joineryflow -c "\dt" | grep -E "board_materials|hardware_materials|custom_made|benchtop_materials|appliances|equipment_hire"
```
Expected: all six.

- [ ] **Step 3: Commit**

```bash
git add db/alembic/versions/0003_material_catalog.py
git commit -m "feat(db): material catalog (six tables + derivatives)"
```

---

##### Task 12: Migration 0004 — auth tables

**Files:**
- Create: `db/alembic/versions/0004_auth.py`

- [ ] **Step 1: Write migration**

```python
"""auth

Revision ID: 0004
Revises: 0003
"""
from alembic import op
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

def upgrade():
    op.execute(r"""
    CREATE TABLE workspace (
      id          BIGSERIAL PRIMARY KEY,
      slug        citext NOT NULL UNIQUE,
      name        text NOT NULL,
      created_at  timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE app_user (
      id            BIGSERIAL PRIMARY KEY,
      workspace_id  BIGINT NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
      email         citext NOT NULL,
      full_name     text NOT NULL,
      password_hash text NOT NULL,
      auth_role     text NOT NULL CHECK (auth_role IN
        ('admin','manager','editor','purchase_officer','viewer')),
      jtbd_role     text,
      is_active     boolean NOT NULL DEFAULT true,
      created_at    timestamptz NOT NULL DEFAULT now(),
      UNIQUE (workspace_id, email)
    );

    CREATE TABLE session (
      token_hash      bytea PRIMARY KEY,
      user_id         BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
      created_at      timestamptz NOT NULL DEFAULT now(),
      last_seen_at    timestamptz NOT NULL DEFAULT now(),
      hard_expires_at timestamptz NOT NULL,
      revoked_at      timestamptz
    );
    CREATE INDEX session_user_idx ON session(user_id);

    CREATE TABLE audit_log (
      id            BIGSERIAL PRIMARY KEY,
      workspace_id  BIGINT NOT NULL,
      actor_id      BIGINT,
      event         text NOT NULL,
      target        text,
      payload       jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at    timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX audit_workspace_time_idx ON audit_log(workspace_id, created_at DESC);
    """)

def downgrade():
    op.execute("DROP TABLE IF EXISTS audit_log, session, app_user, workspace CASCADE;")
```

- [ ] **Step 2: Apply + verify**

```bash
docker compose exec api bash -c "cd /db && alembic upgrade head"
docker compose exec db psql -U jf -d joineryflow -c "\d app_user"
```
Expected: `auth_role` constraint visible with all 5 values.

- [ ] **Step 3: Commit**

```bash
git add db/alembic/versions/0004_auth.py
git commit -m "feat(db): auth tables (workspace, app_user, session, audit_log)"
```

---

#### Phase 4 — Auth core (TDD)

##### Task 13: pytest conftest with ephemeral schema

**Files:**
- Create: `apps/api/tests/conftest.py`

- [ ] **Step 1: Write fixture**

```python
import os, pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def db():
    url = os.environ["DATABASE_URL"]
    eng = create_engine(url, future=True)
    conn = eng.connect()
    trans = conn.begin()
    Session = sessionmaker(bind=conn, autoflush=False, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        conn.close()

@pytest.fixture
def workspace_id(db):
    wid = db.execute(text(
      "INSERT INTO workspace(slug,name) VALUES('test','Test') RETURNING id"
    )).scalar()
    return wid
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/tests/conftest.py
git commit -m "test(api): ephemeral schema fixture"
```

---

##### Task 14: passwords.py (argon2id)

**Files:**
- Create: `apps/api/app/auth/__init__.py`, `apps/api/app/auth/passwords.py`
- Create: `apps/api/tests/test_passwords.py`

- [ ] **Step 1: Failing test**

```python
from app.auth.passwords import hash_password, verify_password

def test_hash_then_verify():
    h = hash_password("hartwood-dev")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "hartwood-dev")
    assert not verify_password(h, "wrong")
```

- [ ] **Step 2: Run to confirm failure**

```bash
docker compose exec api pytest tests/test_passwords.py -q
```
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()

def hash_password(raw: str) -> str:
    return _ph.hash(raw)

def verify_password(stored: str, raw: str) -> bool:
    try:
        return _ph.verify(stored, raw)
    except VerifyMismatchError:
        return False
```

- [ ] **Step 4: Pass + commit**

```bash
docker compose exec api pytest tests/test_passwords.py -q
git add apps/api/app/auth/__init__.py apps/api/app/auth/passwords.py apps/api/tests/test_passwords.py
git commit -m "feat(auth): argon2id password hashing"
```

---

##### Task 15: permissions.py static matrix

**Files:**
- Create: `apps/api/app/auth/permissions.py`
- Create: `apps/api/tests/test_permissions.py`

- [ ] **Step 1: Failing test**

```python
import pytest
from app.auth.permissions import has_permission

CASES = [
    ("admin",            "it_management", "write",   True),
    ("admin",            "orderbook",     "approve", True),
    ("manager",          "tracking",      "write",   True),
    ("manager",          "it_management", "write",   False),
    ("editor",           "tracking",      "write",   True),
    ("editor",           "orderbook",     "approve", False),
    ("purchase_officer", "tracking",      "read",    True),
    ("purchase_officer", "tracking",      "write",   False),
    ("purchase_officer", "tracking",      "comment", True),
    ("purchase_officer", "list",          "read",    True),
    ("purchase_officer", "list",          "write",   False),
    ("purchase_officer", "orderbook",     "write",   True),
    ("purchase_officer", "orderbook",     "approve", True),
    ("purchase_officer", "it_management", "read",    False),
    ("viewer",           "tracking",      "read",    True),
    ("viewer",           "tracking",      "write",   False),
    ("viewer",           "orderbook",     "approve", False),
]

@pytest.mark.parametrize("role,module,action,expected", CASES)
def test_matrix(role, module, action, expected):
    assert has_permission(role, module, action) is expected
```

- [ ] **Step 2: Implement**

```python
from typing import Literal

Role = Literal["admin","manager","editor","purchase_officer","viewer"]
Module = Literal["dashboard","tracking","list","shop_dwgs","isample","orderbook","it_management"]
Action = Literal["read","write","approve","comment"]

_ALL_MODULES = ("dashboard","tracking","list","shop_dwgs","isample","orderbook","it_management")

MATRIX: dict[Role, dict[str, set[str]]] = {
    "admin":   {m: {"read","write","approve","comment"} for m in _ALL_MODULES},
    "manager": {m: {"read","write","approve","comment"}
                for m in _ALL_MODULES if m != "it_management"}
               | {"it_management": {"read"}},
    "editor":  {m: {"read","write","comment"}
                for m in ("dashboard","tracking","list","shop_dwgs","isample")}
               | {"orderbook": {"read","comment"}, "it_management": set()},
    "purchase_officer": {
        "dashboard":    {"read"},
        "tracking":     {"read","comment"},
        "list":         {"read"},
        "shop_dwgs":    {"read"},
        "isample":      {"read"},
        "orderbook":    {"read","write","approve","comment"},
        "it_management": set(),
    },
    "viewer":  {m: {"read"} for m in _ALL_MODULES if m != "it_management"}
               | {"it_management": set()},
}

def has_permission(role: str, module: str, action: str) -> bool:
    return action in MATRIX.get(role, {}).get(module, set())
```

- [ ] **Step 3: Pass + commit**

```bash
docker compose exec api pytest tests/test_permissions.py -q
git add apps/api/app/auth/permissions.py apps/api/tests/test_permissions.py
git commit -m "feat(auth): static RBAC matrix"
```

---

##### Task 16: sessions.py (create/lookup/revoke + sliding + hard-cap)

**Files:**
- Create: `apps/api/app/auth/sessions.py`
- Create: `apps/api/tests/test_sessions.py`

- [ ] **Step 1: Failing test**

```python
import secrets, hashlib
from datetime import timedelta, datetime, timezone
from sqlalchemy import text
import pytest
from app.auth.sessions import (
    create_session, lookup_session, revoke_session,
    SessionExpired, SessionHardCapped, AuthUser,
)
from app.auth.passwords import hash_password

def _mk_user(db, wid):
    return db.execute(text("""
      INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
      VALUES (:w,'a@b','A',:h,'admin') RETURNING id
    """), {"w": wid, "h": hash_password("x")}).scalar()

def test_create_lookup(db, workspace_id):
    uid = _mk_user(db, workspace_id)
    token = create_session(db, uid)
    u = lookup_session(db, token)
    assert isinstance(u, AuthUser)
    assert u.id == uid

def test_revoke(db, workspace_id):
    uid = _mk_user(db, workspace_id)
    token = create_session(db, uid)
    revoke_session(db, token)
    with pytest.raises(SessionExpired):
        lookup_session(db, token)

def test_hard_cap(db, workspace_id):
    uid = _mk_user(db, workspace_id)
    token = create_session(db, uid)
    h = hashlib.sha256(token.encode()).digest()
    past = datetime.now(timezone.utc) - timedelta(days=1)
    db.execute(text("UPDATE session SET hard_expires_at=:t WHERE token_hash=:h"),
               {"t": past, "h": h})
    with pytest.raises(SessionHardCapped):
        lookup_session(db, token)
```

- [ ] **Step 2: Implement**

```python
import secrets, hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..config import settings

class SessionExpired(Exception): ...
class SessionHardCapped(Exception): ...

@dataclass
class AuthUser:
    id: int
    workspace_id: int
    email: str
    full_name: str
    auth_role: str

def _h(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()

def create_session(db: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    hard = datetime.now(timezone.utc) + timedelta(days=settings.session_hard_cap_days)
    db.execute(text("""
        INSERT INTO session(token_hash,user_id,hard_expires_at)
        VALUES (:h,:u,:e)
    """), {"h": _h(token), "u": user_id, "e": hard})
    db.commit()
    return token

def lookup_session(db: Session, token: str) -> AuthUser:
    now = datetime.now(timezone.utc)
    sliding = timedelta(days=settings.session_sliding_days)
    row = db.execute(text("""
        SELECT s.user_id, s.last_seen_at, s.hard_expires_at, s.revoked_at,
               u.workspace_id, u.email, u.full_name, u.auth_role, u.is_active
        FROM session s JOIN app_user u ON u.id = s.user_id
        WHERE s.token_hash = :h
    """), {"h": _h(token)}).mappings().first()
    if not row or row["revoked_at"] is not None or not row["is_active"]:
        raise SessionExpired()
    if row["hard_expires_at"] <= now:
        raise SessionHardCapped()
    if row["last_seen_at"] + sliding <= now:
        raise SessionExpired()
    db.execute(text("UPDATE session SET last_seen_at=:n WHERE token_hash=:h"),
               {"n": now, "h": _h(token)})
    db.commit()
    return AuthUser(
        id=row["user_id"], workspace_id=row["workspace_id"],
        email=row["email"], full_name=row["full_name"], auth_role=row["auth_role"],
    )

def revoke_session(db: Session, token: str) -> None:
    db.execute(text("UPDATE session SET revoked_at=now() WHERE token_hash=:h"),
               {"h": _h(token)})
    db.commit()
```

- [ ] **Step 3: Pass + commit**

```bash
docker compose exec api pytest tests/test_sessions.py -q
git add apps/api/app/auth/sessions.py apps/api/tests/test_sessions.py
git commit -m "feat(auth): session create/lookup/revoke with sliding + hard-cap"
```

---

##### Task 17: audit.py

**Files:**
- Create: `apps/api/app/auth/audit.py`
- Create: `apps/api/tests/test_audit.py`

- [ ] **Step 1: Failing test**

```python
from sqlalchemy import text
from app.auth.audit import write_audit

def test_write_audit(db, workspace_id):
    write_audit(db, workspace_id=workspace_id, actor_id=None,
                event="auth.login", target="a@b", payload={"ip":"127.0.0.1"})
    row = db.execute(text("SELECT event,payload FROM audit_log")).mappings().first()
    assert row["event"] == "auth.login"
    assert row["payload"]["ip"] == "127.0.0.1"
```

- [ ] **Step 2: Implement**

```python
import json
from sqlalchemy import text
from sqlalchemy.orm import Session

def write_audit(db: Session, *, workspace_id: int, actor_id: int | None,
                event: str, target: str | None = None, payload: dict | None = None) -> None:
    db.execute(text("""
      INSERT INTO audit_log(workspace_id,actor_id,event,target,payload)
      VALUES (:w,:a,:e,:t,CAST(:p AS jsonb))
    """), {"w": workspace_id, "a": actor_id, "e": event, "t": target,
           "p": json.dumps(payload or {})})
    db.commit()
```

- [ ] **Step 3: Pass + commit**

```bash
docker compose exec api pytest tests/test_audit.py -q
git add apps/api/app/auth/audit.py apps/api/tests/test_audit.py
git commit -m "feat(auth): audit log writer"
```

---

##### Task 18: rbac.py (current_user + require_permission)

**Files:**
- Create: `apps/api/app/auth/rbac.py`
- Create: `apps/api/tests/test_rbac.py`

- [ ] **Step 1: Failing test**

```python
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from app.auth.rbac import current_user, require_permission
from app.auth.sessions import create_session
from app.auth.passwords import hash_password
from app.db import SessionLocal
from sqlalchemy import text

def _seed(role):
    db = SessionLocal()
    wid = db.execute(text("INSERT INTO workspace(slug,name) VALUES('t2','T') RETURNING id")).scalar()
    uid = db.execute(text("""
      INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
      VALUES (:w,'u@t','U',:h,:r) RETURNING id
    """), {"w": wid, "h": hash_password("x"), "r": role}).scalar()
    tok = create_session(db, uid)
    db.commit()
    return tok

def _app():
    a = FastAPI()
    @a.get("/me", dependencies=[Depends(current_user)])
    def me(): return {"ok": True}
    @a.post("/it")
    def it(_=Depends(require_permission("it_management","write"))): return {"ok": True}
    return a

def test_requires_auth():
    c = TestClient(_app())
    assert c.get("/me").status_code == 401

def test_admin_can_it():
    tok = _seed("admin")
    c = TestClient(_app())
    r = c.post("/it", cookies={"jf_session": tok})
    assert r.status_code == 200

def test_editor_cannot_it():
    tok = _seed("editor")
    c = TestClient(_app())
    r = c.post("/it", cookies={"jf_session": tok})
    assert r.status_code == 403
```

- [ ] **Step 2: Implement**

```python
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from ..db import get_db
from ..config import settings
from .sessions import lookup_session, AuthUser, SessionExpired, SessionHardCapped
from .permissions import has_permission

def current_user(request: Request, db: Session = Depends(get_db)) -> AuthUser:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="no session")
    try:
        return lookup_session(db, token)
    except (SessionExpired, SessionHardCapped):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")

def require_permission(module: str, action: str):
    def _dep(user: AuthUser = Depends(current_user)) -> AuthUser:
        if not has_permission(user.auth_role, module, action):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return user
    return _dep
```

- [ ] **Step 3: Pass + commit**

```bash
docker compose exec api pytest tests/test_rbac.py -q
git add apps/api/app/auth/rbac.py apps/api/tests/test_rbac.py
git commit -m "feat(auth): current_user + require_permission deps"
```

---

##### Task 19: auth routes (/auth/login, /auth/logout, /auth/me)

**Files:**
- Create: `apps/api/app/auth/schemas.py`, `apps/api/app/auth/routes.py`
- Create: `apps/api/tests/test_auth_routes.py`
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: schemas.py**

```python
from pydantic import BaseModel, EmailStr

class LoginIn(BaseModel):
    workspace_slug: str
    email: EmailStr
    password: str

class MeOut(BaseModel):
    id: int
    workspace_id: int
    email: str
    full_name: str
    auth_role: str
```

- [ ] **Step 2: routes.py**

```python
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..db import get_db
from ..config import settings
from .schemas import LoginIn, MeOut
from .passwords import verify_password
from .sessions import create_session, revoke_session, AuthUser
from .rbac import current_user
from .audit import write_audit

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
def login(body: LoginIn, resp: Response, db: Session = Depends(get_db)):
    row = db.execute(text("""
      SELECT u.id, u.password_hash, u.workspace_id, u.is_active
      FROM app_user u JOIN workspace w ON w.id = u.workspace_id
      WHERE w.slug = :s AND u.email = :e
    """), {"s": body.workspace_slug, "e": body.email}).mappings().first()
    if not row or not row["is_active"] or not verify_password(row["password_hash"], body.password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = create_session(db, row["id"])
    write_audit(db, workspace_id=row["workspace_id"], actor_id=row["id"],
                event="auth.login", target=body.email)
    resp.set_cookie(
        settings.session_cookie_name, token,
        httponly=True, samesite="lax", secure=False, path="/",
        max_age=settings.session_sliding_days * 86400,
    )
    return {"ok": True}

@router.post("/logout")
def logout(request: Request, resp: Response, db: Session = Depends(get_db),
           user: AuthUser = Depends(current_user)):
    tok = request.cookies.get(settings.session_cookie_name)
    if tok:
        revoke_session(db, tok)
    write_audit(db, workspace_id=user.workspace_id, actor_id=user.id, event="auth.logout")
    resp.delete_cookie(settings.session_cookie_name, path="/")
    return {"ok": True}

@router.get("/me", response_model=MeOut)
def me(user: AuthUser = Depends(current_user)):
    return MeOut(**user.__dict__)
```

- [ ] **Step 3: Mount in main.py**

```python
from fastapi import FastAPI
from .auth.routes import router as auth_router

app = FastAPI(title="JoineryFlow API")
app.include_router(auth_router)

@app.get("/health")
def health(): return {"ok": True}
```

- [ ] **Step 4: Route test**

```python
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.db import SessionLocal
from app.auth.passwords import hash_password

def _seed():
    db = SessionLocal()
    db.execute(text("DELETE FROM app_user")); db.execute(text("DELETE FROM workspace"))
    wid = db.execute(text("INSERT INTO workspace(slug,name) VALUES('h','H') RETURNING id")).scalar()
    db.execute(text("""
      INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
      VALUES (:w,'x@h','X',:p,'admin')"""), {"w": wid, "p": hash_password("pw")})
    db.commit()

def test_login_me_logout():
    _seed()
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug":"h","email":"x@h","password":"pw"})
    assert r.status_code == 200
    r2 = c.get("/auth/me")
    assert r2.status_code == 200 and r2.json()["email"] == "x@h"
    r3 = c.post("/auth/logout")
    assert r3.status_code == 200
```

- [ ] **Step 5: Pass + commit**

```bash
docker compose exec api pytest tests/test_auth_routes.py -q
git add apps/api/app/auth apps/api/app/main.py apps/api/tests/test_auth_routes.py
git commit -m "feat(auth): login/logout/me routes"
```

---

#### Phase 5 — Workspace/users + seed

##### Task 20: /workspace + /users endpoints

**Files:**
- Create: `apps/api/app/workspaces/__init__.py`, `apps/api/app/workspaces/routes.py`
- Create: `apps/api/app/users/__init__.py`, `apps/api/app/users/schemas.py`, `apps/api/app/users/routes.py`
- Create: `apps/api/tests/test_users_routes.py`
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: workspaces/routes.py**

```python
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..db import get_db
from ..auth.rbac import current_user
from ..auth.sessions import AuthUser

router = APIRouter(prefix="/workspace", tags=["workspace"])

@router.get("")
def get_workspace(user: AuthUser = Depends(current_user), db: Session = Depends(get_db)):
    row = db.execute(text("SELECT id,slug,name FROM workspace WHERE id=:i"),
                     {"i": user.workspace_id}).mappings().first()
    return dict(row)
```

- [ ] **Step 2: users/schemas.py**

```python
from pydantic import BaseModel, EmailStr

class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    auth_role: str
    jtbd_role: str | None
    is_active: bool

class UserPatch(BaseModel):
    full_name: str | None = None
    auth_role: str | None = None
    jtbd_role: str | None = None
    is_active: bool | None = None
```

- [ ] **Step 3: users/routes.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..db import get_db
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..auth.audit import write_audit
from .schemas import UserOut, UserPatch

router = APIRouter(prefix="/users", tags=["users"])

@router.get("", response_model=list[UserOut])
def list_users(user: AuthUser = Depends(require_permission("it_management","read")),
               db: Session = Depends(get_db)):
    rows = db.execute(text("""
      SELECT id,email,full_name,auth_role,jtbd_role,is_active
      FROM app_user WHERE workspace_id=:w ORDER BY full_name
    """), {"w": user.workspace_id}).mappings().all()
    return [dict(r) for r in rows]

@router.patch("/{uid}", response_model=UserOut)
def patch_user(uid: int, body: UserPatch,
               user: AuthUser = Depends(require_permission("it_management","write")),
               db: Session = Depends(get_db)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "no fields")
    if "auth_role" in fields and fields["auth_role"] not in (
        "admin","manager","editor","purchase_officer","viewer"):
        raise HTTPException(400, "bad auth_role")
    sets = ", ".join(f"{k}=:{k}" for k in fields)
    params = {**fields, "i": uid, "w": user.workspace_id}
    row = db.execute(text(f"""
      UPDATE app_user SET {sets} WHERE id=:i AND workspace_id=:w
      RETURNING id,email,full_name,auth_role,jtbd_role,is_active
    """), params).mappings().first()
    if not row:
        raise HTTPException(404)
    db.commit()
    write_audit(db, workspace_id=user.workspace_id, actor_id=user.id,
                event="user.update", target=str(uid), payload=fields)
    return dict(row)
```

- [ ] **Step 4: Mount in main.py**

```python
from .workspaces.routes import router as ws_router
from .users.routes import router as users_router
app.include_router(ws_router)
app.include_router(users_router)
```

- [ ] **Step 5: Test (list + forbidden PATCH for editor)**

```python
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.db import SessionLocal
from app.auth.passwords import hash_password

def _login(role):
    db = SessionLocal()
    db.execute(text("DELETE FROM session")); db.execute(text("DELETE FROM app_user"))
    db.execute(text("DELETE FROM workspace"))
    wid = db.execute(text("INSERT INTO workspace(slug,name) VALUES('h','H') RETURNING id")).scalar()
    db.execute(text("""INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
                       VALUES (:w,'u@h','U',:p,:r)"""),
               {"w": wid, "p": hash_password("pw"), "r": role})
    db.commit()
    c = TestClient(app)
    c.post("/auth/login", json={"workspace_slug":"h","email":"u@h","password":"pw"})
    return c

def test_admin_lists_users():
    c = _login("admin")
    r = c.get("/users")
    assert r.status_code == 200 and len(r.json()) == 1

def test_editor_cannot_list_users():
    c = _login("editor")
    r = c.get("/users")
    assert r.status_code == 403
```

- [ ] **Step 6: Commit**

```bash
docker compose exec api pytest tests/test_users_routes.py -q
git add apps/api/app/workspaces apps/api/app/users apps/api/app/main.py apps/api/tests/test_users_routes.py
git commit -m "feat(api): workspace + users endpoints"
```

---

##### Task 21: Seed script — hartwood-joinery + 8 users

**Files:**
- Create: `seed/__init__.py`, `seed/hartwood_joinery.py`

- [ ] **Step 1: Write seed**

```python
from sqlalchemy import text
from app.db import SessionLocal
from app.auth.passwords import hash_password

USERS = [
    ("aria.voss@hartwood.test",   "Aria Voss",   "admin",            "CEO"),
    ("rin.park@hartwood.test",    "Rin Park",    "manager",          "PM"),
    ("theo.blake@hartwood.test",  "Theo Blake",  "manager",          "PM"),
    ("noa.lindqvist@hartwood.test","Noa Lindqvist","editor",         "Drafter"),
    ("juno.okafor@hartwood.test", "Juno Okafor", "editor",           "Foreman"),
    ("kai.matthews@hartwood.test","Kai Matthews","editor",           "Machine"),
    ("mina.klee@hartwood.test",   "Mina Klee",   "purchase_officer", "Procurement"),
    ("sam.ito@hartwood.test",     "Sam Ito",     "viewer",           "Observer"),
]

def main():
    db = SessionLocal()
    wid = db.execute(text(
      "INSERT INTO workspace(slug,name) VALUES('hartwood-joinery','Hartwood Joinery') "
      "ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name RETURNING id"
    )).scalar()
    pw = hash_password("hartwood-dev")
    for email, name, role, jtbd in USERS:
        db.execute(text("""
          INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role,jtbd_role)
          VALUES (:w,:e,:n,:p,:r,:j)
          ON CONFLICT(workspace_id,email) DO NOTHING
        """), {"w": wid, "e": email, "n": name, "p": pw, "r": role, "j": jtbd})
    db.commit()
    print(f"seeded workspace {wid} with {len(USERS)} users")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run + verify**

```bash
docker compose exec api python -m seed.hartwood_joinery
docker compose exec db psql -U jf -d joineryflow -c "SELECT email,auth_role FROM app_user ORDER BY full_name"
```
Expected: 8 users, Mina Klee → `purchase_officer`.

- [ ] **Step 3: Commit**

```bash
git add seed && git commit -m "feat(seed): hartwood-joinery workspace + 8 users"
```

---

##### Task 22: Port legacy `procurement_api.py` — split into schemas/queries/routes

**Files:**
- Create: `apps/api/app/procurement/__init__.py`, `schemas.py`, `queries.py`, `routes.py`
- Reference: `legacy/procurement_api.py`
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: Extract Pydantic shapes into `schemas.py`** — one class per request/response body in the legacy file. Keep names identical.

- [ ] **Step 2: Extract each SQL call into `queries.py`** functions returning rows. Apply MySQL → Postgres conversions **mechanically**:
  - `AUTO_INCREMENT` / `LAST_INSERT_ID()` → `RETURNING id`
  - `ON DUPLICATE KEY UPDATE` → `ON CONFLICT (...) DO UPDATE SET ...`
  - `LIMIT n, m` → `LIMIT m OFFSET n`
  - backtick quoting ``` `col` ``` → double-quote `"col"` (or unquoted)
  - `NOW()` stays; `UTC_TIMESTAMP()` → `now() AT TIME ZONE 'UTC'`
  - `IFNULL` → `COALESCE`
  - Named params `%s` → SQLAlchemy `:name`

- [ ] **Step 3: `routes.py`** — FastAPI routers that call `queries.py` and gate with `require_permission("orderbook", action)`.

- [ ] **Step 4: Mount**

```python
from .procurement.routes import router as proc_router
app.include_router(proc_router, prefix="/procurement")
```

- [ ] **Step 5: Smoke-test that it imports**

```bash
docker compose exec api python -c "from app.main import app; print(len(app.routes))"
```
Expected: prints a number > baseline.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/procurement apps/api/app/main.py
git commit -m "feat(procurement): split legacy api into schemas/queries/routes (postgres)"
```

---

#### Phase 6 — Next.js shell

##### Task 23: Design tokens (H palette)

**Files:**
- Create: `apps/web/lib/tokens.ts`
- Modify: `apps/web/app/globals.css`
- Modify: `apps/web/tailwind.config.ts`

- [ ] **Step 1: tokens.ts**

```ts
export const H = {
  bg:      "oklch(98% 0.005 95)",
  surface: "oklch(100% 0 0)",
  ink:     "oklch(22% 0.02 95)",
  muted:   "oklch(55% 0.02 95)",
  line:    "oklch(90% 0.005 95)",
  accent:  "oklch(56% 0.15 150)",
} as const;
```

- [ ] **Step 2: globals.css — CSS vars**

```css
:root {
  --h-bg: oklch(98% 0.005 95);
  --h-surface: #fff;
  --h-ink: oklch(22% 0.02 95);
  --h-muted: oklch(55% 0.02 95);
  --h-line: oklch(90% 0.005 95);
  --h-accent: oklch(56% 0.15 150);
}
body { background: var(--h-bg); color: var(--h-ink); }
```

- [ ] **Step 3: tailwind.config.ts — extend colors**

```ts
import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        h: {
          bg: "var(--h-bg)", surface: "var(--h-surface)", ink: "var(--h-ink)",
          muted: "var(--h-muted)", line: "var(--h-line)", accent: "var(--h-accent)",
        },
      },
    },
  },
};
export default config;
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/lib/tokens.ts apps/web/app/globals.css apps/web/tailwind.config.ts
git commit -m "feat(web): H design tokens"
```

---

##### Task 24: Next.js proxy route

**Files:**
- Create: `apps/web/app/api/[...proxy]/route.ts`

- [ ] **Step 1: Write proxy**

```ts
import { NextRequest, NextResponse } from "next/server";

const API = process.env.API_URL ?? "http://api:8000";

async function forward(req: NextRequest, ctx: { params: Promise<{ proxy: string[] }> }) {
  const { proxy } = await ctx.params;
  const url = `${API}/${proxy.join("/")}${req.nextUrl.search}`;
  const headers = new Headers(req.headers);
  headers.delete("host");
  const body = ["GET","HEAD"].includes(req.method) ? undefined : await req.arrayBuffer();
  const upstream = await fetch(url, { method: req.method, headers, body, redirect: "manual" });
  const respHeaders = new Headers(upstream.headers);
  respHeaders.delete("content-encoding");
  respHeaders.delete("transfer-encoding");
  return new NextResponse(upstream.body, { status: upstream.status, headers: respHeaders });
}

export { forward as GET, forward as POST, forward as PATCH, forward as PUT, forward as DELETE };
```

- [ ] **Step 2: Verify**

```bash
curl -s http://localhost:3000/api/health
```
Expected: `{"ok":true}`

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/api
git commit -m "feat(web): server-side proxy to fastapi"
```

---

##### Task 25: lib/session.ts + middleware.ts

**Files:**
- Create: `apps/web/lib/session.ts`
- Create: `apps/web/middleware.ts`

- [ ] **Step 1: lib/session.ts**

```ts
import { cookies } from "next/headers";

export async function getSessionCookie() {
  const c = await cookies();
  return c.get("jf_session")?.value ?? null;
}

export async function fetchMe() {
  const tok = await getSessionCookie();
  if (!tok) return null;
  const r = await fetch(`${process.env.API_URL}/auth/me`, {
    headers: { cookie: `jf_session=${tok}` }, cache: "no-store",
  });
  return r.ok ? r.json() : null;
}
```

- [ ] **Step 2: middleware.ts**

```ts
import { NextResponse, type NextRequest } from "next/server";

const PUBLIC = ["/login", "/api", "/_next", "/favicon.ico"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (PUBLIC.some(p => pathname.startsWith(p))) return NextResponse.next();
  const tok = req.cookies.get("jf_session")?.value;
  if (!tok) return NextResponse.redirect(new URL("/login", req.url));
  return NextResponse.next();
}

export const config = { matcher: "/((?!_next/static|_next/image|favicon.ico).*)" };
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/lib/session.ts apps/web/middleware.ts
git commit -m "feat(web): auth middleware + session helpers"
```

---

##### Task 26: Login page

**Files:**
- Create: `apps/web/app/(public)/login/page.tsx`

- [ ] **Step 1: Write page**

```tsx
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function Login() {
  const r = useRouter();
  const [email, setEmail] = useState("rin.park@hartwood.test");
  const [password, setPassword] = useState("hartwood-dev");
  const [err, setErr] = useState<string|null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const resp = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ workspace_slug: "hartwood-joinery", email, password }),
    });
    if (!resp.ok) { setErr("Invalid credentials"); return; }
    r.replace("/dashboard");
  }

  return (
    <main className="min-h-screen grid place-items-center bg-h-bg">
      <form onSubmit={submit} className="w-[360px] rounded-2xl bg-h-surface p-8 shadow-sm border border-h-line space-y-4">
        <h1 className="text-xl font-semibold text-h-ink">JoineryFlow</h1>
        <label className="block text-sm">
          <span className="text-h-muted">Email</span>
          <input className="mt-1 w-full rounded border border-h-line px-3 py-2"
                 value={email} onChange={e=>setEmail(e.target.value)} />
        </label>
        <label className="block text-sm">
          <span className="text-h-muted">Password</span>
          <input type="password" className="mt-1 w-full rounded border border-h-line px-3 py-2"
                 value={password} onChange={e=>setPassword(e.target.value)} />
        </label>
        {err && <p className="text-sm text-red-600">{err}</p>}
        <button className="w-full rounded bg-h-accent text-white py-2">Sign in</button>
      </form>
    </main>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add "apps/web/app/(public)"
git commit -m "feat(web): login page"
```

---

##### Task 27: App chrome + layout

**Files:**
- Create: `apps/web/components/chrome/HAppChrome.tsx`, `TopBar.tsx`, `TabStrip.tsx`, `SideBar.tsx`
- Create: `apps/web/app/(app)/layout.tsx`

- [ ] **Step 1: TabStrip.tsx**

```tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/tracking",  label: "Tracking" },
  { href: "/list",      label: "List" },
  { href: "/shop-dwgs", label: "Shop Dwgs" },
  { href: "/isample",   label: "iSample" },
  { href: "/orderbook", label: "Orderbook" },
];

export function TabStrip() {
  const p = usePathname();
  return (
    <nav className="flex gap-1 border-b border-h-line px-4">
      {TABS.map(t => {
        const active = p.startsWith(t.href);
        return (
          <Link key={t.href} href={t.href}
                className={`px-4 py-2 text-sm ${active ? "border-b-2 border-h-accent text-h-ink" : "text-h-muted"}`}>
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 2: TopBar.tsx**

```tsx
export function TopBar({ user }: { user: { full_name: string; auth_role: string } }) {
  return (
    <header className="flex items-center justify-between px-4 h-14 border-b border-h-line bg-h-surface">
      <div className="font-semibold text-h-ink">JoineryFlow</div>
      <form action="/api/auth/logout" method="post">
        <button className="text-sm text-h-muted hover:text-h-ink">
          {user.full_name} · {user.auth_role} · Sign out
        </button>
      </form>
    </header>
  );
}
```

- [ ] **Step 3: SideBar.tsx** (stub — context-dependent later)

```tsx
export function SideBar() {
  return <aside className="w-56 border-r border-h-line p-4 text-sm text-h-muted">—</aside>;
}
```

- [ ] **Step 4: HAppChrome.tsx**

```tsx
import { TopBar } from "./TopBar";
import { TabStrip } from "./TabStrip";
import { SideBar } from "./SideBar";

export function HAppChrome({ user, children }: {
  user: { full_name: string; auth_role: string }; children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-h-bg">
      <TopBar user={user} />
      <TabStrip />
      <div className="flex">
        <SideBar />
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: (app)/layout.tsx**

```tsx
import { redirect } from "next/navigation";
import { fetchMe } from "@/lib/session";
import { HAppChrome } from "@/components/chrome/HAppChrome";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const me = await fetchMe();
  if (!me) redirect("/login");
  return <HAppChrome user={me}>{children}</HAppChrome>;
}
```

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/chrome "apps/web/app/(app)/layout.tsx"
git commit -m "feat(web): app chrome + 6-tab strip"
```

---

##### Task 28: Stub tab pages

**Files:**
- Create: `apps/web/app/(app)/dashboard/page.tsx`, `tracking/page.tsx`, `list/page.tsx`, `shop-dwgs/page.tsx`, `isample/page.tsx`, `orderbook/page.tsx`, `it/page.tsx`

- [ ] **Step 1: Generic stub template** (apply per module)

```tsx
import { fetchMe } from "@/lib/session";

export default async function Page() {
  const me = await fetchMe();
  return (
    <section>
      <h1 className="text-2xl font-semibold text-h-ink">Tracking</h1>
      <p className="text-sm text-h-muted">Stub. Implemented in PM Workbench sub-project.</p>
      {me?.auth_role === "purchase_officer" && (
        <p className="mt-4 text-sm text-h-accent">Read-only + comment mode (Purchase Officer).</p>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Create all six analogous files** (change the heading + strip the purchase_officer hint on non-tracking pages). `it/page.tsx` should be gated:

```tsx
import { fetchMe } from "@/lib/session";
import { redirect } from "next/navigation";

export default async function ITPage() {
  const me = await fetchMe();
  if (me?.auth_role !== "admin") redirect("/dashboard");
  return <section><h1 className="text-2xl font-semibold">IT Management</h1></section>;
}
```

- [ ] **Step 3: Commit**

```bash
git add "apps/web/app/(app)"
git commit -m "feat(web): stub pages for 6 tabs + IT gate"
```

---

#### Phase 7 — E2E + acceptance

##### Task 29: Playwright smoke test

**Files:**
- Create: `apps/web/playwright.config.ts`
- Create: `tests/e2e/smoke.spec.ts`
- Modify: `apps/web/package.json` (add `@playwright/test`)

- [ ] **Step 1: Install**

```bash
pnpm --dir apps/web add -D @playwright/test && pnpm --dir apps/web exec playwright install --with-deps chromium
```

- [ ] **Step 2: playwright.config.ts**

```ts
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "../../tests/e2e",
  use: { baseURL: "http://localhost:3000", headless: true },
});
```

- [ ] **Step 3: smoke.spec.ts**

```ts
import { test, expect } from "@playwright/test";

test("login → six tabs → logout", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="email"], input:not([type])', "rin.park@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/dashboard$/);
  for (const label of ["Dashboard","Tracking","List","Shop Dwgs","iSample","Orderbook"]) {
    await expect(page.getByRole("link", { name: label })).toBeVisible();
  }
  await page.click('button:has-text("Sign out")');
  await expect(page).toHaveURL(/\/login$/);
});
```

- [ ] **Step 4: Run**

```bash
make up && make migrate && make seed && make e2e
```
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/web/playwright.config.ts tests/e2e apps/web/package.json apps/web/pnpm-lock.yaml
git commit -m "test(e2e): login/tabs/logout smoke"
```

---

##### Task 30: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append dev commands + Foundation status**

Add a "Foundation dev loop" section:

```markdown
## Foundation dev loop

- `make up` — build + start db/api/web
- `make migrate` — apply Alembic migrations (0001–0004)
- `make seed` — seed hartwood-joinery + 8 users
- `make test` — pytest
- `make e2e` — Playwright smoke
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md && git commit -m "docs(claude): foundation dev loop"
```

---

##### Task 31: Acceptance checklist

- [ ] `docker compose up -d --build` → `db`, `api`, `web` all healthy
- [ ] `make migrate` → alembic reaches revision `0004`
- [ ] `make seed` → 8 users exist; Mina Klee is `purchase_officer`
- [ ] `curl http://localhost:3000/api/health` → `{"ok":true}`
- [ ] Open http://localhost:3000 → redirected to `/login`
- [ ] Login as `rin.park@hartwood.test` / `hartwood-dev` → land on `/dashboard`
- [ ] Six tabs visible; `/it` not accessible
- [ ] Sign in as `aria.voss@hartwood.test` → `/it` renders
- [ ] Sign in as `mina.klee@hartwood.test` → `/tracking` shows purchase-officer hint; `/it` redirects
- [ ] `make test` → all pytest suites green
- [ ] `make e2e` → Playwright smoke green
- [ ] `audit_log` contains `auth.login` + `auth.logout` rows after the flow

---

#### Self-Review

**Spec coverage:** §2 tech stack → T4/T5/T6; §3 architecture → T4/T24/T25; §4 repo layout → T1/T2 + file structure above; §5.1 DDL → T12; §5.2 material catalog six tables → T11; §5.3 seeds → T21; §6.4 matrix → T15; §6.5 deps → T18; §6.6 audit → T17/T19/T20; §6.7 endpoints → T19/T20; §7 dev loop + tests → T3/T13/T29; §7.5 acceptance → T31. Procurement port obligation → T22.

**Placeholder scan:** No TBDs. All SQL, Python, TSX, CSS, and commands are concrete. T9/T10 intentionally defer paste-in of the legacy CREATE TABLE statements to the engineer because the legacy files live on disk — the conversion rules are explicit.

**Type consistency:** `AuthUser` fields (id, workspace_id, email, full_name, auth_role) match MeOut schema and are consumed unchanged by `HAppChrome`/`TopBar`. `auth_role` enum values are identical in T12 (CHECK constraint), T15 (matrix keys), T20 (PATCH validator), T21 (seed), and T27 (JSX display). Session cookie name `jf_session` matches across T3 env, T18 dep, T19 routes, and T25 middleware.
