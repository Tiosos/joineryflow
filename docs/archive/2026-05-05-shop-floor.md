# Shop Floor

> Merged from `specs/2026-05-05-shop-floor-design.md`, `plans/2026-05-08-shop-floor.md` (October 2026). Each part below is the original text, verbatim, with headings pushed down two levels; use `git log --follow` on the original paths for history. This is a record of intent at one moment, not a description of the current code: see `docs/sub-projects/` and `CLAUDE.md`.


## Design spec

### JoineryFlow Shop Floor Ops (v2 — Foreman Worker Assignment) — Design Spec

**Date:** 2026-05-05
**Sub-project:** #8 (Foreman + Machine team Shop Floor Ops; the first surface for the Foreman JTBD role)
**Sequencing:** Ships **after** Cabinet Vision sub-project #7 (slices #7a/#7b/#7c). Assumes migrations 0017–0019 are already applied.
**Branch base:** `feat/foundation` post-#7c (latest migration on disk: 0019; matrix has 9 modules incl. `catalog` + `cut_floor`).
**Prior context:**
- `docs/archive/2026-04-22-foundation.md`
- `docs/archive/2026-04-25-pm-workbench.md`
- `docs/archive/2026-04-28-procurement-workbench.md`
- `docs/archive/2026-05-01-shop-drawings.md`
- `docs/archive/2026-05-02-pdf-generation.md`
- `docs/archive/2026-05-02-isample.md`
- `docs/archive/2026-05-05-cabinet-vision.md`
- `legacy/product_spec.md` §2, §4.2
- `legacy/trackingv2.md`

---

#### 0. Goal

A Foreman in the office assigns shop workers to specific items at specific lifecycle stages (DOWN, CNC, EDGED, PAINTED, MADE) on a Foreman Office board. A tablet mounted on the shop floor shows that worker their queue and lets them mark a stage done with one tap, with optional note. Marking done writes back to `item_stages.done_date` and to a new immutable `stage_completion_log`, atomically with an `audit_log` row, and advances the item lifecycle if every part of the item is done. PM dashboards consume the same `item_stages` they always have — Shop Floor Ops is purely additive write-traffic into surfaces v1 already reads.

This sub-project also closes the v1 placeholder gap on lifecycle stages DOWN→MADE: today, those stages can only be moved by a Drafter editing `item_stages` in the item editor; after #8, the shop floor itself owns those transitions.

---

#### 1. Scope

##### In scope

1. **Worker registry** — extend `app_user` with `is_shop_worker boolean NOT NULL DEFAULT false`. Single column, no separate `workers` table.
2. **`worker_assignment` table** — assignment of one worker (`app_user.id`) to one (item, stage_key) at a time, with `started_at`, `ended_at`, status enum (`assigned`, `in_progress`, `done`, `cancelled`), optional note. Uniqueness invariant: at most one active assignment per (item_id, stage_key).
3. **`stage_completion_log` table** — append-only, immutable, who-marked-which-stage-done audit (separate from generic `audit_log` because PM dashboards aggregate from this; querying by item is hot path).
4. **Foreman Office surface** at `/shop-floor` (Foreman + manager + admin) — kanban board grouped by stage_key column (DOWN | CNC | EDGED | PAINTED | MADE) showing item cards as draggable to assign or reassign.
5. **Shop-floor display surface** at `/shop-floor/station/[worker_id]` (kiosk-friendly, larger touch targets) — the assigned worker's queue + a single-tap "Mark done" + optional note dialog.
6. **Lifecycle integration** — marking done writes `item_stages.done_date = today`, writes `stage_completion_log`, writes `audit_log`. All in one transaction.
7. **Undo window** — within 5 minutes of mark-done, the worker (or any Foreman+) can undo: clears `done_date`, marks `worker_assignment.status = 'in_progress'`, writes `shop_floor.stage_undo` audit row. After 5 min, only Foreman+ from the office can undo.
8. **RBAC matrix update** — add 10th IA module `shop_floor`. Permissions matrix entries below.
9. **Audit hooks** — `shop_floor.assign`, `shop_floor.unassign`, `shop_floor.reassign`, `shop_floor.stage_start`, `shop_floor.stage_complete`, `shop_floor.stage_undo`.
10. **Seed updates** — 4 demo workers + 6 demo assignments across stages on ALF-001.

##### Out of scope (deferred to v2.5 or v3)

- **Mobile-first responsive UI** — the shop-floor display is tablet-sized only (1024+ landscape).
- **Real-time pub/sub** — board polls `GET /shop-floor/board` every 15s.
- **Efficiency analytics dashboards** — schema records the data; UI deferred.
- **Per-part painting tracking** — PAINTED stage is marked at the item level.
- **`time_record` table** — explicit clock-in / clock-out for payroll. The `worker_assignment.started_at`/`ended_at` pair is the v2 surrogate.
- **Worker self-assignment** — workers act only on what the Foreman assigned.
- **Quality / rework loop** — if a stage is marked done but later fails QC, the office Foreman manually undoes.
- **Cross-project worker view** — board is per-project.
- **Worker login** — the shop-floor display is auto-selected by `worker_id` in the URL on a wall-mounted tablet (no per-worker auth in v2).

---

#### 2. Architecture

##### 2.1 Backend layout

