# Implementation Plan — Material Take → Material Summary (sub-project #12)

> **Status: in progress** (A1, B1 done — local only). Migration `0034_material_take`; it follows
> `0033_search_outbox` (#11, PR #14), so **A1 cannot land before #14 merges**.
> Design: `docs/superpowers/specs/2026-09-24-material-take-design.md`. As with
> #10 and #11, checkboxes are kept current and each finished task gets a `→`
> note recording what shipped and how it was verified.

**Selected by:** `ALIGNMENT.md` §6 step 3. **Decisions:** Q80, Q495–Q501,
Q581–Q585 (all confirmed). **RBAC:** no matrix change — `("list", action)`
throughout. **IA:** no new top-level tab.
**Format:** summary (see `docs/superpowers/plans/README.md`); the spec holds
the detail.

**Working rule for this sub-project: CI minutes are scarce.** Every task is
verified locally — full `pytest` against a Postgres migrated to head, `tsc`,
`pnpm build`, and e2e against a locally running stack — and pushed in **one
batch per milestone** (after B, after C, after E), not per task. `ci.yml` now
skips docs-only pushes and cancels superseded runs.

---

## 0. Why this order

The take is the unit everything else consumes, and its generation rule
(Q581's sheet estimate) is the one piece with real arithmetic in it, so it is
built and pinned first as a pure function. The summary only reads approved
takes, so it cannot be tested until takes can be approved. Drift (B4) comes
last among the take tasks because it reuses generation to compare.

## 1. Binding decisions

| Area | Rule | Source |
| --- | --- | --- |
| Granularity | One take per Joinery Item; related parts excluded | §20, Q495, Q424 |
| Versioning | Approved take is immutable; change = version `n + 1`; ≤ 1 draft and ≤ 1 approved per item (partial unique indexes) | Q500 |
| Boards | Unit `sheet`, **fractional per item** (`Σ len×wid×qty / sheet_area`, rounded up to 2 dp), plus adjustable `wastage_pct`; m² when no size is known. The summary rounds up **once** | Q581 as amended by **Q586** |
| Sheet size | Largest **in-stock** `board_inventory` size → else largest **recorded** size (qty 0 still names a real size) → else catalog `sheet_len_mm × sheet_wid_mm` → else `m2` | Q581, clarified here (see note) |
| Nest | Sheet count per SKU shown on the **summary** only, from the project's latest CutPlan | Q582 |
| Drift | Generate-and-compare against the live lines on read; no drawing trigger | Q583 |
| Edging / finishing | Manual `OTHER` lines only | Q584 |
| Ordering | Summary shows on-order / received read-only; no create-order | Q585 |
| PM confirm | Advisory; nothing refuses an unconfirmed summary | Q499 |
| Stock | Never reserved or decremented | Q501 |
| Logging | Every take mutation: `audit_log` + `item_edit_log`, one transaction | CLAUDE.md |

> **Clarification, not a departure.** Spec §4 says "largest in-stock
> `board_inventory` size … else the catalog row's size". The seed has a board
> (`PLY-12-BIR`) whose only recorded size has `qty_on_hand = 0`, and no catalog
> row carries a sheet size at all — so the literal rule would drop that board to
> m² despite a known size. The plan inserts "largest recorded size" between the
> two; it only ever resolves a size the spec would otherwise have left unknown.

## 2. Tasks

### A. Schema

- [x] **A1** Migration `0034_material_take` — the six tables in spec §3,
  partial unique indexes `uniq_take_draft` / `uniq_take_approved`, and the
  `OTHER`-has-no-`material_id` CHECK. Downgrade drops them in reverse order.
  **No search triggers** (spec §3).
  *Done when:* upgrade → downgrade → upgrade is clean on a seeded DB, and the
  full suite still passes (the `0033` trigger tests must be untouched by it).
  → **done.** Beyond spec §3: `material_summary_source`'s FKs **cascade** —
  items can be hard-deleted (`items/queries.py`, `related_parts/queries.py`),
  which RESTRICT would have blocked once an item was summarised; a lost source
  makes the line's sources stop summing to `qty_consolidated`, which C2 reports
  as stale. Two extra CHECKs tie `status`/`approved_at` and
  `source`/`qty_generated` together. *Verified:* upgrade → downgrade → upgrade
  clean on a seeded DB; six tables created. Full suite deferred to milestone 1.

### B. Material Take (`apps/api/app/material_takes/`)

- [x] **B1** `generation.py` — **pure** functions: `estimate_sheets(parts,
  sheet)` and `resolve_sheet_size(...)` following the §1 fallback order, then
  `generate_lines(db, item_id)` that reads parts + hardware lines and returns
  line dicts (no writes).
  *Done when:* unit tests pin the arithmetic — fractional sheets rounded up
  to 2 dp (never 0.00 for a real part), an exact multiple stays exact, ten
  0.38-sheet items consolidate to **4** sheets (Q586), no size anywhere →
  `unit='m2'`, a zero-stock recorded size is used; hardware sums per
  `(material_type, material_id)`; another workspace's stock is ignored.
  *(This line originally named whole-sheet figures — 4 and 2 per item — which
  Q586 retired; corrected in place so the check matches the rule.)*
  → **done.** `app/material_takes/generation.py`: `estimate_sheets`,
  `pick_sheet_size`, `summary_sheets` pure; `generate_lines` the one read;
  `generated_signature` for B4. *Verified:* `tests/test_material_take_generation.py`
  12 passed. Against the seed, ALF-001's MDF consolidates to **3** sheets
  (per-item rounding would have said 6) — the finding that raised **Q586**.

- [ ] **B2** Generate + draft CRUD routes: `POST /items/{iid}/material-take/generate`
  (`409 DRAFT_EXISTS`), `POST /material-takes/{tid}/regenerate`,
  `POST/PATCH/DELETE /material-takes/{tid}/lines[/{lid}]`. `("list","write")`
  + `require_drafter()`. Each writes `audit_log` + `item_edit_log`
  (before / after values on edits).
  *Done when:* route tests cover each call, `409 TAKE_NOT_DRAFT` on editing an
  approved take, a manual `OTHER` line with no `material_id`, and the two log
  rows landing in one transaction (a forced failure leaves neither).
- [ ] **B3** `POST /material-takes/{tid}/approve` (`("list","approve")`):
  draft → approved, previous approved → superseded, version history via
  `GET /items/{iid}/material-takes`.
  *Done when:* approving v2 supersedes v1; a viewer / editor gets 403; the
  partial unique indexes reject a second draft or approved row inserted
  directly.
- [ ] **B4** Drift + review: `GET /items/{iid}/material-take` returns
  `outdated: true` when `generate_lines` would now differ from the approved
  take's **generated** lines (manual lines and adjusted quantities are not
  drift); `POST /material-takes/{tid}/reviews` records No / Partial / Full,
  and Partial / Full opens `n + 1` pre-generated.
  *Done when:* adding a part flips `outdated`; editing only an approved take's
  wastage never does; a Full review yields a draft whose lines match the live
  generation.
- [ ] **B5** Workspace isolation + role matrix tests for every take route
  (the `test_*_workspace_isolation.py` pattern: another workspace's item is a
  404, never a 403).

**Milestone push 1** — after B5, one push.

### C. Material Summary (`apps/api/app/material_summaries/`)

- [ ] **C1** `POST /projects/{pid}/material-summary` builds a draft from each
  Joinery Item's current approved take: group by `(material_type,
  material_id, unit)`, `OTHER` by exact `(description, unit)`; one
  `material_summary_source` row per contributing take line; response lists
  `missing_takes`.
  *Done when:* two items with the same board produce one line whose sources
  sum to it; an item with only a draft appears in `missing_takes`, not in the
  lines.
- [ ] **C2** `GET /projects/{pid}/material-summary` computes `stale` on read
  (any source whose item's approved version now exceeds `take_version`) and,
  for board lines, `nest_sheets` from the project's latest `cut_plan`
  (sheets counted per `cut_sheet.material_sku`, matched to the line's
  material sku). Plus `on_order` / `received` per material from the existing
  `procurement_v1` rollup query, reused, not copied.
  *Done when:* approving a new take version flips the old summary's line to
  stale; the seeded `ALF-001 v1 nest` shows `nest_sheets = 1` against `18-PB`;
  a material with an in-transit batch shows it on order.
- [ ] **C3** `PATCH /material-summaries/{sid}/lines/{lid}` (`qty_confirmed`,
  `note`) and `POST /material-summaries/{sid}/confirm` (`("list","approve")`);
  history via `GET /projects/{pid}/material-summaries`.
  *Done when:* confirm sets status + actor; a purchase officer can read but
  gets 403 on confirm; audit rows `material_summary.{build,line_edit,confirm}`.

**Milestone push 2** — after C3, one push.

### D. Web

- [ ] **D1** Item editor **Material Take** tab (`?tab=take`, added to
  `EditorTabs` `TABS` / `TAB_LABELS`): generate, the line grid (generated vs
  adjusted qty, wastage, unit, note), add / remove, approve, version history,
  *Outdated* banner with the review action. `lib/material-take-types.ts`
  types numeric columns as **strings** (the `orders-types.ts` lesson —
  Pydantic `Decimal` arrives as JSON strings).
- [ ] **D2** Procurement page **Summary** tab
  (`/projects/[id]/procurement?tab=summary`): build, consolidated lines with an
  expandable per-item breakdown, stale badges, missing-takes list, nest sheet
  count beside board estimates, on-order / received, confirm.
- [ ] **D3** `tests/e2e/material_take.spec.ts`: generate a take on a seeded
  item, bump a wastage %, approve, build the project summary, see the line.
  *Done when (D1–D3):* `tsc --noEmit` + `pnpm build` clean; e2e passes against
  a local stack.

### E. Seed + close

- [ ] **E1** Seed on ALF-001: one item with an **approved** take (v1) and a
  **newer approved** v2 so a pre-built summary shows a stale line; one item
  with only a draft (appears under missing takes); one built summary.
  Idempotent, and — per CLAUDE.md's recurring trap — created *by the seed*,
  not assumed from a migration backfill.
- [ ] **E2** Docs: a *Material Take (sub-project #12)* section in `CLAUDE.md`
  (dev-loop numbers, migration head `0034`), `ALIGNMENT.md` §19 / §20 rows →
  `PARTIAL`, this plan's and the spec's status headers.

**Milestone push 3** — after E2, one push.

## 3. Risks

| Risk | Mitigation |
| --- | --- |
| Sheet estimate reads as authoritative | Generated vs adjusted qty shown side by side; nest count shown at summary (Q582) |
| Drift flag noisy | Compares **generated** lines only; manual edits never count as drift (B4) |
| Stale flag drifts from truth | Computed on read, never stored (spec §5) |
| Money / quantity typed as numbers in the web | `*-types.ts` types them as strings, per the #10 lesson |
| CI minutes | Local verification; three milestone pushes; docs-only pushes skip CI |

## 4. Out of scope

See spec §9.
