"""Pilot-data importer for FileMaker's "Tracking 2.0" grid export (E3, first slice).

One workbook, one sheet, one project: a row per item. Run it from the api container (or any venv with
`DATABASE_URL` set):

    python -m app.importers.tracking_grid FILE.xlsx --workspace-slug SLUG --actor-email EMAIL \\
        --project-code 2325 --project-name "..."            # a dry run: validates, writes nothing
    python -m app.importers.tracking_grid ... --commit       # the same, then keeps it

Settled with the user (2026-10-08):

- Item IDs (`ItemId`) and cutlist numbers (`CutlistNumber`) are **kept as they are** (`items.num`,
  `cutlist.cutlist_no`); the shared `joinery_number_seq` is moved past the highest of them afterwards.
- The date columns are **done dates** (`item_stages.done_date`), except `Date_ReqOnSite`, which is the REQ
  stage's **due** date. `Date_Optimized` has no stage and is not imported (it is counted in the report).
  `Date_Created` becomes `items.created_at`.
- `_Contractor` (e.g. `TG`) is a **factory** (`factory`, `items.factory_id`); `Tag_TgSolidItem` is the
  separate `items.tg_solid` tag.
- A cutlist number written with a leading `#` (`#101973`, 65 rows in the pilot file) is imported as the
  cutlist number **101973**: the `#` is stripped (settled with the user, 2026-10-08).
- A row with no usable cutlist number is imported as an item **without** a cutlist (the data model allows
  it, Q440); any other cutlist text that is not a number is kept in the item's notes.

A dry run does the real inserts inside one transaction and rolls it back, so a constraint that would fail
on `--commit` fails the dry run too. (Postgres sequences are not rolled back: a dry run burns a few
`items_item_id_seq` values, which is harmless, and never touches `joinery_number_seq`.)

Re-running is safe: an item whose `ItemId` already exists in the workspace is skipped, deleted ones included.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import sys
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit

REQUIRED_HEADERS = (
    "CutlistNumber", "_Contractor", "Tag_TgSolidItem", "Zone", "STG", "LevelTXT", "RmDesc", "RoomNoTXT",
    "Item", "JID", "QTY", "PID", "Notes", "Date_Created", "Date_ReqOnSite", "Date_SiteMeasured",
    "Date_Listed", "Date_Optimized", "Date_SentDown", "Date_MachinedCompleted", "Date_Edged", "Date_Made",
    "Date_Painted", "Date_Delivered", "Date_Installed", "ListerName", "Assembler", "ItemId",
    "DWG_FullDrawingPlan", "DWG_DetailPlan", "DWG_RoomFloorPlan", "Status", "_StatusNoteLatest", "ItemId_Old",
)

# FileMaker column -> (stage_key, which item_stages column it fills)
STAGE_DATES: tuple[tuple[str, str, str], ...] = (
    ("Date_ReqOnSite", "REQ", "due_date"),
    ("Date_SiteMeasured", "SM", "done_date"),
    ("Date_Listed", "LISTED", "done_date"),
    ("Date_SentDown", "DOWN", "done_date"),
    ("Date_MachinedCompleted", "CNC", "done_date"),
    ("Date_Edged", "EDGED", "done_date"),
    ("Date_Painted", "PAINTED", "done_date"),
    ("Date_Made", "MADE", "done_date"),
    ("Date_Delivered", "DEL", "done_date"),
    ("Date_Installed", "INST", "done_date"),
)

# A cutlist number FileMaker shows with a leading `#`.
HASH_CUTLIST = re.compile(r"^#\s*(\d+)$")

# Values FileMaker uses where no single area / level applies.
NO_AREA = {"VARIES"}

# items column -> max length (varchar), so an over-long value is cut and reported, not a failed insert.
MAX_LEN = {
    "description": 255, "stage": 64, "level": 16, "rm_no": 16, "rm_desc": 128, "jid_code": 32,
    "lister": 128, "assembler": 128, "floor_plan": 64, "rls": 64, "joiery_details": 64,
    "legacy_item_ref": 64,
}
VALID_STATUS = {"CLEAR", "VOID", "NOTE!", "LIVE", "APPROVED", "HOLD"}


class ImportErrorReport(Exception):
    """The workbook cannot be imported at all (missing columns, several projects, a clash)."""


@dataclass
class ItemPlan:
    item_id_fm: int                    # FileMaker ItemId -> items.num
    cutlist_no: int | None
    description: str
    qty: int
    stage: str | None
    level: str | None
    rm_no: str | None
    rm_desc: str | None
    area: str | None                   # area name, None when there is no usable STG
    jid_code: str | None
    status: str
    status_note: str | None
    lister: str | None
    assembler: str | None
    floor_plan: str | None             # DWG_RoomFloorPlan
    rls: str | None                    # DWG_FullDrawingPlan (to be confirmed with the user)
    joiery_details: str | None         # DWG_DetailPlan
    notes: str | None                  # FileMaker Notes (+ a cutlist number that was not a number)
    factory: str | None
    tg_solid: bool
    legacy_ref: str | None
    created: dt.date | None
    stages: dict[str, tuple[str, dt.date]] = field(default_factory=dict)   # stage_key -> (column, date)


@dataclass
class Plan:
    pid: int | None
    items: list[ItemPlan]
    areas: list[str]
    rooms: "OrderedDict[tuple[str, str], str | None]"          # (area, rm_no) -> rm_desc
    factories: list[str]
    cutlists: "OrderedDict[int, dt.date | None]"               # cutlist_no -> earliest Date_Created
    anomalies: list[tuple[str, str]] = field(default_factory=list)   # (kind, detail)
    skipped_optimized: int = 0

    def note(self, kind: str, detail: str) -> None:
        self.anomalies.append((kind, detail))


def _clean(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _int(v) -> int | None:
    s = _clean(v)
    if s is None:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f == int(f) else None


def _date(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    return v if isinstance(v, dt.date) else None


def read_rows(path: str | Path) -> list[dict]:
    """The sheet as a list of {header: value}. Raises ImportErrorReport when columns are missing."""
    import openpyxl    # imported here so the module (and its tests of the planner) load without a workbook

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    header = [(_clean(h) or "") for h in next(it)]
    missing = [h for h in REQUIRED_HEADERS if h not in header]
    if missing:
        raise ImportErrorReport(f"the sheet is missing columns: {', '.join(missing)}")
    return [dict(zip(header, r)) for r in it if any(c is not None and str(c).strip() for c in r)]


def build_plan(rows: list[dict], *, pid: int | None = None) -> Plan:
    """Validate and normalise the rows; no database. Everything odd is recorded in `plan.anomalies`."""
    pids = Counter(_int(r.get("PID")) for r in rows if _int(r.get("PID")) is not None)
    if pid is None:
        if len(pids) > 1:
            raise ImportErrorReport(f"the sheet holds several projects (PID {sorted(pids)}); pass one with --pid")
        pid = next(iter(pids), None)
    plan = Plan(pid=pid, items=[], areas=[], rooms=OrderedDict(), factories=[], cutlists=OrderedDict())
    seen: set[int] = set()

    for n, r in enumerate(rows, start=2):                      # sheet row numbers, header = 1
        if pid is not None and _int(r.get("PID")) not in (None, pid):
            plan.note("other_project", f"row {n}: PID {r.get('PID')} is not {pid}; skipped")
            continue
        fm_id = _int(r.get("ItemId"))
        if fm_id is None:
            plan.note("bad_item_id", f"row {n}: ItemId {r.get('ItemId')!r} is not a number; skipped")
            continue
        if fm_id in seen:
            plan.note("duplicate_item_id", f"row {n}: ItemId {fm_id} appears twice; the second is skipped")
            continue
        seen.add(fm_id)

        def cut(field_name: str, value: str | None) -> str | None:
            limit = MAX_LEN.get(field_name)
            if value is not None and limit is not None and len(value) > limit:
                plan.note("too_long", f"item {fm_id}: {field_name} is {len(value)} characters; cut to {limit}")
                return value[:limit]
            return value

        notes = _clean(r.get("Notes"))
        raw_cutlist = _clean(r.get("CutlistNumber"))
        cutlist_no = _int(raw_cutlist)
        hashed = HASH_CUTLIST.match(raw_cutlist) if raw_cutlist else None
        if hashed:
            cutlist_no = int(hashed.group(1))
            plan.note("hash_cutlist", f"item {fm_id}: cutlist number {raw_cutlist!r} imported as {cutlist_no}")
        elif raw_cutlist is None:
            plan.note("no_cutlist", f"item {fm_id} ({_clean(r.get('Item'))}): no cutlist number; imported without one")
        elif cutlist_no is None:
            plan.note("bad_cutlist", f"item {fm_id}: cutlist number {raw_cutlist!r} is not a number; "
                                     "imported without a cutlist, the text kept in the notes")
            kept = f"FileMaker cutlist number: {raw_cutlist}"
            notes = f"{notes}\n{kept}" if notes else kept

        stg = _clean(r.get("STG"))
        area = None if stg is None or stg.upper() in NO_AREA else stg
        if stg is not None and area is None:
            plan.note("varies", f"item {fm_id}: stage {stg!r} names no single area; imported without an area or room")
        level = _clean(r.get("LevelTXT"))
        if level is not None and level.upper() in NO_AREA:
            plan.note("varies", f"item {fm_id}: level {level!r}; kept as text")
        rm_no = cut("rm_no", _clean(r.get("RoomNoTXT")))
        rm_desc = cut("rm_desc", _clean(r.get("RmDesc")))

        raw_status = _clean(r.get("Status"))
        status = raw_status.upper() if raw_status else "CLEAR"
        if status not in VALID_STATUS:
            plan.note("bad_status", f"item {fm_id}: status {status!r} is not one of ours; imported as CLEAR")
            status = "CLEAR"
        status_note = _clean(r.get("_StatusNoteLatest"))

        qty = _int(r.get("QTY")) or 1
        description = _clean(r.get("Item")) or f"(no description, FileMaker item {fm_id})"

        stages: dict[str, tuple[str, dt.date]] = {}
        for column, stage_key, target in STAGE_DATES:
            d = _date(r.get(column))
            if d is not None:
                stages[stage_key] = (target, d)
        if _date(r.get("Date_Optimized")) is not None:
            plan.skipped_optimized += 1
        made, delivered, installed = (stages.get(k, (None, None))[1] for k in ("MADE", "DEL", "INST"))
        if made and delivered and made > delivered:
            plan.note("date_order", f"item {fm_id}: made {made} is after delivered {delivered}")
        if delivered and installed and delivered > installed:
            plan.note("date_order", f"item {fm_id}: delivered {delivered} is after installed {installed}")

        item = ItemPlan(
            item_id_fm=fm_id, cutlist_no=cutlist_no, description=cut("description", description) or "",
            qty=qty, stage=cut("stage", stg), level=cut("level", level), rm_no=rm_no, rm_desc=rm_desc,
            area=area, jid_code=cut("jid_code", _clean(r.get("JID"))), status=status, status_note=status_note,
            lister=cut("lister", _clean(r.get("ListerName"))),
            assembler=cut("assembler", _clean(r.get("Assembler"))),
            floor_plan=cut("floor_plan", _clean(r.get("DWG_RoomFloorPlan"))),
            rls=cut("rls", _clean(r.get("DWG_FullDrawingPlan"))),
            joiery_details=cut("joiery_details", _clean(r.get("DWG_DetailPlan"))),
            notes=notes, factory=_clean(r.get("_Contractor")), tg_solid=_int(r.get("Tag_TgSolidItem")) == 1,
            legacy_ref=cut("legacy_item_ref", _clean(r.get("ItemId_Old"))),
            created=_date(r.get("Date_Created")), stages=stages,
        )
        plan.items.append(item)

        if area is not None:
            if area not in plan.areas:
                plan.areas.append(area)
            if rm_no is not None:
                key = (area, rm_no)
                if key not in plan.rooms:
                    plan.rooms[key] = rm_desc
                elif rm_desc and plan.rooms[key] and plan.rooms[key] != rm_desc:
                    plan.note("room_desc_conflict", f"room {rm_no} in area {area}: {plan.rooms[key]!r} and "
                                                    f"{rm_desc!r}; the first is used")
                elif rm_desc and not plan.rooms[key]:
                    plan.rooms[key] = rm_desc
        if item.factory and item.factory not in plan.factories:
            plan.factories.append(item.factory)
        if cutlist_no is not None:
            c = plan.cutlists.get(cutlist_no)
            plan.cutlists[cutlist_no] = min(filter(None, (c, item.created)), default=None)
    return plan


@dataclass
class Result:
    project_id: int | None = None
    project_created: bool = False
    factories_created: int = 0
    areas_created: int = 0
    rooms_created: int = 0
    cutlists_created: int = 0
    items_created: int = 0
    items_skipped_existing: int = 0
    stage_rows: int = 0
    status_notes: int = 0
    sequence_to: int | None = None


def apply(
    db: Session, plan: Plan, *, workspace_id: int, actor_id: int, project_code: str, project_name: str,
    source_sha256: str, advance_sequence: bool,
) -> Result:
    """Write the plan. Flushes, never commits: the caller commits (`--commit`) or rolls back (dry run)."""
    res = Result()
    actor_email = db.execute(text("SELECT email FROM app_user WHERE id = :u AND workspace_id = :w"),
                             {"u": actor_id, "w": workspace_id}).scalar()

    # ---- project -------------------------------------------------------------------------------------
    pr = db.execute(text("SELECT project_id FROM projects WHERE project_code = :c AND workspace_id = :w"),
                    {"c": project_code, "w": workspace_id}).first()
    if pr is None:
        res.project_id = db.execute(
            text("""INSERT INTO projects(project_code, name, workspace_id, pm_id, created_by)
                    VALUES (:c, :n, :w, :u, :e) RETURNING project_id"""),
            {"c": project_code, "n": project_name, "w": workspace_id, "u": actor_id, "e": actor_email},
        ).scalar()
        res.project_created = True
    else:
        res.project_id = pr[0]
    pid = res.project_id

    # ---- clashes: fixed numbers must be free, or already ours ------------------------------------------
    nums = [i.item_id_fm for i in plan.items]
    existing = {r[0]: r[1] for r in db.execute(
        text("SELECT i.num, p.project_id FROM items i JOIN projects p ON p.project_id = i.project_id"
             " WHERE i.num = ANY(:n)"), {"n": nums})}                      # deleted ones count: `num` is unique
    foreign = sorted(n for n, owner in existing.items() if owner != pid)
    if foreign:
        raise ImportErrorReport(f"ItemId already used by another project: {foreign[:10]}")
    cl_nos = list(plan.cutlists)
    clashes = [r[0] for r in db.execute(
        text("SELECT c.cutlist_no FROM cutlist c WHERE c.cutlist_no = ANY(:n) AND c.project_id <> :p"),
        {"n": cl_nos, "p": pid})]
    if clashes:
        raise ImportErrorReport(f"cutlist numbers already used by another project: {sorted(clashes)[:10]}")
    # Item IDs and cutlist numbers share one number space (Q541): a six-digit number must never mean two
    # things. Check both directions, against what is already in the database and within the file.
    as_item = sorted({r[0] for r in db.execute(text("SELECT i.num FROM items i WHERE i.num = ANY(:n)"),
                                               {"n": cl_nos})})
    if as_item:
        raise ImportErrorReport(f"cutlist numbers that are already an Item ID: {as_item[:10]}")
    as_cutlist = sorted({r[0] for r in db.execute(
        text("SELECT c.cutlist_no FROM cutlist c WHERE c.cutlist_no = ANY(:n)"), {"n": nums})})
    if as_cutlist:
        raise ImportErrorReport(f"Item IDs that are already a cutlist number: {as_cutlist[:10]}")
    both = sorted(set(nums) & set(cl_nos))
    if both:
        raise ImportErrorReport(f"numbers used as both an Item ID and a cutlist number in the file: {both[:10]}")

    # ---- lookups -------------------------------------------------------------------------------------
    factory_ids: dict[str, int] = {}
    for code in plan.factories:
        row = db.execute(text("SELECT factory_id FROM factory WHERE workspace_id = :w AND code = :c"),
                         {"w": workspace_id, "c": code}).first()
        if row is None:
            row = db.execute(text("INSERT INTO factory(workspace_id, code, name) VALUES (:w, :c, :c)"
                                  " RETURNING factory_id"), {"w": workspace_id, "c": code}).first()
            res.factories_created += 1
        factory_ids[code] = row[0]

    area_ids: dict[str, int] = {}
    for sort, name in enumerate(plan.areas):
        row = db.execute(text("SELECT area_id FROM area WHERE project_id = :p AND name = :n"),
                         {"p": pid, "n": name}).first()
        if row is None:
            row = db.execute(text("INSERT INTO area(project_id, name, sort_order) VALUES (:p, :n, :s)"
                                  " RETURNING area_id"), {"p": pid, "n": name, "s": sort}).first()
            res.areas_created += 1
        area_ids[name] = row[0]

    room_ids: dict[tuple[str, str], int] = {}
    for sort, ((area, rm_no), rm_desc) in enumerate(plan.rooms.items()):
        row = db.execute(text("SELECT room_id FROM room WHERE area_id = :a AND rm_no = :n"),
                         {"a": area_ids[area], "n": rm_no}).first()
        if row is None:
            row = db.execute(text("INSERT INTO room(area_id, rm_no, rm_desc, sort_order) VALUES (:a, :n, :d, :s)"
                                  " RETURNING room_id"),
                             {"a": area_ids[area], "n": rm_no, "d": rm_desc, "s": sort}).first()
            res.rooms_created += 1
        room_ids[(area, rm_no)] = row[0]

    cutlist_ids: dict[int, int] = {}
    for no, created in plan.cutlists.items():
        row = db.execute(text("SELECT cutlist_id FROM cutlist WHERE cutlist_no = :n AND project_id = :p"),
                         {"n": no, "p": pid}).first()
        if row is None:
            row = db.execute(
                text("""INSERT INTO cutlist(project_id, cutlist_no, created_by, created_at)
                        VALUES (:p, :n, :u, COALESCE(CAST(:c AS timestamptz), now())) RETURNING cutlist_id"""),
                {"p": pid, "n": no, "u": actor_id, "c": created}).first()
            res.cutlists_created += 1
        cutlist_ids[no] = row[0]

    # ---- items ---------------------------------------------------------------------------------------
    for it in plan.items:
        if it.item_id_fm in existing:
            res.items_skipped_existing += 1
            continue
        area_id = area_ids.get(it.area) if it.area else None
        room_id = room_ids.get((it.area, it.rm_no)) if it.area and it.rm_no else None
        item_id = db.execute(
            text("""
                INSERT INTO items(
                    num, project_id, cutlist_id, area_id, room_id, description, qty, stage, level, rm_no, rm_desc,
                    jid_code, status, lister, assembler, floor_plan, rls, joiery_details, estimator_notes,
                    factory_id, tg_solid, legacy_item_ref, item_locked, created_at)
                VALUES (
                    :num, :p, :cl, :area, :room, :d, :q, :stage, :lvl, :rmno, :rmdesc,
                    :jid, :status, :lister, :asm, :fp, :rls, :jd, :notes,
                    :fac, :tg, :legacy, false, COALESCE(CAST(:cr AS timestamptz), now()))
                RETURNING item_id"""),
            {"num": it.item_id_fm, "p": pid, "cl": cutlist_ids.get(it.cutlist_no) if it.cutlist_no else None,
             "area": area_id, "room": room_id, "d": it.description, "q": it.qty, "stage": it.stage,
             "lvl": it.level, "rmno": it.rm_no, "rmdesc": it.rm_desc, "jid": it.jid_code, "status": it.status,
             "lister": it.lister, "asm": it.assembler, "fp": it.floor_plan, "rls": it.rls,
             "jd": it.joiery_details, "notes": it.notes, "fac": factory_ids.get(it.factory) if it.factory else None,
             "tg": it.tg_solid, "legacy": it.legacy_ref, "cr": it.created},
        ).scalar()
        res.items_created += 1
        for stage_key, (target, d) in it.stages.items():
            db.execute(text(f"INSERT INTO item_stages(item_id, stage_key, {target}) VALUES (:i, :s, :d)"),
                       {"i": item_id, "s": stage_key, "d": d})
            res.stage_rows += 1
        if it.status_note:
            db.execute(text("INSERT INTO item_status_log(item_id, status, note, changed_by)"
                            " VALUES (:i, :s, :n, :by)"),
                       {"i": item_id, "s": it.status, "n": it.status_note, "by": f"import ({actor_email})"})
            res.status_notes += 1

    # ---- the shared number sequence ----------------------------------------------------------------------
    if advance_sequence:
        res.sequence_to = db.execute(text("""
            SELECT setval('joinery_number_seq', GREATEST(
                (SELECT last_value FROM joinery_number_seq),
                COALESCE((SELECT MAX(num) FROM items), 0),
                COALESCE((SELECT MAX(cutlist_no) FROM cutlist), 0)))""")).scalar()

    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="import.tracking_grid",
                target=project_code, payload={
                    "source_sha256": source_sha256, "project_id": pid, "project_created": res.project_created,
                    "items_created": res.items_created, "items_skipped_existing": res.items_skipped_existing,
                    "cutlists_created": res.cutlists_created, "areas_created": res.areas_created,
                    "rooms_created": res.rooms_created, "factories_created": res.factories_created,
                    "stage_rows": res.stage_rows, "anomalies": len(plan.anomalies)})
    db.flush()
    return res


def report(plan: Plan, res: Result | None, *, committed: bool) -> str:
    out: list[str] = []
    out.append(f"Tracking grid import: {len(plan.items)} items for PID {plan.pid}"
               f" ({'COMMITTED' if committed else 'DRY RUN, nothing was written'})")
    out.append(f"  areas: {len(plan.areas)} ({', '.join(plan.areas)})   rooms: {len(plan.rooms)}"
               f"   cutlists: {len(plan.cutlists)}   factories: {', '.join(plan.factories) or '-'}")
    out.append(f"  Tg Solid tagged: {sum(1 for i in plan.items if i.tg_solid)}"
               f"   with a status note: {sum(1 for i in plan.items if i.status_note)}"
               f"   Date_Optimized skipped: {plan.skipped_optimized}")
    stage_counts = Counter(k for i in plan.items for k in i.stages)
    out.append("  stage dates: " + ", ".join(f"{k} {n}" for k, n in sorted(stage_counts.items())))
    if res is not None:
        out.append(f"  would create (or created): project {'new' if res.project_created else 'existing'},"
                   f" {res.factories_created} factories, {res.areas_created} areas, {res.rooms_created} rooms,"
                   f" {res.cutlists_created} cutlists, {res.items_created} items, {res.stage_rows} stage rows,"
                   f" {res.status_notes} status notes; {res.items_skipped_existing} items already existed")
        if res.sequence_to is not None:
            out.append(f"  joinery_number_seq moved to {res.sequence_to}")
    by_kind = Counter(k for k, _ in plan.anomalies)
    out.append(f"  anomalies: {sum(by_kind.values())} ({', '.join(f'{k} {n}' for k, n in sorted(by_kind.items())) or 'none'})")
    for kind in sorted(by_kind):
        for k, detail in [a for a in plan.anomalies if a[0] == kind][:5]:
            out.append(f"    [{k}] {detail}")
        if by_kind[kind] > 5:
            out.append(f"    [{kind}] ... and {by_kind[kind] - 5} more")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file")
    ap.add_argument("--workspace-slug", required=True)
    ap.add_argument("--actor-email", required=True, help="the user the import is recorded under (and the PM)")
    ap.add_argument("--project-code", required=True)
    ap.add_argument("--project-name", required=True)
    ap.add_argument("--pid", type=int, help="FileMaker PID, when the sheet holds more than one project")
    ap.add_argument("--commit", action="store_true", help="keep the result (default: a dry run, rolled back)")
    args = ap.parse_args(argv)

    from ..db import SessionLocal           # imported late so `--help` works without DATABASE_URL

    data = Path(args.file).read_bytes()
    plan = build_plan(read_rows(args.file), pid=args.pid)
    db = SessionLocal()
    try:
        ws = db.execute(text("SELECT id FROM workspace WHERE slug = :s"), {"s": args.workspace_slug}).scalar()
        actor = db.execute(text("SELECT id FROM app_user WHERE email = :e AND workspace_id = :w"),
                           {"e": args.actor_email, "w": ws}).scalar() if ws else None
        if ws is None or actor is None:
            print("unknown workspace or actor", file=sys.stderr)
            return 2
        res = apply(db, plan, workspace_id=ws, actor_id=actor, project_code=args.project_code,
                    project_name=args.project_name, source_sha256=hashlib.sha256(data).hexdigest(),
                    advance_sequence=args.commit)
        if args.commit:
            db.commit()
        else:
            db.rollback()
        print(report(plan, res, committed=args.commit))
        return 0
    except ImportErrorReport as e:
        db.rollback()
        print(f"cannot import: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
