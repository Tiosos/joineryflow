# Tracking 2.0 — Design (sub-project #10)

**Status:** Draft
**Date:** 2026-05-27
**Plan:** `docs/superpowers/plans/2026-05-27-tracking-2-0.md`
**Driver:** Bill — legacy-parity roadmap from `pictures attached/` screenshots.

## 1. Why

`/tracking` today shows fewer columns than the legacy FileMaker grid (Pro 21.1.1), no per-stage dates in cells, no bulk status update, and only stub subtabs (SITE MEASURE / HARDWARE / INVOICE / QC) without real data. The legacy reference screenshots (`pictures attached/Tracking2.0_*.jpeg`) document the target density: workspace-stable item number, JID code + colour swatch, VAR/BOQ classification, contractor, and a per-stage **date** cell instead of a checkmark.

Sub-project #10 closes those gaps **without changing the lifecycle / status / stage taxonomy**, **without** retiring `items.num` (the existing global UNIQUE 6-digit integer already serves the legacy `cutlist#` role), and **without** building the invoice subsystem yet (that lands in #13 — the Invoice subtab here ships placeholder columns only, so the API contract is stable when #13 wires data).

## 2. Confirmed scope

- Switch stage cells from checkmark/text to **`done_date`** (already in `item_stages.done_date`, already returned by the grid endpoint).
- Add new row columns:
  - **JID code + colour swatch** (free-text `jid_code`, hex `jid_color`).
  - **VAR / BOQ** classification (`var_boq` enum, default `BOQ`).
  - **Contractor** (FK to `app_user`, separate from existing `lister` / `assembler` text fields — those stay for backward compat).
  - **Total $** (`total_amount` numeric — derived later but ship a column for now).
