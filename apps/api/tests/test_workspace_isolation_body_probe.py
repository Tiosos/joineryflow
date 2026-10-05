"""Cross-workspace probe of foreign ids inside a request body.

test_workspace_isolation_probe.py covers the id in the path. This covers the other
way in: a request whose *body* names another workspace's row (CLAUDE.md §7: "any FK
to app_user / vendors / projects taken from a request body must be validated against
the caller's workspace"). A route that forgets the check either accepts the foreign
row (data leak, cross-tenant link) or answers differently for it than for a row that
does not exist (existence leak).

The probe runs as workspace A's admin on A's own rows, so the path and permissions
are fine, and varies one body field at a time between three values of the right kind:

  control  a row of A's        proves the field is really reached (answer differs
                               from the ghost's, usually a success)
  foreign  a row of workspace B's
  ghost    an id that exists nowhere

foreign and ghost must be answered identically (status and body, ids masked). Pairs
whose control cannot be told from the ghost (a body the generator cannot fill, a row
the seed lacks) have no signal and must be listed in NOT_PROBED, exactly as in the
path probe; fields whose kind depends on another field are in FIELD_REASONS.
"""
import re

from sqlalchemy import text

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers import login
from .helpers_probe import (
    CLEANUP_TABLES, GHOST_ID, REAL_ID_QUERIES, answer, crash, ids_for, operations,
    prepare_workspace_a, request, resolve,
)

_cleanup = truncate_fixture(*CLEANUP_TABLES)

# Body field -> the kind of row it points at.
FIELD_KIND = {
    "assigned_to": "user", "pm_id": "user", "user_id": "user",
    "requester_id": "user", "approver_id": "user", "contractor_id": "user",
    "mentioned_user_ids": "user", "worker_id": "shop_worker",
    "vendor_id": "vendor", "supplier_id": "vendor",
    "project_id": "project",
    "item_id": "item", "new_parent_item_id": "item", "include_only_item_ids": "item",
    "item_ids": "item",
    "file_blob_id": "file_blob", "photo_file_blob_id": "file_blob",
    "sketch_file_blob_id": "file_blob",
    "customer_id": "customer", "cost_center_id": "cost_center", "cut_plan_id": "cut_plan",
    "area_id": "area", "room_id": "room",
    "board_material_id": "board_material", "material_id": "board_material",
    "target_material_id": "board_material", "source_id": "hardware_material",
    "item_hardware_line_id": "hardware_line", "catalog_id": "catalog_row",
}

# Fields not probed at all, with the reason.
FIELD_REASONS = {
    "object_id": "comments: the kind depends on object_type",
    "parent_id": "comments: a comment id, scoped through its thread",
    "ordered_ids": "cut schedules: the probe has no schedule rows to reorder",
    "ordered_line_ids": "estimate lines: reordered within one revision",
    "include_line_ids": "estimate lines: selected within one revision",
}

# A body field that names the table the id belongs to is set to match its kind.
SIBLINGS = {
    "material_type": "BOARD", "material_table": "board_materials",
    "target_table": "board_materials", "source_table": "hardware_materials",
}

# Foreign ids that ARE answered differently from a nonexistent one today: real defects,
# recorded so the probe can pass while they are open. Must equal the computed set, so
# a new leak fails and a fixed one has to come off this list.
KNOWN_LEAKS: dict[tuple[str, str, str], str] = {
}

# Per-operation exceptions to the above. Keyed by (METHOD, path template).
OP_KIND = {("POST", "/lines/{lid}/hardware"): {"material_id": "hardware_material"}}
OP_SIBLINGS = {("POST", "/lines/{lid}/hardware"): {"material_type": "HARDWARE"}}
OP_BODY = {("POST", "/comments"): lambda a_rows: {"object_type": "project", "object_id": a_rows["project"]}}

# Path ids that must be a particular row for these operations to reach the body (material
# take lines can only be added to a draft take).
BODY_REAL_ID_QUERIES = {
    ("/material-takes/{tid}/lines", "tid"):
        "SELECT take_id FROM material_take WHERE status = 'draft' ORDER BY 1 LIMIT 1",
    ("/material-takes/{tid}/lines/{lid}", "tid"):
        "SELECT take_id FROM material_take WHERE status = 'draft' ORDER BY 1 LIMIT 1",
    ("/material-takes/{tid}/lines/{lid}", "lid"):
        "SELECT line_id FROM material_take_line WHERE take_id ="
        " (SELECT take_id FROM material_take WHERE status = 'draft' ORDER BY 1 LIMIT 1) ORDER BY 1 LIMIT 1",
}

