"""Idempotent dev seed for the Hartwood Joinery workspace.

Run inside the api container:

    docker compose exec api python -m seed.hartwood_joinery

Inserts (or upserts) one workspace `hartwood-joinery` and 8 staff users with
the dev password `hartwood-dev`. Mina Klee is the procurement officer
(auth_role=purchase_officer).

Also seeds:
- Reference tables: stages (10 rows), status_options (6 rows)
- Material catalog: 2 board_materials + 4 hardware_materials
- 2 projects + 5 items each + 1 module + 3 parts per item
- project_hardware_catalog (4 rows per project)
- item_hardware_lines (2 per item)
- item_stages (5 per item: REQ, SM, LISTED, DOWN, CNC)
"""
from datetime import date, timedelta

from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal

DEV_PASSWORD = "hartwood-dev"

USERS: list[tuple[str, str, str, str]] = [
    ("aria.voss@hartwood.test", "Aria Voss", "admin", "CEO"),
    ("rin.park@hartwood.test", "Rin Park", "manager", "PM"),
    ("theo.blake@hartwood.test", "Theo Blake", "manager", "PM"),
    ("noa.lindqvist@hartwood.test", "Noa Lindqvist", "drafter", "Drafter"),
    ("juno.okafor@hartwood.test", "Juno Okafor", "editor", "Foreman"),
    ("kai.matthews@hartwood.test", "Kai Matthews", "editor", "Machine"),
    ("mina.klee@hartwood.test", "Mina Klee", "purchase_officer", "Procurement"),
    ("sam.ito@hartwood.test", "Sam Ito", "viewer", "Observer"),
    # Estimator (#9a). New auth_role 'estimator' allowed by migration 0021.
    ("kai.ngata@hartwood.test", "Kai Ngata", "estimator", "Estimator"),
    # Shop-floor workers (#8). Promoted to is_shop_worker=true after insert.
    ("sam.lee@hartwood.test", "Sam Lee", "editor", "Joiner"),
    ("priya.dhar@hartwood.test", "Priya Dhar", "editor", "CNC operator"),
    ("marko.vil@hartwood.test", "Marko Villas", "editor", "Edge bander"),
    ("kira.osei@hartwood.test", "Kira Osei", "editor", "All-rounder"),
]

SHOP_WORKER_EMAILS: tuple[str, ...] = (
    "sam.lee@hartwood.test",
    "priya.dhar@hartwood.test",
    "marko.vil@hartwood.test",
    "kira.osei@hartwood.test",
)

# (stage_key, label, sort_order)
STAGES: list[tuple[str, str, int]] = [
    ("REQ",     "Requested",      10),
    ("SM",      "Site Measure",   20),
    ("LISTED",  "Cutlist Drawn",  30),
    ("DOWN",    "Marked Down",    40),
    ("CNC",     "CNC Cut",        50),
    ("EDGED",   "Edge Banded",    60),
    ("PAINTED", "Painted",        70),
    ("MADE",    "Assembled",      80),
    ("DEL",     "Delivered",      90),
    ("INST",    "Installed",      100),
]

# (status_key, sort_order)
STATUS_OPTIONS: list[tuple[str, int]] = [
    ("CLEAR",    10),
    ("VOID",     20),
    ("NOTE!",    30),
    ("LIVE",     40),
    ("APPROVED", 50),
    ("HOLD",     60),
]

# Board materials: (sku, code, description, cost_per_sheet)
BOARD_MATERIALS: list[tuple[str, str, str, float]] = [
    ("BM-001", "BM-001", "18mm White MDF",  45.00),
    ("BM-002", "BM-002", "18mm Birch Ply",  78.00),
]

# Hardware materials: (sku, description, hardware_type, cost_per_unit)
HARDWARE_MATERIALS: list[tuple[str, str, str, float]] = [
    ("HM-001", "Hettich Quadro Drawer Slide 500mm", "SLIDE",  35.00),
    ("HM-002", "Blum Hinge 110deg",                  "HINGE",   8.50),
    ("HM-003", "200mm Brass Pull Handle",             "HANDLE", 22.00),
    ("HM-004", "Soft Close Damper",                   "DAMPER",  4.50),
]

# (project_code, name, pm_email, install_start, project_status)
PROJECTS: list[tuple[str, str, str, str, str]] = [
    ("ALF-001", "Alfred Street Renovation", "rin.park@hartwood.test",   "2026-06-15", "Current"),
    ("TRT-014", "Trentham Heights",          "theo.blake@hartwood.test", "2026-08-01", "Current"),
]

# (code, description, level, rm_no, rm_desc, stage_site, zone, qty, status, item_locked)
# num values 290001..290010 — globally unique across both projects
ITEMS_PER_PROJECT: list[tuple[str, str, str, str, str, str, str, int, str, bool]] = [
    ("K-101", "Kitchen island carcass",  "L1", "K1", "Kitchen",  "Stage 1", "1", 1, "LIVE",  False),
    ("K-102", "Pantry tower",            "L1", "K1", "Kitchen",  "Stage 1", "1", 1, "LIVE",  False),
    ("K-103", "Overhead cabinet run",    "L1", "K1", "Kitchen",  "Stage 2", "1", 1, "CLEAR", True),
    ("B-201", "Master ensuite vanity",   "L2", "B1", "Bathroom", "Stage 1", "1", 1, "HOLD",  True),
    ("L-301", "Living TV joinery",       "L1", "L1", "Living",   "Stage 1", "1", 1, "LIVE",  False),
]

# Parts per module: (part_name, len_mm, wid_mm, bm_index)
# bm_index is 0-based index into BOARD_MATERIALS list (resolved to real material_id later)
PARTS_TEMPLATE: list[tuple[str, int, int, int]] = [
    ("Side Panel",  720, 560, 0),
    ("Shelf",       460, 540, 0),
    ("Back Panel",  700, 450, 1),
]

# Lifecycle stage progress pattern
# (stage_key, due_offset_days, done_offset_days_or_None)
# offsets are relative to today; negative = in the past
LIFECYCLE_PROGRESS: list[tuple[str, int, int | None]] = [
    ("REQ",    -30, -25),
    ("SM",     -20, -18),
    ("LISTED", -10, None),   # intentionally not done — drives overdue metric
    ("DOWN",     0, None),
    ("CNC",      5, None),
]


