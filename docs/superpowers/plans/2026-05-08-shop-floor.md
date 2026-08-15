# Implementation Plan — Shop Floor Ops (sub-project #8)

> **Status: shipped.** Migration `0020`. Current state lives in
> `## Shop Floor Ops (sub-project #8)` in `CLAUDE.md`;
> the task checkboxes below were never ticked and are not a progress signal
> (see `docs/superpowers/plans/README.md`).

> **Later change:** Spec §15 Q3 (deactivating a worker who holds active assignments) was
> proposed but never built — see the spec for the consequence.

**Spec:** `docs/superpowers/specs/2026-05-05-shop-floor-design.md`
**Branch base:** `feat/foundation` post-#7c (HEAD `bf6d331`).
**Migration introduced:** `0020_shop_floor.py`.
**RBAC module added:** `shop_floor` (10th IA module).
**Scope decision:** ship as a single merge per user direction.

---

## Schema note

The spec references `items.painting_required`. The actual column name in
the existing migration 0001 is **`items.painting_req`** (boolean default
false). This plan uses the existing column name; no rename in 0020.

## 0. User decisions binding this plan

1. **Stage ordering is per-item via a new column `items.paint_after_assembly` (boolean, default `false`).** When `false`, ordering is `DOWN → CNC → EDGED → PAINTED → MADE`. When `true`, ordering is `DOWN → CNC → EDGED → MADE → PAINTED`. The `prior_stages_done` helper at `apps/api/app/shop_floor/lifecycle.py` reads the column.
2. **Reassign clears `started_at`** and resets status to `'assigned'`. Audit row `shop_floor.reassign` records both the worker swap and the timer reset.
3. **Worker registry**: seed adds 4 workers (12 staff total) + an admin-only toggle UI lives at `/it` (IT Management page) for promoting/retiring `is_shop_worker`. No separate `/shop-floor/workers` admin page in v2.
4. **Single merge** — all 17 tasks land on `feat/foundation` in one cohesive commit series.

---

## 1. Tasks

### Backend (8 tasks)

