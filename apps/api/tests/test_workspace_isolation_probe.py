"""Cross-workspace probe of every id-parameterised route.

The invariant (CLAUDE.md §7): another workspace's row is a 404, never a 403, a 200
or any other answer that tells the caller the row exists. Hand-written isolation
tests cover the routes someone remembered; this one covers every operation in the
OpenAPI schema that has a path parameter, including routes added later.

For each operation, a user of a *different* workspace (B) calls it with an id that
exists in workspace A (the dev seed) and with an id that exists nowhere. The two
answers must be identical (status and body, ids aside). Anything else is a leak:
the route told B something about A's row.

A probe only means something if the row really exists, so each operation is also
called as an admin of A. If A cannot tell the real id from the ghost one either
(no seeded row, a body the generator cannot fill, a non-JSON body) the operation
has *no signal*: it must be listed in NOT_PROBED with a reason. The list has to
match exactly: a new route that cannot be probed fails here until someone either
makes it probable (seed data, BODY_OVERRIDES) or writes a dedicated test and
lists it, and a listed route that becomes probable must come off the list.

Not covered: foreign ids inside a request *body* (the path check answers first),
and routes with no path parameter (they are scoped by the caller's own workspace).
"""
import contextlib
import io
import re
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.main import app

from .helpers import login

pytestmark = pytest.mark.usefixtures("truncate_after")

GHOST_ID = 2_000_000_000
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
    ("POST", "/procurement/approvals/{workflow_id}/decide"): {"decision": "approve"},
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
    ("/workers/{wid}/queue", "wid"):
        "SELECT id FROM app_user WHERE is_shop_worker ORDER BY id LIMIT 1",
    ("/workers/{wid}/recent-completions", "wid"):
        "SELECT id FROM app_user WHERE is_shop_worker ORDER BY id LIMIT 1",
}

# Operations that cannot be probed, with the reason. Must equal the computed set.
NOT_PROBED: dict[tuple[str, str], str] = {
    # The path parameter is a catalog type, not a row id; the routes create rows in the
    # caller's own workspace, so there is no foreign row to find.
    ("POST", "/catalog/{slug}"): "slug is a catalog type, not a row id",
    ("POST", "/catalog/{slug}/bulk"): "slug is a catalog type, not a row id",
    # Covered by a dedicated test: test_lock_semantics.test_lock_request_is_workspace_isolated.
    ("POST", "/lock-requests/{rid}/approve"): "seed has no lock requests; dedicated test exists",
    ("POST", "/lock-requests/{rid}/reject"): "seed has no lock requests; dedicated test exists",
    # Covered by test_procurement_routes.test_decide_approval_cross_workspace_is_404.
    ("POST", "/procurement/approvals/{workflow_id}/decide"):
        "seed has no approval workflows; dedicated test exists",
    # GAPS: no dedicated cross-workspace test (only the attachment *list* has one).
    ("GET", "/procurement/orders/{po_id}/attachments/{attachment_id}/download"):
        "GAP: seed has no PO attachments, no dedicated test",
    ("DELETE", "/procurement/orders/{po_id}/attachments/{attachment_id}"):
        "GAP: seed has no PO attachments, no dedicated test",
    ("POST", "/procurement/orders/{po_id}/attachments"):
        "GAP: multipart body the generator cannot build, no dedicated test",
    ("GET", "/procurement/budget/{cost_center_id}/transactions"):
        "GAP: seed has no cost centres; answers [] for any id, no dedicated test",
    ("POST", "/notifications/{nid}/read"):
        "GAP: the seed's notifications belong to other users; per-recipient, no dedicated test",
}

_METHODS = ("get", "post", "put", "patch", "delete")

# Deleting these removes rows other deletes need, so they run last, children first.
_DELETE_PARENTS = ("/parts/{pid}", "/modules/{mid}", "/items/{id}", "/cutlists/{cid}",
                   "/orders/{po_id}", "/procurement/orders/{po_id}", "/cut-plans/{plan_id}",
                   "/batches/{bid}", "/permission-groups/{gid}")


def _seed_workspace_a() -> None:
    try:
        from seed import hartwood_joinery
    except ImportError:  # run outside the container: the seed lives at the repo root
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from seed import hartwood_joinery
    with contextlib.redirect_stdout(io.StringIO()):
        hartwood_joinery.main()


def _schemas() -> dict:
    return app.openapi().get("components", {}).get("schemas", {})


def _resolve(schema: dict) -> dict:
    while "$ref" in schema:
        schema = _schemas()[schema["$ref"].split("/")[-1]]
    return schema


def _example(schema: dict, depth: int = 0):
    """The smallest value that satisfies `schema`'s required parts."""
    schema = _resolve(schema)
    options = schema.get("anyOf") or schema.get("oneOf")
    if options:
        non_null = [o for o in options if _resolve(o).get("type") != "null"]
        return _example(non_null[0], depth) if non_null else None
    if "allOf" in schema:
        return _example(schema["allOf"][0], depth)
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        return {k: (_example(schema["properties"][k], depth + 1) if depth < 6 else None)
                for k in schema.get("required", [])}
    if kind == "string":
        return {"date": "2026-01-01", "date-time": "2026-01-01T00:00:00Z",
                "email": "x@probe.test"}.get(schema.get("format"), "x")
    if kind in ("integer", "number"):
        return 1
    if kind == "boolean":
        return False
    if kind == "array":
        return [_example(schema["items"], depth + 1)] if schema.get("minItems", 0) > 0 else []
    return None