NOT_PROBED: dict[tuple[str, str, str], str] = {
    ("PATCH", "/comments/{cid}", "mentioned_user_ids"):
        "only a comment's author may edit it; no seeded comment is authored by the control admin",
    ("PATCH", "/material-takes/{tid}/lines/{lid}", "material_id"):
        "the seeded draft take's lines are generated, and their material fields are read-only",
    ("POST", "/procurement/approvals/{workflow_id}/decide", "approver_id"):
        "the seed has no approval workflows",
    ("POST", "/projects/{pid}/optimise", "include_only_item_ids"):
        "needs sheet stock for the SKU, which the seed does not have (NO_SHEET_SIZE)",
    ("POST", "/revisions/{rid}/link-supplier", "supplier_id"):
        "the seeded materials already have a supplier (ALREADY_LINKED)",
}


def _kinds(prop: dict) -> list:
    prop = resolve(prop)
    for key in ("anyOf", "oneOf"):
        if key in prop:
            return [k for option in prop[key] for k in _kinds(option)]
    if prop.get("type") == "array":
        return [f"list:{k}" for k in _kinds(prop["items"])]
    return [prop.get("type")]


def _fk_fields(schema: dict) -> dict[str, bool]:
    """field -> is it a list, for every body field that looks like a foreign key."""
    out = {}
    for name, prop in schema.get("properties", {}).items():
        looks_like_fk = (name in FIELD_KIND or name in FIELD_REASONS
                         or re.search(r"_ids?$", name) or name == "assigned_to")
        kinds = _kinds(prop)
        if looks_like_fk and ("integer" in kinds or "list:integer" in kinds):
            out[name] = "list:integer" in kinds
    return out


def _body_cases():
    """(method, path, op, {fk field: is_list}, required fields) for every JSON-body operation."""
    for method, path, op in operations(path_params_only=False):
        content = (op.get("requestBody") or {}).get("content", {})
        if "application/json" not in content:
            continue
        schema = resolve(content["application/json"]["schema"])
        fields = _fk_fields(schema)
        if fields:
            yield method, path, op, fields, set(schema.get("required", [])), set(schema.get("properties", {}))


def _scalar(db, sql: str, **params):
    return db.execute(text(sql), params).scalar()


def _rows_of_a(db, wid: int) -> dict[str, int]:
    q = {
        "user": "SELECT id FROM app_user WHERE workspace_id = :w AND auth_role = 'editor' ORDER BY id LIMIT 1",
        "shop_worker": "SELECT id FROM app_user WHERE workspace_id = :w AND is_shop_worker ORDER BY id LIMIT 1",
        "vendor": "SELECT vendor_id FROM vendors WHERE workspace_id = :w ORDER BY 1 LIMIT 1",
        "project": "SELECT project_id FROM projects WHERE workspace_id = :w ORDER BY 1 LIMIT 1",
        "item": "SELECT i.item_id FROM items i JOIN projects p ON p.project_id = i.project_id"
                " WHERE p.workspace_id = :w AND i.row_type = 'joinery_item' ORDER BY i.item_id LIMIT 1",
        "file_blob": "SELECT file_blob_id FROM file_blob WHERE workspace_id = :w ORDER BY 1 LIMIT 1",
        "customer": "SELECT customer_id FROM customer WHERE workspace_id = :w ORDER BY 1 LIMIT 1",
        "cost_center": "SELECT cost_center_id FROM cost_centers WHERE workspace_id = :w ORDER BY 1 LIMIT 1",
        "cut_plan": "SELECT id FROM cut_plan WHERE workspace_id = :w ORDER BY 1 LIMIT 1",
        "area": "SELECT a.area_id FROM area a JOIN projects p ON p.project_id = a.project_id"
                " WHERE p.workspace_id = :w ORDER BY 1 LIMIT 1",
        "room": "SELECT r.room_id FROM room r JOIN area a ON a.area_id = r.area_id"
                " JOIN projects p ON p.project_id = a.project_id WHERE p.workspace_id = :w ORDER BY 1 LIMIT 1",
        "board_material": "SELECT material_id FROM board_materials WHERE workspace_id = :w ORDER BY 1 LIMIT 1",
        "hardware_material": "SELECT material_id FROM hardware_materials WHERE workspace_id = :w ORDER BY 1 LIMIT 1",
        "hardware_line": "SELECT l.line_id FROM item_hardware_lines l JOIN items i ON i.item_id = l.item_id"
                         " JOIN projects p ON p.project_id = i.project_id WHERE p.workspace_id = :w ORDER BY 1 LIMIT 1",
        "catalog_row": "SELECT c.catalog_id FROM project_hardware_catalog c JOIN projects p"
                       " ON p.project_id = c.project_id WHERE p.workspace_id = :w ORDER BY 1 LIMIT 1",
    }
    return {kind: _scalar(db, sql, w=wid) for kind, sql in q.items()}