```
apps/api/app/shop_floor/
  __init__.py
  routes.py        # board + assignments + workers + completion endpoints
  queries.py       # text() SQL with audit + lifecycle advancement
  schemas.py       # AssignIn, MarkDoneIn, UndoIn, BoardOut, StationOut
  lifecycle.py     # stage advancement helper (pure function, testable in isolation)

apps/api/app/auth/permissions.py      # MODIFY: add 'shop_floor' module to MATRIX
apps/api/app/main.py                  # MODIFY: mount shop_floor_router
apps/api/tests/conftest.py            # MODIFY: TRUNCATE_TABLES gains worker_assignment + stage_completion_log
```

Auth via `require_permission("shop_floor", action)` for all routes. Workspace isolation via `projects.workspace_id = :w` direct join.

##### 2.2 Web layout

```
apps/web/app/(app)/shop-floor/
  page.tsx                          # Foreman Office board (default)
  station/[worker_id]/page.tsx      # Shop-floor display (kiosk)
  _components/
    ShopFloorClient.tsx             # client wrapper owning URL state
    StageColumn.tsx                 # one column per stage_key
    AssignmentCard.tsx              # item card draggable between worker buckets
    WorkerLane.tsx                  # horizontal swimlane per worker within a stage
    AssignDialog.tsx
    StationClient.tsx
    StationQueue.tsx
    MarkDoneDialog.tsx
    UndoBanner.tsx                  # 5-minute window banner after mark-done
    Refresher.tsx                   # 15-second polling hook wrapper

apps/web/lib/
  shop-floor-types.ts
  shop-floor-fetch.ts
```

State management: raw `fetch()` + URL search params + controlled inputs. **No TanStack Query / RHF / Zustand.**

##### 2.3 Two-surface interaction

**Foreman Office board (`/shop-floor?project=…`)**:
1. URL state: `?project=N&stage=DOWN|CNC|…&worker=worker_id&q=…&assignee=unassigned|me|all`.
2. Board fetches `GET /projects/{pid}/shop-floor/board` (returns 5 stage columns × N items per column).
3. Click an unassigned card → `AssignDialog` with worker picker.
4. Drag a card between worker lanes inside a stage column → `PATCH /assignments/{aid}` with new `worker_id`.
5. Drag across stage columns is **disabled** in v2 (lifecycle is owned by the system).

**Shop-floor display (`/shop-floor/station/[worker_id]`)**:
1. URL is permanent; tablet boots straight here.
2. Page fetches `GET /workers/{wid}/queue` every 15s.
3. Vertical list of giant cards: top card = "active now", remaining greyed.
4. Big "Mark done" button on the active card → `MarkDoneDialog` → confirm → `POST /assignments/{aid}/complete`.
5. After confirmation, an undo banner sits at the top for 5 minutes.

##### 2.4 Why two tables (`worker_assignment` + `stage_completion_log`)

Separates **mutable assignment state** from **immutable completion history**. PM dashboards aggregate from `stage_completion_log` (read-heavy, JOIN-friendly). Foreman office board reads from `worker_assignment` (active rows only).

---

#### 3. Data model

##### 3.1 Migration 0020 — `0020_shop_floor.py`

```sql
-- 1. Worker flag on existing app_user
ALTER TABLE app_user
    ADD COLUMN is_shop_worker boolean NOT NULL DEFAULT false;

CREATE INDEX idx_app_user_workers
    ON app_user (workspace_id)
    WHERE is_shop_worker = true;

-- 2. Worker assignment register
CREATE TABLE worker_assignment (
    assignment_id  bigserial    PRIMARY KEY,
    item_id        bigint       NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
    stage_key      varchar(16)  NOT NULL REFERENCES stages(stage_key),
    worker_id      bigint       NOT NULL REFERENCES app_user(id),
    status         text         NOT NULL CHECK (status IN
                                  ('assigned','in_progress','done','cancelled'))
                                DEFAULT 'assigned',
    note           text,
    assigned_by    bigint       NOT NULL REFERENCES app_user(id),
    assigned_at    timestamptz  NOT NULL DEFAULT now(),
    started_at     timestamptz,
    ended_at       timestamptz,
    cancelled_at   timestamptz,
    cancelled_by   bigint       REFERENCES app_user(id),
    created_at     timestamptz  NOT NULL DEFAULT now(),
    updated_at     timestamptz  NOT NULL DEFAULT now(),
    CHECK (stage_key IN ('DOWN','CNC','EDGED','PAINTED','MADE'))
);

-- At most one ACTIVE assignment per (item, stage). Cancelled/done rows kept for history.
CREATE UNIQUE INDEX uniq_active_assignment
    ON worker_assignment (item_id, stage_key)
    WHERE status IN ('assigned', 'in_progress');

CREATE INDEX idx_assignment_worker
    ON worker_assignment (worker_id, status)
    WHERE status IN ('assigned', 'in_progress');

CREATE INDEX idx_assignment_item
    ON worker_assignment (item_id);

-- 3. Stage completion log (append-only)
CREATE TABLE stage_completion_log (
    log_id         bigserial    PRIMARY KEY,
    item_id        bigint       NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
    stage_key      varchar(16)  NOT NULL REFERENCES stages(stage_key),
    assignment_id  bigint       REFERENCES worker_assignment(assignment_id),
    worker_id      bigint       NOT NULL REFERENCES app_user(id),
    completed_at   timestamptz  NOT NULL DEFAULT now(),
    note           text,
    undone_at      timestamptz,
    undone_by      bigint       REFERENCES app_user(id),
    CHECK (stage_key IN ('DOWN','CNC','EDGED','PAINTED','MADE'))
);

CREATE INDEX idx_completion_item
    ON stage_completion_log (item_id, stage_key);

CREATE INDEX idx_completion_worker
    ON stage_completion_log (worker_id, completed_at DESC)
    WHERE undone_at IS NULL;
```

