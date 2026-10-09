# Material Take

> Merged from `specs/2026-09-24-material-take-design.md`, `plans/2026-09-24-material-take.md` (October 2026). Each part below is the original text, verbatim, with headings pushed down two levels; use `git log --follow` on the original paths for history. This is a record of intent at one moment, not a description of the current code: see `docs/sub-projects/` and `CLAUDE.md`.


## Design spec

### Material Take → Material Summary — design spec (sub-project #12)

> **Status: shipped** (migration `0034_material_take`, stacked on #11's `0033`).
> Current state lives in `CLAUDE.md`; the plan records per task what shipped
> and where it departed from this spec (notably Q586's fractional sheets).
>
> **Fully decided.** Q581–Q585, raised by this spec, were answered 2026-09-24
> with every recommendation taken (`docs/plan-v1/OPEN-QUESTIONS.md` §J). The
> markers below cite them.

**Plan V1 source:** §19 (Material Take) and §20 (Project Material Summary →
Procurement). §18's stock depth and §21's supplier comparison, receiving and
exceptions are **not** in scope (see §9).
**Selected by:** `ALIGNMENT.md` §6 step 3 — a clean insert ahead of
`procurement_v1`'s batches.
**Decisions already taken:** Q80, Q495–Q501 (all confirmed 2026-09-18).
**Gap analysis:** `ALIGNMENT.md` §4 *Plan V1 §18–§21* — both rows `ABSENT`.

---

#### 1. What this adds

Today material demand **is** the live lines: `parts` (via `modules`) and
`item_hardware_lines`. `/projects/{pid}/materials` and `/procurement-queue`
aggregate them on every request, with no artefact anyone signs off and no
record of what was agreed.

This sub-project adds two artefacts:

- **Material Take** (per Joinery Item). It is generated from the item's parts
  and hardware lines, then adjusted by a person (quantities, wastage, extra
  lines, notes) and **approved**. An approved take is frozen; changing it
  means a new version (Q500).
- **Material Summary** (per project). It consolidates the latest approved
  takes into one line per material, keeps each line's per-item breakdown, and
  is **confirmed** by the PM. Procurement works from it.

```
 parts + hardware lines ──generate──▶ Material Take v1 (draft) ──approve──▶ v1 approved
        (live, per item)                    ▲ adjust / add / remove          │
                                            │                               │ consolidate
        live lines drift from v1 ──flag──▶ impact review (No / Partial / Full)
                                            │ Partial / Full → v2 draft      ▼
                                                                  Material Summary (per project)
                                                                    lines ← (take, version) sources
                                                                    PM confirm (advisory, Q499)
                                                                    stale when a source take advances
```

#### 2. Binding decisions

| Area | Rule | Source |
| --- | --- | --- |
| Entity | `material_take` is new; the live lines stay the source of generation, not the take itself | Q495 |
| Generation | System-generated starting point + authorised manual control, every adjustment audited | Q80 |
| Generation inputs | Parts + hardware lines give demand; a CutPlan nest gives real sheet counts | Q496 (**see Q582** for where the nest applies) |
| Drawing gate | **Advisory.** Approving a shop drawing is never blocked by a missing take | Q497 |
| Queue | `/procurement-queue` and `/projects/{pid}/materials` stay as live views; the summary is a separate artefact | Q498 |
| PM confirmation | **Advisory.** Procurement may act on an unconfirmed summary; it is shown as unconfirmed | Q499 (a deliberate departure from §20's prose) |
| Staleness | Takes are versioned; a summary line records the take version it consumed and is stale when that item's latest approved version is higher | Q500 |
| Stock | `/optimise` stays pure; nothing here reserves or decrements `board_inventory` | Q501 |
| Granularity | One take per Joinery Item (§20: "saved with each Joinery Item"), not per cutlist | §20, Q495 |
| Related parts | **Excluded.** A related part is procured through its own order (Q424), which is also why the existing rollup filters with `joinery_items_only` | Q424 |
| Edit log | Every take mutation writes `audit_log` **and** `item_edit_log` in one transaction (PM Workbench invariant) | CLAUDE.md |
| RBAC | **No matrix change.** Takes and summaries use `("list", action)`: `write` to edit, `approve` to approve a take or confirm a summary. That is drafter / manager / admin, matching §20's "PM / Project Coordinator / Designer-Draftsperson". Purchase officers get `read`. Take edits also pass `require_drafter()`, as parts do | Q432 pattern, Q474 |

#### 3. Data model — migration `0034_material_take`

```sql
material_take (
  take_id       bigserial PK,
  item_id       bigint NOT NULL REFERENCES items ON DELETE CASCADE,
  version       int    NOT NULL,                -- 1, 2, 3 … per item
  status        text   NOT NULL CHECK (status IN ('draft','approved','superseded')),
  generated_at  timestamptz NOT NULL,
  approved_by   bigint REFERENCES app_user, approved_at timestamptz,
  created_by    bigint NOT NULL REFERENCES app_user, created_at timestamptz NOT NULL DEFAULT now(),
  notes         text,
  UNIQUE (item_id, version)
);
-- at most one draft and one approved take per item
CREATE UNIQUE INDEX uniq_take_draft    ON material_take (item_id) WHERE status = 'draft';
CREATE UNIQUE INDEX uniq_take_approved ON material_take (item_id) WHERE status = 'approved';

material_take_line (
  line_id        bigserial PK,
  take_id        bigint NOT NULL REFERENCES material_take ON DELETE CASCADE,
  material_type  text NOT NULL CHECK (material_type IN
                   ('BOARD','HARDWARE','CUSTOM','BENCHTOP','APPLIANCE','HIRE','OTHER')),
  material_id    bigint,          -- NULL for OTHER and for unresolved free text
  description    text NOT NULL,   -- snapshot, so a later catalog rename never rewrites history
  unit           text NOT NULL CHECK (unit IN ('sheet','each','m','m2')),
  qty_generated  numeric,         -- NULL on a manually added line
  wastage_pct    numeric NOT NULL DEFAULT 0 CHECK (wastage_pct >= 0),
  qty            numeric NOT NULL CHECK (qty >= 0),   -- the take's answer, after adjustment
  source         text NOT NULL CHECK (source IN ('generated','manual')),
  note           text,
  CHECK (material_type <> 'OTHER' OR material_id IS NULL)  -- OTHER is free text only
);

material_take_review (             -- §19 impact review, one per detected drift
  review_id    bigserial PK,
  take_id      bigint NOT NULL REFERENCES material_take ON DELETE CASCADE,
  detected_at  timestamptz NOT NULL,
  outcome      text CHECK (outcome IN ('no_impact','partial','full')),  -- NULL = open
  note         text,
  reviewed_by  bigint REFERENCES app_user, reviewed_at timestamptz
);

material_summary (
  summary_id   bigserial PK,
  project_id   bigint NOT NULL REFERENCES projects ON DELETE CASCADE,
  status       text NOT NULL CHECK (status IN ('draft','confirmed')),
  confirmed_by bigint REFERENCES app_user, confirmed_at timestamptz,
  created_by   bigint NOT NULL REFERENCES app_user, created_at timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

material_summary_line (
  line_id        bigserial PK,
  summary_id     bigint NOT NULL REFERENCES material_summary ON DELETE CASCADE,
  material_type  text NOT NULL, material_id bigint, description text NOT NULL, unit text NOT NULL,
  qty_consolidated numeric NOT NULL,   -- Σ of sources, as generated
  qty_confirmed    numeric,            -- the PM's figure; NULL until set
  note           text
);

material_summary_source (             -- the per-item breakdown §20 requires
  summary_line_id bigint NOT NULL REFERENCES material_summary_line ON DELETE CASCADE,
  take_line_id    bigint NOT NULL REFERENCES material_take_line,
  take_id         bigint NOT NULL, take_version int NOT NULL,
  qty             numeric NOT NULL,
  PRIMARY KEY (summary_line_id, take_line_id)
);
```

A project may hold several summaries over time. The newest is current, and
earlier ones stay as history. `take_line_id` is never deleted while a summary
references it: approved takes are immutable, and superseded ones are kept.

**Search.** Neither entity is indexed. Plan V1 §13 doesn't list them and
Q576 / Q579 fixed the type list. `0034` adds no search triggers.

#### 4. Generating a take

`POST /items/{iid}/material-take/generate` creates the item's draft, at
version `max + 1`. If a draft already exists it refuses with `409
DRAFT_EXISTS`; use regenerate. Lines:

- **Hardware.** One line per `(material_type, material_id)` over
  `item_hardware_lines → project_hardware_catalog`, unit `each`, `qty_generated`
  = Σ `qty`. This is the same join `/projects/{pid}/materials` uses, scoped to
  one item.
> **Later change (Q586, found building B1):** board lines are **fractional**
> sheets per item, rounded up to 2 dp, and the summary rounds up once over the
> project. Rounding each item up and adding overcounted badly (ALF-001's MDF:
> 6 sheets against 3). Read the `ceil(…)` below as applying at the summary.

- **Boards — (Q581).** One line per `board_material_id`, unit
  **`sheet`**. The existing rollup's `SUM(parts.qty)` is a *part count*, not a
  sheet count, and nobody orders "12 parts" of 18mm particleboard. Decided:
  `ceil(Σ(len × wid × qty) / sheet_area)`, where `sheet_area` is the largest
  in-stock `board_inventory` size for that material (the same pick `/optimise`
  makes), else the catalog row's `sheet_len_mm × sheet_wid_mm`. The line then
  records a default `wastage_pct` that the drafter adjusts. A board with no
  known sheet size generates with `unit = 'm2'` so it is visible, not
  silently dropped.
- **Nest — (Q582).** Q496 wants the nest's real sheet counts. But a
  nest is project-level and its sheets mix items: the seeded
  `ALF-001 v1 nest` has one sheet carrying parts of two items. Decided:
  the nest's count applies at **summary** level (§5), where it is exact, and
  per-item takes keep the area estimate.
- **Edging and finishing — (Q584).** `parts.edge`, `edging_spec` and
  `colour` are free text with no catalog reference, and all three are empty
  on every seeded part (37 of 37). Decided: not generated in v1. The
  drafter adds them as manual `OTHER` lines, unit `m` or `each`.

Generation is a pure read of live lines plus one insert. It never touches
parts, hardware lines, stock or the nest.

**Adjusting** (draft only): `PATCH …/lines/{lid}` (`qty`, `wastage_pct`,
`note`, `material_id` for a manual line), `POST …/lines` (manual line), and
`DELETE …/lines/{lid}`. Every call audits the before and after values
(`material_take.line_edit` / `line_add` / `line_remove`) and writes an
`item_edit_log` row.

**Approving:** `POST /material-takes/{tid}/approve` needs `("list","approve")`
and moves draft → approved. The previous approved take becomes `superseded`.
Once approved, a take is **immutable**, and any later change starts version
`n + 1`.

#### 5. Consolidating a summary

`POST /projects/{pid}/material-summary` builds a new draft summary from each
Joinery Item's **current approved** take (items with no approved take are
listed as `missing_takes` in the response and on the page).

- Lines group by `(material_type, material_id, unit)`. `OTHER` lines group by
  `(description, unit)` exactly, and nothing is fuzzy-matched.
- Each summary line keeps one `material_summary_source` row per contributing
  take line, with its `take_version`: that is §20's "retaining source Joinery
  Item breakdown".
- **(Q582)** Where the project has a CutPlan whose sheets cover a board
  material, the line shows the nest's sheet count for that SKU beside the
  consolidated estimate, and the PM chooses which to confirm.
- `PATCH …/lines/{lid}` sets `qty_confirmed` and `note`.
- `POST /material-summaries/{sid}/confirm` (`("list","approve")`) sets
  `confirmed`. It is **advisory** (Q499): nothing downstream refuses to act on
  a draft summary. The UI labels it *Unconfirmed*.

**Stale lines (Q500).** A line is `stale` when any of its sources has an
item whose current approved take version is greater than the recorded
`take_version`. This is computed on read and never stored, so it can't drift.
Rebuilding the summary is the fix: it creates a new draft summary, and the
old one stays as history.

#### 6. Drift and impact review (§19)

§19 wants a human review when things change after the take. Its trigger is a
*shop drawing* change, **but shop drawings are not linked to items**:
`shop_drawing` carries `project_id` and a free-text `room`, and nothing points
from a drawing to an item (checked against the schema at `0033`).

**(Q583)** Decided for v1: detect drift from the thing a take is
actually generated from. When an item's live parts or hardware lines would
now generate different lines from its current approved take (a
generate-and-compare done on read), the take shows **Outdated**, and a
reviewer records the outcome:

- **No Impact** closes the review.
- **Partial Impact** or **Full Impact** opens a new draft (`n + 1`)
  pre-generated from the live lines.

Original history is always preserved. The drawing-linked trigger, and Q497's
"warn the approver that no take exists", wait for a drawing ↔ item link,
which is its own change to #5a.

#### 7. Ordering from the summary — (Q585)

Q499 says Procurement "may order against unconfirmed lines … flagged as
such", which implies an order can come *from* a summary line. Today nothing
connects them: orders (`purchase_orders`, #10) and batches (#4) are created
from items or directly.

Decided for v1:

- The summary page shows, per line, the quantities **already on order and
  received** for that material from the existing batch rollup (read-only), so
  Procurement sees the shortfall.
- **No create-order-from-line action yet.** That action, and the
  "ordered against an unconfirmed line" flag it needs, is a follow-up once §21's
  required / ordered / received / outstanding model is designed.

#### 8. API and web

**API** (`apps/api/app/material_takes/`, `apps/api/app/material_summaries/`,
all `text()` SQL, workspace-isolated through `items → projects.workspace_id`,
404 across workspaces):

| Route | Gate |
| --- | --- |
| `GET /items/{iid}/material-take` (current draft and approved, with the drift flag) | `list` read |
| `GET /items/{iid}/material-takes` (version history) | `list` read |
| `POST /items/{iid}/material-take/generate` · `POST /material-takes/{tid}/regenerate` | `list` write + `require_drafter` |
| `POST/PATCH/DELETE /material-takes/{tid}/lines[/{lid}]` | `list` write + `require_drafter` |
| `POST /material-takes/{tid}/approve` | `list` approve |
| `POST /material-takes/{tid}/reviews` (record an impact-review outcome) | `list` approve |
| `GET /projects/{pid}/material-summary` (current summary, stale flags, missing takes) · `GET …/material-summaries` | `list` read |
| `POST /projects/{pid}/material-summary` (build) · `PATCH /material-summaries/{sid}/lines/{lid}` | `list` write |
| `POST /material-summaries/{sid}/confirm` | `list` approve |

Audit events: `material_take.{generate,line_add,line_edit,line_remove,approve,review}`
and `material_summary.{build,line_edit,confirm}`.

**Web:**

- **Item editor.** A new **Material Take** tab (`?tab=take`, added to
  `EditorTabs` `TABS` / `TAB_LABELS`) with the line grid, generated-vs-adjusted
  quantities, wastage, add / remove, an approve button, a version history,
  and an *Outdated* banner with the review action.
- **Project Procurement page.** A new **Summary** tab
  (`/projects/[id]/procurement?tab=summary`) with consolidated lines, an
  expandable per-item breakdown, stale badges, the list of items missing a
  take, a confirm button, and the on-order / received columns (§7).
- No new top-level tab. Tokens only, and quantities in `.h-mono`.

#### 9. Out of scope

- Everything in §18: stock depth, reservations, multi-location, stocktake,
  and substitution approval.
- Everything in §21 beyond the read-only on-order column: supplier comparison,
  splitting across POs, receiving, exceptions, price history and quote
  validity.
- Generating edging and finishing lines (Q584), a drawing ↔ item link (Q583),
  creating orders from summary lines (Q585), and reserving stock from a take
  (Q501).
- Takes for related parts (Q424), and exporting the summary as a spreadsheet
  file. §20 calls it a "Material Summary Spreadsheet"; v1 is an on-screen
  grid, and a CSV export is a small follow-up.


## Implementation plan

### Implementation Plan — Material Take → Material Summary (sub-project #12)

> **Status: shipped.** Migration `0034_material_take`. Current state lives in
> `## Material Take → Material Summary (sub-project #12)` in `CLAUDE.md`. it follows
> `0033_search_outbox` (#11, PR #14), so **A1 cannot land before #14 merges**.
> Design: `docs/archive/2026-09-24-material-take.md`. As with
> #10 and #11, checkboxes are kept current and each finished task gets a `→`
> note recording what shipped and how it was verified.

**Selected by:** `ALIGNMENT.md` §6 step 3. **Decisions:** Q80, Q495–Q501,
Q581–Q585 (all confirmed). **RBAC:** no matrix change — `("list", action)`
throughout. **IA:** no new top-level tab.
**Format:** summary (see `docs/archive/README.md`); the spec holds
the detail.

**Working rule for this sub-project: CI minutes are scarce.** Every task is
verified locally — full `pytest` against a Postgres migrated to head, `tsc`,
`pnpm build`, and e2e against a locally running stack — and pushed in **one
batch per milestone** (after B, after C, after E), not per task. `ci.yml` now
skips docs-only *PRs* (for `pull_request` events the path filter sees the whole
PR diff, so a PR containing code runs on every push — learned the hard way:
this PR's docs-only commits still ran) and cancels superseded runs.

---

#### 0. Why this order

The take is the unit everything else consumes, and its generation rule
(Q581's sheet estimate) is the one piece with real arithmetic in it, so it is
built and pinned first as a pure function. The summary only reads approved
takes, so it cannot be tested until takes can be approved. Drift (B4) comes
last among the take tasks because it reuses generation to compare.

#### 1. Binding decisions

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

#### 2. Tasks

##### A. Schema

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

##### B. Material Take (`apps/api/app/material_takes/`)

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

- [x] **B2** Generate + draft CRUD routes: `POST /items/{iid}/material-take/generate`
  (`409 DRAFT_EXISTS`), `POST /material-takes/{tid}/regenerate`,
  `POST/PATCH/DELETE /material-takes/{tid}/lines[/{lid}]`. `("list","write")`
  + `require_drafter()`. Each writes `audit_log` + `item_edit_log`
  (before / after values on edits).
  *Done when:* route tests cover each call, `409 TAKE_NOT_DRAFT` on editing an
  approved take, a manual `OTHER` line with no `material_id`, and the two log
  rows landing in one transaction (a forced failure leaves neither).
  → **done.** Also: a generated line's material / unit / description are
  read-only (`409 GENERATED_FIELD_READ_ONLY`); changing its `wastage_pct`
  without a `qty` re-derives `qty = qty_generated × (1 + w%)`, rounded up to
  2 dp; an `OTHER` line with a `material_id` is a 422; regenerate replaces
  generated lines and keeps manual ones; a related part is
  `409 RELATED_PART_HAS_NO_TAKE` (Q424).
- [x] **B3** `POST /material-takes/{tid}/approve` (`("list","approve")`):
  draft → approved, previous approved → superseded, version history via
  `GET /items/{iid}/material-takes`.
  *Done when:* approving v2 supersedes v1; a viewer / editor gets 403; the
  partial unique indexes reject a second draft or approved row inserted
  directly.
  → **done.** Role matrix pinned: drafter / manager / admin approve; editor,
  viewer, purchase officer 403; editing needs drafter+, reading is open to
  every `list` reader including purchase officers.
- [x] **B4** Drift + review: `GET /items/{iid}/material-take` returns
  `outdated: true` when `generate_lines` would now differ from the approved
  take's **generated** lines (manual lines and adjusted quantities are not
  drift); `POST /material-takes/{tid}/reviews` records No / Partial / Full,
  and Partial / Full opens `n + 1` pre-generated.
  *Done when:* adding a part flips `outdated`; editing only an approved take's
  wastage never does; a Full review yields a draft whose lines match the live
  generation.
  → **done.** Reviews are recorded when decided, so there is no separate
  "open review" state; the take's `outdated` flag is the prompt. A Full or
  Partial review opens v`n+1` while v`n` stays approved until the new one is.
- [x] **B5** Workspace isolation + role matrix tests for every take route
  (the `test_*_workspace_isolation.py` pattern: another workspace's item is a
  404, never a 403).
  → **done.** One test walks all seven take routes as an admin of another
  workspace: every one is 404.
  *Milestone 1 verified:* `test_material_take_generation.py` (12) +
  `test_material_take_routes.py` (28); **full suite 753 passed, 1 skipped**
  (the pre-existing skip) with real Meilisearch, as CI runs it.

**Milestone push 1** — after B5, one push.

##### C. Material Summary (`apps/api/app/material_summaries/`)

- [x] **C1** `POST /projects/{pid}/material-summary` builds a draft from each
  Joinery Item's current approved take: group by `(material_type,
  material_id, unit)`, `OTHER` by exact `(description, unit)`; one
  `material_summary_source` row per contributing take line; response lists
  `missing_takes`.
  *Done when:* two items with the same board produce one line whose sources
  sum to it; an item with only a draft appears in `missing_takes`, not in the
  lines.
  → **done.** Board lines round up **once** here (`summary_sheets`, Q586).
  Build and line edits need `require_drafter()` on top of `list` write — §20
  names PM / Coordinator / Designer, and editors also hold `list` write.
- [x] **C2** `GET /projects/{pid}/material-summary` computes `stale` on read
  (any source whose item's approved version now exceeds `take_version`) and,
  for board lines, `nest_sheets` from the project's latest `cut_plan`
  (sheets counted per `cut_sheet.material_sku`, matched to the line's
  material sku). Plus `on_order` / `received` per material from the existing
  `procurement_v1` rollup query, reused, not copied.
  *Done when:* approving a new take version flips the old summary's line to
  stale; the seeded `ALF-001 v1 nest` shows `nest_sheets = 1` against `18-PB`;
  a material with an in-transit batch shows it on order.
  → **done, with a correction to this line:** the seeded nest's sheets are
  labelled `18-PB`, a **Cabinet Vision code**, not a catalog SKU (the
  optimiser writes the catalog SKU). Matching on SKU alone would have missed
  it, so `nest_sheets` resolves `cut_sheet.material_sku` through the catalog
  SKU **or** `cv_material_mapping`, per workspace. Stale also covers a
  hard-deleted source item (sources no longer sum to the consolidated qty).
  *Verified* on the seed (rolled back): ALF-001's MDF consolidates to **3**
  sheets across 6 items with `nest_sheets = 1`; Hettich slides show **96 on
  order** from the seeded batch; six part-less items listed as missing.
- [x] **C3** `PATCH /material-summaries/{sid}/lines/{lid}` (`qty_confirmed`,
  `note`) and `POST /material-summaries/{sid}/confirm` (`("list","approve")`);
  history via `GET /projects/{pid}/material-summaries`.
  *Done when:* confirm sets status + actor; a purchase officer can read but
  gets 403 on confirm; audit rows `material_summary.{build,line_edit,confirm}`.
  → **done.** Confirming fills any line the PM left unset with its
  consolidated figure, and a confirmed summary is read-only
  (`409 SUMMARY_CONFIRMED`) — rebuild to revise.
  *Milestone 2 verified:* `test_material_summary_routes.py` (17); **full suite
  770 passed, 1 skipped** with real Meilisearch.

**Milestone push 2** — after C3, one push.

##### D. Web

- [x] **D1** Item editor **Material Take** tab (`?tab=take`, added to
  `EditorTabs` `TABS` / `TAB_LABELS`): generate, the line grid (generated vs
  adjusted qty, wastage, unit, note), add / remove, approve, version history,
  *Outdated* banner with the review action. `lib/material-take-types.ts`
  types numeric columns as **strings** (the `orders-types.ts` lesson —
  Pydantic `Decimal` arrives as JSON strings).
- [x] **D2** Procurement page **Summary** tab
  (`/projects/[id]/procurement?tab=summary`): build, consolidated lines with an
  expandable per-item breakdown, stale badges, missing-takes list, nest sheet
  count beside board estimates, on-order / received, confirm.
- [x] **D3** `tests/e2e/material_take.spec.ts`: generate a take on a seeded
  item, bump a wastage %, approve, build the project summary, see the line.
  *Done when (D1–D3):* `tsc --noEmit` + `pnpm build` clean; e2e passes against
  a local stack.
  → **done.** `MaterialTakeTab` (generate / regenerate, inline wastage / qty /
  note, manual lines, approve, version list, *Outdated* banner with No /
  Partial / Full) and `MaterialSummaryPanel` (build / rebuild, expandable
  per-item sources, stale banner, missing-takes list linking to each item's
  take, nest sheets, on-order / received, confirm). *Verified:* `tsc` and
  `pnpm build` clean; `material_take.spec.ts` **passes** against a local api +
  Meilisearch + `next start` on a fresh seed, with `search.spec.ts` still
  green. **Bug found by screenshot, not by any test:** the build dropped the
  space in "4 lines may be outdated" (JSX text continuing after a `{…}` on a
  new line) — fixed with a template string, and the take tab's *Outdated*
  banner guarded the same way; both confirmed from the live DOM.

##### E. Seed + close

- [x] **E1** Seed on ALF-001: one item with an **approved** take (v1) and a
  **newer approved** v2 so a pre-built summary shows a stale line; one item
  with only a draft (appears under missing takes); one built summary.
  Idempotent, and — per CLAUDE.md's recurring trap — created *by the seed*,
  not assumed from a migration backfill.
  → **done.** Uses the API's own query functions, so seeded takes carry real
  audit / edit-log rows. A v2 stales **every** summary line that item
  contributes to (4 on the seed), not one. Re-running the seed gives the same
  counts (5 approved, 1 superseded, 1 draft, 1 summary).
- [x] **E2** Docs: a *Material Take (sub-project #12)* section in `CLAUDE.md`
  (dev-loop numbers, migration head `0034`), `ALIGNMENT.md` §19 / §20 rows →
  `PARTIAL`, this plan's and the spec's status headers.
  → **done.** Also records the JSX whitespace trap in `CLAUDE.md`.
  *Final verification:* full suite **770 passed, 1 skipped** (unchanged since
  milestone 2 — D and E touched only web, seed and docs); e2e green locally.

**Milestone push 3** — after E2, one push.

#### 3. Risks

| Risk | Mitigation |
| --- | --- |
| Sheet estimate reads as authoritative | Generated vs adjusted qty shown side by side; nest count shown at summary (Q582) |
| Drift flag noisy | Compares **generated** lines only; manual edits never count as drift (B4) |
| Stale flag drifts from truth | Computed on read, never stored (spec §5) |
| Money / quantity typed as numbers in the web | `*-types.ts` types them as strings, per the #10 lesson |
| CI minutes | Local verification; three milestone pushes; docs-only pushes skip CI |

#### 4. Out of scope

See spec §9.
