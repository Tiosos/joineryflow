# Item & Project Detail 2.0 — Implementation Plan (#11)

> **Status: partially shipped.** Migration `0036_item_project_detail`.
> Current state lives in `## Item & Project Detail 2.0` in `CLAUDE.md` —
> read it before picking up any of T08–T13 below, it lists exactly what's
> missing (all frontend, seed, most tests). The backend (T01–T07) is done.
> Departures from this doc: T06 records three choices where it was silent;
> T07's attachment kinds are **five, purely additive** — `cv_drawing` is
> *not* treated as a synonym, and the Combined PDF is unchanged (user's
> decision, 2026-09-25). This doc's "PDF gate stays for named slots" is
> also superseded: `sketchup` holds a native `.skp` and `cabvision` a
> `.cvj`, which `/files` now accepts (same 25 MB cap). Design:
> `docs/superpowers/specs/2026-05-27-item-project-detail-2-0-design.md`.
>
> **Later change:** this doc's title says "#11" — free when written
> (2026-05-27), but by the time this plan merged into `main` (2026-09-24,
> commit `8ac99d5`) #11 had gone to Global Search. Go by the migration
> number or merge date, not this label.

**Spec:** `docs/superpowers/specs/2026-05-27-item-project-detail-2-0-design.md`
**Last updated:** 2026-05-27

---

## T01 — Migration 0025

**File:** `db/alembic/versions/0025_item_project_detail.py`

- `projects.closed_at`, `closed_by`.
- `project_contact`, `project_lift_access`, `item_query`, `item_document` tables.
- Expand `item_attachment_kind_check` to add `sketchup`, `cabvision` (keep `cv_drawing`).
- `project_labour_hours_view` (returns zero per project).

**Acceptance:** `make migrate` clean.

## T02 — Project schemas + queries + endpoints

**Files:** `apps/api/app/projects/{schemas,queries,routes}.py`

- `ProjectOut` adds: builder, classification, site_street/suburb/postcode/state, tg_project_manager, tg_coordinator, tg_solid, carell_pid, total_line_items, closed_at, closed_by, closed_by_name, contacts, lift_access, labour_hours.
- `PatchProjectIn` extends with the new metadata fields.
- New `POST /projects/{id}/close-out` (admin/manager). 409 if already closed.

**Acceptance:** existing project tests stay green.

## T03 — Project contacts module

**File:** `apps/api/app/project_contacts/{__init__,queries,routes,schemas}.py`

- POST/GET/PATCH/DELETE contacts.
- `tracking:write` for writes.
- Workspace isolation through project.

## T04 — Project lift access module

**File:** `apps/api/app/project_lift_access/{__init__,queries,routes,schemas}.py`

- PUT/GET/DELETE lift access.

## T05 — Item Query module

**File:** `apps/api/app/item_queries/{__init__,queries,routes,schemas}.py`

- GET list, POST ask, POST answer, PATCH edit-answer.
- 409 if already answered (on first answer).

## T06 — Item Document Register module

**File:** `apps/api/app/item_documents/{__init__,queries,routes,schemas}.py`

- GET list, POST bind, DELETE unbind, PATCH relabel/reorder.

## T07 — Attachments + item PATCH expansion

**Files:** `apps/api/app/item_attachments/routes.py`, `apps/api/app/items/{schemas,queries}.py`

- Expand attachment `KindPath` regex to add sketchup + cabvision.
- Extend `PatchItemIn` and `_PATCH_FIELD_MAP` with floor_plan, rls, joiery_details, cutlist_printed.

## T08 — Frontend: project page

**Files:** `apps/web/app/(app)/projects/[id]/page.tsx` (new), `_components/*`, `lib/pm-types.ts`.

- Extend TS `ProjectOut`.
- 3-column page: header strip / details / contacts / lift / labour hours card.

## T09 — Frontend: item editor

**Files:** `apps/web/app/(app)/items/[id]/_components/EditorTabs.tsx`; new `ActionsTab.tsx`, `QueryTab.tsx`; expand `AttachmentsTab.tsx`; header chips.

## T10 — Tracking modal link

`ProjectDetailModal.tsx` gains "Open full project page →".

## T11 — Seed

- ALF-001: builder + classification + address + 6 contacts + lift sketch + 2 queries + 2 documents. Idempotent.

## T12 — Tests

Files: `test_project_enrichment.py`, `test_project_contacts.py`, `test_project_lift_access.py`, `test_item_queries.py`, `test_item_documents.py`. Extend `test_items_routes.py`.

## T13 — Smoke

`make up && migrate && seed`. Click through.

---

## Dependencies

```
T01 ─┬─> T02 ─┬─> T03, T04
     │        ├─> T05
     │        ├─> T06
     │        └─> T07
     │
     └─> T08, T09 (parallel)
     └─> T10
     └─> T11 (seed)
     └─> T12 (tests parallel after backend)
     └─> T13 (smoke last)
```
