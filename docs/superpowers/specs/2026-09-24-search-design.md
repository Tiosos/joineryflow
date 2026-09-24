# Global Search — design spec (sub-project #11)

> **Status: shipped** (migration `0033_search_outbox`). Current state lives in
> `CLAUDE.md`; the plan (`docs/superpowers/plans/2026-09-24-search.md`)
> records per task what shipped and where it departed from this spec.
>
> **Fully decided.** Q577–Q580, raised by this spec, were answered 2026-09-24
> (every recommendation taken); see `docs/plan-v1/OPEN-QUESTIONS.md`.

**Plan V1 source:** §13 — "global company-wide search for authorised users and
department-specific search", across ~18 kinds of record.
**Selected by:** Q520 (search first). **Built as:** Q525 (dedicated search
service), Q574 (Meilisearch), Q575 (transactional outbox + worker + full
reindex), Q576 (existing entity types only, workspace-scoped, gated on module
`read` grants — amended by Q579), Q577–Q580 (worker, triggers, types,
archived).
**Gap analysis:** `docs/plan-v1/ALIGNMENT.md` §4 *Plan V1 §13–§15* — `ABSENT`.

---

## 1. What this adds

One search box in the top bar that finds any record the signed-in user may
read, by number, code, name or description, typo-tolerant — and a results page
with per-type filtering. Today every surface has its own `q=` filter
(tracking, list, shop-dwgs, isample, catalog, estimating, customers) and there
is no way to ask "where is 297830?" without knowing which screen owns it.

It also adds the **first infrastructure since Postgres** (Q525): a Meilisearch
container and a worker that keeps it in step with the database.

```
 mutation (any path: route, seed, migration, psql)
   │  same transaction
   ▼
 source table ──trigger──▶ search_outbox (entity_type, entity_id)   ← Postgres
                                   │  SELECT … FOR UPDATE SKIP LOCKED
                                   ▼
                          search worker: load current row → document
                                   │  add / delete documents
                                   ▼
                              Meilisearch  ◀── GET /search (api) ◀── web proxy ◀── browser
```

## 2. Binding decisions

| Area | Rule | Source |
| --- | --- | --- |
| Engine | Meilisearch, one container, pinned minor version | Q574 |
| Sync | Transactional outbox drained by a worker; full reindex command | Q575 |
| Outbox writer | **Postgres triggers** on each source table, not app code | Q578 |
| Worker process | Its own compose service, same image as `api` | Q577 |
| Coverage | Existing entity types only — see §3 | Q576 as amended by Q579 |
| Deleted / archived | Soft-deleted items never indexed; archived records indexed, hidden by default | Q580 |
| Isolation | Every query carries a server-side `workspace_id` filter | Q576, CLAUDE.md |
| Authorisation | Result types limited to modules the role can `read` | Q576 |
| Project scope | **Not** applied in v1 — arrives with §3.4 RBAC (Q466) | Q576 |
| RBAC matrix | **No change.** Search is not a module; results inherit their type's module | — |
| IA | No new tab. The top bar hosts the box; `/search` is reached from it only | CLAUDE.md *Design system* |
| Browser path | Browser → Next.js proxy → FastAPI → Meilisearch. The browser never talks to Meilisearch | CLAUDE.md *Web shell* |

## 3. What is indexed

One Meilisearch index, `jf_search`, holding every type, so relevance ranks
across types and one query returns a type facet. Document id is
`"{type}-{pk}"` (Meili ids allow `a-z A-Z 0-9 - _` only; a colon is illegal)
— except `material`, whose six source tables have overlapping PKs, so its id
is `"material-{table}-{pk}"` (e.g. `material-board_materials-5`).

| `type` | Source | Workspace reached via | Gated on | Opens |
| --- | --- | --- | --- | --- |
| `project` (Q579) | `projects` | `projects.workspace_id` | `tracking` | `/tracking?project_id={id}` |
| `item` | `items` where `row_type='joinery_item'` | `projects` | `tracking` | `/items/{id}` |
| `related_part` | `items` where `row_type='related_part'` | `projects` | `tracking` | `/tracking?project_id={pid}` |
| `cutlist` | `cutlist` | `projects` | `list` | `/list?project_id={pid}&cutlist={id}` |
| `order` | `purchase_orders` | `projects`, **or `vendors` when `project_id` is null** (Q554) | `orderbook` | `/orderbook?order={po_number}` |
| `supplier` | `vendors` | `vendors.workspace_id` | `orderbook` | none today (Q579) |
| `drawing` | `shop_drawing` | `projects` | `shop_dwgs` | `/shop-dwgs?project={pid}&drawing={id}` |
| `sample` | `sample` | `projects` | `isample` | `/isample?project={pid}&sample={id}` |
| `customer` | `customer` | `customer.workspace_id` | `estimating` | `/customers/{id}` |
| `estimate` | `estimate` (+ current revision status) | `estimate.workspace_id` | `estimating` | `/estimating/{id}` |
| `material` | the six catalog tables | `workspace_id` on each | `catalog` | `/catalog?tab={tab}&q={sku}` |