##### 3.2 Invariants

- **`stage_key` CHECK** locks the table to the 5 shop-floor stages.
- **Partial unique index `uniq_active_assignment`** enforces "at most one assigned/in-progress assignment per (item, stage_key)".
- **`stage_completion_log.undone_at`** is the soft-undo marker. Aggregates filter `WHERE undone_at IS NULL`.
- **Cascade on `item_id`** so deleting an item clears its assignments and completion history.
- **No CASCADE on `worker_id`** — cannot delete a worker who has assignments. Use `is_shop_worker = false` to retire.

---

#### 4. RBAC + audit + security

##### 4.1 RBAC matrix update — `apps/api/app/auth/permissions.py`

Add `shop_floor` to the `Module` Literal and to `_ALL_MODULES`. Per-role:

| Role             | shop_floor actions                |
|------------------|-----------------------------------|
| admin            | `{read, write, approve, comment}` |
| manager          | `{read, write, comment}`          |
| drafter          | `{read, comment}`                 |
| editor           | `{read, write, comment}`          |
| purchase_officer | `{read}`                          |
| viewer           | `{read}`                          |

Foreman + Machine team both map to `editor`. Restrictions on who can override an in-progress assignment held by another worker are enforced in route handlers, not the matrix.

##### 4.2 Audit events

| Action | `event` | `target` | `payload` |
|---|---|---|---|
| Assign worker | `shop_floor.assign` | `assignment_id` | `{item_id, stage_key, worker_id, assigned_by}` |
| Reassign | `shop_floor.reassign` | `assignment_id` | `{item_id, stage_key, old_worker_id, new_worker_id}` |
| Unassign / cancel | `shop_floor.unassign` | `assignment_id` | `{item_id, stage_key, cancelled_by, reason?}` |
| Worker starts | `shop_floor.stage_start` | `assignment_id` | `{worker_id, started_at}` |
| Mark done | `shop_floor.stage_complete` | `assignment_id` | `{item_id, stage_key, worker_id, completed_at, note?, lifecycle_advanced: bool}` |
| Undo done | `shop_floor.stage_undo` | `log_id` | `{item_id, stage_key, undone_by, original_worker_id, original_completed_at}` |

##### 4.3 Security checklist

- **Workspace isolation** via `projects.workspace_id = :w` on every query.
- **Worker eligibility check at the route layer** — `POST /assignments` validates `worker.is_shop_worker = true AND worker.workspace_id = :w`.
- **Active assignment uniqueness** enforced by partial unique index; route returns 409 with a useful message.
- **Undo window enforcement** at the route layer.
- **Station URL is not authentication** — kiosk runs as a station user with `editor` role.
- **No public file endpoints introduced**.

---

#### 5. Workflow & state machine

##### 5.1 Assignment states

```
   ┌──────────┐  worker first taps   ┌──────────────┐
   │ assigned ├─────────────────────▶│ in_progress  │
   └────┬─────┘                      └──────┬───────┘
        │                                   │
        │ Foreman cancels                   │ worker marks done
        ▼                                   ▼
   ┌───────────┐                      ┌────────┐
   │ cancelled │                      │  done  │
   └───────────┘                      └────────┘
                                           │
                                           │ undo (5 min, worker; any time, Foreman+)
                                           ▼
                                    back to in_progress
```

Key behaviors:

- **`assigned → in_progress`** on first station interaction (idempotent `POST /assignments/{aid}/start`).
- **`in_progress → done`** on Mark done. Writes `stage_completion_log` + `item_stages.done_date` + `audit_log` in one transaction.
- **`done → in_progress` (undo)** within 5 min by worker, any time by Foreman+. Sets `stage_completion_log.undone_at`, never DELETE.
- **`assigned/in_progress → cancelled`** Foreman+ only.
- **Reassign** changes `worker_assignment.worker_id`. Foreman+ only.
- **Stage ordering enforced** — cannot mark CNC done before DOWN done. 409 with `{missing: [...]}`.
- **PAINTED is conditional** — only shown for items where `items.painting_required = true`.

##### 5.2 Permission rules summary

| Action | Required | Additional rule |
|---|---|---|
| GET board / queue | `read` | Workspace match |
| Assign / reassign / cancel | `write` | `editor`+ |
| Start (idempotent) | `write` | Caller is the assigned worker OR `editor`+ |
| Mark done | `write` | Caller is the assigned worker OR `editor`+ |
| Undo done | `write` | Caller is the assigned worker AND <5 min, OR `editor`+ any time |

---

#### 6. SQL — board + station queries

##### 6.1 Foreman Office board

