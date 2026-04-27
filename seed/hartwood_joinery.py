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
                        INSERT INTO projects (project_code, name, pm_id, installation_start, status)
                        VALUES (:code, :name, :pm, :install, :status)
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
                    exists = db.execute(
                        text(
                            "SELECT 1 FROM parts WHERE module_id=:mid AND seq=:seq LIMIT 1"
                        ),
                        {"mid": mod_id, "seq": seq_num},
                    ).scalar()
                    if not exists:
                        db.execute(
                            text(
                                """
                                INSERT INTO parts
                                    (module_id, seq, qty, part_name, len_mm, wid_mm,
                                     board_material_id, paint_instruction)
                                VALUES (:mid, :seq, 1, :name, :len, :wid, :bm, 'NONE')
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
                    exists = db.execute(
                        text(
                            "SELECT 1 FROM item_hardware_lines WHERE item_id=:iid AND seq=:seq LIMIT 1"
                        ),
                        {"iid": item_id, "seq": seq_num},
                    ).scalar()
                    if not exists:
                        db.execute(
                            text(
                                """
                                INSERT INTO item_hardware_lines
                                    (item_id, seq, qty, catalog_id)
                                VALUES (:iid, :seq, 1, :cid)
                                """
                            ),
                            {
                                "iid": item_id,
                                "seq": seq_num,
                                "cid": cat_id,
                            },
                        )

        db.commit()
        print(
            f"seeded workspace {wid} with {len(USERS)} users, "
            f"{len(PROJECTS)} projects, {len(PROJECTS) * len(ITEMS_PER_PROJECT)} items"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
