# E3: pilot-data import (FileMaker "Tracking 2.0" grid), first slice

> Plan task **E3** (`docs/superpowers/plans/2026-09-18-cutlist-related-parts-orderbook.md`; Q436 / Q540: "migrate a copy of
> pilot data and confirm every item kept its recognisable number"). It was blocked on customer data until the user supplied a
> **Tracking 2.0 export for one project** (one sheet, 626 rows, 37 columns). That export holds item headers only, so this slice
> imports **items, cutlists, areas, rooms, stage dates, statuses and factories**. Modules, parts, hardware lines, drawings, QC,
> orders and comments need their own FileMaker exports and are **not** covered.
>
> Settled with the user (2026-10-08), each asked first:
> 1. First slice = import this grid for the pilot project, dry run first.
> 2. The date columns are **done dates**; `Date_ReqOnSite` is the REQ stage's **due** date; `Date_Optimized` has no stage and is skipped.
> 3. **Keep both FileMaker numbers** (`ItemId` → `items.num`, `CutlistNumber` → `cutlist.cutlist_no`); the shared
>    `joinery_number_seq` is moved past the highest of them.
> 4. `_Contractor` (`TG`; `SI` and more to come) is a **factory** (where the work is made), not a user. `Tag_TgSolidItem` is a
>    **separate per-item tag**, not the existing `solid_surface_req`.
> 5. Project code = FileMaker's `PID` (`2325`); name from the file name; rows with no usable cutlist number are imported as
>    items without a cutlist and listed in the report.
> 6. **A cutlist number written with a leading `#` (`#101973`) is imported as cutlist `101973`** (the `#` is stripped).
>    Because Item IDs and cutlist numbers share one number space (Q541), the importer refuses to run if a cutlist number is
>    already an Item ID, an Item ID is already a cutlist number, or the file uses one number as both.

## Migration `0053`
- `factory (factory_id, workspace_id, code, name, is_active)`, `UNIQUE (workspace_id, code)`; `items.factory_id` (nullable FK, `ON DELETE SET NULL`).
- `items.tg_solid boolean NOT NULL DEFAULT false` (mirrors `projects.tg_solid`, there since `0001`) and `items.legacy_item_ref varchar(64)` (FileMaker's `ItemId_Old`).
- Existing rows: no factory, not tagged, no legacy ref. There is **no admin UI for factories yet**: the importer (and the seed) create them; add one by SQL until a screen is asked for.
- Tracking rows carry `factory_code` and `tg_solid`; Tracking gets a **Factory** column (after Lister, not pinned) and the **Tg Solid chip is live** (it filters on the tag). Only the Orders chip is still parked.

## Running it (on the user's own database)
```
docker compose cp "VSBA ... .xlsx" api:/tmp/grid.xlsx
docker compose exec api python -m app.importers.tracking_grid /tmp/grid.xlsx \
    --workspace-slug <slug> --actor-email <an admin's email> \
    --project-code 2325 --project-name "VSBA Aintree North Primary School Kindergarten"          # a dry run
docker compose exec api python -m app.importers.tracking_grid ... --commit                       # keep it
```
A **dry run does the real inserts in one transaction and rolls back**, so anything that would fail on `--commit` fails the dry run.
It never touches `joinery_number_seq` (sequences are not transactional; a dry run only burns a few `items_item_id_seq` values).
`--commit` also writes one `import.tracking_grid` audit row (counts and the file's sha256). Re-running is safe: an item whose
`ItemId` exists in the workspace (deleted ones included) is skipped. A number already used by **another project** stops the import.
`openpyxl` is now an API dependency. **The export is customer data: it is never committed; tests build synthetic workbooks.**

## Column mapping
| FileMaker | JoineryFlow |
| --- | --- |
| `ItemId` | `items.num` (kept) |
| `CutlistNumber` | `cutlist.cutlist_no` (kept; a leading `#` is stripped); items sharing a number share the cutlist; `created_at` = earliest `Date_Created` on it. Any other non-numeric text → no cutlist, the text kept in the notes |
| `ItemId_Old` | `items.legacy_item_ref` |
| `Item` / `QTY` / `JID` | `description` / `qty` / `jid_code` (`code` stays empty: FileMaker has no item code) |
| `STG` | `items.stage` **and** the Area (one per distinct value); `VARIES` → no area, no room |
| `RoomNoTXT` + `RmDesc` | the Room under that Area (`rm_no`, `rm_desc`) and `items.rm_no` / `rm_desc` |
| `LevelTXT` | `items.level` (kept as text, `VARIES` too) |
| `Zone`, `Apt. Type`, `SIZE`, `ColourCode` | empty in the pilot export; not imported |
| `Status` | `items.status` (blank → `CLEAR`); `_StatusNoteLatest` → one `item_status_log` row |
| `ListerName` / `Assembler` | `items.lister` / `items.assembler` (free text, as exported: usernames and full names are not normalised, and the Tracking *Lister* column, which shows `cutlist_owner_id`, is left empty) |
| `_Contractor` | `factory` + `items.factory_id` |
| `Tag_TgSolidItem` | `items.tg_solid` |
| `Notes` | `items.estimator_notes` (**confirmed by the user, 2026-10-08**) |
| `DWG_RoomFloorPlan` / `DWG_FullDrawingPlan` / `DWG_DetailPlan` | `floor_plan` / `rls` / `joiery_details` (**confirmed by the user, 2026-10-08**, after seeing where RLS sits in the item editor) |
| `Date_ReqOnSite` | `item_stages` **REQ `due_date`** |
| `Date_SiteMeasured`, `_Listed`, `_SentDown`, `_MachinedCompleted`, `_Edged`, `_Painted`, `_Made`, `_Delivered`, `_Installed` | `item_stages` **`done_date`** for `SM`, `LISTED`, `DOWN`, `CNC`, `EDGED`, `PAINTED`, `MADE`, `DEL`, `INST` |
| `Date_Optimized` | not imported (counted in the report) |
| `Date_Created` | `items.created_at` |

No `stage_completion_log` / `worker_assignment` rows are written, so imported work carries **no labour hours** in Actual Costs.

## What the pilot file showed (aggregates only)
626 items, 5 areas, 159 rooms, 350 cutlists (310 plain numbers + 40 written with a `#`), 1 factory (`TG`, 178 items), 11 Tg Solid tags, 87 status notes, 4,506 stage rows; the dry run inserted cleanly into an empty database. Anomalies the report lists:
- **65 rows (40 distinct values) have a cutlist number written `#101230`…`#103195`.** Imported as cutlists 101230…103195 (the `#` stripped, settled with the user); none of the 40 overlaps another cutlist number or an Item ID in the file. The old numbers sit near 100000, so the importer's number-space check matters when it runs on a database that already has items.
- 9 rows have no cutlist at all (4 "Prelims" billing lines, 4 pinboards, 1 more).
- 35 room-number clashes: one `(area, room number)` carries different descriptions (e.g. one number for two different rooms); the first description names the Room, each item keeps its own `rm_desc`.
- 32 date-order oddities (made after delivered, delivered after installed); 2 rows with stage/level `VARIES`.

## Still to confirm with the user
Nothing is open in the mapping. (`Notes` → `estimator_notes` and `DWG_FullDrawingPlan` → `rls` were confirmed 2026-10-08.) One
thing deliberately left for later: `ListerName` is kept as free text; it can also set a user (`cutlist_owner_id`) once the real
user names are known.

## Known, unchanged
`projects.name` is `UNIQUE` across **all** workspaces (a `0001` artefact); importing a project whose name already exists elsewhere fails with that constraint. Not touched here.

## Tests
`apps/api/tests/test_import_tracking_grid.py` (16), the `ALLOWED` entries in `test_items_deleted_filter.py` (the importer reads deleted rows on purpose), e2e `tracking_factory_tg_solid.spec.ts`; the seed puts TG / SI on two TRT-014 items.