```sql
WITH item_pool AS (
  SELECT
      i.item_id, i.num AS item_number, i.code, i.description,
      i.painting_required, i.project_id,
      (SELECT s.stage_key
         FROM item_stages s
        WHERE s.item_id = i.item_id
          AND s.stage_key IN ('DOWN','CNC','EDGED','PAINTED','MADE')
          AND s.done_date IS NULL
          AND (s.stage_key != 'PAINTED' OR i.painting_required)
        ORDER BY (CASE s.stage_key
                    WHEN 'DOWN' THEN 1 WHEN 'CNC' THEN 2 WHEN 'EDGED' THEN 3
                    WHEN 'PAINTED' THEN 4 WHEN 'MADE' THEN 5 END)
        LIMIT 1) AS next_stage_key
    FROM items i
    JOIN projects p ON p.project_id = i.project_id
   WHERE p.project_id = :pid AND p.workspace_id = :wid AND i.deleted = false
)
SELECT ip.*, wa.assignment_id, wa.worker_id, wa.status, wa.started_at,
       u.full_name AS worker_name
  FROM item_pool ip
  LEFT JOIN worker_assignment wa
         ON wa.item_id = ip.item_id
        AND wa.stage_key = ip.next_stage_key
        AND wa.status IN ('assigned','in_progress')
  LEFT JOIN app_user u ON u.id = wa.worker_id
 WHERE ip.next_stage_key IS NOT NULL
 ORDER BY ip.next_stage_key, ip.item_number;
```

##### 6.2 Worker station queue

```sql
SELECT wa.assignment_id, wa.item_id, i.num AS item_number, i.code, i.description,
       i.rm_no AS room_no, i.rm_desc AS room_desc, wa.stage_key, wa.status,
       wa.assigned_at, wa.started_at, p.code AS project_code
  FROM worker_assignment wa
  JOIN items i    ON i.item_id    = wa.item_id
  JOIN projects p ON p.project_id = i.project_id
 WHERE wa.worker_id = :wid AND p.workspace_id = :ws
   AND wa.status IN ('assigned','in_progress')
 ORDER BY CASE wa.status WHEN 'in_progress' THEN 0 ELSE 1 END, wa.assigned_at;
```

##### 6.3 Recently-completed (undo banner data)

```sql
SELECT log_id, item_id, stage_key, completed_at, note
  FROM stage_completion_log
 WHERE worker_id = :wid AND undone_at IS NULL
   AND completed_at > now() - interval '5 minutes'
 ORDER BY completed_at DESC;
```

---

#### 7. API surface

| Verb | Path | Purpose | Permission |
|---|---|---|---|
| GET | `/projects/{pid}/shop-floor/board` | Foreman office board | `shop_floor:read` |
| GET | `/projects/{pid}/shop-floor/workers` | List of `is_shop_worker = true` users | `shop_floor:read` |
| GET | `/workers/{wid}/queue` | Station view | `shop_floor:read` |
| GET | `/workers/{wid}/recent-completions` | Undo banner data | `shop_floor:read` |
| POST | `/projects/{pid}/items/{iid}/assignments` | Create assignment | `shop_floor:write` (editor+) |
| PATCH | `/assignments/{aid}` | Reassign or update note | `shop_floor:write` (editor+) |
| DELETE | `/assignments/{aid}` | Cancel | `shop_floor:write` (editor+) |
| POST | `/assignments/{aid}/start` | Idempotent start | `shop_floor:write` (worker OR editor+) |
| POST | `/assignments/{aid}/complete` | Mark done | `shop_floor:write` (worker OR editor+) |
| POST | `/completions/{log_id}/undo` | Undo completion | `shop_floor:write` (worker <5min OR editor+ any time) |

10 endpoints. All mounted in `apps/api/app/main.py`.

##### 7.1 Pydantic schemas

```python
ShopFloorStage = Literal["DOWN", "CNC", "EDGED", "PAINTED", "MADE"]
AssignmentStatus = Literal["assigned", "in_progress", "done", "cancelled"]


class AssignIn(BaseModel):
    stage_key: ShopFloorStage
    worker_id: int
    note: str | None = Field(default=None, max_length=500)


class PatchAssignmentIn(BaseModel):
    worker_id: int | None = None
    note: str | None = Field(default=None, max_length=500)


class CompleteIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class BoardCard(BaseModel):
    item_id: int
    item_number: int
    code: str | None
    description: str | None
    painting_required: bool
    next_stage_key: ShopFloorStage
    assignment: AssignmentOut | None    # null = unassigned


class BoardOut(BaseModel):
    project_id: int
    project_code: str
    columns: dict[str, list[BoardCard]]
```

---

#### 8. Lifecycle integration — mark-done transaction

Mark-done runs in **one DB transaction** through `apps/api/app/shop_floor/lifecycle.py`:

```python
def mark_stage_done(db, *, user, assignment_id, note) -> tuple[int, bool]:
    # 1. Fetch assignment + item under SELECT ... FOR UPDATE
    # 2. Validate: status IN ('assigned','in_progress'); workspace match
    # 3. Validate stage ordering: every prior shop-floor stage on the item has done_date
    # 4. INSERT INTO stage_completion_log
    # 5. UPDATE item_stages SET done_date = CURRENT_DATE
    # 6. UPDATE worker_assignment SET status='done', ended_at=now()
    # 7. Audit: shop_floor.stage_complete with payload
    # 8. Return (log_id, lifecycle_advanced)
```

##### 8.1 Stage-ordering validation

