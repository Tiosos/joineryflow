# Implementation Record — Estimating — sub-project #9a

> **Status: shipped. Written after the fact (2026-08-14).** #9a was built
> directly on `main` without a spec or a plan, so for three months the only
> written record was the `## Estimating (sub-project #9a)` section of
> `CLAUDE.md`. This file backfills the design record so #9a sits alongside the
> other sub-projects; **`CLAUDE.md` remains the statement of current state**,
> and this doc explains the decisions behind it.
>
> Because it is reconstructed from the shipped code rather than written ahead
> of it, treat any disagreement between this file and the code as the code
> being right.
>
> Commits: `a7b8d3d` (module + team-status + tracking overhaul), `620930e`
> (cookie constant, expire button, test gaps), `b910ab1` (tracking follow-ups).
> Migrations: `0021_estimating_core`, `0022_estimate_expires_at`,
> `0023_team_status`.

> **Later change — superseded in part by Plan V1 (see `docs/plan-v1/`).** A
> **Tender Dashboard wraps** this module rather than replacing it: the estimate
> becomes one step of Plan V1 §5's lifecycle (Q487). The **6-state machine in
> `_LEGAL_TRANSITIONS` is replaced by 12 stages** (Q488), and `expired` — which
> has no counterpart in that list — **maps onto Lost**, a lossy migration, while
> `expires_at` survives as the validity window (Q548). **Convert gains a PM
> review step** (Q490) and now **creates Joinery Items** from the quote's lines
> (Q489), which it deliberately does not do today.

---

## 1. Why a seventh role

Estimating is the first surface that belongs to someone who is neither
upstream nor downstream of the Drafter: an estimator prices work that does not
exist yet. Reusing `manager` would have handed them the whole workbench;
reusing `viewer` would have denied them writes on their own quotes. Migration
0021 widens the `app_user.auth_role` CHECK and the matrix gains a **7th role**
plus a **10th operational module**:

- `estimator` → `{read, write, approve, comment}` on `estimating`; read (and
  mostly comment) elsewhere; `it_management` empty.
- Every other role is read-only on `estimating`, except `drafter`
  (`read, comment`).

`/it/labour-rates` is the exception to the module gate: it is workspace
configuration, so it gates on `("it_management", …)` — admin only — even
though it lives in the estimating router.

## 2. Data model

`estimate` is the root (one per quoted job); `estimate_revision` is the
versioned unit (`rev_no`, immutable once it leaves `draft`); `estimate_line`
hangs off a revision, with optional part / hardware / labour breakdown rows.

**The binding decision is snapshotting.** Every cost column on lines, parts,
hardware and labour is stored as `*_snapshot` with `cost_extended` GENERATED,
while the live `material_id` is retained alongside for traceability. A quote
that was sent last month must still print last month's numbers even after the
catalog reprices — so the quote carries its own copy, and the `material_id` is
a breadcrumb, not a lookup key. This is why hard-deleting a catalog row does
not corrupt historical quotes (it does leave a dangling `material_id`, which
is one reason the hard-delete route was retired in `64ef89e`).

Constraints worth knowing:

- `uniq_estimate_draft` — a partial unique index enforcing **at most one
  `draft` revision per estimate**. "Revise" is therefore not idempotent by
  accident; it fails loudly if a draft is already open.
- `estimate_line_labour` is UNIQUE on `(line_id, stage_key)` and snapshots the
  per-stage `workspace_labour_rate` on insert.
- `estimate_line_part.material_type IN ('BOARD','CUSTOM','BENCHTOP')`;
  `estimate_line_hardware.material_type IN ('HARDWARE','APPLIANCE')`.
  **Equipment hire is deliberately excluded** — hire rows carry a `project_id`
  FK on the catalog row itself, and a quote exists before its project does, so
  there is nothing to point at.
- `estimate_no` is generated per workspace (`EST-{year}-{n:04d}`). A shared
  counter would collide on `uq_estimate_no` and disclose another workspace's
  quote volume.

