# Implementation Plan — CutPlan Optimiser — sub-project #9

> **Status: shipped, and superseded in flight.** This plan was written on
> `5e20813` for a deliberately naive single-sheet stub. What shipped is the
> planned wire contract + UI flow **plus** a real MaxRects nesting engine,
> multi-sheet packing, and sheet-stock integration — work the plan below had
> listed as out of scope. This file is now a record of that, not a forward
> plan. Do not implement from §"Original scope" — read §"What shipped".
>
> | | Planned here | Shipped |
> |---|---|---|
> | Algorithm | `pack_naive` shelf packer only | `pack_maxrects` (default) + `pack_naive` retained as selectable baseline |
> | Sheets | single sheet; overflow skipped | `pack_sheets` multi-sheet, `max_sheets` default 20 |
> | Sheet size | request-body override only | override **or** largest in-stock sheet via `board_inventory` |
> | `board_inventory` | out of scope | shipped (migration 0025) |
> | Migration | `0024_grain_locked` | `0024_grain_locked` ✅ + `0025_board_inventory` |
> | Tests | ~10 | 36 in `apps/api/tests/test_optimiser.py` |
>
> Commits: `6283264` (wire contract + stub + UI), `515490c` (MaxRects +
> multi-sheet), `d919b25` (SKU typeahead + item picker), `b29bb31` (empty
> item-filter semantics), `086a930` (board_inventory), `734bb41` (Sheet
> Stock tab).

> **Later change — confirmed and extended by Plan V1 (see `docs/plan-v1/`).**
> The **pure-function invariant holds**: `/optimise` still reads stock and never
> reserves or decrements it; reservation becomes a separate explicit action
> (Q501). `board_inventory` **gains `quantity_reserved`, `reorder_point` and
> `reorder_quantity`**, ported from the legacy `inventory` table, which is
> **dropped** rather than revived (Q544). The nest's part areas also become the
> basis for apportioning shared cutlist labour across items (Q549).