1. **Migration `0020_shop_floor.py`** — `app_user.is_shop_worker`, `worker_assignment` (with the partial unique index `uniq_active_assignment`), `stage_completion_log`, plus the new `items.paint_after_assembly boolean NOT NULL DEFAULT false` column.
2. **Pydantic schemas** at `apps/api/app/shop_floor/schemas.py`: `AssignIn`, `PatchAssignmentIn`, `CompleteIn`, `BoardCard`, `BoardOut`, `AssignmentOut`, `StationCard`, `StationOut`, `RecentCompletionOut`.
3. **`lifecycle.py`** at `apps/api/app/shop_floor/lifecycle.py`: pure helpers `shop_floor_order(paint_after_assembly: bool) -> tuple[str, ...]`, `prior_stages_done(...)`, `is_within_undo_window(...)`. Pure functions, unit-testable.
4. **Queries** at `apps/api/app/shop_floor/queries.py` — workspace-isolated SQL for: board, station queue, recent completions, assignment CRUD, mark-done transaction, undo transaction. Uses `SELECT … FOR UPDATE` on `worker_assignment` rows on the mark-done + undo paths.
5. **Routes** at `apps/api/app/shop_floor/routes.py` (10 endpoints, gated `("shop_floor", action)`):
   - `GET /projects/{pid}/shop-floor/board`
   - `GET /projects/{pid}/shop-floor/workers`
   - `GET /workers/{wid}/queue`
   - `GET /workers/{wid}/recent-completions`
   - `POST /projects/{pid}/items/{iid}/assignments`
   - `PATCH /assignments/{aid}` (reassign clears `started_at`; note edits don't)
   - `DELETE /assignments/{aid}` (cancel)
   - `POST /assignments/{aid}/start` (idempotent)
   - `POST /assignments/{aid}/complete`
   - `POST /completions/{log_id}/undo`
6. **Worker-toggle route** for #3 — `PATCH /users/{uid}/shop-worker` body `{is_shop_worker: bool}`, gated `("it_management", "write")` (admin-only). Lives in the existing `apps/api/app/users/` module so the `/it` page picks it up.
7. **RBAC matrix update** — add `shop_floor` to `_ALL_MODULES` and to `MATRIX` per spec §4.1. Foreman = `editor`, no new role.
8. **Mount router** in `apps/api/app/main.py`, add `worker_assignment` + `stage_completion_log` to `apps/api/tests/conftest.py::TRUNCATE_TABLES`.

### Tests (1 task)

9. **Pytest** — six files matching the spec §11.1 layout:
   - `tests/test_shop_floor_assign.py` (assign/reassign/cancel + perms)
   - `tests/test_shop_floor_complete.py` (mark-done txn, stage ordering, PAINTED skip)
   - `tests/test_shop_floor_undo.py` (worker <5min, foreman any time)
   - `tests/test_shop_floor_board.py` (5 columns, PAINTED filter, unassigned)
   - `tests/test_shop_floor_station.py` (queue, ordering, cross-workspace 404)
   - `tests/test_shop_floor_lifecycle.py` (`prior_stages_done` + `paint_after_assembly` flip + undo window)
   - Cross-workspace + RBAC coverage rolled into the per-feature files.
   Target ≥35 cases, ≥80% line coverage on the new module.

### Web (5 tasks)

10. **Lib** — `apps/web/lib/shop-floor-{types,fetch}.ts` mirroring the API.
11. **Foreman office board** — `/shop-floor/page.tsx` (server component) + `_components/ShopFloorClient.tsx` + `StageColumn.tsx` + `WorkerLane.tsx` + `AssignmentCard.tsx` + `AssignDialog.tsx` + `Refresher.tsx` (15-second polling hook).
12. **Shop-floor display** — `/shop-floor/station/[worker_id]/page.tsx` + `_components/StationClient.tsx` + `StationQueue.tsx` + `MarkDoneDialog.tsx` + `UndoBanner.tsx`.
13. **`/it` worker toggle** — small `WorkerRosterPanel.tsx` rendered on `apps/web/app/(app)/it/page.tsx`. Lists every workspace user with a checkbox column for `is_shop_worker`; clicking the checkbox fires `PATCH /api/users/{uid}/shop-worker`. Admin-only.
14. **SideBar entry** — add a `Shop Floor` link under `Catalog` + `Cut Floor` in `apps/web/components/chrome/SideBar.tsx` for any user with `shop_floor.read`.

### Seed + docs + verification (3 tasks)

15. **Seed** (`seed/hartwood_joinery.py`): grow `USERS` from 8 → 12, set `is_shop_worker = true` on the 4 new rows (Sam Lee, Priya Dhar, Marko Villas, Kira Osei). Insert 6 demo `worker_assignment` rows + 1 `stage_completion_log` row on ALF-001. Idempotent via `WHERE NOT EXISTS` guards. Re-run safety: assignments are scoped per (item, stage) so the unique index protects re-seeds.
16. **CLAUDE.md** — add `## Shop Floor Ops (sub-project #8)` section + a Reference docs entry pointing at this plan + the spec.
17. **Docker verification** — `make migrate` (apply 0020) + `make test` (full pytest) + `make seed` round-trip + manual smoke against `/shop-floor` and `/shop-floor/station/{wid}`.

---

## 2. Status machine (binding)

```
   assigned ─worker taps─▶ in_progress ─mark done─▶ done
        │                       │                    │
        │ Foreman cancel         │                    │ undo (5m worker / ∞ foreman+)
        ▼                       ▼                    ▼
    cancelled              cancelled            in_progress
```

PATCH route accepts `worker_id` change (clears `started_at`, status flips back to `assigned`) OR `note` edit (no status touch). Concurrent assignment to the same `(item_id, stage_key)` is rejected by the partial unique index → 409 with `{code: "ACTIVE_ASSIGNMENT_EXISTS", assignment_id}`.

---

## 3. Stage ordering with `paint_after_assembly`

```python
SHOP_FLOOR_ORDER_DEFAULT = ("DOWN", "CNC", "EDGED", "PAINTED", "MADE")
SHOP_FLOOR_ORDER_PAINT_LAST = ("DOWN", "CNC", "EDGED", "MADE", "PAINTED")

def shop_floor_order(paint_after_assembly: bool) -> tuple[str, ...]:
    return SHOP_FLOOR_ORDER_PAINT_LAST if paint_after_assembly else SHOP_FLOOR_ORDER_DEFAULT
```

`prior_stages_done()` reads `items.painting_required` AND `items.paint_after_assembly` to build the per-item priors list. UI: drafter editor's metadata panel gets a checkbox "Paint after assembly" (gated on `painting_required`) — that ships in this plan as a tiny addition to `ItemMetadataPanel.tsx`.

The board's "next stage" subquery (spec §6.1) is updated to honour the per-item ordering — by joining the item's flags into the `CASE` ordering.

---

## 4. Audit events (binding, all through `write_audit`)

| Event | Payload |
|---|---|
| `shop_floor.assign` | `{item_id, stage_key, worker_id, assigned_by}` |
| `shop_floor.reassign` | `{assignment_id, item_id, stage_key, old_worker_id, new_worker_id, started_at_cleared: true}` |
| `shop_floor.unassign` | `{assignment_id, item_id, stage_key, cancelled_by, reason?}` |
| `shop_floor.stage_start` | `{assignment_id, worker_id, started_at}` |
| `shop_floor.stage_complete` | `{assignment_id, item_id, stage_key, worker_id, completed_at, note?, lifecycle_advanced: bool}` |
| `shop_floor.stage_undo` | `{log_id, item_id, stage_key, undone_by, original_worker_id, original_completed_at}` |
| `it.worker_toggle` | `{user_id, is_shop_worker, by_admin_id}` |

---

## 5. Out of scope (deferred)

Per spec §1 "Out of scope":
- Mobile-first responsive UI (tablet 1024+ landscape only).
- Real-time pub/sub (15-second poll instead).
- Efficiency analytics dashboards (data captured; UI later).
- Per-part painting tracking.
- `time_record` table for payroll.
- Worker self-assignment.
- Quality / rework loop.
- Cross-project worker view.
- Per-worker login (kiosk URL = pseudo-auth).
- PM "today's completions" widget on `/tracking` (spec §15 Q4 — defer).

---

## 6. Exit criteria

- 0020 applies cleanly on top of 0019; downgrade is no-op pattern.
- ≥35 pytest cases pass; existing #7c suite still green.
- `/shop-floor?project=ALF-001` shows 5 columns with the seeded 6 assignments + 1 completed (Item 3 DOWN done yesterday).
- `/shop-floor/station/{sam_lee_id}` shows Sam Lee's queue with the active card on top.
- Mark-done from station writes `item_stages.done_date`, the `stage_completion_log` row, and the `audit_log` `shop_floor.stage_complete` row inside one transaction. Verified by checking PM's existing `/tracking` page reflects the completion.
- Undo within 5 minutes works for the worker; after, only Foreman+ can undo.
- `/it` admin can flip `is_shop_worker` for any workspace user; PATCH writes audit `it.worker_toggle`.
- Cross-workspace GETs and POSTs return 404/403; viewer cannot mutate.