def main() -> None:
    db = SessionLocal()
    today = date.today()
    try:
        # ------------------------------------------------------------------
        # 1. Workspace
        # ------------------------------------------------------------------
        wid = db.execute(
            text(
                """
                INSERT INTO workspace(slug, name)
                VALUES ('hartwood-joinery', 'Hartwood Joinery')
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """
            )
        ).scalar()

        # ------------------------------------------------------------------
        # 2. Users
        # ------------------------------------------------------------------
        pw = hash_password(DEV_PASSWORD)
        for email, name, role, jtbd in USERS:
            db.execute(
                text(
                    """
                    INSERT INTO app_user(workspace_id, email, full_name,
                                         password_hash, auth_role, jtbd_role)
                    VALUES (:w, :e, :n, :p, :r, :j)
                    ON CONFLICT (workspace_id, email) DO NOTHING
                    """
                ),
                {"w": wid, "e": email, "n": name, "p": pw, "r": role, "j": jtbd},
            )
        db.execute(
            text(
                """
                UPDATE app_user SET auth_role='drafter'
                WHERE workspace_id=:w AND email='noa.lindqvist@hartwood.test'
                """
            ),
            {"w": wid},
        )

        # ------------------------------------------------------------------
        # 3. Reference tables: stages + status_options
        # ------------------------------------------------------------------
        for stage_key, label, sort_order in STAGES:
            db.execute(
                text(
                    """
                    INSERT INTO stages (stage_key, label, sort_order)
                    VALUES (:k, :l, :s)
                    ON CONFLICT (stage_key) DO NOTHING
                    """
                ),
                {"k": stage_key, "l": label, "s": sort_order},
            )

        for status_key, sort_order in STATUS_OPTIONS:
            db.execute(
                text(
                    """
                    INSERT INTO status_options (status_key, sort_order)
                    VALUES (:k, :s)
                    ON CONFLICT (status_key) DO NOTHING
                    """
                ),
                {"k": status_key, "s": sort_order},
            )

        # ------------------------------------------------------------------
        # 4. Material catalog source rows
        # ------------------------------------------------------------------
        board_material_ids: list[int] = []
        for sku, code, description, cost_per_sheet in BOARD_MATERIALS:
            mid = db.execute(
                text(
                    """
                    INSERT INTO board_materials
                        (workspace_id, sku, code, description, cost_per_sheet, unit_cost)
                    VALUES (:w, :sku, :code, :desc, :cost, :unit_cost)
                    ON CONFLICT (workspace_id, sku) DO NOTHING
                    RETURNING material_id
                    """
                ),
                {
                    "w": wid,
                    "sku": sku,
                    "code": code,
                    "desc": description,
                    "cost": cost_per_sheet,
                    "unit_cost": cost_per_sheet,
                },
            ).scalar()
            if mid is None:
                # Row already existed — fetch existing id
                mid = db.execute(
                    text(
                        "SELECT material_id FROM board_materials WHERE workspace_id=:w AND sku=:sku"
                    ),
                    {"w": wid, "sku": sku},
                ).scalar()
            board_material_ids.append(mid)

        hardware_material_ids: list[int] = []
        for sku, description, hardware_type, cost_per_unit in HARDWARE_MATERIALS:
            # hardware_materials.sku is globally unique (not workspace-scoped)
            # prefix with workspace slug to avoid collisions in multi-workspace setups
            ws_sku = f"hartwood-{sku}"
            mid = db.execute(
                text(
                    """
                    INSERT INTO hardware_materials
                        (workspace_id, sku, description, hardware_type, cost_per_unit, unit_cost)
                    VALUES (:w, :sku, :desc, :htype, :cost, :unit_cost)
                    ON CONFLICT (sku) DO NOTHING
                    RETURNING material_id
                    """
                ),
                {
                    "w": wid,
                    "sku": ws_sku,
                    "desc": description,
                    "htype": hardware_type,
                    "cost": cost_per_unit,
                    "unit_cost": cost_per_unit,
                },
            ).scalar()
            if mid is None:
                mid = db.execute(
                    text(
                        "SELECT material_id FROM hardware_materials WHERE sku=:sku"
                    ),
                    {"sku": ws_sku},
                ).scalar()
            hardware_material_ids.append(mid)

        # ------------------------------------------------------------------
        # 5. Resolve user ids needed for FK columns
        # ------------------------------------------------------------------
        def get_user_id(email: str) -> int:
            uid = db.execute(
                text("SELECT id FROM app_user WHERE email=:e"),
                {"e": email},
            ).scalar()
            if uid is None:
                raise RuntimeError(f"User not found: {email}")
            return uid

        noa_id = get_user_id("noa.lindqvist@hartwood.test")
        mina_id = get_user_id("mina.klee@hartwood.test")

        # ------------------------------------------------------------------
        # 6. Projects + items + modules + parts + item_stages + hardware
        # ------------------------------------------------------------------
        global_item_num_base = 290001  # 290001..290010 across 10 items

        for proj_idx, (proj_code, proj_name, pm_email, install_start, proj_status) in enumerate(PROJECTS):
            pm_id = get_user_id(pm_email)

            # --- INSERT project (ON CONFLICT on project_code) ---
            # Use CTE-with-fallback pattern to always get project_id
            proj_id = db.execute(
                text(
                    """
                    WITH ins AS (
                        INSERT INTO projects (project_code, name, pm_id, installation_start, status, workspace_id)
                        VALUES (:code, :name, :pm, :install, :status, :wid)
                        ON CONFLICT (name) DO NOTHING
                        RETURNING project_id
                    )
                    SELECT project_id FROM ins
                    UNION ALL
                    SELECT project_id FROM projects WHERE name = :name
                    LIMIT 1
                    """
                ),
                {
                    "code": proj_code,
                    "name": proj_name,
                    "pm": pm_id,
                    "install": install_start,
                    "status": proj_status,
                    "wid": wid,
                },
            ).scalar()

            # --- project_hardware_catalog: 4 rows (one per hardware material) ---
            catalog_ids: list[int] = []
            for hw_mid in hardware_material_ids:
                cat_id = db.execute(
                    text(
                        """
                        WITH ins AS (
                            INSERT INTO project_hardware_catalog
                                (project_id, material_type, material_id, added_by)
                            VALUES (:pid, 'HARDWARE', :mid, :by)
                            ON CONFLICT (project_id, material_type, material_id) DO NOTHING
                            RETURNING catalog_id
                        )
                        SELECT catalog_id FROM ins
                        UNION ALL
                        SELECT catalog_id FROM project_hardware_catalog
                        WHERE project_id=:pid AND material_type='HARDWARE' AND material_id=:mid
                        LIMIT 1
                        """
                    ),
                    {"pid": proj_id, "mid": hw_mid, "by": mina_id},
                ).scalar()
                catalog_ids.append(cat_id)

            # --- Items ---
            for item_idx, (code, description, level, rm_no, rm_desc, stage_site, zone, qty, status, item_locked) in enumerate(ITEMS_PER_PROJECT):
                item_num = global_item_num_base + proj_idx * 5 + item_idx

                item_id = db.execute(
                    text(
                        """
                        WITH ins AS (
                            INSERT INTO items
                                (num, project_id, code, description, level,
                                 rm_no, rm_desc, stage, zone, qty, status,
                                 cutlist_owner_id, item_locked)
                            VALUES (:num, :pid, :code, :desc, :level,
                                    :rm_no, :rm_desc, :stage, :zone, :qty, :status,
                                    :owner, :locked)
                            ON CONFLICT (num) DO NOTHING
                            RETURNING item_id
                        )
                        SELECT item_id FROM ins
                        UNION ALL
                        SELECT item_id FROM items WHERE num=:num
                        LIMIT 1
                        """
                    ),
                    {
                        "num":    item_num,
                        "pid":    proj_id,
                        "code":   code,
                        "desc":   description,
                        "level":  level,
                        "rm_no":  rm_no,
                        "rm_desc": rm_desc,
                        "stage":  stage_site,
                        "zone":   zone,
                        "qty":    qty,
                        "status": status,
                        "owner":  noa_id,
                        "locked": item_locked,
                    },
                ).scalar()

                # --- Area + Room (Q454/Q455, migration 0026).  Same trap as
                #     the cutlist below: 0026 backfilled these from the items
                #     that existed when it ran, so items seeded afterwards get
                #     none and the C6 selectors would have nothing to offer.
                #     Area comes from the site location, Room from rm_no.
                db.execute(
                    text(
                        """
                        WITH ins AS (
                            INSERT INTO area (project_id, name)
                            VALUES (:pid, :area)
                            ON CONFLICT (project_id, name) DO NOTHING
                            RETURNING area_id
                        ), picked_area AS (
                            SELECT area_id FROM ins
                            UNION ALL
                            SELECT area_id FROM area
                             WHERE project_id = :pid AND name = :area
                            LIMIT 1
                        ), ins_room AS (
                            INSERT INTO room (area_id, rm_no, rm_desc)
                            SELECT area_id, :rm_no, :rm_desc FROM picked_area
                            ON CONFLICT (area_id, rm_no) DO NOTHING
                            RETURNING room_id, area_id
                        ), picked_room AS (
                            SELECT room_id FROM ins_room
                            UNION ALL
                            SELECT r.room_id FROM room r
                              JOIN picked_area pa ON pa.area_id = r.area_id
                             WHERE r.rm_no = :rm_no
                            LIMIT 1
                        )
                        UPDATE items
                           SET area_id = (SELECT area_id FROM picked_area),
                               room_id = (SELECT room_id FROM picked_room)
                         WHERE item_id = :iid
                        """
                    ),
                    {"pid": proj_id, "area": stage_site, "rm_no": rm_no,
                     "rm_desc": rm_desc, "iid": item_id},
                )

                # --- Cutlist (Q540: one per existing item, carrying its own
                #     number).  0027 minted these for items that existed when it
                #     ran; items created afterwards — like these — need their own,
                #     and worker_assignment.cutlist_id is NOT NULL since 0030.
                db.execute(
                    text(
                        """
                        WITH ins AS (
                            INSERT INTO cutlist (project_id, cutlist_no, name)
                            VALUES (:pid, :num, :name)
                            ON CONFLICT (cutlist_no) DO NOTHING
                            RETURNING cutlist_id
                        ), picked AS (
                            SELECT cutlist_id FROM ins
                            UNION ALL
                            SELECT cutlist_id FROM cutlist WHERE cutlist_no = :num
                            LIMIT 1
                        )
                        UPDATE items SET cutlist_id = (SELECT cutlist_id FROM picked)
                         WHERE item_id = :iid
                        """
                    ),
                    {"pid": proj_id, "num": item_num, "iid": item_id,
                     "name": description},
                )

                # --- Module (1 per item) ---
                mod_id = db.execute(
                    text(
                        """
                        WITH ins AS (
                            INSERT INTO modules (item_id, module_no, name)
                            VALUES (:iid, '1', :name)
                            ON CONFLICT (item_id, module_no) DO NOTHING
                            RETURNING module_id
                        )
                        SELECT module_id FROM ins
                        UNION ALL
                        SELECT module_id FROM modules WHERE item_id=:iid AND module_no='1'
                        LIMIT 1
                        """
                    ),
                    {"iid": item_id, "name": f"{description} – Module 1"},
                ).scalar()

                # --- Parts (3 per module) ---
                for seq_idx, (part_name, len_mm, wid_mm, bm_idx) in enumerate(PARTS_TEMPLATE):
                    bm_id = board_material_ids[bm_idx]
                    seq_num = seq_idx + 1
                    db.execute(
                        text(
                            """
                            INSERT INTO parts
                                (module_id, seq, qty, part_name, len_mm, wid_mm,
                                 board_material_id, paint_instruction)
                            VALUES (:mid, :seq, 1, :name, :len, :wid, :bm, 'NONE')
                            ON CONFLICT (module_id, seq) DO NOTHING
                            """
                        ),
                        {
                            "mid":  mod_id,
                            "seq":  seq_num,
                            "name": part_name,
                            "len":  len_mm,
                            "wid":  wid_mm,
                            "bm":   bm_id,
                        },
                    )

                # --- item_stages (5 per item) ---
                for stage_key, due_offset, done_offset in LIFECYCLE_PROGRESS:
                    due_date = today + timedelta(days=due_offset)
                    done_date = (today + timedelta(days=done_offset)) if done_offset is not None else None
                    db.execute(
                        text(
                            """
                            INSERT INTO item_stages (item_id, stage_key, due_date, done_date)
                            VALUES (:iid, :sk, :due, :done)
                            ON CONFLICT (item_id, stage_key) DO NOTHING
                            """
                        ),
                        {
                            "iid":  item_id,
                            "sk":   stage_key,
                            "due":  due_date,
                            "done": done_date,
                        },
                    )

                # --- item_hardware_lines (2 per item, using first 2 catalog entries) ---
                for hw_seq, cat_id in enumerate(catalog_ids[:2]):
                    seq_num = hw_seq + 1
                    db.execute(
                        text(
                            """
                            INSERT INTO item_hardware_lines
                                (item_id, seq, qty, catalog_id)
                            VALUES (:iid, :seq, 1, :cid)
                            ON CONFLICT (item_id, seq) DO NOTHING
                            """
                        ),
                        {
                            "iid": item_id,
                            "seq": seq_num,
                            "cid": cat_id,
                        },
                    )

        # --- procurement_v1 demo: 1 delivered + 1 in-transit batch + 1 allocation ---
        proj_alfred_id = db.execute(
            text("SELECT project_id FROM projects WHERE project_code = 'ALF-001'")
        ).scalar()

        catalog_first = db.execute(text(
            "SELECT phc.catalog_id, phc.material_type, phc.material_id "
            "  FROM project_hardware_catalog phc "
            " WHERE phc.project_id = :p ORDER BY phc.catalog_id LIMIT 1"
        ), {"p": proj_alfred_id}).mappings().first()

        if catalog_first:
            line_first = db.execute(text(
                "SELECT ihl.line_id, ihl.qty FROM item_hardware_lines ihl "
                "  JOIN items i ON i.item_id = ihl.item_id "
                " WHERE i.project_id = :p AND ihl.catalog_id = :c "
                " ORDER BY ihl.line_id LIMIT 1"
            ), {"p": proj_alfred_id, "c": catalog_first["catalog_id"]}).mappings().first()

            if line_first:
                delivered_id = db.execute(text(
                    "INSERT INTO procurement_batches "
                    "  (project_id, material_type, material_id, supplier, po_ref, "
                    "   qty_ordered, qty_received, ordered_date, received_date) "
                    "VALUES (:p, :mt, :mid, 'Acme Hardware', 'PO-ALF-001', "
                    "        :qty, :qty, CURRENT_DATE - 14, CURRENT_DATE - 1) "
                    "ON CONFLICT DO NOTHING "
                    "RETURNING batch_id"
                ), {
                    "p":   proj_alfred_id,
                    "mt":  catalog_first["material_type"],
                    "mid": catalog_first["material_id"],
                    "qty": int(line_first["qty"]) - 1 if int(line_first["qty"]) > 1 else int(line_first["qty"]),
                }).scalar()

                db.execute(text(
                    "INSERT INTO procurement_batches "
                    "  (project_id, material_type, material_id, supplier, po_ref, "
                    "   qty_ordered, ordered_date, eta_date) "
                    "VALUES (:p, :mt, :mid, 'Acme Hardware', 'PO-ALF-002', "
                    "        10, CURRENT_DATE - 2, CURRENT_DATE + 7) "
                    "ON CONFLICT DO NOTHING"
                ), {
                    "p":   proj_alfred_id,
                    "mt":  catalog_first["material_type"],
                    "mid": catalog_first["material_id"],
                })

                if delivered_id:
                    db.execute(text(
                        "INSERT INTO batch_allocations(batch_id, item_hardware_line_id, qty_allocated) "
                        "VALUES (:b, :l, 1) "
                        "ON CONFLICT (batch_id, item_hardware_line_id) DO NOTHING"
                    ), {"b": delivered_id, "l": line_first["line_id"]})

        # ── Shop Drawings demo (sub-project #5a) ─────────────────────────────
        from app.files.seed_helper import put_seed_file

        workspace_slug = "hartwood-joinery"
        s = db
        workspace_id = wid

        _kitchen_pdf = "/code/seed/hartwood_joinery/sample_drawings/kitchen-base-run.pdf"
        _bath_pdf = "/code/seed/hartwood_joinery/sample_drawings/bathroom-vanity.pdf"

        # Resolve seeded ALF-001 project + a drafter + manager from the workspace.
        _alf_pid = s.execute(
            text("SELECT project_id FROM projects WHERE project_code = 'ALF-001'")
        ).scalar()
        _drafter_id = s.execute(
            text(
                "SELECT id FROM app_user WHERE workspace_id = :w AND auth_role = 'drafter' "
                "ORDER BY id LIMIT 1"
            ),
            {"w": workspace_id},
        ).scalar()
        _manager_id = s.execute(
            text(
                "SELECT id FROM app_user WHERE workspace_id = :w AND auth_role = 'manager' "
                "ORDER BY id LIMIT 1"
            ),
            {"w": workspace_id},
        ).scalar()

        # ── Item Attachments demo (sub-project #5b) ───────────────────────────────────
        from app.files.seed_helper import put_seed_file as _put_attachment

        _blob_kit = _put_attachment(s, workspace_id=workspace_id, workspace_slug=workspace_slug,
                                    app_user_id=_drafter_id, path=_kitchen_pdf)
        _blob_bat = _put_attachment(s, workspace_id=workspace_id, workspace_slug=workspace_slug,
                                    app_user_id=_drafter_id, path=_bath_pdf)

        # Pick the first two ALF-001 items (in stable insertion order).
        _attach_items = s.execute(text("""
            SELECT item_id FROM items WHERE project_id = :p ORDER BY item_id LIMIT 2
        """), {"p": _alf_pid}).scalars().all()

        if len(_attach_items) >= 2:
            _full_item, _partial_item = _attach_items[0], _attach_items[1]

            # Item 1: all 3 slots populated (cv_drawing + floor_plan + site_measure)
            for kind in ("cv_drawing", "floor_plan", "site_measure"):
                s.execute(text("""
                    INSERT INTO item_attachment(item_id, kind, file_blob_id, uploaded_by)
                    VALUES (:i, :k, :b, :u)
                    ON CONFLICT (item_id, kind) DO UPDATE
                      SET file_blob_id = EXCLUDED.file_blob_id, uploaded_by = EXCLUDED.uploaded_by, uploaded_at = now()
                """), {"i": _full_item, "k": kind, "b": _blob_kit, "u": _drafter_id})

            # Item 2: only cv_drawing (Combined will render placeholder pages for the missing two)
            s.execute(text("""
                INSERT INTO item_attachment(item_id, kind, file_blob_id, uploaded_by)
                VALUES (:i, 'cv_drawing', :b, :u)
                ON CONFLICT (item_id, kind) DO UPDATE
                  SET file_blob_id = EXCLUDED.file_blob_id, uploaded_by = EXCLUDED.uploaded_by, uploaded_at = now()
            """), {"i": _partial_item, "b": _blob_bat, "u": _drafter_id})

            s.commit()
            print(f"seeded item attachments: full_item={_full_item} (3/3), partial_item={_partial_item} (1/3)")
        else:
            print("skipping item attachments seed: ALF-001 has fewer than 2 items")

        # Re-run safety: clear out any existing demo drawings on ALF-001 so
        # the script remains idempotent (revisions cascade via FK).
        s.execute(
            text("DELETE FROM shop_drawing WHERE project_id = :p"),
            {"p": _alf_pid},
        )

        _blob_kitchen = put_seed_file(
            s,
            workspace_id=workspace_id,
            workspace_slug=workspace_slug,
            app_user_id=_drafter_id,
            path=_kitchen_pdf,
        )
        _blob_bath = put_seed_file(
            s,
            workspace_id=workspace_id,
            workspace_slug=workspace_slug,
            app_user_id=_drafter_id,
            path=_bath_pdf,
        )

        def _make_drawing(*, title, room, archived=False, archived_by=None):
            did = s.execute(
                text(
                    """
                    INSERT INTO shop_drawing(project_id, title, room, created_by)
                    VALUES (:p, :t, :r, :u) RETURNING drawing_id
                    """
                ),
                {"p": _alf_pid, "t": title, "r": room, "u": _drafter_id},
            ).scalar()
            if archived:
                s.execute(
                    text(
                        "UPDATE shop_drawing SET archived_at = now(), archived_by = :u "
                        "WHERE drawing_id = :d"
                    ),
                    {"u": archived_by, "d": did},
                )
            return did

        def _add_rev(did, *, rev_no, blob_id, status, uploaded_by, reviewed_by=None, note=None):
            rid = s.execute(
                text(
                    """
                    INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status,
                                                      uploaded_by, reviewed_by, reviewed_at, review_note)
                    VALUES (:d, :n, :b, :s, :u, CAST(:rv AS bigint),
                            CASE WHEN CAST(:rv AS bigint) IS NULL THEN NULL ELSE now() END,
                            CAST(:note AS text))
                    RETURNING revision_id
                    """
                ),
                {
                    "d": did,
                    "n": rev_no,
                    "b": blob_id,
                    "s": status,
                    "u": uploaded_by,
                    "rv": reviewed_by,
                    "note": note,
                },
            ).scalar()
            return rid

        # D1: Kitchen base run — rev1 approved, rev2 approved (current), rev3 pending
        d1 = _make_drawing(title="Kitchen base run", room="Kitchen")
        _add_rev(d1, rev_no=1, blob_id=_blob_kitchen, status="approved",
                 uploaded_by=_drafter_id, reviewed_by=_manager_id)
        r1_2 = _add_rev(d1, rev_no=2, blob_id=_blob_kitchen, status="approved",
                        uploaded_by=_drafter_id, reviewed_by=_manager_id)
        s.execute(
            text("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
            {"r": r1_2, "d": d1},
        )
        _add_rev(d1, rev_no=3, blob_id=_blob_kitchen, status="pending",
                 uploaded_by=_drafter_id)

        # D2: Bathroom vanity — rev1 rejected (note), rev2 approved (current)
        d2 = _make_drawing(title="Bathroom vanity", room="Bathroom")
        _add_rev(d2, rev_no=1, blob_id=_blob_bath, status="rejected",
                 uploaded_by=_drafter_id, reviewed_by=_manager_id,
                 note="Need finished dimensions")
        r2_2 = _add_rev(d2, rev_no=2, blob_id=_blob_bath, status="approved",
                        uploaded_by=_drafter_id, reviewed_by=_manager_id)
        s.execute(
            text("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
            {"r": r2_2, "d": d2},
        )

        # D3: Kitchen island — single draft revision
        d3 = _make_drawing(title="Kitchen island", room="Kitchen")
        _add_rev(d3, rev_no=1, blob_id=_blob_kitchen, status="draft",
                 uploaded_by=_drafter_id)

        # D4: Walk-in robe — single pending revision
        d4 = _make_drawing(title="Walk-in robe", room="Bedroom")
        _add_rev(d4, rev_no=1, blob_id=_blob_bath, status="pending",
                 uploaded_by=_drafter_id)

        # D5: Pantry — approved + archived
        d5 = _make_drawing(title="Pantry", room="Kitchen", archived=True,
                           archived_by=_manager_id)
        r5_1 = _add_rev(d5, rev_no=1, blob_id=_blob_kitchen, status="approved",
                        uploaded_by=_drafter_id, reviewed_by=_manager_id)
        s.execute(
            text("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
            {"r": r5_1, "d": d5},
        )

        # D6: Hallway storage — single approved revision
        d6 = _make_drawing(title="Hallway storage", room="Hallway")
        r6_1 = _add_rev(d6, rev_no=1, blob_id=_blob_bath, status="approved",
                        uploaded_by=_drafter_id, reviewed_by=_manager_id)
        s.execute(
            text("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
            {"r": r6_1, "d": d6},
        )

        db.commit()
        print(f"seeded shop drawings: d1={d1}, d2={d2}, d3={d3}, d4={d4}, d5={d5}, d6={d6}")

        # ── iSample demo (sub-project #5c) ────────────────────────────────────
        from app.files.seed_helper import put_seed_file as _put_sample_photo

        _stone_png = "/code/seed/hartwood_joinery/sample_photos/stone-corian.png"

        # Resolve drafter + manager users (drafter creator, manager reviewer).
        _sample_drafter = s.execute(text("""
            SELECT id FROM app_user WHERE workspace_id = :w AND auth_role = 'drafter' ORDER BY id LIMIT 1
        """), {"w": workspace_id}).scalar()
        _sample_manager = s.execute(text("""
            SELECT id FROM app_user WHERE workspace_id = :w AND auth_role = 'manager' ORDER BY id LIMIT 1
        """), {"w": workspace_id}).scalar()

        # Idempotent insert helper
        def _seed_sample(*, title, room, hex_swatch, supplier, status, reviewer_id=None,
                         review_note=None, photo_blob_id=None, archived=False):
            existing = s.execute(text("""
                SELECT sample_id FROM sample WHERE project_id = :p AND title = :t LIMIT 1
            """), {"p": _alf_pid, "t": title}).scalar()
            if existing:
                return existing
            sid = s.execute(text("""
                INSERT INTO sample(project_id, title, room, hex_swatch, supplier, status,
                                   review_note, reviewed_by, reviewed_at,
                                   photo_file_blob_id, created_by)
                VALUES (:p, :t, :r, :h, :sup, :st,
                        :note, CAST(:rid AS bigint),
                        CASE WHEN CAST(:rid AS bigint) IS NULL THEN NULL ELSE now() END,
                        CAST(:ph AS bigint), :u)
                RETURNING sample_id
            """), {
                "p": _alf_pid, "t": title, "r": room, "h": hex_swatch, "sup": supplier,
                "st": status, "note": review_note, "rid": reviewer_id,
                "ph": photo_blob_id, "u": _sample_drafter,
            }).scalar()
            if archived:
                s.execute(text("UPDATE sample SET archived_at = now(), archived_by = :u WHERE sample_id = :s"),
                          {"u": _sample_manager, "s": sid})
            return sid

        # Stone Corian gets a photo
        _blob_stone = _put_sample_photo(s, workspace_id=workspace_id, workspace_slug=workspace_slug,
                                        app_user_id=_sample_drafter, path=_stone_png)

        _seed_sample(title="Oak veneer — Briggs 0412", room="L3 / Reception",
                     hex_swatch="#c29075", supplier="Briggs", status="approved",
                     reviewer_id=_sample_manager, review_note="Signed")
        _seed_sample(title="Walnut banding", room="L3 / Reception",
                     hex_swatch="#6b6256", supplier="Briggs", status="approved",
                     reviewer_id=_sample_manager)
        _seed_sample(title="Laminate — Polytec Oxide", room="L3 / Meeting Rm",
                     hex_swatch="#8a4434", supplier="Polytec", status="pending")
        _seed_sample(title="Stone — Corian Deep Black", room="L3 / Kitchen",
                     hex_swatch="#2d2b27", supplier="Corian", status="pending",
                     photo_blob_id=_blob_stone)
        _seed_sample(title="Timber edge 3mm walnut", room="L3 / Kitchen",
                     hex_swatch="#3c3028", supplier="Briggs", status="rejected",
                     reviewer_id=_sample_manager, review_note="Too dark for finish spec")
        _seed_sample(title="Acoustic panel grey", room="L3 / Workzone",
                     hex_swatch="#7a7366", supplier=None, status="approved",
                     reviewer_id=_sample_manager, archived=True)

        s.commit()
        print("seeded 6 iSample samples on ALF-001 (Board=4, Archive=2, 1 with photo)")

        # ── Catalog enrichment + CV mappings (sub-project #7a) ────────────────
        # Enrich existing 2 board_materials (BM-001, BM-002) with synonyms +
        # default supplier + lead time. Idempotent.
        s.execute(text("""
            UPDATE board_materials
               SET synonyms = ARRAY['BM-001','18-WHITE-MDF','18mm white mdf'],
                   default_supplier = 'Laminex Australia',
                   default_lead_time_days = 5
             WHERE workspace_id = :w AND code = 'BM-001'
        """), {"w": workspace_id})
        s.execute(text("""
            UPDATE board_materials
               SET synonyms = ARRAY['BM-002','18-BIRCH-PLY','18mm birch ply'],
                   default_supplier = 'Plyco',
                   default_lead_time_days = 10
             WHERE workspace_id = :w AND code = 'BM-002'
        """), {"w": workspace_id})

        # Enrich the 4 existing hardware_materials. SKUs are workspace-prefixed
        # by the seed (`hartwood-HM-001` etc.).
        for sku, syns, supp, lt in [
            ("hartwood-HM-001", ["HM-001","quadro-500","drawer-slide-500"], "Hettich Australia", 14),
            ("hartwood-HM-002", ["HM-002","blum-110","hinge-110"],          "Blum Australia",    14),
            ("hartwood-HM-003", ["HM-003","brass-pull-200","handle-200"],   "House of Brass",    21),
            ("hartwood-HM-004", ["HM-004","soft-close","damper"],           "Hettich Australia",  7),
        ]:
            s.execute(text("""
                UPDATE hardware_materials
                   SET synonyms = :syn,
                       default_supplier = :sup,
                       default_lead_time_days = :lt
                 WHERE workspace_id = :w AND sku = :sku
            """), {"w": workspace_id, "sku": sku, "syn": syns, "sup": supp, "lt": lt})

        # 4 new board_materials demo rows (codes globally unique → namespace BM-1xx).
        for code, sku, desc, syns, supp, lt in [
            ("BM-101", "MEL-19-WH",  "19mm Melamine White",  ["19-WH-MEL","Melamine 19 White"], "Laminex Australia",  5),
            ("BM-102", "MEL-16-BK",  "16mm Melamine Black",  ["16-BK","Black 16"],              "Laminex Australia",  5),
            ("BM-103", "VEN-19-WAL", "19mm Walnut Veneer",   ["19-WAL","Walnut Veneer"],        "Briggs Veneers",    21),
            ("BM-104", "PLY-12-BIR", "12mm Birch Plywood",   ["12-PLY-BIR","Birch 12"],         "Plyco",             10),
        ]:
            s.execute(text("""
                INSERT INTO board_materials
                  (workspace_id, code, sku, description,
                   synonyms, default_supplier, default_lead_time_days)
                VALUES (:w, :code, :sku, :desc, :syn, :sup, :lt)
                ON CONFLICT (workspace_id, sku) DO NOTHING
            """), {"w": workspace_id, "code": code, "sku": sku, "desc": desc,
                   "syn": syns, "sup": supp, "lt": lt})

        # Walnut veneer has visible directional grain → lock rotation so the
        # optimiser (#9) never flips it. Idempotent (INSERT above is DO NOTHING).
        s.execute(text("""
            UPDATE board_materials SET grain_locked = true
             WHERE workspace_id = :w AND code = 'BM-103'
        """), {"w": workspace_id})

        # Sheet stock on hand (#board_inventory / migration 0025) so the
        # optimiser can default its sheet size and show a shortfall without
        # anyone typing dimensions. BM-101 is deliberately stocked in two
        # sizes; BM-104 is deliberately at zero to exercise the out-of-stock
        # path. Idempotent via the (workspace, material, size) upsert.
        for code, len_mm, wid_mm, qty, loc in [
            ("BM-001", 2440, 1220, 24, "Rack A1"),
            ("BM-002", 2440, 1220,  9, "Rack A2"),
            ("BM-101", 2440, 1220, 15, "Rack B1"),
            ("BM-101", 3600, 1800,  4, "Rack B2"),   # oversize stock
            ("BM-103", 2440, 1220,  6, "Rack C1"),   # grain-locked walnut
            ("BM-104", 2440, 1220,  0, "Rack C2"),   # out of stock
        ]:
            s.execute(text("""
                INSERT INTO board_inventory
                    (workspace_id, material_id, len_mm, wid_mm, qty_on_hand,
                     location, created_by)
                SELECT :w, bm.material_id, :len, :wid, :qty, :loc, :cb
                  FROM board_materials bm
                 WHERE bm.workspace_id = :w AND bm.code = :code
                ON CONFLICT (workspace_id, material_id, len_mm, wid_mm)
                DO UPDATE SET qty_on_hand = EXCLUDED.qty_on_hand,
                              location    = EXCLUDED.location,
                              updated_at  = now()
            """), {"w": workspace_id, "code": code, "len": len_mm,
                   "wid": wid_mm, "qty": qty, "loc": loc, "cb": _drafter_id})
        print("seeded board_inventory: 6 stock rows across 5 boards")

        # 2 cv_material_mapping demo rows (drafter creator).
        _drafter_id = s.execute(text(
            "SELECT id FROM app_user WHERE workspace_id = :w AND auth_role = 'drafter' LIMIT 1"
        ), {"w": workspace_id}).scalar()
        _bm_001_mid = s.execute(text(
            "SELECT material_id FROM board_materials WHERE workspace_id = :w AND code = 'BM-001'"
        ), {"w": workspace_id}).scalar()
        _hm_002_mid = s.execute(text(
            "SELECT material_id FROM hardware_materials WHERE workspace_id = :w AND sku = 'hartwood-HM-002'"
        ), {"w": workspace_id}).scalar()
        s.execute(text("""
            INSERT INTO cv_material_mapping
              (workspace_id, cv_code, target_material_table, target_material_id, created_by)
            VALUES (:w, '18-PB', 'board_materials', :tid, :u)
            ON CONFLICT (workspace_id, cv_code) DO NOTHING
        """), {"w": workspace_id, "tid": _bm_001_mid, "u": _drafter_id})
        s.execute(text("""
            INSERT INTO cv_material_mapping
              (workspace_id, cv_code, target_material_table, target_material_id, created_by)
            VALUES (:w, '700.0KC2.054.00', 'hardware_materials', :tid, :u)
            ON CONFLICT (workspace_id, cv_code) DO NOTHING
        """), {"w": workspace_id, "tid": _hm_002_mid, "u": _drafter_id})

        s.commit()
        print("seeded #7a catalog enrichment: 6 board (2 enriched + 4 new) · 4 hardware enriched · 2 cv mappings")

        # === CV Import demo (#7b) =========================================
        # 1 committed cv_import_run on the first ALF-001 item.
        # Idempotent: delete then re-insert.
        _alf_pid = s.execute(
            text("SELECT project_id FROM projects WHERE project_code = 'ALF-001'")
        ).scalar()
        if _alf_pid is not None:
            _alf_iid = s.execute(text(
                "SELECT item_id FROM items WHERE project_id = :p ORDER BY item_id LIMIT 1"
            ), {"p": _alf_pid}).scalar()
            if _alf_iid is not None:
                s.execute(
                    text("DELETE FROM cv_import_run WHERE item_id = :iid"),
                    {"iid": _alf_iid},
                )
                s.execute(text("""
                    INSERT INTO cv_import_run(
                        project_id, item_id, source_filename, sha256,
                        row_count, status, started_at, completed_at,
                        error_log, created_by
                    )
                    VALUES (
                        :pid, :iid, 'demo-cv-import.csv', :sha,
                        9, 'committed',
                        now() - interval '1 day',
                        now() - interval '1 day' + interval '5 second',
                        '[]'::jsonb, :uid
                    )
                """), {
                    "pid": _alf_pid,
                    "iid": _alf_iid,
                    "sha": "a" * 64,
                    "uid": _drafter_id,
                })
                s.commit()
                print("seeded #7b cv_import_run: 1 committed run on ALF-001 item 1")

        # === Cut Floor demo (#7c) =========================================
        # 1 cut_plan with 1 sheet + 8 part_slots on ALF-001, plus 2
        # cut_schedule rows (one running today, one planned tomorrow).
        # Idempotent: wipe ALF-001 cut_plan rows before inserting.
        _alf_pid_7c = s.execute(
            text("SELECT project_id FROM projects WHERE project_code = 'ALF-001'")
        ).scalar()
        if _alf_pid_7c is not None:
            s.execute(
                text("DELETE FROM cut_plan WHERE project_id = :p"),
                {"p": _alf_pid_7c},
            )
            _plan_id = s.execute(text("""
                INSERT INTO cut_plan(workspace_id, project_id, name, notes,
                                     created_by)
                VALUES (:w, :p, 'ALF-001 v1 nest',
                        'Auto-seeded demo plan', :u)
                RETURNING id
            """), {"w": workspace_id, "p": _alf_pid_7c,
                   "u": _drafter_id}).scalar()
            _sheet_id = s.execute(text("""
                INSERT INTO cut_sheet(cut_plan_id, sheet_no, material_sku)
                VALUES (:cp, 1, '18-PB')
                RETURNING id
            """), {"cp": _plan_id}).scalar()

            # Pull up to 6 parts from ALF-001 item 1 (the CV-imported parts)
            # plus any other parts to highlight foreign-slot rendering.
            _alf_iid_7c = s.execute(text(
                "SELECT item_id FROM items WHERE project_id = :p ORDER BY item_id LIMIT 1"
            ), {"p": _alf_pid_7c}).scalar()
            _own_parts: list[int] = []
            if _alf_iid_7c is not None:
                _own_parts = [
                    r[0] for r in s.execute(text("""
                        SELECT p.part_id
                        FROM parts p
                        JOIN modules m ON m.module_id = p.module_id
                        WHERE m.item_id = :iid
                        ORDER BY p.part_id
                        LIMIT 6
                    """), {"iid": _alf_iid_7c}).all()
                ]
            _foreign_parts = [
                r[0] for r in s.execute(text("""
                    SELECT p.part_id
                    FROM parts p
                    JOIN modules m ON m.module_id = p.module_id
                    JOIN items   i ON i.item_id   = m.item_id
                    WHERE i.project_id = :p
                      AND (:owniid IS NULL OR i.item_id <> :owniid)
                    ORDER BY p.part_id
                    LIMIT 2
                """), {"p": _alf_pid_7c, "owniid": _alf_iid_7c}).all()
            ]

            # Layout: 6 own slots in 2 rows + 2 foreign slots on right edge.
            _slot_rows: list[dict] = []
            _x = 0
            _y = 0
            for idx, pid in enumerate(_own_parts):
                _slot_rows.append({
                    "x": _x, "y": _y, "w": 720, "h": 580,
                    "label": f"P{idx + 1}",
                    "part_id": pid,
                })
                _x += 730
                if (idx + 1) % 3 == 0:
                    _x = 0
                    _y += 590
            _fx = 2200
            _fy = 0
            for idx, pid in enumerate(_foreign_parts):
                _slot_rows.append({
                    "x": _fx, "y": _fy, "w": 200, "h": 200,
                    "label": f"foreign-{idx + 1}",
                    "part_id": pid,
                })
                _fy += 220

            for row in _slot_rows:
                s.execute(text("""
                    INSERT INTO part_slot(cut_sheet_id, x, y, w, h, label, part_id)
                    VALUES (:cs, :x, :y, :w, :h, :lbl, :pid)
                """), {
                    "cs": _sheet_id,
                    "x": row["x"], "y": row["y"],
                    "w": row["w"], "h": row["h"],
                    "lbl": row["label"],
                    "pid": row["part_id"],
                })

            # 2 cut_schedule rows: one running today (priority 100),
            # one planned tomorrow (priority 100).
            s.execute(text("""
                INSERT INTO cut_schedule(
                    cut_plan_id, scheduled_for, status,
                    priority, assigned_to, created_by
                )
                VALUES (:cp, CURRENT_DATE, 'running', 100, :u, :u)
            """), {"cp": _plan_id, "u": _drafter_id})
            s.execute(text("""
                INSERT INTO cut_schedule(
                    cut_plan_id, scheduled_for, status,
                    priority, assigned_to, created_by
                )
                VALUES (:cp, CURRENT_DATE + INTERVAL '1 day',
                        'planned', 100, :u, :u)
            """), {"cp": _plan_id, "u": _drafter_id})

            s.commit()
            print(
                f"seeded #7c cut_floor: 1 cut_plan + 1 sheet + "
                f"{len(_slot_rows)} slots + 2 schedules on ALF-001"
            )

        # === Shop Floor Ops (#8) =========================================
        # Promote 4 demo workers + insert 6 demo assignments + 1 completion
        # on ALF-001. Idempotent: assignments scoped per (item, stage) so
        # the partial unique index protects re-seeds; explicit DELETE for
        # the completion log row + matching done assignment.
        s.execute(
            text(
                """
                UPDATE app_user SET is_shop_worker = true
                WHERE workspace_id = :w AND email = ANY(:emails)
                """
            ),
            {"w": workspace_id, "emails": list(SHOP_WORKER_EMAILS)},
        )

        _alf_pid_8 = s.execute(
            text("SELECT project_id FROM projects WHERE project_code = 'ALF-001'")
        ).scalar()
        if _alf_pid_8 is not None:
            _worker_ids = {
                row[0]: row[1]
                for row in s.execute(
                    text(
                        """
                        SELECT email, id FROM app_user
                        WHERE workspace_id = :w AND email = ANY(:emails)
                        """
                    ),
                    {"w": workspace_id, "emails": list(SHOP_WORKER_EMAILS)},
                ).all()
            }
            _alf_items = [
                row[0]
                for row in s.execute(
                    text(
                        """
                        SELECT item_id FROM items
                        WHERE project_id = :p
                          AND row_type = 'joinery_item'
                          AND cutlist_id IS NOT NULL
                        ORDER BY item_id LIMIT 6
                        """
                    ),
                    {"p": _alf_pid_8},
                ).all()
            ]
            sam = _worker_ids.get("sam.lee@hartwood.test")
            priya = _worker_ids.get("priya.dhar@hartwood.test")
            marko = _worker_ids.get("marko.vil@hartwood.test")
            kira = _worker_ids.get("kira.osei@hartwood.test")
            foreman_id = s.execute(
                text(
                    """
                    SELECT id FROM app_user
                    WHERE workspace_id = :w AND email = 'juno.okafor@hartwood.test'
                    """
                ),
                {"w": workspace_id},
            ).scalar() or _drafter_id

            # Wipe shop-floor demo state for the ALF-001 items so re-runs
            # are idempotent.
            if _alf_items:
                s.execute(
                    text(
                        """
                        DELETE FROM stage_completion_log
                        WHERE cutlist_id IN (
                            SELECT cutlist_id FROM items
                            WHERE item_id = ANY(:items) AND cutlist_id IS NOT NULL
                        )
                        """
                    ),
                    {"items": _alf_items},
                )
                s.execute(
                    text(
                        """
                        DELETE FROM worker_assignment
                        WHERE cutlist_id IN (
                            SELECT cutlist_id FROM items
                            WHERE item_id = ANY(:items) AND cutlist_id IS NOT NULL
                        )
                        """
                    ),
                    {"items": _alf_items},
                )

            _assignments: list[tuple[int, str, int | None, str]] = []
            if len(_alf_items) >= 1 and sam is not None:
                _assignments.append((_alf_items[0], "DOWN", sam, "in_progress"))
            if len(_alf_items) >= 2 and sam is not None:
                _assignments.append((_alf_items[1], "DOWN", sam, "assigned"))
            if len(_alf_items) >= 3 and priya is not None:
                _assignments.append((_alf_items[2], "DOWN", priya, "done"))
            if len(_alf_items) >= 4 and priya is not None:
                _assignments.append((_alf_items[3], "CNC", priya, "assigned"))
            if len(_alf_items) >= 5 and marko is not None:
                _assignments.append((_alf_items[4], "DOWN", marko, "assigned"))
            if len(_alf_items) >= 6 and kira is not None:
                _assignments.append((_alf_items[5], "EDGED", kira, "assigned"))

            for iid, stage, wkr, status in _assignments:
                if wkr is None:
                    continue
                if status == "done":
                    aid = s.execute(
                        text(
                            """
                            INSERT INTO worker_assignment(
                                cutlist_id, stage_key, worker_id, status,
                                assigned_by, started_at, ended_at
                            )
                            VALUES ((SELECT cutlist_id FROM items WHERE item_id = :i),
                                    :s, :w, 'done', :a,
                                    now() - interval '1 day',
                                    now() - interval '1 day' + interval '2 hours')
                            RETURNING assignment_id
                            """
                        ),
                        {"i": iid, "s": stage, "w": wkr, "a": foreman_id},
                    ).scalar()
                    s.execute(
                        text(
                            """
                            INSERT INTO stage_completion_log(
                                cutlist_id, stage_key, assignment_id, worker_id,
                                completed_at, note
                            )
                            VALUES ((SELECT cutlist_id FROM items WHERE item_id = :i),
                                    :s, :a, :w,
                                    now() - interval '1 day' + interval '2 hours',
                                    'auto-seeded done')
                            """
                        ),
                        {"i": iid, "s": stage, "a": aid, "w": wkr},
                    )
                    # Mark the matching item_stages.done_date so PM
                    # dashboards reflect the completion.
                    s.execute(
                        text(
                            """
                            INSERT INTO item_stages(item_id, stage_key, done_date)
                            VALUES (:i, :s, CURRENT_DATE - 1)
                            ON CONFLICT (item_id, stage_key)
                            DO UPDATE SET done_date = CURRENT_DATE - 1
                            """
                        ),
                        {"i": iid, "s": stage},
                    )
                else:
                    started = (
                        "now() - interval '30 minutes'"
                        if status == "in_progress"
                        else "NULL"
                    )
                    s.execute(
                        text(
                            f"""
                            INSERT INTO worker_assignment(
                                cutlist_id, stage_key, worker_id, status,
                                assigned_by, started_at
                            )
                            VALUES ((SELECT cutlist_id FROM items WHERE item_id = :i),
                                    :s, :w, :st, :a, {started})
                            """
                        ),
                        {"i": iid, "s": stage, "w": wkr,
                         "st": status, "a": foreman_id},
                    )

            s.commit()
            print(
                f"seeded #8 shop_floor: 4 workers promoted + "
                f"{len(_assignments)} assignments on ALF-001"
            )

        # === Estimating Core (#9a) =======================================
        # workspace_labour_rate (10 stages) + 2 customers + 3 demo estimates
        # (one draft, one sent, one accepted-and-ready-to-convert).
        # Idempotent: wipes EST-2026-* for this workspace before reinserting.
        _labour_rates = [
            ("REQ", 0.00), ("SM", 0.00), ("LISTED", 0.00),
            ("DOWN", 85.00), ("CNC", 95.00), ("EDGED", 80.00),
            ("PAINTED", 90.00), ("MADE", 95.00),
            ("DEL", 70.00), ("INST", 110.00),
        ]
        for sk, rate in _labour_rates:
            s.execute(
                text(
                    """
                    INSERT INTO workspace_labour_rate
                        (workspace_id, stage_key, hourly_rate, updated_by)
                    VALUES (:w, :s, :r, :a)
                    ON CONFLICT (workspace_id, stage_key) DO UPDATE
                      SET hourly_rate = EXCLUDED.hourly_rate,
                          updated_at = now()
                    """
                ),
                {"w": workspace_id, "s": sk, "r": rate, "a": _drafter_id},
            )

        _estimator_id = s.execute(
            text(
                """
                SELECT id FROM app_user
                WHERE workspace_id = :w AND email = 'kai.ngata@hartwood.test'
                """
            ),
            {"w": workspace_id},
        ).scalar() or _drafter_id

        # Customers — case-insensitive UNIQUE name so we use ON CONFLICT.
        _customers = [
            ("ACME Property Group", "ops@acme.test", "0400 100 100",
             "12 Industrial Way, Sydney NSW 2000", "12 345 678 901"),
            ("Bayside Joinery Clients", "hello@bayside.test", "0400 200 200",
             "88 Foreshore Rd, Brighton VIC 3186", None),
        ]
        _customer_id_by_name: dict[str, int] = {}
        for cname, cemail, cphone, caddr, abn in _customers:
            cid = s.execute(
                text(
                    """
                    INSERT INTO customer
                        (workspace_id, name, email, phone,
                         billing_address, abn, created_by)
                    VALUES (:w, :n, :e, :p, :a, :abn, :cb)
                    ON CONFLICT (workspace_id, name) DO UPDATE
                      SET email = EXCLUDED.email,
                          phone = EXCLUDED.phone,
                          billing_address = EXCLUDED.billing_address,
                          abn = EXCLUDED.abn,
                          updated_at = now()
                    RETURNING customer_id
                    """
                ),
                {"w": workspace_id, "n": cname, "e": cemail,
                 "p": cphone, "a": caddr, "abn": abn, "cb": _estimator_id},
            ).scalar()
            _customer_id_by_name[cname] = int(cid)

        # Idempotency: wipe any prior EST-2026-* estimates for this workspace.
        s.execute(
            text(
                """
                DELETE FROM estimate
                WHERE workspace_id = :w AND estimate_no LIKE 'EST-2026-%'
                """
            ),
            {"w": workspace_id},
        )

        _bm_001 = s.execute(
            text(
                """
                SELECT material_id, cost_per_sheet, description, sku, default_supplier
                  FROM board_materials
                 WHERE workspace_id = :w
                   AND (sku = 'BM-001' OR code = 'BM-001')
                 ORDER BY material_id LIMIT 1
                """
            ),
            {"w": workspace_id},
        ).mappings().first()
        _hm_001 = s.execute(
            text(
                """
                SELECT material_id, cost_per_unit, description, sku, default_supplier
                  FROM hardware_materials
                 WHERE workspace_id = :w
                   AND (sku = 'HM-001' OR sku LIKE '%HM-001')
                 ORDER BY material_id LIMIT 1
                """
            ),
            {"w": workspace_id},
        ).mappings().first()

        def _insert_estimate(
            *, est_no: str, customer_name: str, title: str,
            site_address: str | None,
            status: str, markup_pct: float,
            line_specs: list[dict],
        ) -> int:
            cid = _customer_id_by_name[customer_name]
            eid = s.execute(
                text(
                    """
                    INSERT INTO estimate
                        (workspace_id, customer_id, estimate_no, title,
                         site_address, created_by)
                    VALUES (:w, :c, :no, :t, :sa, :cb)
                    RETURNING estimate_id
                    """
                ),
                {"w": workspace_id, "c": cid, "no": est_no,
                 "t": title, "sa": site_address, "cb": _estimator_id},
            ).scalar()
            rid = s.execute(
                text(
                    """
                    INSERT INTO estimate_revision
                        (estimate_id, rev_no, status, markup_pct, gst_pct,
                         terms_text, created_by)
                    VALUES (:e, 1, :st, :mu, 10.00,
                            'Payment terms 30 days from invoice. Quote valid 30 days.',
                            :cb)
                    RETURNING revision_id
                    """
                ),
                {"e": eid, "st": status if status == "draft" else "draft",
                 "mu": markup_pct, "cb": _estimator_id},
            ).scalar()
            for seq, spec in enumerate(line_specs, start=1):
                lid = s.execute(
                    text(
                        """
                        INSERT INTO estimate_line
                            (revision_id, seq, description, qty, unit,
                             has_breakdown)
                        VALUES (:r, :s, :d, :q, 'EA', :hb)
                        RETURNING line_id
                        """
                    ),
                    {"r": rid, "s": seq,
                     "d": spec["description"], "q": spec["qty"],
                     "hb": bool(spec.get("parts") or spec.get("hardware"))},
                ).scalar()
                for p in spec.get("parts", []):
                    s.execute(
                        text(
                            """
                            INSERT INTO estimate_line_part
                                (line_id, material_type, material_id,
                                 sku_snapshot, description_snapshot,
                                 supplier_snapshot, qty, len_mm, wid_mm,
                                 cost_per_unit_snapshot, paint_instruction)
                            VALUES (:l, :mt, :mid, :sku, :desc, :sup,
                                    :q, :lmm, :wmm, :c, 'NONE')
                            """
                        ),
                        {"l": lid, **p},
                    )
                for h in spec.get("hardware", []):
                    s.execute(
                        text(
                            """
                            INSERT INTO estimate_line_hardware
                                (line_id, material_type, material_id,
                                 sku_snapshot, description_snapshot,
                                 supplier_snapshot, qty,
                                 cost_per_unit_snapshot)
                            VALUES (:l, :mt, :mid, :sku, :desc, :sup, :q, :c)
                            """
                        ),
                        {"l": lid, **h},
                    )
                for lab in spec.get("labour", []):
                    rate = next(
                        (r for (k, r) in _labour_rates if k == lab["stage_key"]),
                        0.0,
                    )
                    s.execute(
                        text(
                            """
                            INSERT INTO estimate_line_labour
                                (line_id, stage_key, hours, rate_snapshot)
                            VALUES (:l, :s, :h, :r)
                            """
                        ),
                        {"l": lid, "s": lab["stage_key"],
                         "h": lab["hours"], "r": rate},
                    )
            # Roll up cached totals so the list page shows correct sums.
            s.execute(
                text(
                    """
                    UPDATE estimate_line l
                       SET material_cost = COALESCE((
                               SELECT SUM(cost_extended)::numeric(12,2)
                                 FROM estimate_line_part WHERE line_id = l.line_id
                           ), 0) + COALESCE((
                               SELECT SUM(cost_extended)::numeric(12,2)
                                 FROM estimate_line_hardware WHERE line_id = l.line_id
                           ), 0),
                           labour_cost = COALESCE((
                               SELECT SUM(cost_extended)::numeric(12,2)
                                 FROM estimate_line_labour WHERE line_id = l.line_id
                           ), 0)
                     WHERE l.revision_id = :r
                    """
                ),
                {"r": rid},
            )
            s.execute(
                text(
                    """
                    UPDATE estimate_revision r
                       SET subtotal_cost = COALESCE((
                               SELECT SUM(total_cost * qty)::numeric(14,2)
                                 FROM estimate_line WHERE revision_id = r.revision_id
                           ), 0),
                           subtotal_sell = COALESCE((
                               SELECT SUM(
                                 CASE
                                   WHEN l.unit_sell_override IS NOT NULL THEN l.unit_sell_override * l.qty
                                   ELSE l.total_cost * l.qty * (1 + r.markup_pct / 100.0)
                                 END
                               )::numeric(14,2)
                                 FROM estimate_line l
                                WHERE l.revision_id = r.revision_id
                           ), 0),
                           total_inc_gst = COALESCE((
                               SELECT (SUM(
                                 CASE
                                   WHEN l.unit_sell_override IS NOT NULL THEN l.unit_sell_override * l.qty
                                   ELSE l.total_cost * l.qty * (1 + r.markup_pct / 100.0)
                                 END
                               ) * (1 + r.gst_pct / 100.0))::numeric(14,2)
                                 FROM estimate_line l
                                WHERE l.revision_id = r.revision_id
                           ), 0)
                     WHERE r.revision_id = :r
                    """
                ),
                {"r": rid},
            )
            # Apply final status (skip draft).
            if status == "sent":
                s.execute(
                    text(
                        """
                        UPDATE estimate_revision
                           SET status = 'sent',
                               sent_at = now(), sent_by = :a,
                               locked_at = now(), locked_by = :a
                         WHERE revision_id = :r
                        """
                    ),
                    {"a": _estimator_id, "r": rid},
                )
            elif status == "accepted":
                s.execute(
                    text(
                        """
                        UPDATE estimate_revision
                           SET status = 'accepted',
                               sent_at = now() - interval '1 day',
                               sent_by = :a,
                               locked_at = now() - interval '1 day',
                               locked_by = :a,
                               accepted_at = now()
                         WHERE revision_id = :r
                        """
                    ),
                    {"a": _estimator_id, "r": rid},
                )
            # Stamp the estimate's current_revision_id pointer.
            s.execute(
                text(
                    """
                    UPDATE estimate
                       SET current_revision_id = :r
                     WHERE estimate_id = :e
                    """
                ),
                {"r": rid, "e": eid},
            )
            return int(eid)

        # Demo estimate #1: draft, 3 lines (1 stub + 2 broken-down).
        if _bm_001 is not None and _hm_001 is not None:
            _bm_cost = float(_bm_001["cost_per_sheet"])
            _hm_cost = float(_hm_001["cost_per_unit"])
            _insert_estimate(
                est_no="EST-2026-0001",
                customer_name="ACME Property Group",
                title="Kitchen + butler's pantry refit",
                site_address="22 Hill Ave, Mosman NSW 2088",
                status="draft", markup_pct=35.00,
                line_specs=[
                    {"description": "Kitchen island 2400×900 (allow for waterfall ends)",
                     "qty": 1, "parts": [], "hardware": [], "labour": []},
                    {"description": "Pantry tower 600×900×2400",
                     "qty": 2,
                     "parts": [{
                         "mt": "BOARD", "mid": int(_bm_001["material_id"]),
                         "sku": _bm_001["sku"], "desc": _bm_001["description"],
                         "sup": _bm_001.get("default_supplier") or "Hartwood Supplies",
                         "q": 3, "lmm": 2400, "wmm": 900, "c": _bm_cost,
                     }],
                     "hardware": [{
                         "mt": "HARDWARE", "mid": int(_hm_001["material_id"]),
                         "sku": _hm_001["sku"], "desc": _hm_001["description"],
                         "sup": _hm_001.get("default_supplier") or "Hartwood Supplies",
                         "q": 8, "c": _hm_cost,
                     }],
                     "labour": [
                         {"stage_key": "DOWN", "hours": 2},
                         {"stage_key": "CNC", "hours": 4},
                         {"stage_key": "EDGED", "hours": 2},
                         {"stage_key": "MADE", "hours": 6},
                     ]},
                    {"description": "Walk-in pantry shelving (10 shelves)",
                     "qty": 1,
                     "parts": [{
                         "mt": "BOARD", "mid": int(_bm_001["material_id"]),
                         "sku": _bm_001["sku"], "desc": _bm_001["description"],
                         "sup": _bm_001.get("default_supplier") or "Hartwood Supplies",
                         "q": 4, "lmm": 1800, "wmm": 350, "c": _bm_cost,
                     }],
                     "hardware": [],
                     "labour": [
                         {"stage_key": "CNC", "hours": 3},
                         {"stage_key": "EDGED", "hours": 2},
                         {"stage_key": "INST", "hours": 4},
                     ]},
                ],
            )

            # Demo estimate #2: sent, 4 lines fully broken down.
            _insert_estimate(
                est_no="EST-2026-0002",
                customer_name="Bayside Joinery Clients",
                title="Library + study fit-out",
                site_address="14 Esplanade, Brighton VIC 3186",
                status="sent", markup_pct=40.00,
                line_specs=[
                    {"description": "Library bookcase 3600×2400 (built-in)",
                     "qty": 1,
                     "parts": [{
                         "mt": "BOARD", "mid": int(_bm_001["material_id"]),
                         "sku": _bm_001["sku"], "desc": _bm_001["description"],
                         "sup": _bm_001.get("default_supplier") or "Hartwood Supplies",
                         "q": 6, "lmm": 3600, "wmm": 350, "c": _bm_cost,
                     }],
                     "hardware": [{
                         "mt": "HARDWARE", "mid": int(_hm_001["material_id"]),
                         "sku": _hm_001["sku"], "desc": _hm_001["description"],
                         "sup": _hm_001.get("default_supplier") or "Hartwood Supplies",
                         "q": 14, "c": _hm_cost,
                     }],
                     "labour": [
                         {"stage_key": "CNC", "hours": 6},
                         {"stage_key": "EDGED", "hours": 4},
                         {"stage_key": "MADE", "hours": 10},
                         {"stage_key": "INST", "hours": 8},
                     ]},
                    {"description": "Study desk 1800×750",
                     "qty": 1,
                     "parts": [{
                         "mt": "BOARD", "mid": int(_bm_001["material_id"]),
                         "sku": _bm_001["sku"], "desc": _bm_001["description"],
                         "sup": _bm_001.get("default_supplier") or "Hartwood Supplies",
                         "q": 2, "lmm": 1800, "wmm": 750, "c": _bm_cost,
                     }],
                     "hardware": [],
                     "labour": [
                         {"stage_key": "CNC", "hours": 2},
                         {"stage_key": "EDGED", "hours": 1},
                         {"stage_key": "MADE", "hours": 3},
                     ]},
                    {"description": "Window seat with storage 1600×450",
                     "qty": 1,
                     "parts": [{
                         "mt": "BOARD", "mid": int(_bm_001["material_id"]),
                         "sku": _bm_001["sku"], "desc": _bm_001["description"],
                         "sup": _bm_001.get("default_supplier") or "Hartwood Supplies",
                         "q": 2, "lmm": 1600, "wmm": 450, "c": _bm_cost,
                     }],
                     "hardware": [{
                         "mt": "HARDWARE", "mid": int(_hm_001["material_id"]),
                         "sku": _hm_001["sku"], "desc": _hm_001["description"],
                         "sup": _hm_001.get("default_supplier") or "Hartwood Supplies",
                         "q": 4, "c": _hm_cost,
                     }],
                     "labour": [
                         {"stage_key": "CNC", "hours": 2},
                         {"stage_key": "MADE", "hours": 4},
                         {"stage_key": "INST", "hours": 2},
                     ]},
                    {"description": "Hidden drawer file unit (3 drawers)",
                     "qty": 2,
                     "parts": [{
                         "mt": "BOARD", "mid": int(_bm_001["material_id"]),
                         "sku": _bm_001["sku"], "desc": _bm_001["description"],
                         "sup": _bm_001.get("default_supplier") or "Hartwood Supplies",
                         "q": 2, "lmm": 700, "wmm": 500, "c": _bm_cost,
                     }],
                     "hardware": [{
                         "mt": "HARDWARE", "mid": int(_hm_001["material_id"]),
                         "sku": _hm_001["sku"], "desc": _hm_001["description"],
                         "sup": _hm_001.get("default_supplier") or "Hartwood Supplies",
                         "q": 6, "c": _hm_cost,
                     }],
                     "labour": [
                         {"stage_key": "CNC", "hours": 3},
                         {"stage_key": "EDGED", "hours": 2},
                         {"stage_key": "MADE", "hours": 4},
                     ]},
                ],
            )

            # Demo estimate #3: accepted, 2 lines — ready for Convert demo.
            _insert_estimate(
                est_no="EST-2026-0003",
                customer_name="ACME Property Group",
                title="Bathroom vanity replacement",
                site_address="22 Hill Ave, Mosman NSW 2088",
                status="accepted", markup_pct=38.00,
                line_specs=[
                    {"description": "Vanity 1500×550 wall-hung",
                     "qty": 1,
                     "parts": [{
                         "mt": "BOARD", "mid": int(_bm_001["material_id"]),
                         "sku": _bm_001["sku"], "desc": _bm_001["description"],
                         "sup": _bm_001.get("default_supplier") or "Hartwood Supplies",
                         "q": 2, "lmm": 1500, "wmm": 550, "c": _bm_cost,
                     }],
                     "hardware": [{
                         "mt": "HARDWARE", "mid": int(_hm_001["material_id"]),
                         "sku": _hm_001["sku"], "desc": _hm_001["description"],
                         "sup": _hm_001.get("default_supplier") or "Hartwood Supplies",
                         "q": 6, "c": _hm_cost,
                     }],
                     "labour": [
                         {"stage_key": "CNC", "hours": 2},
                         {"stage_key": "EDGED", "hours": 1},
                         {"stage_key": "MADE", "hours": 3},
                         {"stage_key": "INST", "hours": 2},
                     ]},
                    {"description": "Tall mirror cabinet 600×1800",
                     "qty": 1, "parts": [], "hardware": [],
                     "labour": [{"stage_key": "INST", "hours": 2}]},
                ],
            )

        s.commit()
        print("seeded #9a estimating_core: 1 estimator + 2 customers + 3 estimates")

        # ==================================================================
        # === Legacy mocks import =========================================
        # Extracts demo content from legacy/{home,tracking_dashboard,
        # drafter_item_editor,procurement_orderbook_dashboard}.html into
        # the live data model so the post-login surfaces render rich for
        # rin.park@hartwood.test. Idempotent within its own scope.
        # ==================================================================
        rin_id = get_user_id("rin.park@hartwood.test")
        theo_id = get_user_id("theo.blake@hartwood.test")
        alf_pid = s.execute(
            text("SELECT project_id FROM projects WHERE project_code = 'ALF-001'")
        ).scalar()
        trt_pid = s.execute(
            text("SELECT project_id FROM projects WHERE project_code = 'TRT-014'")
        ).scalar()

        # --- Page 2a: 3 extra projects (sidebar fodder, all-projects count)
        legacy_projects = [
            ("MON-2347", "Monash FFT",       rin_id,  "2026-09-01", "Current"),
            ("VSB-2351", "VSBA Mickleham",   theo_id, "2026-10-15", "Current"),
            ("FLW-2318", "7ss Flinder West", theo_id, "2026-11-30", "Hold"),
        ]
        for code, name, pm_id, install, pstatus in legacy_projects:
            s.execute(
                text(
                    """
                    INSERT INTO projects
                        (project_code, name, pm_id, installation_start,
                         status, workspace_id)
                    VALUES (:c, :n, :pm, :i, :s, :w)
                    ON CONFLICT (name) DO NOTHING
                    """
                ),
                {"c": code, "n": name, "pm": pm_id, "i": install,
                 "s": pstatus, "w": workspace_id},
            )
        mon_pid = s.execute(
            text("SELECT project_id FROM projects WHERE project_code = 'MON-2347'")
        ).scalar()

        # --- Page 2b: 3 favourites for rin.park (sidebar Fav scope)
        for pid in (alf_pid, trt_pid, mon_pid):
            if pid is not None:
                s.execute(
                    text(
                        """
                        INSERT INTO project_favourites(user_id, project_id)
                        VALUES (:u, :p)
                        ON CONFLICT (user_id, project_id) DO NOTHING
                        """
                    ),
                    {"u": rin_id, "p": pid},
                )

        # --- Page 2c: shape KPI metrics for the PM dashboard
        # In-Optimisation requires DOWN done AND CNC not done. Mark DOWN
        # done on the first 2 ALF-001 items so the count is > 0.
        # Awaiting-Install requires DEL done AND INST not done. Insert
        # DEL done_date for 1 ALF-001 item.
        kpi_items = [
            row[0]
            for row in s.execute(
                text(
                    """
                    SELECT item_id FROM items
                    WHERE project_id = :p ORDER BY item_id LIMIT 3
                    """
                ),
                {"p": alf_pid},
            ).all()
        ]
        for iid in kpi_items[:2]:
            s.execute(
                text(
                    """
                    UPDATE item_stages
                       SET done_date = CURRENT_DATE - 1
                     WHERE item_id = :i AND stage_key = 'DOWN'
                       AND done_date IS NULL
                    """
                ),
                {"i": iid},
            )
        if kpi_items:
            s.execute(
                text(
                    """
                    INSERT INTO item_stages(item_id, stage_key, due_date, done_date)
                    VALUES (:i, 'DEL', CURRENT_DATE - 2, CURRENT_DATE - 2)
                    ON CONFLICT (item_id, stage_key) DO UPDATE
                      SET done_date = EXCLUDED.done_date,
                          due_date  = EXCLUDED.due_date
                    """
                ),
                {"i": kpi_items[0]},
            )

        # --- Page 2d: 4 deliveries-today batches (matches mock list)
        # Use the first hardware material as a stand-in receiver and the
        # ALF-001 project. Distinct po_refs so re-runs collide on UNIQUE.
        first_hw_mid = s.execute(
            text(
                """
                SELECT material_id FROM hardware_materials
                WHERE workspace_id = :w ORDER BY material_id LIMIT 1
                """
            ),
            {"w": workspace_id},
        ).scalar()
        deliveries_today = [
            ("Briggs Veneer", "PO-LEG-001", 20),
            ("Hafele",        "PO-LEG-002", 60),
            ("Polytec",       "PO-LEG-003",  4),
            ("Laminex",       "PO-LEG-004",  2),
        ]
        s.execute(
            text(
                """
                DELETE FROM procurement_batches
                WHERE po_ref = ANY(:refs)
                """
            ),
            {"refs": [r[1] for r in deliveries_today]},
        )
        for supplier, po, qty in deliveries_today:
            s.execute(
                text(
                    """
                    INSERT INTO procurement_batches
                        (project_id, material_type, material_id,
                         supplier, po_ref, qty_ordered,
                         ordered_date, eta_date)
                    VALUES (:p, 'HARDWARE', :m, :sup, :po, :q,
                            CURRENT_DATE - 7, CURRENT_DATE)
                    """
                ),
                {"p": alf_pid, "m": first_hw_mid,
                 "sup": supplier, "po": po, "q": qty},
            )

        s.commit()
        print(
            "seeded legacy/home: 3 extra projects + 3 favourites + "
            "KPI shaping + 4 deliveries-today batches"
        )

        # ==================================================================
        # === Page 3: tracking_dashboard.html — 7 more ALF-001 items =====
        # Mock has 12 items (codes JO-SS01..JO-TP01) spanning
        # Joinery General / Joinery Lab / PC2 / Stone stages. Live ALF-001
        # already has 5 items. Append 7 more matching the mock's item codes
        # so /tracking shows a populated grid. Append-only (existing
        # subproject seeds use ORDER BY item_id LIMIT N — appending is safe).
        # Idempotent: ON CONFLICT (num) DO NOTHING.
        # ==================================================================
        legacy_items = [
            # (num, code, description, level, rm_no, rm_desc, stage, zone, qty, status)
            (297830, "JO-SS01",  "SS Bench",                "03", "057", "Dirty Utilities", "Joinery General", "03", 1, "LIVE"),
            (297871, "JO-SS02",  "SS Bench + OH Cupboard",  "03", "057", "Dirty Utilities", "Joinery General", "03", 1, "LIVE"),
            (297910, "JL-BE01a", "Lab Bench",               "03", "068", "Bacterial Room",  "Joinery Lab",     "03", 1, "CLEAR"),
            (297956, "JL-SB01a", "SS Lab Bench",            "03", "068", "Bacterial Room",  "Joinery Lab",     "03", 1, "LIVE"),
            (297961, "JL-PC201", "PC2 Containment Bench",   "03", "102", "PC2 Holding",     "PC2",             "04", 1, "NOTE!"),
            (297975, "ST-CT01",  "Reception Counter Top",   "03", "104", "Reception",       "Stone",           "04", 1, "LIVE"),
            (297988, "JO-TP01",  "Tea Point Joinery",       "03", "201", "Tea Point",       "Joinery General", "05", 1, "CLEAR"),
        ]
        for num, code, desc, level, rm_no, rm_desc, stage, zone, qty, ist in legacy_items:
            s.execute(
                text(
                    """
                    INSERT INTO items
                        (num, project_id, code, description, level,
                         rm_no, rm_desc, stage, zone, qty, status,
                         cutlist_owner_id, item_locked)
                    VALUES (:num, :pid, :code, :desc, :level,
                            :rm_no, :rm_desc, :stage, :zone, :qty, :st,
                            :owner, false)
                    ON CONFLICT (num) DO NOTHING
                    """
                ),
                {"num": num, "pid": alf_pid, "code": code, "desc": desc,
                 "level": level, "rm_no": rm_no, "rm_desc": rm_desc,
                 "stage": stage, "zone": zone, "qty": qty, "st": ist,
                 "owner": rin_id},
            )
            # Seed 3 lifecycle stages per item (REQ done, SM done, LISTED open)
            iid = s.execute(
                text("SELECT item_id FROM items WHERE num = :n"),
                {"n": num},
            ).scalar()
            if iid is not None:
                # Areas and Rooms for these too — the C6 selectors read them,
                # and 0026's backfill never saw a row seeded after it ran.
                s.execute(
                    text(
                        """
                        WITH ins AS (
                            INSERT INTO area (project_id, name)
                            VALUES (:pid, :area)
                            ON CONFLICT (project_id, name) DO NOTHING
                            RETURNING area_id
                        ), picked_area AS (
                            SELECT area_id FROM ins
                            UNION ALL
                            SELECT area_id FROM area
                             WHERE project_id = :pid AND name = :area
                            LIMIT 1
                        ), ins_room AS (
                            INSERT INTO room (area_id, rm_no, rm_desc)
                            SELECT area_id, :rm_no, :rm_desc FROM picked_area
                            ON CONFLICT (area_id, rm_no) DO NOTHING
                            RETURNING room_id
                        ), picked_room AS (
                            SELECT room_id FROM ins_room
                            UNION ALL
                            SELECT r.room_id FROM room r
                              JOIN picked_area pa ON pa.area_id = r.area_id
                             WHERE r.rm_no = :rm_no
                            LIMIT 1
                        )
                        UPDATE items
                           SET area_id = (SELECT area_id FROM picked_area),
                               room_id = (SELECT room_id FROM picked_room)
                         WHERE item_id = :iid
                        """
                    ),
                    {"pid": alf_pid, "area": stage, "rm_no": rm_no,
                     "rm_desc": rm_desc, "iid": iid},
                )

                # Q540: every Joinery Item carries its own cutlist, numbered as
                # itself.  Shop Floor keys on it and worker_assignment.cutlist_id
                # is NOT NULL since 0030, so an item without one breaks a re-run
                # of this seed the moment the shop-floor block reaches it.
                s.execute(
                    text(
                        """
                        WITH ins AS (
                            INSERT INTO cutlist (project_id, cutlist_no, name)
                            VALUES (:pid, :num, :name)
                            ON CONFLICT (cutlist_no) DO NOTHING
                            RETURNING cutlist_id
                        ), picked AS (
                            SELECT cutlist_id FROM ins
                            UNION ALL
                            SELECT cutlist_id FROM cutlist WHERE cutlist_no = :num
                            LIMIT 1
                        )
                        UPDATE items SET cutlist_id = (SELECT cutlist_id FROM picked)
                         WHERE item_id = :iid AND cutlist_id IS NULL
                        """
                    ),
                    {"pid": alf_pid, "num": num, "iid": iid, "name": desc},
                )
                for sk, due_off, done_off in [
                    ("REQ",    -25, -20),
                    ("SM",     -15, -12),
                    ("LISTED",  -2, None),
                ]:
                    s.execute(
                        text(
                            """
                            INSERT INTO item_stages
                                (item_id, stage_key, due_date, done_date)
                            VALUES (:i, :sk,
                                    CURRENT_DATE + CAST(:due AS integer),
                                    CASE WHEN CAST(:done AS integer) IS NULL THEN NULL
                                         ELSE CURRENT_DATE + CAST(:done AS integer) END)
                            ON CONFLICT (item_id, stage_key) DO NOTHING
                            """
                        ),
                        {"i": iid, "sk": sk, "due": due_off, "done": done_off},
                    )

        s.commit()
        print(f"seeded legacy/tracking: {len(legacy_items)} extra items on ALF-001")

        # ==================================================================
        # === Page 4a: drafter_item_editor.html — catalog extensions =====
        # Mock has 5 boards, 5 hardware (already in seed), 1 custom_made,
        # 1 benchtop, 1 appliance, 1 equipment_hire. Live already has
        # 6 boards (2 base + 4 from #7a) and 4 hardware. Add the 4 missing
        # boards (32-MDF / 16-BLACK / 19-A-WALNUT / 25-SS304), 1 custom,
        # 1 benchtop, 1 appliance, 1 equipment_hire. Idempotent via UNIQUE.
        # ==================================================================
        legacy_boards = [
            ("BM-200", "32-MDF",      "32mm MDF",                            "Laminex Australia",  5,  60.00),
            ("BM-201", "16-BLACK",    "16mm Black Melamine",                 "Laminex Australia",  5,  40.00),
            ("BM-202", "19-A-WALNUT", "19mm A-Grade Walnut Veneer / BAM X",  "Briggs Veneers",    21, 180.00),
            ("BM-203", "25-SS304",    "25mm Stainless 304 Sheet",            "CDK Stone",         28, 320.00),
        ]
        for code, sku, desc, sup, lt, cost in legacy_boards:
            s.execute(
                text(
                    """
                    INSERT INTO board_materials
                        (workspace_id, code, sku, description,
                         synonyms, default_supplier, default_lead_time_days,
                         cost_per_sheet, unit_cost)
                    VALUES (:w, :c, :sku, :d, :syn,
                            :sup, :lt, :cost, :cost)
                    ON CONFLICT (workspace_id, sku) DO NOTHING
                    """
                ),
                {"w": workspace_id, "c": code, "sku": sku, "d": desc,
                 "syn": [code, sku],
                 "sup": sup, "lt": lt, "cost": cost},
            )

        # custom_made.internal_ref is globally UNIQUE → prefix with workspace.
        s.execute(
            text(
                """
                INSERT INTO custom_made
                    (internal_ref, description, vendor, cost, lead_time_days)
                VALUES ('hartwood-CM-SIGNBOX-01',
                        'Bespoke signage box (reception)',
                        'Metalform', 1250.00, 14)
                ON CONFLICT (internal_ref) DO NOTHING
                """
            )
        )
        # benchtop_materials.slab_id is globally UNIQUE → prefix.
        s.execute(
            text(
                """
                INSERT INTO benchtop_materials
                    (slab_id, description, material_type, thickness_mm,
                     supplier, cost_per_slab, lead_time_days)
                VALUES ('hartwood-CST-2297-A',
                        'Caesarstone 6131 Bianco Drift 20mm',
                        'stone', 20.00, 'CDK Stone', 1450.00, 21)
                ON CONFLICT (slab_id) DO NOTHING
                """
            )
        )
        # appliances.model_number is globally UNIQUE → prefix.
        s.execute(
            text(
                """
                INSERT INTO appliances
                    (model_number, description, manufacturer, supplier,
                     cost_per_unit, lead_time_days)
                VALUES ('hartwood-MIELE-H7164BP',
                        'Miele 60cm Oven H7164BP', 'Miele',
                        'Winning Appliances', 3450.00, 14)
                ON CONFLICT (model_number) DO NOTHING
                """
            )
        )
        # equipment_hire requires project_id FK; scope to ALF-001.
        if alf_pid is not None:
            s.execute(
                text(
                    """
                    INSERT INTO equipment_hire
                        (contract_ref, project_id, description, supplier,
                         rate, rate_unit, hire_start, hire_end, total_cost)
                    VALUES ('hartwood-KENNARDS-0423-881', :p,
                            'Kennards scissor lift — Alfred site',
                            'Kennards', 285.00, 'DAY',
                            CURRENT_DATE - 7, CURRENT_DATE + 21, 8000.00)
                    ON CONFLICT (contract_ref) DO NOTHING
                    """
                ),
                {"p": alf_pid},
            )

        # ==================================================================
        # === Page 4b: drafter_item_editor.html — enrich JO-SS02 ==========
        # Mock's flagship item is JO-SS02 (num=297871) with 2 modules
        # (Bench Carcass / OH Cupboard), 7 parts, 4 hardware lines.
        # Idempotent: DELETE modules for this item before re-inserting
        # (cascades to parts via FK).
        # ==================================================================
        jo_ss02_iid = s.execute(
            text("SELECT item_id FROM items WHERE num = 297871"),
        ).scalar()
        if jo_ss02_iid is not None:
            s.execute(
                text("DELETE FROM modules WHERE item_id = :i"),
                {"i": jo_ss02_iid},
            )
            board_id_by_sku: dict[str, int] = {
                row[0]: row[1]
                for row in s.execute(
                    text(
                        """
                        SELECT sku, material_id FROM board_materials
                        WHERE workspace_id = :w
                        """
                    ),
                    {"w": workspace_id},
                ).all()
            }
            mod_specs = [
                ("MOD 1", "Bench Carcass"),
                ("MOD 2", "OH Cupboard"),
            ]
            mod_ids: list[int] = []
            for mod_no, mod_name in mod_specs:
                mid = s.execute(
                    text(
                        """
                        INSERT INTO modules (item_id, module_no, name)
                        VALUES (:i, :mn, :name)
                        RETURNING module_id
                        """
                    ),
                    {"i": jo_ss02_iid, "mn": mod_no, "name": mod_name},
                ).scalar()
                mod_ids.append(int(mid))

            # 7 parts: (mod_id, seq, qty, part_name, len, wid, board_sku, paint)
            mod1, mod2 = mod_ids
            parts_specs = [
                (mod1, 1, 2, "Side Panel", 720,  580, "BM-001",   "NONE"),
                (mod1, 2, 1, "Top",        1500, 600, "25-SS304", "NONE"),
                (mod1, 3, 1, "Bottom",     1460, 580, "BM-001",   "NONE"),
                (mod1, 4, 1, "Back",       1460, 700, "BM-001",   "SINGLE_SIDE"),
                (mod2, 1, 2, "OH Side",    700,  320, "BM-001",   "DOUBLE_SIDE"),
                (mod2, 2, 1, "OH Top",     1500, 320, "BM-001",   "SINGLE_SIDE"),
                (mod2, 3, 2, "OH Door",    695,  745, "BM-001",   "EDGE_ONLY"),
            ]
            for mid, seq, qty, pname, lmm, wmm, bsku, paint in parts_specs:
                bid = board_id_by_sku.get(bsku)
                if bid is None:
                    continue
                s.execute(
                    text(
                        """
                        INSERT INTO parts
                            (module_id, seq, qty, part_name,
                             len_mm, wid_mm, board_material_id,
                             paint_instruction)
                        VALUES (:m, :s, :q, :n, :l, :w, :b, :p)
                        """
                    ),
                    {"m": mid, "s": seq, "q": qty, "n": pname,
                     "l": lmm, "w": wmm, "b": bid, "p": paint},
                )

            # 4 hardware lines on JO-SS02 using existing ALF-001 catalog.
            s.execute(
                text(
                    "DELETE FROM item_hardware_lines WHERE item_id = :i"
                ),
                {"i": jo_ss02_iid},
            )
            alf_catalog = [
                row[0]
                for row in s.execute(
                    text(
                        """
                        SELECT catalog_id FROM project_hardware_catalog
                        WHERE project_id = :p
                        ORDER BY catalog_id LIMIT 4
                        """
                    ),
                    {"p": alf_pid},
                ).all()
            ]
            hw_specs = [
                (6, "OH cupboard doors"),
                (2, "OH cupboard handles"),
                (8, "Adjustable shelves"),
                (2, "Not yet on-site"),
            ]
            for seq, (cat_id, (qty, note)) in enumerate(zip(alf_catalog, hw_specs), start=1):
                s.execute(
                    text(
                        """
                        INSERT INTO item_hardware_lines
                            (item_id, seq, qty, catalog_id, note)
                        VALUES (:i, :s, :q, :c, :n)
                        ON CONFLICT (item_id, seq) DO UPDATE
                          SET qty = EXCLUDED.qty,
                              catalog_id = EXCLUDED.catalog_id,
                              note = EXCLUDED.note
                        """
                    ),
                    {"i": jo_ss02_iid, "s": seq, "q": qty,
                     "c": cat_id, "n": note},
                )

        s.commit()
        print(
            "seeded legacy/drafter: catalog extensions + JO-SS02 enrichment "
            "(2 modules / 7 parts / up to 4 hardware lines)"
        )

        # ==================================================================
        # === Page 5: procurement_orderbook_dashboard.html — 2 batches ====
        # Mock has 12 POs; 10 are generic IT/office (skip). Extract the 2
        # joinery rows: PO-2024-009 Schiavello SS benchtop, PO-2024-011
        # Mitchell Laminates Echopanel. Translate to procurement_batches
        # on ALF-001 with the materials they map to. Idempotent by po_ref.
        # ==================================================================
        legacy_orderbook = [
            # (supplier, po_ref, material_type, lookup, qty, cost, eta_offset, ord_offset)
            ("Schiavello Manufacturing", "PO-2273-LEG-009", "BENCHTOP",
             ("benchtop_materials", "slab_id", "hartwood-CST-2297-A"),
             2, 3551.00,  14,  -10),
            ("Mitchell Laminates Pty Ltd", "PO-2273-LEG-011", "BOARD",
             ("board_materials", "sku", "16-BLACK"),
             2,  920.00, None, -5),
        ]
        s.execute(
            text(
                """
                DELETE FROM procurement_batches
                WHERE po_ref = ANY(:refs)
                """
            ),
            {"refs": [r[1] for r in legacy_orderbook]},
        )
        for supplier, po, mtype, (table, key_col, key_val), qty, cost, eta_off, ord_off in legacy_orderbook:
            mid = s.execute(
                text(f"SELECT material_id FROM {table} WHERE {key_col} = :v"),
                {"v": key_val},
            ).scalar()
            if mid is None:
                continue
            s.execute(
                text(
                    """
                    INSERT INTO procurement_batches
                        (project_id, material_type, material_id, supplier,
                         po_ref, qty_ordered, cost_per_unit,
                         ordered_date, eta_date)
                    VALUES (:p, :mt, :mid, :sup, :po, :q, :c,
                            CURRENT_DATE + CAST(:ord AS integer),
                            CASE WHEN CAST(:eta AS integer) IS NULL THEN NULL
                                 ELSE CURRENT_DATE + CAST(:eta AS integer) END)
                    """
                ),
                {"p": alf_pid, "mt": mtype, "mid": mid, "sup": supplier,
                 "po": po, "q": qty, "c": cost, "ord": ord_off, "eta": eta_off},
            )

        s.commit()
        print(
            f"seeded legacy/orderbook: {len(legacy_orderbook)} joinery batches "
            "(Schiavello + Mitchell Laminates)"
        )

        # ── Advance the shared number sequence past the seeded fixtures ────────
        #
        # Every item above is inserted with a FIXED `num` (290001.. and
        # 297830..) so the seed stays idempotent and demo numbers stay stable.
        # Migration 0027 seeds `joinery_number_seq` from whatever `items` holds
        # AT MIGRATE TIME — which is nothing, because `make migrate` runs before
        # `make seed`. The sequence would therefore sit at 100000 while seeded
        # rows reach 297988, and every runtime allocation would start ~198k
        # below the demo data.
        #
        # setval() is idempotent and monotonic here: GREATEST() never moves the
        # sequence backwards, so re-running the seed is safe.
        seq_row = s.execute(
            text(
                """
                SELECT setval('joinery_number_seq', GREATEST(
                    (SELECT last_value FROM joinery_number_seq),
                    COALESCE((SELECT MAX(num) FROM items), 0)
                ))
                """
            )
        ).scalar()
        s.commit()
        print(f"advanced joinery_number_seq to {seq_row}")

        # ==================================================================
        # === Sub-project #10: cutlist + related parts + Orderbook (D1) ===
        # Demo state for the four things this sub-project introduced that no
        # other seed block exercises:
        #
        #   * a cutlist SHARED by two items, with one completed stage fanned
        #     out to both (Q439) — the whole point of moving the production
        #     workflow off the item;
        #   * a third item linked to that cutlist AFTER the completion, whose
        #     earlier stages stay blank (Q539);
        #   * two related parts under one Joinery Item, one carrying an issued
        #     order and one carrying none (Q417/Q429);
        #   * the supplier (Q506/Q556: `vendors` IS the supplier entity) and
        #     the purchase order behind that first one.
        #
        # It works on the seven `legacy_items` rather than the five
        # ITEMS_PER_PROJECT ones because the shop-floor block (#8) wipes
        # stage_completion_log for every cutlist the first six ALF items
        # touch — a fan-out written there would not survive its own seed.
        #
        # It runs after the setval above so the related parts draw their
        # numbers from nextval() exactly as the API allocates them (Q541),
        # landing just past the seeded fixtures instead of ~198k below them.
        # ==================================================================
        def _seed_item_by_num(num: int) -> int | None:
            return s.execute(
                text("SELECT item_id FROM items WHERE num = :n"), {"n": num}
            ).scalar()

        _shared_head = _seed_item_by_num(297830)   # JO-SS01 — keeps its cutlist
        _shared_mate = _seed_item_by_num(297871)   # JO-SS02 — moves onto it
        _late_joiner = _seed_item_by_num(297910)   # JL-BE01a — links after the fact
        _rp_parent   = _seed_item_by_num(297975)   # ST-CT01 — carries the related parts

        if None not in (_shared_head, _shared_mate, _late_joiner, _rp_parent):
            _shared_cid = s.execute(
                text("SELECT cutlist_id FROM items WHERE item_id = :i"),
                {"i": _shared_head},
            ).scalar()

            def _move_onto_shared(item_id: int) -> None:
                """Re-point one item at the shared cutlist, dropping the one it
                vacates. Q411 lets an item hold at most one cutlist, so the old
                row is left with nothing; an empty cutlist would still show up
                in /list, so it goes — but only once nothing references it.

                The drop is unconditional, not a consequence of the move: the
                blocks above re-INSERT a cutlist numbered as the item on every
                run (their own idempotency guard is on `items`, not `cutlist`),
                so a move that already happened still leaves one behind."""
                s.execute(
                    text("UPDATE items SET cutlist_id = :c, updated_at = now()"
                         " WHERE item_id = :i AND cutlist_id IS DISTINCT FROM :c"),
                    {"c": _shared_cid, "i": item_id},
                )
                s.execute(
                    text(
                        """
                        DELETE FROM cutlist c
                         USING items i
                         WHERE i.item_id = :i
                           AND c.cutlist_no = i.num
                           AND c.cutlist_id <> :keep
                           AND NOT EXISTS (SELECT 1 FROM items
                                            WHERE cutlist_id = c.cutlist_id)
                           AND NOT EXISTS (SELECT 1 FROM worker_assignment
                                            WHERE cutlist_id = c.cutlist_id)
                           AND NOT EXISTS (SELECT 1 FROM stage_completion_log
                                            WHERE cutlist_id = c.cutlist_id)
                        """
                    ),
                    {"i": item_id, "keep": _shared_cid},
                )

            _move_onto_shared(_shared_mate)
            s.execute(
                text("UPDATE cutlist SET name = :n, updated_at = now()"
                     " WHERE cutlist_id = :c"),
                {"n": "SS Bench run (shared)", "c": _shared_cid},
            )

            # The completion has to be in order to read as real: these two
            # items are seeded with LISTED still open.
            for _iid in (_shared_head, _shared_mate):
                s.execute(
                    text(
                        """
                        INSERT INTO item_stages (item_id, stage_key, done_date)
                        VALUES (:i, 'LISTED', CURRENT_DATE - 3)
                        ON CONFLICT (item_id, stage_key)
                        DO UPDATE SET done_date = CURRENT_DATE - 3
                        """
                    ),
                    {"i": _iid},
                )

            _cut_worker = s.execute(
                text(
                    "SELECT id FROM app_user WHERE workspace_id = :w"
                    " AND is_shop_worker = true ORDER BY id LIMIT 1"
                ),
                {"w": workspace_id},
            ).scalar() or _drafter_id
            _cut_boss = s.execute(
                text(
                    "SELECT id FROM app_user WHERE workspace_id = :w"
                    " AND auth_role = 'manager' ORDER BY id LIMIT 1"
                ),
                {"w": workspace_id},
            ).scalar() or _cut_worker

            # Idempotent: the log references the assignment, so it goes first.
            s.execute(
                text("DELETE FROM stage_completion_log"
                     " WHERE cutlist_id = :c AND stage_key = 'DOWN'"),
                {"c": _shared_cid},
            )
            s.execute(
                text("DELETE FROM worker_assignment"
                     " WHERE cutlist_id = :c AND stage_key = 'DOWN'"),
                {"c": _shared_cid},
            )
            _shared_aid = s.execute(
                text(
                    """
                    INSERT INTO worker_assignment (
                        cutlist_id, stage_key, worker_id, status,
                        assigned_by, started_at, ended_at)
                    VALUES (:c, 'DOWN', :w, 'done', :a,
                            now() - interval '2 days',
                            now() - interval '2 days' + interval '3 hours')
                    RETURNING assignment_id
                    """
                ),
                {"c": _shared_cid, "w": _cut_worker, "a": _cut_boss},
            ).scalar()
            s.execute(
                text(
                    """
                    INSERT INTO stage_completion_log (
                        cutlist_id, stage_key, assignment_id, worker_id,
                        completed_at, note)
                    VALUES (:c, 'DOWN', :a, :w,
                            now() - interval '2 days' + interval '3 hours',
                            'seeded: one completion, fanned out across the cutlist')
                    """
                ),
                {"c": _shared_cid, "a": _shared_aid, "w": _cut_worker},
            )
            # Q439: the projection lands on every item linked AT THIS MOMENT.
            for _iid in (_shared_head, _shared_mate):
                s.execute(
                    text(
                        """
                        INSERT INTO item_stages (item_id, stage_key, done_date)
                        VALUES (:i, 'DOWN', CURRENT_DATE - 2)
                        ON CONFLICT (item_id, stage_key)
                        DO UPDATE SET done_date = CURRENT_DATE - 2
                        """
                    ),
                    {"i": _iid},
                )

            # Q539: and only now does the third item join. It gets no DOWN row
            # — the stage was completed before it was on the cutlist, so its
            # strip reads blank there and catches up at the next completion.
            _move_onto_shared(_late_joiner)
            s.execute(
                text("DELETE FROM item_stages WHERE item_id = :i AND stage_key = 'DOWN'"),
                {"i": _late_joiner},
            )

            # --- Related parts (Q447): rows in `items`, one level only ------
            _rp_parent_row = s.execute(
                text(
                    """
                    SELECT i.num, c.cutlist_no, a.name AS area_name,
                           p.name AS project_name
                      FROM items i
                      JOIN projects p ON p.project_id = i.project_id
                      LEFT JOIN cutlist c ON c.cutlist_id = i.cutlist_id
                      LEFT JOIN area    a ON a.area_id    = i.area_id
                     WHERE i.item_id = :i
                    """
                ),
                {"i": _rp_parent},
            ).mappings().first()

            _rp_ids: list[int] = []
            for _type_key, _descr, _qty, _st in [
                ("benchtop", "Reception counter — 20mm stone top", 1, "LIVE"),
                ("metal",    "Counter support brackets — folded 3mm", 6, "CLEAR"),
            ]:
                _rid = s.execute(
                    text("SELECT item_id FROM items"
                         " WHERE parent_item_id = :p AND description = :d"),
                    {"p": _rp_parent, "d": _descr},
                ).scalar()
                if _rid is None:
                    _rid = s.execute(
                        text(
                            """
                            INSERT INTO items (
                                num, project_id, description, qty, status,
                                row_type, parent_item_id,
                                related_part_type_key, group_id)
                            VALUES (nextval('joinery_number_seq'), :p, :d, :q, :st,
                                    'related_part', :parent, :tk, :gid)
                            RETURNING item_id
                            """
                        ),
                        {"p": alf_pid, "d": _descr, "q": _qty, "st": _st,
                         "parent": _rp_parent, "tk": _type_key,
                         "gid": str(_rp_parent_row["num"])},
                    ).scalar()
                _rp_ids.append(_rid)

            # --- Supplier (Q506/Q556: `vendors` is the supplier entity) -----
            _vendor_name = "Corian Stoneworks"
            _vendor_id = s.execute(
                text("SELECT vendor_id FROM vendors"
                     " WHERE workspace_id = :w AND name = :n"),
                {"w": workspace_id, "n": _vendor_name},
            ).scalar()
            if _vendor_id is None:
                _vendor_id = s.execute(
                    text(
                        """
                        INSERT INTO vendors (
                            workspace_id, name, category, contact_name,
                            contact_email, contact_phone, status, payment_terms)
                        VALUES (:w, :n, 'Benchtop', 'Dee Ramsay',
                                'orders@corianstoneworks.test', '+61 3 9000 1188',
                                'Active', '30 days EOM')
                        RETURNING vendor_id
                        """
                    ),
                    {"w": workspace_id, "n": _vendor_name},
                ).scalar()

            # --- One issued order, against the FIRST related part only ------
            # Q417/Q418: this number is what Tracking shows where a cutlist
            # number would be, so `date_ordered` must be set (Q567) or the
            # row reads as unordered. Q428: the CUTLIST NO. carried onto the
            # order is the PARENT's — 0028 forbids a related part having one.
            #
            # Delete-then-insert, so the dates stay relative to today. The
            # cost is one po_number_seq value per re-run; the sequence is
            # unowned and numbers are never asserted absolutely.
            _slab_mid = s.execute(
                text("SELECT material_id FROM benchtop_materials"
                     " WHERE slab_id = 'hartwood-CST-2297-A'"),
            ).scalar()
            s.execute(
                text("DELETE FROM purchase_orders WHERE item_id = ANY(:ids)"),
                {"ids": _rp_ids},
            )
            _po_id = s.execute(
                text(
                    """
                    INSERT INTO purchase_orders (
                        po_number, vendor_id, requester_id, description, category,
                        item_id, project_id, project_name, location, cutlist_no,
                        supplier_ref_no, status, priority,
                        product_code, product_description,
                        quantity, unit_of_measure, unit_cost, total_amount,
                        required_date, date_ordered, due_date, internal_comments)
                    VALUES (
                        'PO-' || EXTRACT(year FROM now())::int || '-' ||
                            lpad(nextval('po_number_seq')::text, 4, '0'),
                        :v, :req, :descr, 'Benchtop',
                        :item, :p, :pname, :loc, :cno,
                        'CSW-88214', 'Approved', 'Medium',
                        'hartwood-CST-2297-A',
                        '20mm Corian Deep Black, polished front edge',
                        1, 'slab', 3551.00, 3551.00,
                        CURRENT_DATE + 21, CURRENT_DATE - 6, CURRENT_DATE + 14,
                        'Seeded demo order — the O/BOOK subtab reads this row.')
                    RETURNING po_id
                    """
                ),
                {
                    "v": _vendor_id, "req": mina_id,
                    "descr": "Reception counter stone top",
                    "item": _rp_ids[0], "p": alf_pid,
                    "pname": _rp_parent_row["project_name"],
                    "loc": _rp_parent_row["area_name"],
                    "cno": (str(_rp_parent_row["cutlist_no"])
                            if _rp_parent_row["cutlist_no"] is not None else None),
                },
            ).scalar()
            s.execute(
                text(
                    """
                    INSERT INTO po_line_items (
                        po_id, line_number, item_description, sku,
                        quantity, unit, unit_price, material_table, material_id)
                    VALUES (:o, 1, '20mm Corian Deep Black slab — cut to counter',
                            'hartwood-CST-2297-A', 1, 'slab', 3551.00,
                            CASE WHEN CAST(:m AS bigint) IS NULL
                                 THEN NULL ELSE 'benchtop_materials' END,
                            CAST(:m AS bigint))
                    """
                ),
                {"o": _po_id, "m": _slab_mid},
            )

            s.commit()
            print(
                "seeded #10 cutlist/orderbook: 1 shared cutlist (3 items, "
                "1 fanned-out DOWN completion, 1 late joiner) + 2 related "
                f"parts + supplier {_vendor_name!r} + 1 purchase order"
            )

        # ------------------------------------------------------------------
        # #12 Material Take + Material Summary (Plan V1 §19–§20).
        # Built through the same query functions the API uses, so seeded
        # takes carry audit / edit-log rows like real ones. On ALF-001: every
        # item with parts gets an approved take except one left as a draft
        # (it shows under "missing takes"); a summary is built; then one item
        # approves a v2, so that summary shows a stale line. Idempotent: the
        # project's takes and summaries are dropped first.
        # ------------------------------------------------------------------
        from app.material_summaries import queries as _summaries
        from app.material_takes import queries as _takes

        _alf = db.execute(text("SELECT project_id FROM projects WHERE project_code = 'ALF-001'"
                               " AND workspace_id = :w"), {"w": wid}).scalar()
        _drafter = db.execute(text("SELECT id FROM app_user WHERE workspace_id = :w"
                                   " AND auth_role = 'drafter' ORDER BY id LIMIT 1"),
                              {"w": wid}).scalar()
        if _alf and _drafter:
            db.execute(text("DELETE FROM material_summary WHERE project_id = :p"), {"p": _alf})
            db.execute(text("DELETE FROM material_take WHERE item_id IN"
                            " (SELECT item_id FROM items WHERE project_id = :p)"), {"p": _alf})
            _take_items = [r[0] for r in db.execute(text("""
                SELECT i.item_id FROM items i
                 WHERE i.project_id = :p AND i.row_type = 'joinery_item'
                   AND EXISTS (SELECT 1 FROM modules m WHERE m.item_id = i.item_id)
                 ORDER BY i.num"""), {"p": _alf})]
            if len(_take_items) >= 2:
                _draft_only, _revised = _take_items[1], _take_items[0]
                for _iid in _take_items:
                    _tid = _takes.generate(db, _iid, wid, _drafter)
                    if _iid != _draft_only:
                        _takes.approve(db, _tid, wid, _drafter)
                _summaries.build(db, _alf, wid, _drafter)
                _takes.approve(db, _takes.generate(db, _revised, wid, _drafter), wid, _drafter)
                db.commit()
                print(f"seeded #12 material take: {len(_take_items) - 1} approved takes "
                      f"(1 at v2), 1 draft, 1 project summary whose lines for that item read stale")

        print(
            f"seeded workspace {wid} with {len(USERS)} users, "
            f"{len(PROJECTS)} projects, {len(PROJECTS) * len(ITEMS_PER_PROJECT)} items"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