```python
SHOP_FLOOR_ORDER = ("DOWN", "CNC", "EDGED", "PAINTED", "MADE")

def prior_stages_done(db, item_id, stage_key, painting_required):
    idx = SHOP_FLOOR_ORDER.index(stage_key)
    priors = SHOP_FLOOR_ORDER[:idx]
    if not painting_required:
        priors = tuple(s for s in priors if s != "PAINTED")
    if not priors:
        return True
    rows = db.execute(text("""
        SELECT stage_key, done_date IS NOT NULL AS done
          FROM item_stages
         WHERE item_id = :iid AND stage_key = ANY(:priors)
    """), {"iid": item_id, "priors": list(priors)}).all()
    return all(r.done for r in rows) and len(rows) == len(priors)
```

If validation fails, return 409: `{"error": "stage_out_of_order", "missing": ["DOWN"]}`.

##### 8.2 Undo path

Symmetric: clears `item_stages.done_date`, sets `stage_completion_log.undone_at`, sets `worker_assignment.status = 'in_progress', ended_at = NULL`, writes `shop_floor.stage_undo`. The 5-minute window check is a Python `if` against `completed_at`.

##### 8.3 PM dashboard read-side compatibility

PM tracking grids today read `item_stages.done_date` directly. Once `mark_stage_done` writes there, PM dashboards "just work" — no PM-side change required.

---

#### 9. Web — UI components

##### 9.1 Foreman Office board

- **Header:** project chip selector, counts, Refresh button (auto-polls every 15s).
- **Filter strip:** search by item code, worker chip dropdown, stage filter.
- **5-column kanban:** DOWN | CNC | EDGED | PAINTED | MADE. PAINTED column dimmed when project has zero painting-required items.
- **Within each column:** Worker swimlanes + "Unassigned" lane at top.
- **Card interactions:** click → drawer; drag between worker lanes → reassign; "× cancel" on hover.

##### 9.2 Shop-floor display

- Sized for 1024×768+ landscape tablets. Larger touch targets, thicker fonts.
- **Header:** Worker name + project banner. Big clock top-right.
- **Active card (top):** ~70% viewport height. Item code + description in display-size font. Single big green button: "Mark DOWN done".
- **Upcoming cards (below):** dimmed, smaller, scrollable.
- **Mark done flow:** tap big button → full-screen modal with optional note → Confirm/Cancel.
- **Undo banner:** sticky top after a completion, 5-minute countdown.

##### 9.3 Polling hook

```tsx
function useBoardPolling(fetchFn, intervalMs = 15000) {
  useEffect(() => {
    const ctrl = new AbortController();
    fetchFn();
    const id = setInterval(fetchFn, intervalMs);
    return () => { clearInterval(id); ctrl.abort(); };
  }, []);
}
```

---

#### 10. Seed updates

`seed/hartwood_joinery.py` — add 4 demo workers + 6 in-flight assignments on ALF-001:

**Workers** (toggle `is_shop_worker = true`):

| Email | Full name | Role |
|---|---|---|
| `sam.lee@hartwood.test` | Sam Lee | editor (Joiner) |
| `priya.dhar@hartwood.test` | Priya Dhar | editor (CNC operator) |
| `marko.vil@hartwood.test` | Marko Villas | editor (Edge bander + painter) |
| `kira.osei@hartwood.test` | Kira Osei | editor (All-rounder) |

Roster grows from 8 to 12 staff users.

**Assignments on ALF-001:**

| # | Item # | Stage | Worker | Status |
|---|---|---|---|---|
| 1 | 1 | DOWN | Sam Lee | in_progress |
| 2 | 2 | DOWN | Sam Lee | assigned |
| 3 | 3 | DOWN | Priya Dhar | done (yesterday) |
| 4 | 4 | CNC | Priya Dhar | assigned |
| 5 | 5 | DOWN | Marko Villas | assigned |
| 6 | 6 | EDGED | Kira Osei | assigned |

Item 3's "done" assignment also writes a real `stage_completion_log` row. Idempotent via `WHERE NOT EXISTS` guards.

---

#### 11. Testing

##### 11.1 Pytest suite (~43 cases)

| File | Cases | Focus |
|---|---|---|
| `test_shop_floor_assign.py` | 8 | Create/reassign/cancel; cross-workspace 404; duplicate active 409; perms |
| `test_shop_floor_complete.py` | 10 | Transactional write; out-of-order 409; PAINTED skip; concurrent FOR UPDATE |
| `test_shop_floor_undo.py` | 6 | Worker <5min; foreman any time; soft-undo via `undone_at` |
| `test_shop_floor_board.py` | 5 | All 5 columns; PAINTED filter; unassigned cards |
| `test_shop_floor_station.py` | 4 | Active-only queue; ordering; cross-workspace 404 |
| `test_shop_floor_workspace_isolation.py` | 4 | Cross-workspace GET/POST returns 404/403 |
| `test_shop_floor_lifecycle.py` | 6 | `prior_stages_done` helper unit tests |

`worker_assignment` and `stage_completion_log` added to `TRUNCATE_TABLES` in `apps/api/tests/conftest.py`.

##### 11.2 Playwright E2E

`tests/e2e/shop_floor.spec.ts` — single happy-path covering both surfaces, then out-of-order 409 and undo flows.

##### 11.3 Manual smoke

10-step checklist covering: login → assign → drag-reassign → station mark-done → undo → 5-min expiry → out-of-order → cross-workspace 404 → viewer permission → manager override.

---

#### 12. Implementation order

