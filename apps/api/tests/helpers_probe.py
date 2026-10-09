"""Shared machinery for the cross-workspace probes (test_workspace_isolation_*probe.py):
the OpenAPI walker, a minimal-body generator, request building and answer masking."""
import contextlib
import io
import re
import sys
from pathlib import Path

from sqlalchemy import text

from app.db import SessionLocal
from app.main import app

from .helpers import log_in

# Tables the standard TRUNCATE does not reach.
CLEANUP_TABLES = ("budget_transactions", "cost_centers")

GHOST_ID = 2_000_000_000
# Workspace A's own admin (the seed gives them a notification); the control user.
ADMIN_A_EMAIL = "aria.voss@hartwood.test"
REAL_ID = 1  # the seed runs on freshly truncated tables, so most rows start at 1

# Path-parameter values that are not ids.
PATH_VALUES = {
    "kind": "cv_drawing",
    "material_type": "BOARD",
    "stage_key": "REQ",
    "table": "board_materials",
    "slug": "board-materials",
}

# Fields the generic body builder cannot guess (a pattern, an enum, a non-empty
# patch), merged over the generated body. Keyed by (METHOD, path template).
BODY_OVERRIDES = {
    ("POST", "/projects/{pid}/samples"): {"hex_swatch": "#aabbcc"},
    ("PATCH", "/samples/{sid}"): {"title": "x"},
    ("PATCH", "/users/{uid}"): {"full_name": "x"},
    ("POST", "/items/{iid}/qc/rework"): {"kind": "internal"},
    ("POST", "/suppliers/{vendor_id}/materials"): {"material_table": "board_materials"},
}

# Where id 1 is not the right kind of row (it is an ordinary item, not a related part;
# an editor, not a shop worker), pick a real one from workspace A. Keyed by
# (path template, parameter name).
REAL_ID_QUERIES = {
    ("/related-parts/{rid}", "rid"):
        "SELECT item_id FROM items WHERE row_type = 'related_part' ORDER BY item_id LIMIT 1",
    ("/related-parts/{rid}/reparent", "rid"):
        "SELECT item_id FROM items WHERE row_type = 'related_part' ORDER BY item_id LIMIT 1",
    ("/notifications/{nid}/read", "nid"):
        "SELECT n.notification_id FROM notification n JOIN app_user u ON u.id = n.recipient_id"
        f" WHERE u.email = '{ADMIN_A_EMAIL}' ORDER BY 1 LIMIT 1",
    ("/lock-requests/{rid}/approve", "rid"):
        "SELECT request_id FROM item_lock_request WHERE status = 'pending' ORDER BY request_id LIMIT 1",
    ("/lock-requests/{rid}/reject", "rid"):
        "SELECT request_id FROM item_lock_request WHERE status = 'pending' ORDER BY request_id LIMIT 1",
    ("/workers/{wid}/queue", "wid"):
        "SELECT id FROM app_user WHERE is_shop_worker ORDER BY id LIMIT 1",
    ("/workers/{wid}/recent-completions", "wid"):
        "SELECT id FROM app_user WHERE is_shop_worker ORDER BY id LIMIT 1",
}

METHODS = ("get", "post", "put", "patch", "delete")

PERMISSION_GROUP_OPS = (
    ("POST", "/permission-groups/{gid}/memberships"),
    ("DELETE", "/permission-groups/memberships/{mid}"),
    ("PUT", "/permission-groups/{gid}/grants"),
    ("DELETE", "/permission-groups/{gid}"),
)

# Deleting these removes rows other deletes need, so they run last, children first.
DELETE_PARENTS = ("/parts/{pid}", "/modules/{mid}", "/items/{id}", "/cutlists/{cid}",
                   "/orders/{po_id}", "/cut-plans/{plan_id}",
                   "/batches/{bid}", "/permission-groups/{gid}")


def seed_workspace_a() -> None:
    try:
        from seed import hartwood_joinery
    except ImportError:  # run outside the container: the seed lives at the repo root
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from seed import hartwood_joinery
    with contextlib.redirect_stdout(io.StringIO()):
        hartwood_joinery.main()


def schemas() -> dict:
    return app.openapi().get("components", {}).get("schemas", {})


def resolve(schema: dict) -> dict:
    while "$ref" in schema:
        schema = schemas()[schema["$ref"].split("/")[-1]]
    return schema


def example(schema: dict, depth: int = 0):
    """The smallest value that satisfies `schema`'s required parts."""
    schema = resolve(schema)
    options = schema.get("anyOf") or schema.get("oneOf")
    if options:
        non_null = [o for o in options if resolve(o).get("type") != "null"]
        return example(non_null[0], depth) if non_null else None
    if "allOf" in schema:
        return example(schema["allOf"][0], depth)
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        return {k: (example(schema["properties"][k], depth + 1) if depth < 6 else None)
                for k in schema.get("required", [])}
    if kind == "string":
        return {"date": "2026-01-01", "date-time": "2026-01-01T00:00:00Z",
                "email": "x@probe.test"}.get(schema.get("format"), "x")
    if kind in ("integer", "number"):
        return 1
    if kind == "boolean":
        return False
    if kind == "array":
        return [example(schema["items"], depth + 1)] if schema.get("minItems", 0) > 0 else []
    return None


