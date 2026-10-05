"""Cross-workspace probe of foreign ids in the query string.

The third way in, next to the path (test_workspace_isolation_probe.py) and the body
(test_workspace_isolation_body_probe.py): a list or filter such as `GET /batches?project_id=`
or `GET /estimates?customer_id=` that is handed another workspace's id. A route that
forgets the workspace check either returns the other workspace's rows or answers
differently for that id than for one that does not exist.

Same oracle as the other probes: the foreign and the nonexistent id must be answered
identically (status and body, ids masked), the control must differ from them (otherwise
the pair has no signal and is listed in NOT_PROBED with the reason), and any 5xx fails.

Who calls depends on the operation. A list with no path parameter (`GET /batches`) is not
scoped by anything but the caller's workspace, so the caller is workspace B's admin and the
id is a row of workspace A's, which has the data to leak. An operation with a path
parameter (`GET /projects/{pid}/shop-drawings`) is already scoped by that path, so the
caller is A's admin on A's own path and the filter id is a row of B's. The control is
always A's admin with A's own row.
"""
import re

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers import login
from .helpers_probe import (
    CLEANUP_TABLES, FIELD_KIND, GHOST_ID, REAL_ID_QUERIES, answer, crash, ids_for, operations,
    prepare_workspace_a, request, rows_of_a, rows_of_b, scalar,
)
_cleanup = truncate_fixture(*CLEANUP_TABLES)

# Query parameters not probed at all, with the reason.
PARAM_REASONS = {
    "include_line_ids": "estimate lines: selected within one revision, not a workspace-level id",
}

# Operations left out entirely, with the reason.
EXCLUDED_OPS = {
    ("GET", "/search"): "answers 503 without a live Meilisearch, so a probe means nothing; "
                        "test_search_routes covers workspace isolation and project_id on a fake index",
}

# Fixed companions of a parameter whose kind depends on another one, and the kind to use.
# Keyed by (METHOD, path template).
OP_QUERY = {("GET", "/comments"): ({"object_type": "project"}, {"object_id": "project"})}

# Where "any row of that kind" is not enough: the filter must name a row that the listed
# rows actually carry (the seeded purchase order's vendor and requester).
A_ROW_QUERIES = {
    ("GET", "/procurement/orders", "vendor_id"): "SELECT vendor_id FROM purchase_orders ORDER BY 1 LIMIT 1",
    ("GET", "/procurement/orders", "requester_id"): "SELECT requester_id FROM purchase_orders ORDER BY 1 LIMIT 1",
    ("GET", "/procurement/orders/filter/my-orders", "requester_id"):
        "SELECT requester_id FROM purchase_orders ORDER BY 1 LIMIT 1",
}

# (METHOD, path template, parameter) pairs that cannot be probed, with the reason.
NOT_PROBED: dict[tuple[str, str, str], str] = {
    ("GET", "/procurement/approvals/history", "approver_id"):
        "lists decided workflows; the seeded one is still pending",
}


def _query_params(op: dict) -> list[str]:
    return [p["name"] for p in op.get("parameters", [])
            if p["in"] == "query" and (p["name"] in FIELD_KIND or p["name"] in PARAM_REASONS
                                       or re.search(r"_ids?$", p["name"]) or p["name"] == "assigned_to")]


def _kind(method: str, path: str, param: str) -> str:
    return OP_QUERY.get((method, path), ({}, {}))[1].get(param, FIELD_KIND.get(param))


def test_foreign_ids_in_a_query_string_look_like_nonexistent_ones(truncate_all, monkeypatch, tmp_path):
    admin_a = prepare_workspace_a(truncate_all, monkeypatch, tmp_path, raise_server_exceptions=False)
    admin_b, wid_b, uid_b = login("admin", prefix="probe-b", raise_server_exceptions=False)
    with SessionLocal() as db:
        a_rows = rows_of_a(db, scalar(db, "SELECT id FROM workspace WHERE slug = 'hartwood-joinery'"))
        b_rows = rows_of_b(db, wid_b, uid_b)
        db.commit()
        real_ids = {key: scalar(db, sql) for key, sql in REAL_ID_QUERIES.items()}
        a_values = {key: scalar(db, sql) for key, sql in A_ROW_QUERIES.items()}

    cases = [(m, p, op, param) for m, p, op in operations(path_params_only=False)
             if (m, p) not in EXCLUDED_OPS for param in _query_params(op)]
    unmapped = sorted({param for m, p, _, param in cases
                       if _kind(m, p, param) is None and param not in PARAM_REASONS})
    assert not unmapped, (
        "New query parameters that look like ids: add each to helpers_probe.FIELD_KIND (the "
        f"kind of row it points at) or PARAM_REASONS (why it is not probed): {unmapped}"
    )
    pairs = [(m, p, op, param) for m, p, op, param in cases if param not in PARAM_REASONS]

    def a_row(method, path, param):
        return a_values.get((method, path, param), a_rows[_kind(method, path, param)])

    def call(client, method, path, op, param, value):
        path_ids = ids_for(path, True, real_ids)
        fixed = OP_QUERY.get((method, path), ({}, {}))[0]
        response = request(client, method, path, op, path_ids, query_patch={**fixed, param: value})
        return response, {**path_ids, "q": value}

    leaks, crashes = [], []
    for method, path, op, param in pairs:
        kind = _kind(method, path, param)
        if "{" in path:      # scoped by the path: A's admin, a row of B's in the filter
            caller, foreign_value = admin_a, b_rows[kind]
        else:                # scoped by the caller's workspace only: B's admin, a row of A's
            caller, foreign_value = admin_b, a_row(method, path, param)
        foreign, f_ids = call(caller, method, path, op, param, foreign_value)
        ghost, g_ids = call(caller, method, path, op, param, GHOST_ID)
        crashes += filter(None, [crash(f"{method} {path} ?{param} (foreign {kind})", foreign),
                                 crash(f"{method} {path} ?{param} (nonexistent)", ghost)])
        if answer(foreign, f_ids) != answer(ghost, g_ids):
            leaks.append(f"{method} {path} ?{param}: another workspace's {kind} -> "
                         f"{foreign.status_code} {foreign.text[:100]}, nonexistent id -> {ghost.status_code}")
    assert not leaks, (
        "Another workspace's id in a query string must be answered exactly like one that does "
        "not exist:\n  " + "\n  ".join(leaks)
    )

    # The control: A's admin with A's own row must be told apart from a nonexistent one.
    no_signal = set()
    for method, path, op, param in pairs:
        control, c_ids = call(admin_a, method, path, op, param, a_row(method, path, param))
        ghost, g_ids = call(admin_a, method, path, op, param, GHOST_ID)
        crashes += filter(None, [crash(f"{method} {path} ?{param} (own row, as A)", control)])
        if answer(control, c_ids) == answer(ghost, g_ids):
            no_signal.add((method, path, param))
    assert not crashes, "No probe request may crash the server (5xx):\n  " + "\n  ".join(crashes)

    unlisted = sorted(no_signal - set(NOT_PROBED))
    stale = sorted(set(NOT_PROBED) - no_signal)
    assert not unlisted, (
        "These (operation, parameter) pairs were not really probed: A's own row is answered like "
        "a nonexistent one (no data in the seed, or a request the generator cannot make valid). "
        "Make them probable or list them in NOT_PROBED with the reason:\n  "
        + "\n  ".join(f"{m} {p} ?{q}" for m, p, q in unlisted)
    )
    assert not stale, (
        "These NOT_PROBED entries are probed now (or no longer exist); remove them:\n  "
        + "\n  ".join(f"{m} {p} ?{q}" for m, p, q in stale)
    )