1. Migration 0020 (worker flag + 2 tables + indexes).
2. RBAC matrix update (10th module `shop_floor`).
3. Pydantic schemas + lifecycle.py helper with unit tests.
4. queries.py (board, station, recent-completions, assignment CRUD).
5. routes.py — first 5 endpoints (board, workers, queue, recent-completions, assign).
6. Routes part 2 — patch, delete, start, complete, undo + concurrency tests.
7. Workspace isolation tests.
8. Web `lib/` types + fetch wrappers.
9. Office page shell + 5-column kanban.
10. AssignmentCard + StageColumn + WorkerLane with drag-to-reassign.
11. AssignDialog.
12. Station page — StationClient + StationQueue.
13. MarkDoneDialog + UndoBanner + Refresher polling.
14. Seed update.
15. Playwright E2E spec.
16. CLAUDE.md update + reference doc entries.

16 tasks total.

---

#### 13. Audit log events

Already enumerated in §4.2. The IT Management timeline at `/it` aggregates `audit_log` and surfaces all 6 events for free.

---

#### 14. Resolved decisions

- **Worker registry**: `app_user.is_shop_worker` boolean, not separate table.
- **Sub-project module name**: `shop_floor` (snake_case).
- **Auth role for Foreman**: `editor`, no new role.
- **5 stages owned by Shop Floor**: DOWN, CNC, EDGED, PAINTED, MADE.
- **PAINTED conditional** on `items.painting_required`.
- **Two tables**: mutable `worker_assignment` + immutable `stage_completion_log`.
- **Undo window**: 5 min for worker; unlimited for Foreman+.
- **Stage ordering enforced**: cannot mark CNC done before DOWN done.
- **Polling, not push**: 15s interval.
- **Two surfaces, one app**: office + station kiosk both under `/shop-floor`.
- **Single project per board**.
- **Lifecycle is derived**: no `items.current_lifecycle_stage` column added.

---

#### 15. Open questions — resolved 2026-08-14

Q1 and Q2 were answered by the implementation plan and shipped. Q3 and Q4 were
never dispositioned and sat here as live questions long after #8 shipped;
recorded below against what the code actually does.

1. **PAINTED-after-MADE stage ordering** — spec says PAINTED before MADE. Some shops assemble first, then paint. Confirm before implementation.
   → **RESOLVED — both orders supported.** Migration 0020 adds
   `items.paint_after_assembly`; when true the order becomes
   DOWN → CNC → EDGED → MADE → PAINTED. `prior_stages_done()` reads it
   alongside `items.painting_req`, and PAINTED drops out of the order entirely
   when `painting_req = false`.
2. **Reassign-on-in-progress behavior**: clear `started_at` on reassign (new worker starts fresh) vs preserve. Proposed: clear.
   → **RESOLVED as proposed.** `PATCH /assignments/{aid}` clears `started_at`
   and resets status to `assigned`.
3. **What happens when a worker is deactivated while holding active assignments?** Proposed: route-layer flip rejects with 409 if active assignments exist.
   → **RESOLVED as proposed — 409 reject.** Both mutation paths now consult
   `worker_assignment` before the flip: `PATCH /users/{uid}` when it sets
   `is_active=false`, and `PATCH /users/{uid}/shop-worker` when it sets
   `is_shop_worker=false`. If the worker still holds any `assigned` /
   `in_progress` assignment in the workspace, the request returns
   `409 {code: "HAS_ACTIVE_ASSIGNMENTS", assignments: [...]}` and nothing
   changes; the admin must reassign or cancel that work first. The
   cascade-cancel alternative was rejected — silently cancelling in-progress
   work as a side effect of a user edit loses the record of who held it.
   Enforced by `shop_floor.queries.active_assignments_for_worker` +
   `users.routes._guard_active_assignments`.
4. **PM "Labour & Progress" panel** — does PM need a small "today's completions" widget on `/tracking`? Proposed: defer.
   → **RESOLVED: deferred as proposed.** Not built; listed under #8's
   out-of-scope items in `CLAUDE.md`. `stage_completion_log` already holds
   everything such a widget would need.

---

**End of spec.** Ready for the planner agent to break into a 16-task implementation plan covering migration 0020, the `shop_floor` app module, RBAC matrix update, two-surface UI, seed updates, and the test suite.


## Implementation plan

### Implementation Plan — Shop Floor Ops (sub-project #8)

> **Status: shipped.** Migration `0020`. Current state lives in
> `## Shop Floor Ops (sub-project #8)` in `CLAUDE.md`;
> the task checkboxes below were never ticked and are not a progress signal
> (see `docs/archive/README.md`).

> **Later change:** Spec §15 Q3 (deactivating a worker who holds active assignments) was
> proposed but never built — see the spec for the consequence.

> **Later change — superseded in part by Plan V1 (see `docs/plan-v1/`).** This
> module is re-keyed. `worker_assignment` and `stage_completion_log` move from
> `(item_id, stage_key)` to **`(cutlist_id, stage_key)` for production stages**,
> keeping `(item_id, 'INST')` for installation (Q445) — including the partial
> unique index `uniq_active_assignment`. Completion **fans out** to every item on
> the cutlist (Q439) and **undo reverses the whole cutlist** atomically (Q446).
> A **Packing** stage joins the lifecycle, with scanning (Q519), and QC arrives
> as its own module rather than a stage (Q515).