Deep links were checked against the pages' actual `searchParams` handling
(`tracking/page.tsx`, `list/page.tsx`, `shop-dwgs/page.tsx`,
`isample/page.tsx`, `catalog/page.tsx`, `OrdersClient.tsx`). Two types have no
record-level destination today: a related part opens its project's Tracking
grid, and a catalog row opens its tab pre-filtered on its SKU. **Suppliers
have no page at all**, so per Q579 their hits show contact details with no link.

**Area / Room are not their own type** (Q579): their names are folded into
every item document, so searching "Kitchen" or a room number finds the items
there. **People** (`app_user`) are deferred — there is no page to open except
the admin-only `/it`.

### 3.1 Document shape

```jsonc
{
  "id": "item-412",
  "type": "item",
  "entity_id": 412,
  "workspace_id": 1,
  "project_id": 7,            // null for workspace-level types
  "project_code": "ALF-001",
  "codes": ["297830", "ST-CT01"],      // exact identifiers — see §3.2
  "title": "Kitchen island bench",
  "subtitle": "ALF-001 · Level 2 · Kitchen · Rm 2.04",
  "body": "…",                          // descriptive free text, notes
  "status": "LIVE",
  "archived": false,
  "updated_at": 1790000000,             // epoch seconds, sortable
  "url": "/items/412"
}
```

The worker computes `url` and `subtitle`, so the web renders a hit without a
second round trip. Per-type field sources live in one mapping module
(`app/search/documents.py`), one function per type, each a single `text()`
query. That is the only place that knows the source schema.

**Which text goes where** (the full list is task B2's first deliverable, and
must be reviewed against §3.3):

- `item` / `related_part` — `codes`: `num`, `code`, `item_code`, `group_id`,
  the cutlist's `cutlist_no`; `title`: `description`; `subtitle`: project
  code · area name · room `rm_no`/`rm_desc` · `level`; `body`:
  `estimator_notes`, plus `stage` / `rm_desc` from the legacy columns, which
  are still written (the terminology pin — `stage` here is the **site
  location**, never a lifecycle stage).
- `order` — `codes`: `po_number`, `order_number`, `cutlist_no`,
  `supplier_ref_no`, `product_code`; `title`: `description`; `body`:
  `product_description`, `notes`, `internal_comments`, vendor name.
- `material` — `codes`: `sku` plus the table's legacy unique column (`code`,
  `internal_ref`, `slab_id`, `model_number`, `contract_ref`); `title`:
  `description`; `body`: `synonyms[]`, `default_supplier` plus the per-table
  supplier column (`vendor` on `custom_made`, `supplier` elsewhere — the
  CLAUDE.md caveat applies), `brand` / `manufacturer` where present.

### 3.2 Index settings

Applied idempotently by the worker at start-up and by the reindex command:

- `searchableAttributes`: `codes`, `title`, `subtitle`, `body` — in that order,
  so an exact number beats a description that mentions it.
- `filterableAttributes`: `workspace_id`, `type`, `project_id`, `archived`, `status`.
- `sortableAttributes`: `updated_at`.
- `typoTolerance.disableOnAttributes`: `["codes"]`. **Binding.** A six-digit
  number that is one keystroke off is a *different record* (`joinery_number_seq`
  is shared, Q541), so "297831" must never return 297830.
- `faceting` on `type`, so the results page shows per-type counts.
- Every search sends `matchingStrategy: "all"` — **every query word must
  match**. Found while building: Meili's default drops trailing words, so
  `EST-2026-0001` (three tokens) also returned `EST-2026-0002`, the same
  wrong-record hazard as a typo'd number.

### 3.3 What must never be indexed

The index is a second copy of data, so it inherits the data's sensitivity.
Excluded by construction: password hashes, session tokens, file bytes, money
columns (no `total_amount`, `unit_cost`, `grand_total`, estimate totals),
`vendors.bank_account` / `tax_id`, customer `abn`. (Order `internal_comments`
*is* indexed: the Orderbook page already shows it to every `orderbook` reader,
`OrdersClient.tsx:279`.) A test pins the document field allow-list per type.

## 4. Keeping the index in step (Q575)

### 4.1 Outbox — migration `0033_search_outbox`

```sql
CREATE TABLE search_outbox (
  outbox_id   bigserial PRIMARY KEY,
  entity_type text   NOT NULL,
  entity_id   bigint NOT NULL,
  enqueued_at timestamptz NOT NULL DEFAULT now()
);
```