def _rows_of_b(db, wid: int, uid: int) -> dict[str, int]:
    """One row of each kind in workspace B (whose only existing row is its admin)."""
    def one(sql, **p):
        return db.execute(text(sql), {"w": wid, "u": uid, **p}).scalar()

    project = one("INSERT INTO projects(project_code, name, pm_id, workspace_id)"
                  " VALUES ('B-1', 'B project', :u, :w) RETURNING project_id")
    item = one("INSERT INTO items(num, project_id, description, status)"
               " VALUES (nextval('joinery_number_seq'), :p, 'B item', 'CLEAR') RETURNING item_id", p=project)
    area = one("INSERT INTO area(project_id, name) VALUES (:p, 'B area') RETURNING area_id", p=project)
    board = one("INSERT INTO board_materials(code, description, workspace_id, sku, unit_cost)"
                " VALUES ('B-BRD', 'B board', :w, 'B-BRD', 1) RETURNING material_id")
    catalog = one("INSERT INTO project_hardware_catalog(project_id, material_type, material_id, added_by)"
                  " VALUES (:p, 'BOARD', :m, :u) RETURNING catalog_id", p=project, m=board)
    return {
        "user": uid,
        "shop_worker": one(
            "INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role, is_shop_worker)"
            " VALUES (:w, 'b-worker@probe.test', 'B worker', 'x', 'editor', true) RETURNING id"),
        "vendor": one("INSERT INTO vendors(name, category, workspace_id)"
                      " VALUES ('B vendor', 'Board', :w) RETURNING vendor_id"),
        "project": project,
        "item": item,
        "file_blob": one(
            "INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename,"
            " storage_key, uploaded_by) VALUES (:w, 'bbbb', 'application/pdf', 10, 'b.pdf', 'b', :u)"
            " RETURNING file_blob_id"),
        "customer": one("INSERT INTO customer(workspace_id, name) VALUES (:w, 'B customer')"
                        " RETURNING customer_id"),
        "cost_center": one(
            "INSERT INTO cost_centers(workspace_id, code, name, fiscal_year, budget_amount)"
            " VALUES (:w, 'BCC', 'B cost centre', 2026, 1) RETURNING cost_center_id"),
        "cut_plan": one("INSERT INTO cut_plan(workspace_id, project_id, name) VALUES (:w, :p, 'B plan')"
                        " RETURNING id", p=project),
        "area": area,
        "room": one("INSERT INTO room(area_id, rm_no) VALUES (:a, 'B1') RETURNING room_id", a=area),
        "board_material": board,
        "hardware_material": one(
            "INSERT INTO hardware_materials(sku, description, workspace_id, unit_cost)"
            " VALUES ('B-HW', 'B hardware', :w, 1) RETURNING material_id"),
        "hardware_line": one("INSERT INTO item_hardware_lines(item_id, catalog_id, qty)"
                             " VALUES (:i, :c, 1) RETURNING line_id", i=item, c=catalog),
        "catalog_row": catalog,
    }


def _kind(method: str, path: str, field: str) -> str:
    return OP_KIND.get((method, path), {}).get(field, FIELD_KIND[field])


def _body_patch(method: str, path: str, fields: dict[str, bool], required: set, props: set,
                a_rows: dict, probed: str, value) -> dict:
    """Every required FK field set to A's row, sibling table names to match, and the
    probed field to `value`."""
    patch = {name: ([a_rows[_kind(method, path, name)]] if is_list else a_rows[_kind(method, path, name)])
             for name, is_list in fields.items() if name in required and name in FIELD_KIND}
    patch.update({k: v for k, v in SIBLINGS.items() if k in props})
    patch.update(OP_SIBLINGS.get((method, path), {}))
    if (method, path) in OP_BODY:
        patch.update(OP_BODY[(method, path)](a_rows))
    patch[probed] = [value] if fields[probed] else value
    return patch


