# JoineryFlow — Foundation Design

**Date:** 22/04/2026
**Status:** Approved (pending written-spec review)
**Scope:** Sub-project #1 of the JoineryFlow build. Provides the tech stack, repo scaffold, DB + migrations, auth + RBAC, base chrome, and local dev loop. All user-facing business surfaces (PM Workbench, Drafter Editor, Procurement UI, CV import, PDF) are later sub-projects.

## 1. Context & Decomposition

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

## 2. Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Frontend | **Next.js 15** (App Router) + TypeScript + Tailwind | Closest to the existing `hi-*.jsx` hi-fi files; minimal translation cost. |
| Backend | **FastAPI** (Python 3.12) + SQLAlchemy Core (`text()` queries) + Pydantic v2 | Preserves `procurement_api.py` without rewrite. |
| Database | **Postgres 16** | Stronger constraints, JSON support, citext, modern hosting. Ports the two existing MySQL `.sql` files. |
| Auth | **Self-built**, server-side sessions, httpOnly cookie | Full control; no vendor dependency. |
| Migrations | **Alembic** | Python-native, fits FastAPI repo. |
| Dev env | **docker-compose** (`web`, `api`, `db`) | Local-only for now; production target deferred to a later spec. |
| Monorepo | Single git repo | `apps/web`, `apps/api`, `db/`, `docs/` at root. |

## 3. Architecture

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

## 4. Repo Layout

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

## 5. Data Model (Foundation only)

Foundation adds only the tables required to authenticate and route by role. Business tables (items, materials, procurement batches) land in later specs.

### 5.1 New tables

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

### 5.2 Design rationale

- `session.token_hash` stores `sha256(token)`; the raw token lives only in the cookie. A DB breach cannot replay sessions.
- `citext` on email: case-insensitive uniqueness without app-layer normalization.
- `jsonb` `audit_log.detail` survives schema drift in the future admin log surface.
- `jtbd_role` is separate from `auth_role`. Six operational roles (CEO/PM/Drafter/Foreman/Machine/Procurement) map onto five RBAC tiers with a default mapping but admin-overridable per user.
- `gen_random_uuid()` requires the `pgcrypto` extension — migration `0004` enables it if not present.

### 5.3 Seeded fixtures

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

### 5.4 Out of scope for Foundation

Password reset flow, email delivery, invitations, SSO, MFA, password policy, rate limiting on login. All are auth features but are scoped to a later module — not blockers for an authenticated stub app.

## 6. Auth, RBAC & Request Flow

### 6.1 Password hashing

argon2id via `argon2-cffi`. Parameters from env:
- `ARGON2_TIME_COST=3`
- `ARGON2_MEMORY_KB=65536`
- parallelism = 1

No legacy hashes to support.

### 6.2 Session token

32 random bytes (`secrets.token_bytes(32)`), base64url-encoded. Raw token goes in the cookie; `sha256(token)` is stored in `session.token_hash`.

- Sliding expiry: `expires_at` extended to `now() + SESSION_TTL_DAYS` on every authenticated request.
- Hard cap: sessions older than `issued_at + SESSION_MAX_DAYS` are rejected even if sliding expiry is fresh.
- Defaults: `SESSION_TTL_DAYS=14`, `SESSION_MAX_DAYS=30`.

### 6.3 Cookie

```
Set-Cookie: jf_session=<token>; HttpOnly; SameSite=Lax; Path=/;
            Secure (prod only); Max-Age=1209600
```

- `Secure` is toggled off in dev so it works over plain http; `COOKIE_SECURE=false` in `.env.example`.
- `SameSite=Lax` — the app is first-party; no embedded cross-site POSTs needed.

### 6.4 RBAC model — module × action

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

### 6.5 FastAPI dependencies

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

### 6.6 Audit events written in Foundation

- `auth.login.success` — detail: `{ workspace_slug, ip, user_agent }`
- `auth.login.failure` — detail: `{ workspace_slug, email_tried, reason }` (reason ∈ `unknown_user | wrong_password | workspace_mismatch | user_suspended`)
- `auth.logout` — detail: `{}`
- `auth.session.expired` — detail: `{ session_age_days }` (written lazily on first failed lookup)
- `user.role_changed` — detail: `{ target_user_id, from, to }`
- `user.status_changed` — detail: `{ target_user_id, from, to }`

Everything else (project.created, po.approved, etc.) is written by its own module.

### 6.7 Endpoints shipped in Foundation

```
POST   /auth/login          { workspace_slug, email, password } → Set-Cookie
POST   /auth/logout         → clears cookie, deletes session row
GET    /auth/me             → { user, workspace }
GET    /workspace           → workspace info for chrome
GET    /users               admin-only; list workspace users
PATCH  /users/{id}          admin-only; change auth_role or status
```

No other endpoints ship in Foundation. The six tab pages in `apps/web` render stub content gated by `current_user()`.

## 7. Dev Loop, Config & Testing

### 7.1 Environment variables

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

### 7.2 docker-compose services

- `db` — `postgres:16`, named volume for data, healthcheck on `pg_isready`.
- `api` — builds from `apps/api`, runs `uvicorn joineryflow_api.main:app --host 0.0.0.0 --reload`, depends on db healthcheck.
- `web` — builds from `apps/web`, runs `next dev`, depends on api.

### 7.3 Makefile

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

### 7.4 Testing (Foundation scope)

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

### 7.5 "Foundation done" — acceptance checklist

1. `git clone && cp .env.example .env && make up && make migrate && make seed` → running stack, no manual steps.
2. Visit `http://localhost:3000` → `HiLogin` surface with workspace selector prefilled to `hartwood-joinery`.
3. Log in as each seeded user → correct default tab, 6-tab chrome renders, sidebar shows fixture projects by name (no data yet), logout works.
4. As admin, `PATCH /users/{id}` changes another user's `auth_role`; `user.role_changed` audit row written.
5. `purchase_officer` user hits `/orderbook` → full access. Hits `/tracking` → read-only UI with visible "can comment, cannot edit" hint.
6. All Alembic migrations reversible: `alembic downgrade base` runs clean.
7. `make test` green. `make e2e` green.

## 8. Explicitly Out of Scope

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

## 9. Open Questions

None blocking. Spec is ready for a written-spec review pass, then an implementation plan.

## 10. Reference

- `docs/product_spec.md` — product overview, roles, data-model invariants, design tokens, IA. Authoritative.
- `docs/trackingv2.md` — v1 module build plan.
- `CLAUDE.md` — repo-level guidance for future Claude Code sessions.