def operations(path_params_only: bool = True) -> list[tuple[str, str, dict]]:
    """(METHOD, path template, operation) for every operation with a path parameter (or
    every operation), ordered so a probe cannot remove the rows a later probe needs:
    reads, then writes, then deletes with children before parents."""
    ops = [(m.upper(), p, op)
           for p, item in app.openapi()["paths"].items() if "{" in p or not path_params_only
           for m, op in item.items() if m in METHODS]
    rank = {"GET": 0, "POST": 1, "PUT": 1, "PATCH": 1, "DELETE": 2}

    def order(o):
        method, path, _ = o
        if (method, path) in PERMISSION_GROUP_OPS:
            # Changing a group's grants or members changes what the control user (a
            # member of the Admin group) may do, so these run after everything else,
            # members before grants and the group itself last.
            return (100 + PERMISSION_GROUP_OPS.index((method, path)), path)
        if method == "DELETE" and path in DELETE_PARENTS:
            return (3 + DELETE_PARENTS.index(path), path)
        return (rank[method], path)

    return sorted(ops, key=order)


def ids_for(path: str, real: bool, real_ids: dict) -> dict[str, int]:
    """The value for each path parameter: the real row's id, or the ghost id."""
    return {n: (real_ids.get((path, n), REAL_ID) if real else GHOST_ID)
            for n in re.findall(r"\{(\w+)\}", path)}


def multipart(schema: dict) -> tuple[dict, dict]:
    """(files, data) for a multipart body: a tiny PDF for each binary field, an example for the rest."""
    schema = resolve(schema)
    files, data = {}, {}
    for name, prop in schema.get("properties", {}).items():
        prop = resolve(prop)
        if prop.get("format") == "binary" or "contentMediaType" in prop:  # OpenAPI 3.0 / 3.1
            files[name] = ("probe.pdf", b"%PDF-1.4\n%probe\n%%EOF\n", "application/pdf")
        elif name in schema.get("required", []):
            data[name] = example(prop)
    return files, data


def request(client, method: str, path: str, op: dict, ids: dict[str, int],
            body_patch: dict | None = None, query_patch: dict | None = None):
    """Call `op` with `ids` in the path slots (`body_patch` merged into a JSON body,
    `query_patch` into the query string); None if no request can be built."""
    url = re.sub(r"\{(\w+)\}", lambda m: str(PATH_VALUES.get(m.group(1), ids[m.group(1)])), path)
    kwargs = {}
    request_body = op.get("requestBody")
    if request_body:
        content = request_body["content"]
        if "application/json" in content:
            body = example(content["application/json"]["schema"])
            if isinstance(body, dict):
                body.update(BODY_OVERRIDES.get((method, path), {}))
                body.update(body_patch or {})
            kwargs["json"] = body
        elif "multipart/form-data" in content:
            kwargs["files"], kwargs["data"] = multipart(content["multipart/form-data"]["schema"])
        else:
            return None
    required_query = {
        p["name"]: PATH_VALUES.get(p["name"]) or example(p["schema"])
        for p in op.get("parameters", []) if p["in"] == "query" and p.get("required")
    }
    if required_query or query_patch:
        kwargs["params"] = {**required_query, **(query_patch or {})}
    return client.request(method, url, **kwargs)


def answer(response, ids: dict[str, int]) -> tuple[int, str]:
    """Status and body with the probed ids masked, so 'item 1' and 'item 2000000000' compare equal."""
    body = response.text
    for value in set(ids.values()):
        body = re.sub(rf"(?<!\d){value}(?!\d)", "<ID>", body)
    return response.status_code, body


def prepare_workspace_a(truncate_all, monkeypatch, tmp_path, *, raise_server_exceptions: bool = True):
    """Empty the tables, seed workspace A and log in as its seeded admin -> client.

    cost_centers and budget_transactions are not reached by the standard TRUNCATE, so
    a test using this must also clean them (`truncate_fixture(*CLEANUP_TABLES)`).
    """
    truncate_all()
    with SessionLocal() as db:
        db.execute(text("TRUNCATE budget_transactions, cost_centers RESTART IDENTITY CASCADE"))
        db.commit()
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    seed_workspace_a()
    return log_in("hartwood-joinery", ADMIN_A_EMAIL, "hartwood-dev",
                  raise_server_exceptions=raise_server_exceptions)


def crash(label: str, response) -> str | None:
    """A note if `response` is a server error (5xx), else None. A route that crashes on a
    bad id answers the real and the ghost id alike, so the foreign-vs-ghost comparison
    alone would pass it."""
    if response is not None and response.status_code >= 500:
        return f"{label} -> {response.status_code} {response.text[:100]}"
    return None


# Body field -> the kind of row it points at.
FIELD_KIND = {
    "assigned_to": "user", "pm_id": "user", "user_id": "user",
    "requester_id": "user", "approver_id": "admin_user", "reviewer_id": "user", "contractor_id": "user",
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


def scalar(db, sql: str, **params):
    return db.execute(text(sql), params).scalar()


def rows_of_a(db, wid: int) -> dict[str, int]:
    q = {
        "user": "SELECT id FROM app_user WHERE workspace_id = :w AND auth_role = 'editor' ORDER BY id LIMIT 1",
        "admin_user": "SELECT id FROM app_user WHERE workspace_id = :w AND auth_role = 'admin' ORDER BY id LIMIT 1",
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
    return {kind: scalar(db, sql, w=wid) for kind, sql in q.items()}


def rows_of_b(db, wid: int, uid: int) -> dict[str, int]:
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
        "admin_user": uid,
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
