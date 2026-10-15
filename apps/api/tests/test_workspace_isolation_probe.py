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
from sqlalchemy import text

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers_probe import (
    CLEANUP_TABLES, REAL_ID_QUERIES, answer, crash, ids_for, operations, prepare_workspace_a, request,
)
from .helpers import login

_cleanup = truncate_fixture(*CLEANUP_TABLES)

# Operations that cannot be probed, with the reason. Must equal the computed set.
_PO_REASON = ("the seed has no PO document; every operation is called by another workspace in "
              "test_purchase_order_documents.test_other_workspace_is_404")

_PO_WINDOWS = ("the seed has no PO document; called by another workspace in "
               "test_po_invoice_authorisation.test_other_workspace_is_404")

_TABS = ("the seed has no delivery, docket, logo or image; called by another workspace in "
         "test_order_tabs.test_other_workspace_is_404")

NOT_PROBED: dict[tuple[str, str], str] = {
    ("GET", "/orders/{po_id}/attachments/{attachment_id}/download"):
        "the seed has no order attachment; test_order_attachments.test_other_workspace_is_404 downloads one as another workspace",
    ("DELETE", "/orders/{po_id}/deliveries/{delivery_id}/docket"): _TABS,
    ("GET", "/orders/{po_id}/timber/form"): "the seed has no created form; called by another workspace in test_order_tabs_b.test_other_workspace_is_404",
    ("GET", "/orders/{po_id}/deliveries/{delivery_id}/docket"): _TABS,
    ("GET", "/suppliers/{vendor_id}/logo"): _TABS,
    ("PUT", "/orders/{po_id}/image"): _TABS,
    ("PUT", "/suppliers/{vendor_id}/logo"): _TABS,
    ("DELETE", "/purchase-orders/{doc_id}/authorisation/signed"): _PO_WINDOWS,
    ("DELETE", "/purchase-orders/{doc_id}/invoices/{invoice_id}/files/{slot}"): _PO_WINDOWS,
    ("GET", "/purchase-orders/staff/{user_id}/photo"):
        "the seed holds no photo; test_po_invoice_authorisation.test_other_workspace_is_404 reads one as another workspace",
    ("GET", "/purchase-orders/{doc_id}/authorisation"): _PO_WINDOWS,
    ("GET", "/purchase-orders/{doc_id}/authorisation/{which}"): _PO_WINDOWS,
    ("GET", "/purchase-orders/{doc_id}/invoices/{invoice_id}/files/{slot}"): _PO_WINDOWS,
    ("POST", "/purchase-orders/{doc_id}/authorisation/form"): _PO_WINDOWS,
    ("POST", "/purchase-orders/{doc_id}/authorisation/signed"): _PO_WINDOWS,
    ("POST", "/purchase-orders/{doc_id}/invoices/{invoice_id}/files/{slot}"): _PO_WINDOWS,
    ("PUT", "/purchase-orders/{doc_id}/authorisation"): _PO_WINDOWS,
    ("PUT", "/users/{uid}/photo"):
        "a file upload the generator cannot fill; test_po_invoice_authorisation.test_other_workspace_is_404 sets another workspace's user photo",
    ("DELETE", "/purchase-orders/{doc_id}/delivery"): _PO_REASON,
    ("DELETE", "/purchase-orders/{doc_id}/invoices/{invoice_id}"): _PO_REASON,
    ("DELETE", "/purchase-orders/{doc_id}/orders/{order_id}"): _PO_REASON,
    ("GET", "/purchase-orders/{doc_id}"): _PO_REASON,
    ("GET", "/purchase-orders/{doc_id}/excel"): _PO_REASON,
    ("GET", "/purchase-orders/{doc_id}/pdf"): _PO_REASON,
    ("PATCH", "/purchase-orders/{doc_id}"): _PO_REASON,
    ("PATCH", "/purchase-orders/{doc_id}/invoices/{invoice_id}"): _PO_REASON,
    ("POST", "/purchase-orders/{doc_id}/cancel"): _PO_REASON,
    ("POST", "/purchase-orders/{doc_id}/invoices"): _PO_REASON,
    ("POST", "/purchase-orders/{doc_id}/orders"): _PO_REASON,
    ("PUT", "/purchase-orders/{doc_id}/delivery"): _PO_REASON,

    # The path parameter is a catalog type, not a row id; the routes create rows in the
    # caller's own workspace, so there is no foreign row to find.
    # The foreign id that matters here is the supplier in the body or the row: covered by
    # test_catalog_supplier_link (create / patch refuse an unknown or foreign supplier and
    # never echo its name; bulk import never matches another workspace's supplier by name).
    ("POST", "/catalog/{slug}"): "slug is a catalog type, not a row id",
    ("POST", "/catalog/{slug}/bulk"): "slug is a catalog type, not a row id",
}


def test_another_workspace_cannot_tell_a_row_exists(truncate_all, monkeypatch, tmp_path):
    # A route that crashes on a bad id must be reported below, not abort the run.
    admin_a = prepare_workspace_a(truncate_all, monkeypatch, tmp_path, raise_server_exceptions=False)
    admin_b, _, _ = login("admin", prefix="probe-b", raise_server_exceptions=False)

    with SessionLocal() as db:
        real_ids = {key: db.execute(text(sql)).scalar() for key, sql in REAL_ID_QUERIES.items()}
    assert all(real_ids.values()), f"the seed no longer has the rows REAL_ID_QUERIES picks: {real_ids}"

    all_ops = operations()
    leaks, crashes, unbuildable = [], [], set()

    for method, path, op in all_ops:
        real_ids_for, ghost_ids = ids_for(path, True, real_ids), ids_for(path, False, real_ids)
        real = request(admin_b, method, path, op, real_ids_for)
        ghost = request(admin_b, method, path, op, ghost_ids)
        if real is None or ghost is None:
            unbuildable.add((method, path))
            continue
        crashes += filter(None, [crash(f"{method} {path} (foreign id, as B)", real),
                                 crash(f"{method} {path} (nonexistent id, as B)", ghost)])
        if answer(real, real_ids_for) != answer(ghost, ghost_ids):
            leaks.append(f"{method} {path}: foreign id -> {real.status_code} {real.text[:100]}, "
                         f"nonexistent id -> {ghost.status_code}")

    assert not leaks, (
        "Another workspace's row must look exactly like a row that does not exist:\n  "
        + "\n  ".join(leaks)
    )

    # Which operations did the probe above actually exercise? Only those where A's own
    # admin sees a difference between the real row and the ghost one.
    no_signal = set(unbuildable)
    for method, path, op in all_ops:
        if (method, path) in unbuildable:
            continue
        real_ids_for, ghost_ids = ids_for(path, True, real_ids), ids_for(path, False, real_ids)
        real = request(admin_a, method, path, op, real_ids_for)
        ghost = request(admin_a, method, path, op, ghost_ids)
        crashes += filter(None, [crash(f"{method} {path} (real id, as A)", real),
                                 crash(f"{method} {path} (nonexistent id, as A)", ghost)])
        if answer(real, real_ids_for) == answer(ghost, ghost_ids):
            no_signal.add((method, path))

    assert not crashes, "No probe request may crash the server (5xx):\n  " + "\n  ".join(crashes)

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