def test_foreign_ids_in_a_body_look_like_nonexistent_ones(truncate_all, monkeypatch, tmp_path):
    # A route that crashes on a bad id must show up as a leak below, not abort the run.
    admin_a = prepare_workspace_a(truncate_all, monkeypatch, tmp_path, raise_server_exceptions=False)
    _, wid_b, uid_b = login("admin", prefix="probe-b")
    with SessionLocal() as db:
        wid_a = _scalar(db, "SELECT id FROM workspace WHERE slug = 'hartwood-joinery'")
        a_rows = _rows_of_a(db, wid_a)
        b_rows = _rows_of_b(db, wid_b, uid_b)
        db.commit()
        real_ids = {key: _scalar(db, sql)
                    for key, sql in {**REAL_ID_QUERIES, **BODY_REAL_ID_QUERIES}.items()}
    missing = sorted(k for k, v in a_rows.items() if v is None)
    assert not missing, f"the seed has no row of these kinds: {missing}"

    cases = list(_body_cases())
    unmapped = sorted({f for *_, fields, _req, _props in cases for f in fields
                       if f not in FIELD_KIND and f not in FIELD_REASONS})
    assert not unmapped, (
        "New body fields that look like foreign keys: add each to FIELD_KIND (the kind of "
        f"row it points at) or FIELD_REASONS (why it is not probed): {unmapped}"
    )

    pairs = [(method, path, field, op, fields, required, props)
             for method, path, op, fields, required, props in cases
             for field in fields if field in FIELD_KIND]

    def call(method, path, op, fields, required, props, field, value):
        path_ids = ids_for(path, True, real_ids)
        patch = _body_patch(method, path, fields, required, props, a_rows, field, value)
        response = request(admin_a, method, path, op, path_ids, body_patch=patch)
        return response, {**path_ids, "fk": value}

    leaks, answers, unbuildable, crashes = {}, {}, set(), []
    for method, path, field, op, fields, required, props in pairs:
        kind = _kind(method, path, field)
        foreign, foreign_ids = call(method, path, op, fields, required, props, field, b_rows[kind])
        ghost, ghost_ids = call(method, path, op, fields, required, props, field, GHOST_ID)
        if foreign is None or ghost is None:
            unbuildable.add((method, path, field))
            continue
        crashes += filter(None, [crash(f"{method} {path} [{field}] (foreign {kind})", foreign),
                                 crash(f"{method} {path} [{field}] (nonexistent)", ghost)])
        answers[(method, path, field)] = answer(ghost, ghost_ids)
        if answer(foreign, foreign_ids) != answer(ghost, ghost_ids):
            leaks[(method, path, field)] = (
                f"{method} {path} [{field}]: another workspace's {kind} -> "
                f"{foreign.status_code} {foreign.text[:100]}, nonexistent id -> {ghost.status_code}")
    new_leaks = [msg for key, msg in leaks.items() if key not in KNOWN_LEAKS]
    assert not new_leaks, (
        "A row of another workspace in a request body must be answered exactly like a row "
        "that does not exist:\n  " + "\n  ".join(new_leaks)
    )
    fixed = sorted(set(KNOWN_LEAKS) - set(leaks))
    assert not fixed, (
        "These KNOWN_LEAKS no longer leak; remove them:\n  "
        + "\n  ".join(f"{m} {p} [{f}]" for m, p, f in fixed)
    )

    no_signal = set(unbuildable)
    for method, path, field, op, fields, required, props in pairs:
        if (method, path, field) in unbuildable:
            continue
        control, control_ids = call(method, path, op, fields, required, props, field,
                                    a_rows[_kind(method, path, field)])
        crashes += filter(None, [crash(f"{method} {path} [{field}] (own row)", control)])
        if answer(control, control_ids) == answers[(method, path, field)]:
            no_signal.add((method, path, field))

    assert not crashes, "No probe request may crash the server (5xx):\n  " + "\n  ".join(crashes)

    unlisted = sorted(no_signal - set(NOT_PROBED))
    stale = sorted(set(NOT_PROBED) - no_signal)
    assert not unlisted, (
        "These (operation, field) pairs were not really probed: A's own row is answered like "
        "a nonexistent one (a body the generator cannot fill, or no row in the seed). Make "
        "them probable or list them in NOT_PROBED with the reason:\n  "
        + "\n  ".join(f"{m} {p} [{f}]" for m, p, f in unlisted)
    )
    assert not stale, (
        "These NOT_PROBED entries are probed now (or no longer exist); remove them:\n  "
        + "\n  ".join(f"{m} {p} [{f}]" for m, p, f in stale)
    )