(`entity_type` is CHECK-constrained to the 15 source kinds; the primary key
already orders the worker's scan, so no extra index.)

The outbox carries **identity only, never a payload**. The worker always
reads the row's *current* state. That makes processing idempotent and
order-independent: two updates of one row collapse into one document write,
and a delete is simply "row not found → delete document".

**(Q578) Rows are written by `AFTER INSERT OR UPDATE OR DELETE …
FOR EACH ROW` triggers**, one shared plpgsql function parameterised by type.
Why triggers rather than an `enqueue()` call in application code:

- **Coverage.** Writes to these tables are spread across 13 modules
  (`areas`, `catalog`, `cutlists`, `cv`, `estimating`, `items`, `orders`,
  `procurement`, `projects`, `related_parts`, `samples`, `shop_drawings`,
  `suppliers` — `catalog` and `cv` build table names dynamically, so a plain
  grep misses them). One missed `enqueue()`
  is a silently stale index, and no test catches a call site nobody wrote.
- **Seed and migrations.** CLAUDE.md records *the recurring trap*: Alembic
  backfills touch only rows that exist when they run, and `make seed` inserts
  afterwards. Triggers index seed data, migration data and hand-run SQL with
  no extra step.
- **Cost.** One insert of two integers per written row, inside the writer's
  transaction.

The trade-off is that **triggers are a new pattern in this repo** — no
migration from `0001` to `0032` creates one — and they are invisible to someone
reading only Python. The migration's docstring and CLAUDE.md must say so.

**Dependent documents.** An item document embeds its project code, area name,
room and cutlist number. So:

- `projects` UPDATE of `project_code` / `name` also enqueues that project's
  items, cutlists, drawings, samples and orders;
- `area` / `room` UPDATE enqueues their items;
- `cutlist` UPDATE of `cutlist_no` enqueues its items;
- `estimate_revision` INSERT / UPDATE enqueues its `estimate`;
- `vendors` UPDATE of `name` enqueues its orders.

These are `INSERT … SELECT` statements inside the same trigger function,
guarded by `IS DISTINCT FROM` on the embedded columns so an ordinary save
doesn't fan out.

**Backfill.** `0033` seeds the outbox with every existing row of every indexed
table, so the first worker run indexes the whole tree. A fresh environment
needs no manual reindex.

### 4.2 Worker — `python -m app.search.worker`

Loop:

1. In one transaction, `SELECT outbox_id, entity_type, entity_id FROM
   search_outbox ORDER BY outbox_id LIMIT 500 FOR UPDATE SKIP LOCKED`.
2. Deduplicate by `(entity_type, entity_id)`, then batch-load current rows per
   type through `documents.py`. Found → upsert document. Not found, or excluded
   (soft-deleted item) → delete document.
3. Send `addDocuments` / `deleteDocuments` to Meilisearch and wait for the
   **enqueue acknowledgement** (Meili persists an accepted task before
   answering).
4. `DELETE FROM search_outbox WHERE outbox_id = ANY(:locked_ids)` and commit.

The delete names **the ids it locked, never the entity key**. A write that
commits while the worker is between steps 2 and 4 has its own outbox row, which
survives and gets processed on the next pass. That is what makes the race safe.

If Meilisearch is down, step 3 raises, the transaction rolls back, the rows stay
and the worker backs off exponentially (1 s → 60 s cap). Nothing is lost —
Q575's reason for choosing an outbox. With the batch empty it sleeps 1 s. Target
freshness is **a few seconds** after commit, not real time.

**Multiple workers are safe** (`SKIP LOCKED`), but compose runs one.

**(Q577) Placement:** a separate `search-worker` service in
`docker-compose.yml` that runs the api image with a different command. A crash
or a tight retry loop then cannot starve request handling, and `docker compose
logs search-worker` isolates it. The alternative is a background task inside
the uvicorn process: one service fewer, but `--reload` restarts it on every
code edit, and it would run once per uvicorn worker.

### 4.3 Full reindex — `make reindex`

`python -m app.search.reindex` builds every document into a new index
`jf_search_{timestamp}`, applies the settings, then **atomically swaps** it
with `jf_search` (Meili `swap-indexes`) and deletes the old one. Search keeps
working throughout. It is used for recovery, after a settings change and after
a `documents.py` change. It does not touch the outbox.

## 5. API — `apps/api/app/search/`

`GET /search?q=&types=&project_id=&include_archived=false&limit=20&offset=0`

- Auth: `current_user` only (no `require_permission` — search is not a module).
- `allowed_types` = the types whose module the role can `read`, from
  `permissions.MATRIX`. `types=` is intersected with it, never widened; a type
  the role cannot read is silently dropped, not 403'd, so nothing about its
  existence leaks. Today every role reads every module, so this is a no-op
  until the matrix changes — but it is tested with a patched matrix.
- The Meili filter is built **server-side only**:
  `workspace_id = {me.workspace_id} AND type IN [...] [AND project_id = N]
  [AND archived = false]`. No client input is interpolated into the filter
  string except validated integers and the fixed type enum.
- `q` is trimmed. Empty `q` → `422`. Max 200 chars.
- Response:
  `{ hits: [{type, entity_id, title, subtitle, codes, status, archived, url,
  project_code}], type_counts: {type: n}, total: n, took_ms: n }`.
- Meilisearch unreachable → `503 {code: "SEARCH_UNAVAILABLE"}`. **No Postgres
  fallback**: per-page `q=` filters still work, and a silent fallback with
  different ranking would hide an outage.
- Not audited (reads never are in this codebase).

`GET /search/health` (admin, `("it_management","read")`) →
`{meili: "ok"|"down", outbox_depth: n, oldest_enqueued_at}`. This is the
"component to run and monitor" that Q525 accepted, surfaced on `/it`.

The Meilisearch client sits behind a small `SearchIndex` protocol with a real
HTTP implementation (via `httpx`, already a dev dependency, promoted to a
runtime one) and an in-memory fake for pytest. There is no Meilisearch SDK
dependency: the five endpoints needed don't justify one.

Config (`app/config.py`): `meili_url` (default `http://meili:7700`),
`meili_api_key`, `search_index` (default `jf_search`).

## 6. Web

- **Top bar search box** (`components/chrome/SearchBox.tsx`, mounted in
  `TopBar.tsx`). `/` focuses it; typing debounces 200 ms and calls
  `/api/search?q=&limit=8`. The dropdown groups hits by type, shows the `codes`
  identifier in JetBrains Mono (`.h-mono`), and Enter on a hit follows its
  `url`. Enter with nothing selected goes to `/search?q=`. Esc closes it.
  Keyboard ↑/↓.
- **`/search?q=&type=&include_archived=`** — a results page under
  `app/(app)/search/`. Type chips carry counts from `type_counts`, and there
  is an archived toggle. Results are paged 20 at a time. It is not in the tab
  strip.
- **`/it`** gains a small *Search* panel reading `/search/health`.
- Tokens only from `globals.css` / `lib/tokens.ts`. No new colours. Raw
  `fetch()` + URL params, per CLAUDE.md (no TanStack Query).
- `SEARCH_UNAVAILABLE` renders an inline "Search is temporarily unavailable"
  message, not an error page.

## 7. Operations

- `docker-compose.yml`: `meili` (image `getmeili/meilisearch:v1.x` pinned,
  `MEILI_MASTER_KEY` from `.env`, `MEILI_ENV=development`, named volume
  `meilidata`, **no host port** — only the api and worker talk to it) and
  `search-worker` (Q577). That takes compose from three services to five.
- `.env.example` gains `MEILI_MASTER_KEY`, `MEILI_URL`, `MEILI_API_KEY`.
  Dev uses the master key as the api key. Scoped keys are out of scope.
- `Makefile`: `reindex`.
- CI: the `api-tests` job's `docker compose up -d --build db api` gains
  `meili`. Only the tests marked `meili` need it — the rest use the fake.
- Meili's data is **disposable**: it can always be rebuilt from Postgres by
  `make reindex`. It is not backed up.

## 8. Testing

- **Unit (no Meili):** document builders per type against seeded rows — field
  allow-list (§3.3), `codes` content, `url`, and the orphan-order
  workspace path.
- **Outbox triggers:** insert / update / delete on each table produces a row.
  The dependent fan-out fires on a project code rename and **doesn't** fire on
  an unrelated item save.
- **Worker:** processes a batch against the fake. On a raised send, rows stay
  (the no-loss guarantee). A row written mid-batch survives the delete.
- **Route:** workspace isolation (a workspace-B record is never returned to A,
  the pattern of the existing `test_*_workspace_isolation.py` files), type
  gating under a patched matrix, filter-string injection attempts in `types=`
  / `project_id=`, `503` on fake outage.
- **Integration (`@pytest.mark.meili`, real container):** typo tolerance on
  `title` ("kitchn" → Kitchen), **no** typo tolerance on `codes`
  ("297831" ↛ 297830), and the reindex swap.
- **e2e:** `search.spec.ts` — type a seeded cutlist number in the top bar,
  pick the hit, land on `/list` with that cutlist open.

## 9. Out of scope (v1)

Project-scoped results (waits for §3.4 / Q466); people, tasks, comms,
documents-in-SharePoint, history/audit search (entities not built, or §H
blocked); searching inside PDF contents; saved searches; search analytics;
highlighting beyond Meili's `_formatted`; Meili scoped API keys; multi-node
Meili; a Postgres fallback.
