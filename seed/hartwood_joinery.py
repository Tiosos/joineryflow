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
]

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

        print(
            f"seeded workspace {wid} with {len(USERS)} users, "
            f"{len(PROJECTS)} projects, {len(PROJECTS) * len(ITEMS_PER_PROJECT)} items"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
