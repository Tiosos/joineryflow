# Sub-project history

Full per-sub-project records, moved out of `CLAUDE.md`. Read the relevant file before large changes to that area.

- `00-foundation-and-architecture.md` (repo nature, dev loop, auth/RBAC, web shell, architecture invariants, design system)
- `01-early-sub-projects.md`
- `02-cutlist-search-material-take.md`
- `03-tracking-and-item-detail.md`
- `04-rbac-and-locks.md`
- `05-tender-and-qc.md`
- `06-orders-procurement.md`
- `07-comments.md`
- `08-audits-and-ci.md`
- `09-e3-pilot-data-import.md` (E3: the FileMaker Tracking 2.0 grid importer, migration `0053`)

## Reference docs (read before large changes)

> **Read `docs/archive/README.md` first.** It defines the status
> header every plan carries (shipped / in progress, migrations introduced,
> later changes), why the `- [ ]` checkboxes are *not* a progress signal, and
> which plans are shipped-state records written after the fact rather than
> forward plans.
>
> Treat a plan as the design record for the sub-project it names, and this
> file as the record of current state. Migration **0010** (item_edit_log
> reshape) has neither spec nor plan; the sub-project sections here are its
> only written reference.

- `docs/plan-v1/plan_v1.md` — **Plan V1**, the customer's canonical target spec, answered through Q431. A target, not current state.
- `docs/plan-v1/ALIGNMENT.md` — Plan V1 mapped onto this tree; read §3 before starting any Plan V1 work.
- `docs/archive/2026-09-18-cutlist-related-parts-orderbook.md` — plan for sub-project #10: cutlist entity, related-part rows, Area/Room entities, and the Orderbook. **A1–A4, B1–B7, C1–C6, D1–D3 and E1–E2 are done**; only **E3** is open, blocked on a copy of the customer's real pilot data. Unusually for this repo its checkboxes *are* kept current and each finished task carries a `→` note recording what shipped and how it was verified.
- `docs/plan-v1/OPEN-QUESTIONS.md` — Q432–Q586, **150 of 154 resolved**. Every answerable question is answered; the four left are customer inputs — Q480 (SharePoint site URL), Q547 (drawing filename pattern), Q550 (Cars / OH&S contents) and Q572 (what the Scope tab holds).
- `legacy/product_spec.md` — product overview, JTBD roles, data model invariants, design tokens, IA. Authoritative for v1 product surface. (The Foundation spec's §10 cites this as `docs/product_spec.md`; it lives in `legacy/`.)
- `legacy/REFINEMENT_BACKLOG.md` — 7 open follow-ups from the 2026-05-10 alignment pass (the `make migrate -w /db` workaround, 7 missing palette tokens, a `/dev/legacy` compare route, mobile + dark-mode passes). Graduate an item into `docs/archive/` when you pick it up.
- `legacy/trackingv2.md` — detailed v1 build plan for Project Information Management. Authoritative for module 1.
- `docs/archive/2026-04-22-foundation.md` — Foundation spec.
- `docs/archive/2026-04-22-foundation.md` — 31-task implementation plan (tracks all build decisions).
- `docs/archive/2026-04-25-pm-workbench.md` — PM Workbench + Drafter Editor spec (sub-projects #2 + #3).
- `docs/archive/2026-04-25-pm-workbench.md` — 33-task implementation plan for sub-projects #2 + #3.
- `docs/archive/2026-04-28-procurement-workbench.md` — Procurement Workbench v1 spec (sub-project #4).
- `docs/archive/2026-04-28-procurement-workbench.md` — 24-task implementation plan for sub-project #4.
- `docs/archive/2026-05-01-shop-drawings.md` — Shop Drawings + file-upload subsystem v1 spec (sub-project #5a).
- `docs/archive/2026-05-01-shop-drawings.md` — 21-task implementation plan for sub-project #5a.
- `docs/archive/2026-05-02-pdf-generation.md` — PDF generation + item attachments v1 spec (sub-project #5b).
- `docs/archive/2026-05-02-pdf-generation.md` — 15-task implementation plan for sub-project #5b.
- `docs/archive/2026-05-02-isample.md` — iSample (sample wall) v1 spec (sub-project #5c).
- `docs/archive/2026-05-02-isample.md` — 14-task implementation plan for sub-project #5c.
- `docs/archive/2026-05-05-cabinet-vision.md` — Cabinet Vision Integration spec (sub-projects #7a + #7b + #7c).
- `docs/archive/2026-05-05-cabinet-vision.md` — 15-task implementation plan for sub-project #7a.
- `docs/archive/2026-05-05-cabinet-vision.md` — 19-task implementation plan for sub-project #7b.
- `docs/archive/2026-05-05-cabinet-vision.md` — 12-task implementation plan for sub-project #7c.
- `docs/archive/2026-05-05-shop-floor.md` — Shop Floor Ops v2 spec (sub-project #8).
- `docs/archive/2026-05-05-shop-floor.md` — 17-task implementation plan for sub-project #8.
- `docs/archive/2026-05-26-estimating.md` — shipped-state record for sub-project #9a (migrations 0021–0023), backfilled 2026-08-14. Explains *why* the schema and workflow read as they do; this file stays the statement of current state.
- `docs/archive/2026-05-27-tracking-2-0.md` + `docs/archive/2026-05-27-tracking-2-0.md` — Tracking 2.0 (migration `0035`). **Shipped** — backend, frontend and seed. Authored before the numbers "#10"/"#11" were reassigned to Cutlist and Search; see *Tracking 2.0* below for the numbering note.
- `docs/archive/2026-05-27-item-project-detail-2-0.md` + `docs/archive/2026-05-27-item-project-detail-2-0.md` — Item & Project Detail 2.0 (migration `0036`). **Shipped** — backend, frontend, seed data and an e2e spec are all in. See *Item & Project Detail 2.0* below for what shipped and where it departs from the design doc.
- `docs/archive/2026-09-24-search.md` + `docs/archive/2026-09-24-search.md` — Global Search (sub-project #11, Plan V1 §13). **Shipped** (migration `0033`); the plan's checkboxes are kept current with a `→` note per task. See *Global Search* below.
- `docs/archive/2026-09-24-material-take.md` + `docs/archive/2026-09-24-material-take.md` — Material Take → Material Summary (sub-project #12, Plan V1 §19–§20). **Shipped** (migration `0034`); the plan's checkboxes are kept current with a `→` note per task. See *Material Take* below.
- `docs/archive/2026-05-09-cutplan-optimiser.md` — shipped-state record for sub-project #9 (CutPlan optimiser: MaxRects + multi-sheet + board_inventory; migrations 0024 + 0025). Written as a stub plan, superseded in flight — the doc carries a planned-vs-shipped table.

## Plan V1 — target architecture (seven sub-projects built)

`docs/plan-v1/` holds **Plan V1**, the customer's specification for a
company-wide joinery workflow and control platform, with its interview
questions answered through Q431 (supplied 2026-09-17). It is mostly a
**target**, not a description of this tree — with seven exceptions: **Plan V1
#10 (Cutlist + related parts + Orderbook)**, **#11 (Global Search, §13)**,
**#12 (Material Take → Summary, §19–§20)**, **§3.4 (Dynamic RBAC engine,
Q466–473)**, **§I (Tender Lifecycle + Financials, §5–§6/§11/§16)**,
**§M (QC / Rework / Packing, §26–§28)** and **§L (Locking, Concurrency,
§11–§12, Q508/Q511/Q512)** are built, each with its own section below.
Everything else in Plan V1 remains unimplemented, apart from **§29 Comments** (a
partial build: 6 of its 8 object types, replies and @mentions, plus a minimal
in-app inbox — see *Comments, mentions and notifications* and *Comment threads
on Modules and shop-drawing revisions*).

- `docs/plan-v1/plan_v1.md` — the spec, verbatim and canonical.
- `docs/plan-v1/ALIGNMENT.md` — every Plan V1 section mapped onto current
  state: 82 rows, **17 shipped · 38 partial · 25 absent**, with 2 rows still
  labelled re-architecture (SharePoint, bounded; the stage list, deferred) —
  **re-scored 2026-10-02**. The 37 rows built work moved carry their new verdict
  and what shipped; the rest keep their 2026-09-18 wording on purpose, and its §3
  (conflicts) and §6 (sequencing) are history, each with a note saying so.
  Counts come from a mechanical recount of the verdict column.
- `docs/plan-v1/OPEN-QUESTIONS.md` — Q432–Q586, continuing Plan V1's own
  numbering. **150 of 154 resolved; every answerable question is answered.**
  Q574–Q580 settle the Search design (sub-project #11); Q581–Q586 the Material
  Take design (#12).
  Q552–Q573 were raised *while building* the Cutlist sub-project, each where a
  document and the code disagreed.
  The four left are **inputs only the customer can supply**: the SharePoint
  site URL (Q480), a real drawing filename (Q547), what the Cars / OH&S
  tabs hold (Q550), and what the Scope tab holds (Q572). The first two block
  §H entirely.

**Confirmed 2026-09-18** (Plan V1 §43, `OPEN-QUESTIONS.md` §A):

- **Q433** — Plan V1 is the **roadmap for this codebase**. It is not a separate
  product and not a rebuild; JoineryFlow evolves into it.
- **Q435** — shipped behaviour **may change, but only behind data-preserving
  migrations**.
- **Q438** — the **Cutlist becomes a first-class entity** owning the production
  workflow (conflict 1 below is accepted, not avoided).
- **Q437** — the **next sub-project is Cutlist + related parts** (conflicts 1
  and 2), built as one change. **Done** — widened by Q542 to take the whole
  Orderbook with it. See *Cutlist + related parts + Orderbook* below.

Apart from #10, #11, #12, the RBAC engine, §I, §M and §L, this section still
describes a target, and `CLAUDE.md` remains the record of what is actually
true in the tree.

**Before building anything from Plan V1, read `ALIGNMENT.md` §3.** It lists
seven places where Plan V1 contradicted an invariant stated as binding in *this*
file. **All seven are now decided** (re-scored 2026-09-18):

| Conflict | Outcome |
| --- | --- |
| 1. **Cutlist owns the workflow** (Q410–Q413) | **Built** (`0027`, `0030`). `item_stages` stays per-item as a **projection**, written by fan-out on completion (Q439). Shop Floor re-keyed to `(cutlist_id, stage_key)`; the `(item_id, 'INST')` half of Q445 turned out to be unreachable — Shop Floor has never been able to hold DEL or INST (**Q561**). |
| 2. **Related-part rows** (Q416–Q424) | **Built** (`0028`). Rows in `items` with a `row_type` + parent FK (Q447). The measured cost was **50 SQL call sites across 13 modules**; only **35** actually take the filter — `apps/api/app/row_types.py` holds the one definition and B1's note classifies the rest. |
| 3. **Project files in SharePoint** (Q398–Q400) | **Bounded.** Additive only — `file_blob` survives and keeps serving shop drawings, attachments and sample photos (Q479). Nothing in #5a/#5b/#5c is rewritten. Blocked on three customer inputs. |
| 4. **RBAC as data** (Plan V1 §3) | **Built** (`0037`). DB-backed with groups, but **project scope only — not item, not tab** (Q466). The 4 actions stay (Q469); today's 7 roles became 7 seed groups with identical grants (Q468), so day one is behaviour-preserving. See *Dynamic RBAC engine* below — Q472's rule-engine migration and Q473's comments feature were not part of this build (**Q473 has since been built — see *Comments, mentions and notifications***). |
| 5. ~~Navigation / Cutlist module~~ | **Closed (Q474).** Cutlist **is** the `List` tab — which the RBAC module name already reflects. The primary six do not grow. |
| 6. **Area / Room as entities** | **Built** (`0026`). Real project-scoped tables with Room **nested under** Area (Q552) and a composite FK `items (area_id, room_id) → room`. It was *not* the pure rename Q455 anticipated: `items.stage` / `rm_no` / `rm_desc` are **kept and still written** alongside the new FKs (Q435), so the terminology pin below still stands. |
| 7. **10 vs 14 lifecycle stages** | **Deferred (Q459).** Today's 10 stand; `PAINTED` before `MADE` with `paint_after_assembly` (Q461); one global `stages` lookup (Q462). Packing is the first extra stage to arrive (Q519). |

**Three decisions deliberately depart from Plan V1's prose** — the code is right
and should not be "fixed" to match: **Q499** (PM confirmation of the Material
Summary is advisory, against §20's release gate), **Q513** (no rollback, against
§11's 20 change states) and **Q527** (fixed KPI catalogue, against §32's
IT-defined formulas).