def _operations() -> list[tuple[str, str, dict]]:
    """(METHOD, path template, operation) for every operation with a path parameter,
    ordered so a probe cannot remove the rows a later probe needs: reads, then
    writes, then deletes with children before parents."""
    ops = [(m.upper(), p, op)
           for p, item in app.openapi()["paths"].items() if "{" in p
           for m, op in item.items() if m in _METHODS]
    rank = {"GET": 0, "POST": 1, "PUT": 1, "PATCH": 1, "DELETE": 2}

    def order(o):
        method, path, _ = o
        if method == "DELETE" and path in _DELETE_PARENTS:
            return (3 + _DELETE_PARENTS.index(path), path)
        return (rank[method], path)

    return sorted(ops, key=order)


def _ids(path: str, real: bool, real_ids: dict) -> dict[str, int]:
    """The value for each path parameter: the real row's id, or the ghost id."""
    return {n: (real_ids.get((path, n), REAL_ID) if real else GHOST_ID)
            for n in re.findall(r"\{(\w+)\}", path)}


def _request(client, method: str, path: str, op: dict, ids: dict[str, int]):
    """Call `op` with `ids` in the path slots; None if no request can be built."""
    url = re.sub(r"\{(\w+)\}", lambda m: str(PATH_VALUES.get(m.group(1), ids[m.group(1)])), path)
    kwargs = {}
    request_body = op.get("requestBody")
    if request_body:
        content = request_body["content"]
        if "application/json" not in content:
            return None
        body = _example(content["application/json"]["schema"])
        if isinstance(body, dict):
            body.update(BODY_OVERRIDES.get((method, path), {}))
        kwargs["json"] = body
    required_query = {
        p["name"]: PATH_VALUES.get(p["name"]) or _example(p["schema"])
        for p in op.get("parameters", []) if p["in"] == "query" and p.get("required")
    }
    if required_query:
        kwargs["params"] = required_query
    return client.request(method, url, **kwargs)


def _answer(response, ids: dict[str, int]) -> tuple[int, str]:
    """Status and body with the probed ids masked, so 'item 1' and 'item 2000000000' compare equal."""
    body = response.text
    for value in set(ids.values()):
        body = re.sub(rf"(?<!\d){value}(?!\d)", "<ID>", body)
    return response.status_code, body


def test_another_workspace_cannot_tell_a_row_exists(truncate_all, monkeypatch, tmp_path):
    truncate_all()
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    _seed_workspace_a()
    with SessionLocal() as db:
        wid_a = db.execute(text("SELECT id FROM workspace WHERE slug = 'hartwood-joinery'")).scalar()
    admin_a, _, _ = login("admin", wid=wid_a)
    admin_b, _, _ = login("admin", prefix="probe-b")

    with SessionLocal() as db:
        real_ids = {key: db.execute(text(sql)).scalar() for key, sql in REAL_ID_QUERIES.items()}
    assert all(real_ids.values()), f"the seed no longer has the rows REAL_ID_QUERIES picks: {real_ids}"

    operations = _operations()
    leaks, unbuildable = [], set()

    for method, path, op in operations:
        real_ids_for, ghost_ids = _ids(path, True, real_ids), _ids(path, False, real_ids)
        real = _request(admin_b, method, path, op, real_ids_for)
        ghost = _request(admin_b, method, path, op, ghost_ids)
        if real is None or ghost is None:
            unbuildable.add((method, path))
            continue
        if _answer(real, real_ids_for) != _answer(ghost, ghost_ids):
            leaks.append(f"{method} {path}: foreign id -> {real.status_code} {real.text[:100]}, "
                         f"nonexistent id -> {ghost.status_code}")

    assert not leaks, (
        "Another workspace's row must look exactly like a row that does not exist:\n  "
        + "\n  ".join(leaks)
    )

    # Which operations did the probe above actually exercise? Only those where A's own
    # admin sees a difference between the real row and the ghost one.
    no_signal = set(unbuildable)
    for method, path, op in operations:
        if (method, path) in unbuildable:
            continue
        real_ids_for, ghost_ids = _ids(path, True, real_ids), _ids(path, False, real_ids)
        real = _request(admin_a, method, path, op, real_ids_for)
        ghost = _request(admin_a, method, path, op, ghost_ids)
        if _answer(real, real_ids_for) == _answer(ghost, ghost_ids):
            no_signal.add((method, path))

    unlisted = sorted(no_signal - set(NOT_PROBED))
    stale = sorted(set(NOT_PROBED) - no_signal)
    assert not unlisted, (
        "These operations were not really probed (no seeded row, a body the generator "
        "cannot fill, or a non-JSON body). Make them probable (seed data or "
        "BODY_OVERRIDES) or write a dedicated cross-workspace test and list them in "
        "NOT_PROBED with the reason:\n  " + "\n  ".join(f"{m} {p}" for m, p in unlisted)
    )
    assert not stale, (
        "These NOT_PROBED entries are probed now (or no longer exist); remove them:\n  "
        + "\n  ".join(f"{m} {p}" for m, p in stale)
    )