Migration 0021's **downgrade is a no-op** — it is irreversible by design;
recover from 0001–0020.

## 3. Revision workflow (binding)

`_LEGAL_TRANSITIONS` in `queries.py`:

```
draft ──► sent ──► accepted
  │        ├──► rejected
  │        ├──► expired
  │        └──► withdrawn
  └──► withdrawn
```

`accepted`, `rejected`, `expired`, `withdrawn` are terminal. Anything else
returns `409 {code: "BAD_TRANSITION", from, to}`. `revise` clones the current
revision into a new `draft` at `rev_no + 1`. The `approve` action gates
lock-and-send and Convert.

`0022` adds `estimate_revision.expires_at` (a date) for the quote validity
window — the `expired` transition is a human action against that date, not a
scheduled job.

## 4. Convert-to-Project

`POST /revisions/{rid}/convert` is the seam between estimating and the rest of
the app. It requires status `accepted` (`409 BAD_STATUS` otherwise), refuses a
revision already converted (`409 ALREADY_CONVERTED`, echoing the existing
`project_id`), refuses an archived customer, re-resolves each part snapshot,
and creates a project wired to `projects.estimate_revision_id` +
`projects.customer_id`.

**It stops at project creation.** Generating supplier orders from an accepted
quote is deferred — the procurement side owns that, and forcing it here would
couple the two modules on a workflow nobody has specified yet.

## 5. Surface

32 endpoints, all at top-level paths (no prefix): customers CRUD + archive;
estimates list / detail / create / patch / revise; revision detail + patch +
the six transitions; line CRUD + reorder; per-line part / hardware / labour
add / patch / delete; `GET`+`PATCH /it/labour-rates`; and
`GET /revisions/{rid}/quote.pdf` (WeasyPrint, reusing #5b's engine, `inline`
with an RFC 8187 dual filename).

Web: `/estimating?subtab=active|archive&q=&customer=&status=` plus
`/estimating/[eid]`, and the `/customers` registry with `/customers/[cid]`.
Both are **secondary** TabStrip entries — the primary six IA tabs do not grow.

## 6. What shipped alongside (not strictly estimating)

These landed in the same batch and touch shared chrome, which is why they are
easy to mistake for estimating work:

- **`/home` → `/dashboard`.** `/home` became a bare `redirect("/dashboard")`,
  reversing the #2 decision that made `/home` the landing page.
- **`GET /public/stats`** — unauthenticated, feeds the dashboard and the login
  page's stats block, replacing hardcoded numbers.
- **Team status** (migration `0023`) — `app_user.work_status`
  (`IN|ON_SITE|SHOP|WFH|OFF`, nullable) + `location_label`, with
  `PATCH /me/status` and `GET /workspace/team` behind the dashboard Team card.
  Nothing to do with quoting; it shipped here because the dashboard was
  already being rebuilt.
- **TabStrip secondary row** and the **full hi-fi palette** in `globals.css`
  (`ink2/3/4`, `surfaceAlt`, `accentSoft`, `info`).
- **Tracking overhaul** — `TrackingClient` split into quick-filter chips +
  sub-tabs + search, with `ItemsTable`, `ItemDetailModal`,
  `ProjectDetailModal`, `StatusPopup`, `ProjectInfoBar`, `TrackingMetrics`;
  `/list` wired to the shared `ItemsTable`.

## 7. Known gaps

- **`_role_view` does not know this role.** `/home/dashboard` branches on
  `auth_role` alone; `estimator` (and `editor`) fall through to the viewer
  shape, and `HomeDashboardOut.role_view` has no `estimator` member. An
  estimator gets a viewer's dashboard.
- No workspace-isolation suite shipped with #9a. Added later in `901d0d6`.

## 8. Out of scope (deferred)

PO / supplier-order generation from an accepted quote; multi-currency; client
e-signature or portal; estimate templates; per-line margin overrides beyond
`unit_sell_override`; a revision diff UI.