# The routes that take a catalog material in the body: (method, path, field).
_MATERIAL_ROUTES = (
    ("POST", "/modules/{mid}/parts", "board_material_id"),
    ("PATCH", "/parts/{pid}", "board_material_id"),
    ("POST", "/batches", "material_id"),
    ("POST", "/orders/{po_id}/lines", "material_id"),
    ("POST", "/material-takes/{tid}/lines", "material_id"),
    ("PATCH", "/material-takes/{tid}/lines/{lid}", "material_id"),
    ("POST", "/catalog/cv-mappings", "target_material_id"),
    ("PATCH", "/catalog/cv-mappings/{mid}", "target_material_id"),
)

# Everything those routes could write a material id (or a new row) into.
_MATERIAL_SNAPSHOT = """
    SELECT (SELECT count(*) FROM parts), (SELECT coalesce(sum(board_material_id), 0) FROM parts),
           (SELECT count(*) FROM procurement_batches), (SELECT count(*) FROM po_line_items),
           (SELECT count(*) FROM material_take_line),
           (SELECT coalesce(sum(material_id), 0) FROM material_take_line),
           (SELECT count(*) FROM cv_material_mapping),
           (SELECT coalesce(sum(target_material_id), 0) FROM cv_material_mapping)
"""


def test_a_material_of_another_workspace_is_a_404_and_writes_nothing(truncate_all, monkeypatch, tmp_path):
    """A material that is another workspace's, or that does not exist, is refused with
    404 MATERIAL_NOT_FOUND on every route that takes one, before anything is written."""
    admin_a = prepare_workspace_a(truncate_all, monkeypatch, tmp_path, raise_server_exceptions=False)
    _, wid_b, uid_b = login("admin", prefix="probe-b")
    with SessionLocal() as db:
        a_rows = _rows_of_a(db, _scalar(db, "SELECT id FROM workspace WHERE slug = 'hartwood-joinery'"))
        b_rows = _rows_of_b(db, wid_b, uid_b)
        db.commit()
        real_ids = {key: _scalar(db, sql)
                    for key, sql in {**REAL_ID_QUERIES, **BODY_REAL_ID_QUERIES}.items()}
    operations_by_key = {(m, p): (op, fields, required, props)
                         for m, p, op, fields, required, props in _body_cases()}

    # A manual take line of A's, so the PATCH route has a line whose material may change.
    tid = real_ids[("/material-takes/{tid}/lines", "tid")]
    line = admin_a.post(f"/material-takes/{tid}/lines", json={
        "material_type": "BOARD", "material_id": a_rows["board_material"], "description": "manual",
        "unit": "sheet", "qty": 1, "wastage_pct": 0})
    assert line.status_code == 201, line.text
    real_ids[("/material-takes/{tid}/lines/{lid}", "lid")] = line.json()["line_id"]

    def snapshot():
        with SessionLocal() as db:
            return tuple(db.execute(text(_MATERIAL_SNAPSHOT)).one())

    for method, path, field in _MATERIAL_ROUTES:
        op, fields, required, props = operations_by_key[(method, path)]
        for what, value in (("another workspace's", b_rows["board_material"]), ("nonexistent", GHOST_ID)):
            before = snapshot()
            response = request(admin_a, method, path, op, ids_for(path, True, real_ids),
                               body_patch=_body_patch(method, path, fields, required, props,
                                                      a_rows, field, value))
            assert response.status_code == 404, f"{method} {path} with {what} material: {response.text}"
            assert response.json()["detail"]["code"] == "MATERIAL_NOT_FOUND", \
                f"{method} {path} with {what} material: {response.text}"
            assert snapshot() == before, f"{method} {path} with {what} material changed data"
