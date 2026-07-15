# Implementation Plan — CutPlan Optimiser (stub) — sub-project #9

> **Rebased 2026-07-15.** This plan was written on top of `5e20813` and
> reserved migration `0021_grain_locked`, but sub-project **#9a
> (Estimating)** shipped first and consumed slots **0021–0023**. The
> migration is renumbered **`0024_grain_locked`** (base `0023`)
> throughout; nothing else in the design changes. #9 is still unbuilt.

**Branch base:** current `main` head (migration head `0023`, after #9a).
**Migration introduced:** `0024_grain_locked.py`.
**Spec source:** §8.1 of `docs/superpowers/specs/2026-05-05-cabinet-vision-design.md` ("Bin-packing engine API contract — RESOLVED. Future optimizer ships as a separate POST /projects/{pid}/optimise endpoint that *returns* a CutPlanIn for the user to confirm-then-commit.")

**Scope shape (per user decisions):**
- **Algorithm: stub only.** A naive single-sheet grid placement that fits *some* parts and emits a `CutPlanIn` proposal. The wire contract + UI flow ship now; the real bin-packing engine slots in behind the same endpoint in a future pass.
- **Rotation: per-material `grain_locked` toggle.** Migration 0024 adds `grain_locked boolean NOT NULL DEFAULT false` to `board_materials` and `benchtop_materials`. Optimiser may rotate non-grain-locked parts.
- **UI entry: "Optimise" button on `/cut-floor`** next to "Add to schedule". Opens a dialog → user picks project + sheet dims → server returns a proposal → user reviews + clicks "Save as plan" → reuses the existing `POST /projects/{pid}/cut-plans` endpoint.
- **Sheet stock: per-optimisation override.** User enters `sheet_len_mm` and `sheet_wid_mm` at optimisation time. Defaults seeded from the picked material's catalog row when present.

---

## 0. Wire contract

```http
POST /projects/{pid}/optimise
{
  "name": "ALF-001 v2 nest",
  "material_sku": "18-PB",
  "sheet_len_mm": 2440,
  "sheet_wid_mm": 1220,
  "kerf_mm": 3,
  "include_only_item_ids": [1, 3, 5]   // optional; default = all undeleted items
}
→ 200 { "proposal": CutPlanIn,
        "summary": { "total_parts": 12, "placed": 9, "skipped": 3,
                     "skipped_reasons": [...], "sheets_used": 1,
                     "utilization_pct": 0.62 } }
```

The returned `proposal` is the **identical shape** as the body accepted by `POST /projects/{pid}/cut-plans` (already shipped in #7c). The Optimise dialog shows a preview of the proposal, then the user clicks "Save as plan" which simply forwards the proposal to the existing create-plan endpoint. **No new persistence in #9** — `optimise` is pure-function; only `cut-plans` writes.

The optimiser **never** mutates state. No new audit events are added — the existing `cut_plan.create` audit (from #7c) covers the post-confirm write.

---

## 1. Tasks (≤10)

### Backend (5 tasks)

1. **Migration `0024_grain_locked.py`** (base `0023`) — add `grain_locked boolean NOT NULL DEFAULT false` to `board_materials` and `benchtop_materials`. No index needed (low-cardinality flag, only ever read by optimiser).
2. **`apps/api/app/cut_floor/optimiser.py`** — pure helper module. Functions:
   - `pack_naive(parts, sheet_len, sheet_wid, kerf, allow_rotation_per_part) -> PackResult` — places parts in a single sheet using a left-to-right, top-to-bottom shelf walk. Skips parts that don't fit. Returns `(placed_slots, skipped, utilization_pct)`. **Deliberately simple** — single sheet only, no bin overflow, no global optimisation. The real engine replaces this function.
   - Pure-Python, no deps. Tested with unit tests against deterministic inputs.
3. **Schemas** — extend `apps/api/app/cut_floor/schemas.py` with `OptimiseIn`, `OptimiseSummary`, `OptimiseOut`. The `proposal` field on `OptimiseOut` reuses the existing `CutPlanIn` schema.
4. **Route** at `apps/api/app/cut_floor/routes.py` — `POST /projects/{pid}/optimise` gated by `("cut_floor", "write")`. Pulls candidate parts via a SQL query (joining `parts -> modules -> items` filtered to project, optional `include_only_item_ids`). Calls the optimiser. Returns the proposal. **No DB writes.**
5. **Catalog routes update** — extend the patch schemas for `board_materials` + `benchtop_materials` so the `grain_locked` toggle round-trips through `/catalog/board-materials/{mid}` PATCH.

### Tests (1 task)

6. **Pytest** at `apps/api/tests/test_optimiser.py` — ~10 cases:
   - `pack_naive` unit tests: 1 part fits, multiple parts grid-packed, rotation tried when `grain_locked=false`, skip-when-too-large, kerf accounted for in spacing.
   - Route tests: empty project returns proposal with 0 placed, RBAC (viewer 403), workspace iso (cross-workspace 404), audit log NOT written (route is non-mutating), grain-locked parts not rotated.

### Web (2 tasks)

7. **`apps/web/lib/cut-floor-fetch.ts`** — add `optimiseProject(projectId, body)` returning `OptimiseOut`. Add `OptimiseIn` / `OptimiseOut` / `OptimiseSummary` to `cut-floor-types.ts`.
8. **`OptimiseDialog.tsx`** — new component in `apps/web/app/(app)/cut-floor/_components/`. Two-step:
   - Step 1: Pick project (defaults from page filter), material SKU (typeahead), sheet dims (defaults seeded from material catalog), kerf (default 3 mm), optional include_only_item_ids (default empty = all).
   - Step 2: Render the proposal — one SVG per `cut_sheet` (reuses `BoardTab.tsx`'s SheetCanvas component, factored out into a shared `SheetCanvas.tsx` for reuse). Show `summary` panel (placed / skipped / utilization). "Save as plan" button POSTs to `/api/projects/{pid}/cut-plans` with the proposal body. "Discard" closes.
   - The "Optimise" button on the CutFloorClient header opens the dialog.

### Seed + docs (2 tasks)

9. **Seed update** — set `grain_locked = true` on the 18-WALNUT board (since walnut has visible grain) seeded by #7a. No other changes.
10. **CLAUDE.md** — add a `## CutPlan Optimiser stub (#9)` section + Reference docs entries for this plan + (already-cited) cabinet-vision spec §8.1.

---

## 2. Stub algorithm (binding for v1)

```python
# apps/api/app/cut_floor/optimiser.py — pseudocode

def pack_naive(parts, sheet_len, sheet_wid, kerf, allow_rotation):
    """
    Single-sheet shelf packing:
    1. Sort parts by max(len, wid) descending.
    2. Maintain `cursor_x`, `cursor_y`, `shelf_height`.
    3. For each part:
        - If not rotation-locked, try both orientations; pick the one with
          smaller height that still fits the current shelf width.
        - If part fits at (cursor_x, cursor_y) with current shelf_height:
            place it; advance cursor_x by part_w + kerf.
        - Else if cursor_y + shelf_height + part_h <= sheet_wid:
            new shelf at y = cursor_y + shelf_height + kerf; place at x=0.
        - Else: skip part with reason='no_room'.
    4. Compute utilization = sum(part_w*part_h) / (sheet_len*sheet_wid).
    """
```

This is deliberately mediocre. Acceptance criterion is **wire-shape correctness**, not packing quality. A future ticket replaces `pack_naive` with FFD/MaxRects/etc. behind the same signature.

---

## 3. Schema additions

```sql
-- Migration 0024_grain_locked.py
ALTER TABLE board_materials
    ADD COLUMN grain_locked boolean NOT NULL DEFAULT false;
ALTER TABLE benchtop_materials
    ADD COLUMN grain_locked boolean NOT NULL DEFAULT false;
```

Pydantic `BoardOut` / `BenchtopOut` gain `grain_locked: bool`. Patch schemas accept it.

---

## 4. Out of scope (deferred)

- **Real bin-packing algorithm** — `pack_naive` ships, FFD/MaxRects come later.
- **Multi-sheet packing.** v1 uses a single sheet; if parts overflow, they're skipped with reason `no_room` and the user runs optimisation again with more sheets / bigger stock.
- **`board_inventory` table** for actual stock-on-hand tracking. Per-optimisation sheet override is the v1 contract.
- **Custom-shape parts** (non-rectangular). Joinery is rectangular cuts in v1.
- **Grain-direction visualisation** in the SVG render. The `grain_locked` flag affects packing only.
- **Saving partially-completed proposals** (drafts). The proposal is ephemeral until "Save as plan" forwards to the existing create-plan endpoint.
- **Item attachment carrying through to the new plan.** Optimiser is pure-function; it doesn't touch the existing #5b PDF generation.

---

## 5. Exit criteria

- 0024 applies cleanly on top of 0023. Downgrade is the no-op pattern.
- ≥10 pytest cases pass; existing 8 sub-projects' targeted tests stay green.
- `/cut-floor` shows the new "Optimise" button. Clicking it opens the dialog. Submitting calls `POST /projects/{pid}/optimise`, displays the proposal SVG, and "Save as plan" successfully persists via the existing create-plan flow.
- Catalog edit on `/catalog?tab=board` exposes the `grain_locked` checkbox; round-trips through PATCH.