- Expose **already-existing** columns in the grid API: `floor_plan`, `rls`, `joiery_details`, `painting_req`, `solid_surface_req`, `cutlist_printed`, `group_id`, `item_code`, `assembler`, `lister`.
- Add `items.site_measure_notes` (text) for the **Site Measure** subtab.
- Add **`workspace_counter(workspace_id, name, next_value)`** table — not consumed by #10 itself, but seeded here so #12 (PO number), #13 (invoice / variation numbers), and the JID auto-generator (if we add one later) all share one mechanism.
- **Bulk status:** new `POST /items/bulk-status` taking `{item_ids[], status, note}`. Note **required** (matches `item_status_log.note NOT NULL`). Tighten `PATCH /items/{id}/status` to also require note (currently optional with empty-string fallback).
- Four tracking subtabs over the existing items grid:
  - **DATE** (already the default) — per-stage `done_date` cells, dense column set.
  - **SITE MEASURE** — REQ + SM dates from `item_stages`, site-measure notes per row, "By" = `lister`, "Snapshot" = optional `site_measure` attachment (already exists via #5b `item_attachment.kind='site_measure'`).
  - **HARDWARE** — read-only roll-up of `item_hardware_lines` per item: total lines, blocked count, ready count. Same logic as `availability.ready/blocked` already returned.
  - **TO BE ORDERED** — items with **blocked > 0** (at least one hardware line has no `batch_allocations` row). Filter, not a separate table.
  - **INVOICE** — placeholder columns landing here so the column model is stable when #13 ships actual data. Shows `—` until then.

Out of scope for #10 (deferred):

- The `iTIME`, `QC` subtabs (their stub columns stay in the table model but ship with `—`).
- Sketchup vs CabVision attachment split (lives in #11).
- Project page enrichment (#11).
- PO generation, supplier email, priority chips (#12).
- Invoice request workflow + Tracking Invoice subtab actual data (#13).
- Variation / VAR-tag driver (#13 wires `project_variation_item` to drive `items.var_boq`).

## 3. Schema changes — migration 0024

```sql
-- Workspace counter (shared, name-keyed). Reused by #12 (PO #), #13 (invoice/var #).
CREATE TABLE workspace_counter (
    workspace_id BIGINT      NOT NULL,
    name         VARCHAR(32) NOT NULL,
    next_value   BIGINT      NOT NULL DEFAULT 1,
    PRIMARY KEY (workspace_id, name),
    FOREIGN KEY (workspace_id) REFERENCES workspace(id) ON DELETE CASCADE
);

-- Item enrichment columns
ALTER TABLE items
    ADD COLUMN jid_code           VARCHAR(32),
    ADD COLUMN jid_color          CHAR(7),              -- hex like '#ABCDEF'
    ADD COLUMN var_boq            VARCHAR(8)  NOT NULL DEFAULT 'BOQ',
    ADD COLUMN contractor_id      BIGINT,
    ADD COLUMN total_amount       NUMERIC(12, 2),
    ADD COLUMN site_measure_notes TEXT,
    ADD CONSTRAINT items_var_boq_check     CHECK (var_boq IN ('BOQ', 'VAR')),
    ADD CONSTRAINT items_jid_color_check   CHECK (jid_color IS NULL OR jid_color ~ '^#[0-9A-Fa-f]{6}$'),
    ADD CONSTRAINT items_contractor_fkey   FOREIGN KEY (contractor_id) REFERENCES app_user(id) ON DELETE SET NULL;

CREATE INDEX idx_items_var_boq    ON items (var_boq);
CREATE INDEX idx_items_contractor ON items (contractor_id);
```

`items.num` stays as the legacy 6-digit cutlist#. No new column. No data migration required.

## 4. API surface

### 4.1 Grid endpoint (extend in place)

`GET /projects/{pid}/items` — adds to each item row:
- `jid_code`, `jid_color`, `var_boq`
- `contractor_id`, `contractor_name` (joined from `app_user.full_name`)
- `total_amount`
- `site_measure_notes`
- `floor_plan`, `rls`, `joiery_details`, `painting_required`, `solid_surface_required`, `cutlist_printed`, `group_id`, `item_code`, `assembler`, `lister`
- `site_measure_attachment_id` (nullable — joins `item_attachment WHERE kind='site_measure'`)

`stages[stage_key].done_date` is already returned; the frontend just starts rendering it instead of a checkmark.

New query param `availability=blocked` (used by **TO BE ORDERED** subtab): filters to items where the existing `blocked` count > 0.

### 4.2 Bulk status

`POST /items/bulk-status`

```json
{
  "item_ids": [598208, 598220],
  "status":   "HOLD",
  "note":     "Awaiting client signoff on RLS 6328-T1"
}
```

- Requires `tracking:write` (admin, manager, editor, drafter).
- Note **required** (min length 1). 422 if missing.
- For each item: same writes as single-item `patch_item_status` (UPDATE items.status, INSERT item_status_log, write_audit, write_edit_log). All in one transaction.
- Returns `{updated, not_found: [item_ids], cross_workspace: [item_ids]}`. Cross-workspace items don't 404 the whole call — they're listed separately.
- Audit event: `item.status.bulk` per item, with `bulk_size` in payload.

### 4.3 Single-item status (tighten existing)

`PATCH /items/{id}/status` — change `PatchItemStatusIn.note` to required (currently `str | None`). Returns 422 instead of silent empty-string write.

### 4.4 Patch fields (add to existing PATCH /items/{id})

- `jid_code`, `jid_color` (hex validated)
- `var_boq` (enum {`BOQ`, `VAR`})
- `contractor_id` (must be in caller's workspace; 422 otherwise)
- `total_amount` (numeric)
- `site_measure_notes` (text)

All written through the existing `_PATCH_FIELD_MAP` mechanism — same audit + edit_log behaviour.

### 4.5 Counter util

New module `apps/api/app/counters/`:

```python
def next_value(db: Session, *, workspace_id: int, name: str) -> int:
    """Reserve and return the next value for (workspace_id, name).
    UPSERT with FOR UPDATE row lock — safe under concurrent callers.
    """
```

#10 doesn't call this directly; ships the table + helper so #12/#13 can use it without re-paving.

## 5. RBAC

No matrix changes. Bulk status uses the same `tracking:write` gate as single-item status — that gate already includes drafter. Item PATCH (new fields) keeps the existing `require_drafter()` + `tracking:write` combo from `items/routes.py`.

## 6. Workspace isolation

All new fields and the bulk-status endpoint reuse the existing `_WORKSPACE_FILTER` chain (`items -> projects.workspace_id`). `contractor_id` is validated against `app_user.workspace_id = caller.workspace_id` to prevent cross-workspace user injection. `workspace_counter` rows are PK-scoped by `(workspace_id, name)`.

## 7. Frontend

`apps/web/app/(app)/tracking/_components/ItemsTable.tsx`:
- Extend the column model with the new fields.
- **DATE** subtab stage cells: render `stages[stage_key].done_date` (formatted `DD.MM.YY`) when present; render `due_date` in muted text when only due is set; blank otherwise. Reuse existing `dateCellColor()` helper.
- **JID** column: render `jid_code` + a 12-px swatch using `jid_color`.
- **VAR/BOQ** column: pill (`VAR` = orange, `BOQ` = neutral).
- **Contractor** column: `contractor_name`.
- **Total $** column: right-aligned `tnum` currency.

New `BulkStatusDialog.tsx`:
- Multi-select rows (checkbox column, "select all visible").
- Dialog with status picker (`CLEAR / VOID / NOTE! / LIVE / APPROVED / HOLD`) + required note textarea (validated).
- Inline error display for `not_found` / `cross_workspace` lists from response.
- Reuses existing `StatusPopup.tsx` styling.

Subtab data wiring:
- **SITE MEASURE** — pull `stages.REQ.due_date`, `stages.SM.due_date`, `stages.SM.done_date`, `site_measure_notes`, `lister`. Snapshot = link to `site_measure_attachment_id` (open in new tab if present).
- **HARDWARE** — show `availability.ready` / `availability.blocked`, plus a hardware-lines count from a new sidecar field `hardware_line_count`.
- **TO BE ORDERED** — same component as DATE subtab but with `?availability=blocked` filter; collapses DATE columns to a tighter set focused on the procurement stages.
- **INVOICE** — placeholder columns rendered as `—` (#13 wires).

URL state pattern stays the same: `?subtab=date|site_measure|hardware|to_be_ordered|invoice|qc|itime`.

## 8. Seed updates

`seed/hartwood_joinery.py` — extend item INSERTs on ALF-001:
- Set `jid_code` (`JO-SS02`-style) + a deterministic `jid_color` per JID.
- Set `var_boq` (one item marked `VAR` to demo the pill).
- Set `contractor_id` on 2 items (link to existing seed users).
- Set `total_amount` on every item.
- Populate `site_measure_notes` on the SS-Bench item.
- Ensure the `workspace_counter` row for the hartwood workspace is initialised (`name='_test'`, `next_value=1`) just so the table isn't empty after seed.

Re-runnable: every UPDATE keyed on `items.num`.

## 9. Verification

- `make migrate` — 0024 runs clean.
- `make test` — new tests in `apps/api/tests/test_tracking_bulk_status.py` + extensions to `test_items_routes.py`:
  - happy-path bulk update across 3 items (asserts audit + status_log + items.status all written).
  - bulk-status with missing note returns 422.
  - cross-workspace items in `item_ids` returned in `cross_workspace`, not 404.
  - RBAC: viewer / purchase_officer denied.
  - new `jid_color` regex CHECK rejects bad hex.
  - contractor_id from another workspace rejected with 422.
  - workspace_counter `next_value` increments under FOR UPDATE (sequential test).
- `make seed` — ALF-001 grid shows JID swatches, one VAR pill, contractors, totals, one site-measure note.
- Manual: `make up` → log in → `/tracking?project=ALF-001` → switch subtabs → multi-select 2 items → bulk-HOLD with note → confirm Status Log shows the note + bulk event.

## 10. Open questions (call during execution)

- Should `jid_color` default to a workspace-wide colour palette (deterministic from `jid_code` hash) rather than free-form hex? **Default: free-form hex, deterministic auto-suggest in the UI later.**
- Currency for `total_amount` — single workspace-level currency setting, or per-project? **Default: single AUD; per-project deferred.**
- Should the **TO BE ORDERED** subtab also include items whose hardware lines have batch allocations but no received_date yet? **Default: no — that's "ordered, in-flight", a distinct concept. To Be Ordered = blocked only.**