**Spec source:** §8.1 of `docs/superpowers/specs/2026-05-05-cabinet-vision-design.md`
("Bin-packing engine API contract — RESOLVED. Future optimizer ships as a
separate POST /projects/{pid}/optimise endpoint that *returns* a CutPlanIn for
the user to confirm-then-commit.")

**Migrations introduced:** `0024_grain_locked.py`, `0025_board_inventory.py`.

---

## What shipped

### Wire contract

```http
POST /projects/{pid}/optimise            # gated ("cut_floor", "write")
{
  "name": "ALF-001 v2 nest",
  "material_sku": "18-PB",
  "sheet_len_mm": 2440,        // optional since 0025 — see "Sheet size" below
  "sheet_wid_mm": 1220,        // optional
  "kerf_mm": 3,
  "include_only_item_ids": [1, 3, 5],   // optional; see semantics below
  "strategy": "maxrects",      // "maxrects" (default) | "naive"
  "max_sheets": 20
}
→ 200 { "proposal": CutPlanIn,
        "summary": { "total_parts": 12, "placed": 12, "skipped": 0,
                     "skipped_reasons": [],
                     "sheets_used": 2,
                     "utilization_pct": 0.71,        // mean across sheets used
                     "sheet_utilization": [0.83, 0.59],
                     "sheet_len_mm": 2440, "sheet_wid_mm": 1220,
                     "sheet_dims_from_stock": false,
                     "sheets_available": 4, "sheet_shortfall": 0 } }
```

`proposal` is the identical shape accepted by `POST /projects/{pid}/cut-plans`
(#7c), now carrying **N** `CutSheetIn` rather than one. The dialog previews it,
then "Save as plan" forwards it to that endpoint, which owns persistence and the
`cut_plan.create` audit row.

**The endpoint is a pure function: no DB writes, no audit.** It *reads*
`board_inventory` but never reserves or decrements it. `test_optimise_does_not_write_audit`
locks this in.

### Sheet size resolution (migration 0025)

1. Explicit `sheet_len_mm` + `sheet_wid_mm` win — ad-hoc stock the catalog
   doesn't know about can still be nested against.
2. Omitted → the server picks the largest in-stock sheet for `material_sku`
   (by area, tie-broken by quantity) and sets `sheet_dims_from_stock=true`.
3. Omitted with no stock on hand → `422 {"code": "NO_SHEET_SIZE"}`.

`sheets_available` is **null when no stock is recorded at that size** — that
means *unknown*, not zero. The UI must not claim a shortfall against null.

### `include_only_item_ids` semantics

`null`/absent = all items in the project. An **empty list means no items**, not
"no filter" — `candidate_parts_for_optimise` short-circuits, and the dialog
disables **Optimise** when nothing is selected (`b29bb31`).

### Packing engine — `apps/api/app/cut_floor/optimiser.py`

Pure stdlib, no DB and no Pydantic, unit-tested against deterministic inputs.

- `PackPart` / `PlacedSlot` / `Skip` / `PackResult` / `MultiPackResult`
  dataclasses. `PackPart.uid` tracks an instance across sheet overflow.
- `pack_naive` — shelf next-fit-decreasing. The original stub, kept as an A/B
  baseline and reachable via `strategy: "naive"`.
- `pack_maxrects` — **MaxRects**. Places parts largest-first, runs three
  free-rect choice heuristics (Best-Short-Side-Fit, Best-Area-Fit,
  Bottom-Left) and keeps the best-yielding sheet. Splits free space against the
  part inflated by `kerf` so neighbours keep a saw gap; rotates parts whose
  board material is not `grain_locked`. Robustly ≥ `pack_naive` on mixed parts,
  matches it on uniform grids.
- `pack_sheets(parts, …, strategy, max_sheets)` — multi-sheet wrapper. `no_room`
  overflow rolls onto a fresh sheet until placed or `max_sheets` is hit;
  `too_large` parts (bigger than the sheet) are never retried.

Rotation is governed by `grain_locked boolean NOT NULL DEFAULT false`, added to
`board_materials` + `benchtop_materials` by migration 0024 and round-tripped
through `/catalog/board-materials` + `/catalog/benchtop-materials` PATCH.

### Board inventory (migration 0025)

One row per `(workspace, board material, sheet size)`: `len_mm`, `wid_mm`,
`qty_on_hand`, `location`, `notes`. UNIQUE on
`(workspace_id, material_id, len_mm, wid_mm)`, so adjusting stock is an UPDATE,
not a second row. Routes in `apps/api/app/cut_floor/` (queries in
`inventory_queries.py`), reads gated `("cut_floor","read")`, writes
`("cut_floor","write")`:

- `GET /board-inventory?material_sku=&in_stock_only=`
- `POST /board-inventory` — upsert by (material, size); omitted `location` /
  `notes` are preserved, not clobbered. `404 UNKNOWN_MATERIAL` on unknown SKU.
- `PATCH /board-inventory/{id}`, `DELETE /board-inventory/{id}`

Audit: `board_inventory.{upsert|update|delete}`. Unlike `/optimise`, these do
write.

### Web

- **`SheetCanvas.tsx`** (`cut-floor/_components/`) — the SVG sheet renderer
  extracted from `BoardTab.tsx`; both surfaces import it. Known sheet dims pass
  `extent`; the Board tab infers extent from slots.
- **`OptimiseDialog.tsx`** — form (project · plan name · material SKU
  typeahead · sheet dims · kerf · algorithm) → preview (summary + one
  `SheetCanvas` per sheet + skipped-parts list) → **Save as plan**. Defaults to
  *Use sheet size from stock* (dim inputs grey out; kerf stays editable, being
  a saw property rather than a stock one), lists what's on hand under the SKU
  field, and shows a shortfall banner when a nest needs more sheets than exist.
  Saving is still allowed — a short nest is a purchasing signal, not an error.
  Opened by an **Optimise…** button on the `/cut-floor` header (mutator roles).
- **`/catalog?tab=board|benchtop`** gains a **Grain** checkbox column.
- **`/catalog?tab=stock`** — `StockPanel`, stock by material + size with inline
  qty/location editing, remove, and a set-stock form (the same upsert, so
  re-entering a size updates it).

### Seed

`make seed` grain-locks the walnut veneer demo board (BM-103) on ALF-001 and
writes 6 stock rows across 5 boards — BM-101 deliberately stocked in **two**
sizes (2440×1220 and 3600×1800) to exercise the largest-sheet pick, and BM-104
at **zero** to exercise the out-of-stock path. Idempotent via the same upsert.

### Tests

36 cases in `apps/api/tests/test_optimiser.py`: packer unit tests (fit, grid
no-overlap, rotation, grain lock, oversize, kerf spacing, empty input),
MaxRects-vs-naive quality, multi-sheet overflow + `max_sheets` cap, route tests
(proposal shape, RBAC 403, cross-workspace 404, no audit written, stock-derived
dims, `NO_SHEET_SIZE` 422, shortfall reporting, empty item filter), board
inventory CRUD + workspace isolation, and a round-trip asserting the proposal is
accepted by `POST /projects/{pid}/cut-plans`.

---

## Still out of scope

- Non-rectangular parts. Joinery is rectangular cuts in v1.
- Grain-**direction** visualisation in the SVG. `grain_locked` affects packing
  only.
- Saving draft proposals — the proposal is ephemeral until "Save as plan".
- **Stock consumption.** `/optimise` reads `board_inventory` and never writes
  it; decrementing on cut-plan completion is a deliberate later decision, not
  an oversight.
- Cabinet Vision API integration (see #7b).

---

## Original scope (superseded — historical record)

The plan as written on `5e20813` called for:

- **Algorithm: stub only.** A naive single-sheet grid placement. "Deliberately
  mediocre. Acceptance criterion is wire-shape correctness, not packing
  quality. A future ticket replaces `pack_naive` with FFD/MaxRects/etc. behind
  the same signature." — that future ticket landed in the same batch
  (`515490c`), so both packers ship.
- **Sheet stock: per-optimisation override.** User enters `sheet_len_mm` and
  `sheet_wid_mm` at optimisation time; a `board_inventory` table was listed as
  deferred. Migration 0025 shipped it, and the dims became optional.
- **Multi-sheet packing: deferred.** "v1 uses a single sheet; if parts
  overflow, they're skipped with reason `no_room` and the user runs
  optimisation again with more sheets / bigger stock." Superseded by
  `pack_sheets`.
- Migration slot: originally reserved as `0021_grain_locked`, renumbered to
  `0024` after sub-project #9a (Estimating) consumed slots 0021–0023.
