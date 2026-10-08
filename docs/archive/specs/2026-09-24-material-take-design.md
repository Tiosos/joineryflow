# Material Take → Material Summary — design spec (sub-project #12)

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

## 1. What this adds

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

## 2. Binding decisions

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

## 3. Data model — migration `0034_material_take`

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

## 4. Generating a take

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

## 5. Consolidating a summary

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

## 6. Drift and impact review (§19)

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

## 7. Ordering from the summary — (Q585)

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

## 8. API and web

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

## 9. Out of scope

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