**Spec:** `docs/archive/2026-05-05-shop-floor.md`
**Branch base:** `feat/foundation` post-#7c (HEAD `bf6d331`).
**Migration introduced:** `0020_shop_floor.py`.
**RBAC module added:** `shop_floor` (10th IA module).
**Scope decision:** ship as a single merge per user direction.

---

#### Schema note

The spec references `items.painting_required`. The actual column name in
the existing migration 0001 is **`items.painting_req`** (boolean default
false). This plan uses the existing column name; no rename in 0020.

#### 0. User decisions binding this plan

1. **Stage ordering is per-item via a new column `items.paint_after_assembly` (boolean, default `false`).** When `false`, ordering is `DOWN → CNC → EDGED → PAINTED → MADE`. When `true`, ordering is `DOWN → CNC → EDGED → MADE → PAINTED`. The `prior_stages_done` helper at `apps/api/app/shop_floor/lifecycle.py` reads the column.
2. **Reassign clears `started_at`** and resets status to `'assigned'`. Audit row `shop_floor.reassign` records both the worker swap and the timer reset.
3. **Worker registry**: seed adds 4 workers (12 staff total) + an admin-only toggle UI lives at `/it` (IT Management page) for promoting/retiring `is_shop_worker`. No separate `/shop-floor/workers` admin page in v2.
4. **Single merge** — all 17 tasks land on `feat/foundation` in one cohesive commit series.

---

#### 1. Tasks

##### Backend (8 tasks)

