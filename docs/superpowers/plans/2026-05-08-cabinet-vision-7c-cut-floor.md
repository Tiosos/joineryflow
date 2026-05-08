# Implementation Plan — Cabinet Vision Integration #7c (CutPlan / CutSchedule + Board tab)

**Spec:** `docs/superpowers/specs/2026-05-05-cabinet-vision-design.md` (§1, §3.2, §4.3, §4.4, §7.3, §7.4, §8 — `0019_cut_floor.py`)
**Branch base:** `feat/foundation` (HEAD ahead of `cd4c57d` — #7b shipped).
**Migration introduced:** `0019_cut_floor.py`.
**RBAC module:** `cut_floor` (already in matrix from #7b).

---

## 0. Context summary

Existing schema (migration 0003):

- `cut_plan(id, workspace_id, project_id, name, created_at)`
- `cut_sheet(id, cut_plan_id, sheet_no, material_sku)` — UNIQUE `(cut_plan_id, sheet_no)`
- `part_slot(id, cut_sheet_id, x, y, w, h, label)`
- `cut_schedule(id, cut_plan_id, scheduled_for, status)` — status CHECK already covers `planned|running|done|cancelled`

The PKs use `id`, not `cut_plan_id`. The plan respects that.

#7c additions:

- `part_slot.part_id` (nullable FK → `parts(part_id)` ON DELETE SET NULL)
- `cut_schedule.priority` (NOT NULL default 0), `assigned_to` (FK → `app_user`), `created_at`, `created_by`, `updated_at`
- `cut_plan.created_by`, `cut_plan.notes`
- Indexes: `idx_part_slot_part`, `idx_cut_schedule_date_priority`

Backend module `apps/api/app/cut_floor/` ships **CutPlan** + **CutSchedule** routes only — CV-import lives in `apps/api/app/cv/`. Both gate on `("cut_floor", action)`.

Web ships **Board tab** (item editor) and **/cut-floor** page (top-level Machine team daily view).

---

## 1. Tasks

### Backend

1. **Migration `0019_cut_floor.py`** — apply all column adds + indexes from §8.
2. **Schemas** at `apps/api/app/cut_floor/schemas.py`: `PartSlotIn`, `CutSheetIn`, `CutPlanIn`, `CutPlanOut`, `CutPlanSummary`, `CutSheetOut`, `PartSlotOut`, `ItemCutPlanOut`, `CutScheduleIn`, `CutSchedulePatchIn`, `ReorderIn`, `CutScheduleOut`. Pydantic v2.
3. **Queries** at `apps/api/app/cut_floor/queries.py` — `text()` SQL, workspace-isolated everywhere via `cut_plan.workspace_id`.
4. **Routes** at `apps/api/app/cut_floor/routes.py`:
   - `POST /projects/{pid}/cut-plans` — single transaction; insert `cut_plan` + `cut_sheet`s + `part_slot`s. Audit `cut_plan.create`.
   - `GET /projects/{pid}/cut-plans` — list newest first.
   - `GET /cut-plans/{plan_id}` — full plan + sheets + slots.
   - `GET /items/{iid}/cut-plan` — pick latest `cut_plan` for the item's project; return only sheets that contain ≥1 slot for this item; flag foreign slots `is_foreign=true`.
   - `DELETE /cut-plans/{plan_id}` — 409 when any non-cancelled `cut_schedule` references the plan; otherwise hard delete (CASCADE).
   - `GET /cut-schedules?date=YYYY-MM-DD&project_id=&status=` — daily list ordered by `priority ASC`. `project_id` is optional; defaults to all projects in workspace.
   - `GET /cut-schedules/{sid}` — single row with embedded plan summary.
   - `POST /cut-schedules` — body `{cut_plan_id, scheduled_for, assigned_to?}`. Auto `priority = MAX(priority WHERE same date) + 100` (or `100` if no rows). Audit `cut_schedule.create`.
   - `PATCH /cut-schedules/{sid}` — partial update. Status transitions enforced: `planned→running`, `running→done`, `planned→cancelled`, `running→cancelled`. Anything else 409. Audit `cut_schedule.update` + `cut_schedule.status_change` when status changes.
   - `POST /cut-schedules/reorder` — body `{scheduled_for, ordered_ids}`. Server rewrites priorities `100, 200, …`. Audit `cut_schedule.reorder`.
   - `DELETE /cut-schedules/{sid}` — soft-cancel (sets `status='cancelled'`). Audit `cut_schedule.cancel`.
5. **Mount router** in `apps/api/app/main.py`.

### Tests

6. **Pytest** at `apps/api/tests/test_cut_floor_routes.py`:
   - CutPlan create transaction (sheets + slots inserted; rollback when invalid).
   - `GET /items/{iid}/cut-plan` returns only relevant sheets, marks foreign slots.
   - CutPlan delete with active schedule → 409; with cancelled-only schedule → succeeds.
   - CutSchedule auto-priority on create.
   - CutSchedule status transition matrix (allowed + denied).
   - CutSchedule reorder rewrites dense `100, 200, 300`.
   - Workspace isolation: cross-workspace GET → 404.
   - RBAC: viewer 403 on POST; purchase_officer 403 on POST.

### Web

7. **Item editor — Board tab**:
   - Add `'board'` between `'hardware'` and `'log'` in `EditorTabs.tsx` `TABS` + `TAB_LABELS`.
   - New `BoardTab.tsx` fetches `/api/items/{id}/cut-plan` and renders one SVG per sheet. Slots from this item highlighted; foreign slots dimmed. Header line + empty state per spec §7.3.
   - Wire from `apps/web/app/(app)/items/[id]/page.tsx`.
8. **/cut-floor page**:
   - `apps/web/app/(app)/cut-floor/page.tsx` (server component) renders `CutFloorClient` with role-gated actions.
   - `_components/ScheduleList.tsx` — date picker (forward/back), project filter chip, sortable list.
   - `_components/ScheduleRow.tsx` — status pill + plan name + assigned-to + Start/Done/Cancel buttons. HTML5 drag-reorder.
   - `_components/AddPlanDialog.tsx` — pick CutPlan (newest 50, all workspace projects) + assigned-to (workspace users) + scheduled_for.
   - Server proxies through existing `app/api/[...proxy]/route.ts`.
9. **SideBar entry** — add `Cut Floor` link visible to `cut_floor.read` users.

### Seed + docs

10. **Seed** (`seed/hartwood_joinery.py`): one `cut_plan` "ALF-001 v1 nest" with 1 sheet of 2440×1220 + 8 part_slots covering 6 of the 9 imported parts; 2 `cut_schedule` rows (one `running` for today, one `planned` for tomorrow). Idempotent — `DELETE FROM cut_plan WHERE project_id = …` first.
11. **CLAUDE.md** — add a `## Cabinet Vision integration — CutPlan + CutSchedule (sub-project #7c)` section summarising: migration 0019, the two new top-level + tab surfaces, the route table, status machine, soft-cancel semantics, foreign-slot rendering.

### Verification

12. `make migrate` (apply 0019) + `make test` (Docker pytest) + `make e2e-docker` smoke (existing specs unaffected).

---

## 2. Status transitions (binding)

```
planned   ──► running  ──► done
   │             │
   └──► cancelled └──► cancelled
```

Any other transition (e.g. `done → running`, `cancelled → running`) returns 409 with `{code: "BAD_TRANSITION"}`.

`DELETE /cut-schedules/{sid}` is **soft-cancel** — sets status to `cancelled`. A second DELETE on an already-cancelled row is a 409.

---

## 3. Foreign-slot rendering rules

For `GET /items/{iid}/cut-plan`:

1. Find `cut_plan_id = MAX(id) WHERE project_id = (SELECT project_id FROM items WHERE item_id = :iid)` (workspace-scoped).
2. If none, return `{plan: null, sheets: []}`.
3. Find every `cut_sheet` that has ≥1 `part_slot.part_id IN (SELECT part_id FROM parts JOIN modules USING(module_id) WHERE item_id = :iid)`.
4. Return all slots on those sheets — flag `is_foreign=true` for slots whose `part_id` is not for this item (or null).
5. Slot label fallback: `slot.label` when set, else `part_name` joined from `parts`, else `"slot {id}"`.

UI: foreign slots `--h-line` 30%, this-item slots `--h-accent` 60%. Tooltip = label.

---

## 4. Out of scope (deferred)

- Bin-packing optimiser (POST `/projects/{pid}/optimise`) — separate sub-project.
- CutPlan edit UI — v1 is create + delete + replace by creating a new plan.
- Real-time WebSocket schedule updates.
- @dnd-kit/core — start with HTML5 DnD; revisit only if QA flags UX.
- Mobile UI for `/cut-floor`.
- `cut_plan.is_current` flag — defer; Board tab uses `MAX(id)`.
- Export CutSchedule to PDF — defer.

---

## 5. Audit events shipped

- `cut_plan.create`, `cut_plan.delete`
- `cut_schedule.create`, `cut_schedule.update`, `cut_schedule.status_change`, `cut_schedule.reorder`, `cut_schedule.cancel`

All routed through `apps/api/app/auth/audit.py::write_audit`.

---

## 6. Exit criteria

- 0019 applies cleanly on top of 0018; downgrade is the no-op pattern matching prior migrations.
- ≥6 new pytest cases pass; existing #7b CV-import tests still pass.
- `/cut-floor?date=today` lists the 1 running + 1 planned seed schedules in priority order.
- Board tab on ALF-001 item 1 renders the seeded sheet with 6 highlighted + 2 foreign slots.
- RBAC: viewer/purchase_officer can read but cannot mutate `/cut-floor`; drafter/manager/admin can.