1. **Migration `0020_shop_floor.py`** — `app_user.is_shop_worker`, `worker_assignment` (with the partial unique index `uniq_active_assignment`), `stage_completion_log`, plus the new `items.paint_after_assembly boolean NOT NULL DEFAULT false` column.
2. **Pydantic schemas** at `apps/api/app/shop_floor/schemas.py`: `AssignIn`, `PatchAssignmentIn`, `CompleteIn`, `BoardCard`, `BoardOut`, `AssignmentOut`, `StationCard`, `StationOut`, `RecentCompletionOut`.
3. **`lifecycle.py`** at `apps/api/app/shop_floor/lifecycle.py`: pure helpers `shop_floor_order(paint_after_assembly: bool) -> tuple[str, ...]`, `prior_stages_done(...)`, `is_within_undo_window(...)`. Pure functions, unit-testable.
4. **Queries** at `apps/api/app/shop_floor/queries.py` — workspace-isolated SQL for: board, station queue, recent completions, assignment CRUD, mark-done transaction, undo transaction. Uses `SELECT … FOR UPDATE` on `worker_assignment` rows on the mark-done + undo paths.
5. **Routes** at `apps/api/app/shop_floor/routes.py` (10 endpoints, gated `("shop_floor", action)`):
   - `GET /projects/{pid}/shop-floor/board`
   - `GET /projects/{pid}/shop-floor/workers`
   - `GET /workers/{wid}/queue`
   - `GET /workers/{wid}/recent-completions`
   - `POST /projects/{pid}/items/{iid}/assignments`
   - `PATCH /assignments/{aid}` (reassign clears `started_at`; note edits don't)
   - `DELETE /assignments/{aid}` (cancel)
   - `POST /assignments/{aid}/start` (idempotent)
   - `POST /assignments/{aid}/complete`
   - `POST /completions/{log_id}/undo`
6. **Worker-toggle route** for #3 — `PATCH /users/{uid}/shop-worker` body `{is_shop_worker: bool}`, gated `("it_management", "write")` (admin-only). Lives in the existing `apps/api/app/users/` module so the `/it` page picks it up.
7. **RBAC matrix update** — add `shop_floor` to `_ALL_MODULES` and to `MATRIX` per spec §4.1. Foreman = `editor`, no new role.
8. **Mount router** in `apps/api/app/main.py`, add `worker_assignment` + `stage_completion_log` to `apps/api/tests/conftest.py::TRUNCATE_TABLES`.

##### Tests (1 task)

9. **Pytest** — six files matching the spec §11.1 layout:
   - `tests/test_shop_floor_assign.py` (assign/reassign/cancel + perms)
   - `tests/test_shop_floor_complete.py` (mark-done txn, stage ordering, PAINTED skip)
   - `tests/test_shop_floor_undo.py` (worker <5min, foreman any time)
   - `tests/test_shop_floor_board.py` (5 columns, PAINTED filter, unassigned)
   - `tests/test_shop_floor_station.py` (queue, ordering, cross-workspace 404)
   - `tests/test_shop_floor_lifecycle.py` (`prior_stages_done` + `paint_after_assembly` flip + undo window)
   - Cross-workspace + RBAC coverage rolled into the per-feature files.
   Target ≥35 cases, ≥80% line coverage on the new module.

##### Web (5 tasks)

10. **Lib** — `apps/web/lib/shop-floor-{types,fetch}.ts` mirroring the API.
11. **Foreman office board** — `/shop-floor/page.tsx` (server component) + `_components/ShopFloorClient.tsx` + `StageColumn.tsx` + `WorkerLane.tsx` + `AssignmentCard.tsx` + `AssignDialog.tsx` + `Refresher.tsx` (15-second polling hook).
12. **Shop-floor display** — `/shop-floor/station/[worker_id]/page.tsx` + `_components/StationClient.tsx` + `StationQueue.tsx` + `MarkDoneDialog.tsx` + `UndoBanner.tsx`.
13. **`/it` worker toggle** — small `WorkerRosterPanel.tsx` rendered on `apps/web/app/(app)/it/page.tsx`. Lists every workspace user with a checkbox column for `is_shop_worker`; clicking the checkbox fires `PATCH /api/users/{uid}/shop-worker`. Admin-only.
14. **SideBar entry** — add a `Shop Floor` link under `Catalog` + `Cut Floor` in `apps/web/components/chrome/SideBar.tsx` for any user with `shop_floor.read`.

##### Seed + docs + verification (3 tasks)

15. **Seed** (`seed/hartwood_joinery.py`): grow `USERS` from 8 → 12, set `is_shop_worker = true` on the 4 new rows (Sam Lee, Priya Dhar, Marko Villas, Kira Osei). Insert 6 demo `worker_assignment` rows + 1 `stage_completion_log` row on ALF-001. Idempotent via `WHERE NOT EXISTS` guards. Re-run safety: assignments are scoped per (item, stage) so the unique index protects re-seeds.
16. **CLAUDE.md** — add `## Shop Floor Ops (sub-project #8)` section + a Reference docs entry pointing at this plan + the spec.
17. **Docker verification** — `make migrate` (apply 0020) + `make test` (full pytest) + `make seed` round-trip + manual smoke against `/shop-floor` and `/shop-floor/station/{wid}`.

---

#### 2. Status machine (binding)

```
   assigned ─worker taps─▶ in_progress ─mark done─▶ done
        │                       │                    │
        │ Foreman cancel         │                    │ undo (5m worker / ∞ foreman+)
        ▼                       ▼                    ▼
    cancelled              cancelled            in_progress
```

PATCH route accepts `worker_id` change (clears `started_at`, status flips back to `assigned`) OR `note` edit (no status touch). Concurrent assignment to the same `(item_id, stage_key)` is rejected by the partial unique index → 409 with `{code: "ACTIVE_ASSIGNMENT_EXISTS", assignment_id}`.

---

#### 3. Stage ordering with `paint_after_assembly`

```python
SHOP_FLOOR_ORDER_DEFAULT = ("DOWN", "CNC", "EDGED", "PAINTED", "MADE")
SHOP_FLOOR_ORDER_PAINT_LAST = ("DOWN", "CNC", "EDGED", "MADE", "PAINTED")

def shop_floor_order(paint_after_assembly: bool) -> tuple[str, ...]:
    return SHOP_FLOOR_ORDER_PAINT_LAST if paint_after_assembly else SHOP_FLOOR_ORDER_DEFAULT
```

`prior_stages_done()` reads `items.painting_required` AND `items.paint_after_assembly` to build the per-item priors list. UI: drafter editor's metadata panel gets a checkbox "Paint after assembly" (gated on `painting_required`) — that ships in this plan as a tiny addition to `ItemMetadataPanel.tsx`.

The board's "next stage" subquery (spec §6.1) is updated to honour the per-item ordering — by joining the item's flags into the `CASE` ordering.

---

#### 4. Audit events (binding, all through `write_audit`)

| Event | Payload |
|---|---|
| `shop_floor.assign` | `{item_id, stage_key, worker_id, assigned_by}` |
| `shop_floor.reassign` | `{assignment_id, item_id, stage_key, old_worker_id, new_worker_id, started_at_cleared: true}` |
| `shop_floor.unassign` | `{assignment_id, item_id, stage_key, cancelled_by, reason?}` |
| `shop_floor.stage_start` | `{assignment_id, worker_id, started_at}` |
| `shop_floor.stage_complete` | `{assignment_id, item_id, stage_key, worker_id, completed_at, note?, lifecycle_advanced: bool}` |
| `shop_floor.stage_undo` | `{log_id, item_id, stage_key, undone_by, original_worker_id, original_completed_at}` |
| `it.worker_toggle` | `{user_id, is_shop_worker, by_admin_id}` |

---

#### 5. Out of scope (deferred)

Per spec §1 "Out of scope":
- Mobile-first responsive UI (tablet 1024+ landscape only).
- Real-time pub/sub (15-second poll instead).
- Efficiency analytics dashboards (data captured; UI later).
- Per-part painting tracking.
- `time_record` table for payroll.
- Worker self-assignment.
- Quality / rework loop.
- Cross-project worker view.
- Per-worker login (kiosk URL = pseudo-auth).
- PM "today's completions" widget on `/tracking` (spec §15 Q4 — defer).

---

#### 6. Exit criteria

- 0020 applies cleanly on top of 0019; downgrade is no-op pattern.
- ≥35 pytest cases pass; existing #7c suite still green.
- `/shop-floor?project=ALF-001` shows 5 columns with the seeded 6 assignments + 1 completed (Item 3 DOWN done yesterday).
- `/shop-floor/station/{sam_lee_id}` shows Sam Lee's queue with the active card on top.
- Mark-done from station writes `item_stages.done_date`, the `stage_completion_log` row, and the `audit_log` `shop_floor.stage_complete` row inside one transaction. Verified by checking PM's existing `/tracking` page reflects the completion.
- Undo within 5 minutes works for the worker; after, only Foreman+ can undo.
- `/it` admin can flip `is_shop_worker` for any workspace user; PATCH writes audit `it.worker_toggle`.
- Cross-workspace GETs and POSTs return 404/403; viewer cannot mutate.
