"""Lock checks on item queries and material takes (Plan V1 §12).

The rule (`assert_item_content_unlocked`, user decision): **Hard Lock and someone
else's Controlled Lock, not the Approval Lock** — an approved item is when takes
are approved and queries answered, so gating them on it would stop the workflow
they belong to.

- Every material-take write — generate, regenerate, add / edit / remove a line,
  approve, record an impact review — answers to both locks.
- *Answering* a query (and editing an answer) answers to both locks.
- *Asking* a query answers to the Hard Lock only: anyone with `list:read` may ask,
  and a Controlled Lock must not stop a person putting a question to its owner.
- QC records are deliberately not locked (production-floor work on items that are
  already approved or claimed).

None of these can be held as a `PatchItemIn` request, so a locked write is refused
`409 {detail: {code, …}}`. A refused write changes and logs nothing.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .helpers_material_take import _cleanup, _item, _sql, _workspace  # noqa: F401
from .helpers import log_in




def _rows(sql, **p):
    s = SessionLocal()
    try:
        return [dict(r) for r in s.execute(text(sql), p).mappings()]
    finally:
        s.close()


def _user(wid: int, role: str, name: str = "U") -> tuple[TestClient, int]:
    email = f"{role}-{uuid.uuid4().hex[:6]}@x.test"
    uid = _sql("INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)"
               " VALUES (:w, :e, :n, :p, :r) RETURNING id",
               w=wid, e=email, n=name, p=hash_password("pw"), r=role)
    slug = _sql("SELECT slug FROM workspace WHERE id = :w", w=wid)
    c = TestClient(app)
    log_in(slug, email, client=c)
    return c, uid


@pytest.fixture
def ws():
    _sql("INSERT INTO status_options(status_key, sort_order)"
         " VALUES ('APPROVED', 5) ON CONFLICT DO NOTHING")
    wid = _workspace()
    drafter, drafter_id = _user(wid, "drafter", "Dee Drafter")
    return {"wid": wid, "drafter": drafter, "drafter_id": drafter_id,
            "item": _item(wid)["item"]}


def _set_item(ws: dict, sql: str, **params) -> None:
    _sql(f"UPDATE items SET {sql} WHERE item_id = :i", i=ws["item"], **params)


def _hard_lock(ws: dict) -> dict:
    _set_item(ws, "hard_locked_at = now(), hard_locked_by = :u", u=ws["drafter_id"])
    return {"code": "HARD_LOCKED", "locked_by": ws["drafter_id"]}


def _controlled_lock(ws: dict) -> tuple[TestClient, int, dict]:
    owner, owner_id = _user(ws["wid"], "drafter", "Olive Owner")
    _set_item(ws, "item_locked = true, cutlist_owner_id = :o", o=owner_id)
    return owner, owner_id, {"code": "ITEM_LOCKED", "owner_id": owner_id,
                             "owner_name": "Olive Owner"}


def _unlock(ws: dict) -> None:
    _set_item(ws, "hard_locked_at = NULL, hard_locked_by = NULL, item_locked = false,"
                  " status = 'LIVE'")


# ============================================================ material takes ===

_TAKE_WRITES = ["generate", "regenerate", "add-line", "patch-line", "delete-line",
                "approve", "review"]


def _take_route(ws: dict, name: str) -> tuple:
    """Prepare the state `name` needs (as the unlocked drafter), then return
    (method, path, json, status when allowed)."""
    c, iid = ws["drafter"], ws["item"]
    if name == "generate":
        return ("post", f"/items/{iid}/material-take/generate", None, 201)
    tid = c.post(f"/items/{iid}/material-take/generate").json()["take_id"]
    if name == "regenerate":
        return ("post", f"/material-takes/{tid}/regenerate", None, 204)
    if name == "add-line":
        return ("post", f"/material-takes/{tid}/lines",
                {"description": "Edging", "unit": "m", "qty": "3"}, 201)
    if name in ("patch-line", "delete-line"):
        lid = c.post(f"/material-takes/{tid}/lines",
                     json={"description": "Edging", "unit": "m", "qty": "3"}).json()["line_id"]
        if name == "patch-line":
            return ("patch", f"/material-takes/{tid}/lines/{lid}", {"qty": "4"}, 204)
        return ("delete", f"/material-takes/{tid}/lines/{lid}", None, 204)
    if name == "approve":
        return ("post", f"/material-takes/{tid}/approve", None, 204)
    assert name == "review"
    assert c.post(f"/material-takes/{tid}/approve").status_code == 204
    return ("post", f"/material-takes/{tid}/reviews", {"outcome": "no_impact"}, 201)


def _send(client, route: tuple):
    method, path, body, _ok = route
    return getattr(client, method)(path, **({"json": body} if body is not None else {}))


def _take_state(ws: dict) -> tuple:
    """Everything a refused write must leave alone."""
    takes = _rows("SELECT take_id, status, version FROM material_take WHERE item_id = :i"
                  " ORDER BY take_id", i=ws["item"])
    lines = _rows("SELECT line_id, qty, source FROM material_take_line l JOIN material_take t"
                  " USING (take_id) WHERE t.item_id = :i ORDER BY line_id", i=ws["item"])
    log = _rows("SELECT count(*) AS n FROM item_edit_log WHERE item_id = :i", i=ws["item"])[0]["n"]
    audit = _rows("SELECT count(*) AS n FROM audit_log WHERE workspace_id = :w"
                  " AND event LIKE 'material_take.%'", w=ws["wid"])[0]["n"]
    return (takes, [{**l, "qty": str(l["qty"])} for l in lines], log, audit)


@pytest.mark.parametrize("name", _TAKE_WRITES)
def test_a_hard_lock_refuses_every_take_write_for_everyone(ws, name):
    route = _take_route(ws, name)
    expected = _hard_lock(ws)
    admin, _ = _user(ws["wid"], "admin")

    before = _take_state(ws)
    for client in (ws["drafter"], admin):           # the lock has no way round
        r = _send(client, route)
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == expected
    assert _take_state(ws) == before, "a refused write must change and log nothing"

    _unlock(ws)
    assert _send(ws["drafter"], route).status_code == route[3]   # the same request goes through


@pytest.mark.parametrize("name", _TAKE_WRITES)
def test_a_controlled_lock_refuses_a_non_owner_but_not_the_owner_or_a_manager(ws, name):
    route = _take_route(ws, name)
    owner, _owner_id, expected = _controlled_lock(ws)

    before = _take_state(ws)
    r = _send(ws["drafter"], route)                 # a different drafter
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == expected
    assert _take_state(ws) == before

    assert _send(owner, route).status_code == route[3]   # the owner passes


@pytest.mark.parametrize("name", ["generate", "approve"])
def test_a_manager_passes_someone_elses_controlled_lock_on_a_take(ws, name):
    route = _take_route(ws, name)
    _controlled_lock(ws)
    manager, _ = _user(ws["wid"], "manager")
    assert _send(manager, route).status_code == route[3]


@pytest.mark.parametrize("name", _TAKE_WRITES)
def test_the_approval_lock_does_not_stop_a_take_write(ws, name):
    """A take is approved on an approved item: the Approval Lock must not gate it."""
    route = _take_route(ws, name)
    _set_item(ws, "status = 'APPROVED'")
    assert _send(ws["drafter"], route).status_code == route[3]


def test_an_unlocked_item_and_a_sticky_owner_do_not_block_a_take(ws):
    """`cutlist_owner_id` survives Unlock; only `item_locked` counts."""
    owner, owner_id = _user(ws["wid"], "drafter", "Olive Owner")
    _set_item(ws, "item_locked = false, cutlist_owner_id = :o", o=owner_id)
    r = ws["drafter"].post(f"/items/{ws['item']}/material-take/generate")
    assert r.status_code == 201, r.text


def test_take_reads_are_never_gated(ws):
    tid = ws["drafter"].post(f"/items/{ws['item']}/material-take/generate").json()["take_id"]
    _hard_lock(ws)
    viewer, _ = _user(ws["wid"], "viewer")
    assert viewer.get(f"/items/{ws['item']}/material-take").status_code == 200
    assert viewer.get(f"/items/{ws['item']}/material-takes").status_code == 200
    assert tid


def test_unknown_take_and_item_ids_stay_404_under_a_hard_lock(ws):
    _hard_lock(ws)
    c = ws["drafter"]
    assert c.post("/material-takes/999999/approve").status_code == 404
    assert c.post("/material-takes/999999/regenerate").status_code == 404
    assert c.post("/items/999999/material-take/generate").status_code == 404


def test_a_refused_review_opens_no_next_version(ws):
    """`review` can create a draft (partial / full impact); a lock refuses that too."""
    c = ws["drafter"]
    tid = c.post(f"/items/{ws['item']}/material-take/generate").json()["take_id"]
    assert c.post(f"/material-takes/{tid}/approve").status_code == 204
    _hard_lock(ws)

    r = c.post(f"/material-takes/{tid}/reviews", json={"outcome": "full"})
    assert r.status_code == 409, r.text
    assert [t["status"] for t in _rows(
        "SELECT status FROM material_take WHERE item_id = :i", i=ws["item"])] == ["approved"]
    assert _rows("SELECT count(*) AS n FROM material_take_review")[0]["n"] == 0


# ================================================================ item queries ===

def _query(ws: dict, answered: bool = False, client: TestClient | None = None) -> int:
    c = client or ws["drafter"]
    qid = c.post(f"/items/{ws['item']}/queries", json={"question": "Handle finish?"}).json()["query_id"]
    if answered:
        assert c.post(f"/queries/{qid}/answer", json={"answer": "Brushed nickel"}).status_code == 200
    return qid


def _query_state(ws: dict) -> tuple:
    qs = _rows("SELECT query_id, question, answer, answered_by FROM item_query"
               " WHERE item_id = :i ORDER BY query_id", i=ws["item"])
    log = _rows("SELECT count(*) AS n FROM item_edit_log WHERE item_id = :i", i=ws["item"])[0]["n"]
    audit = _rows("SELECT count(*) AS n FROM audit_log WHERE workspace_id = :w"
                  " AND event LIKE 'item.query.%'", w=ws["wid"])[0]["n"]
    return (qs, log, audit)


def _answer_route(ws: dict, name: str, client: TestClient | None = None) -> tuple:
    """`client` sets the query up (asks, and for an edit pre-answers it)."""
    if name == "answer":
        qid = _query(ws, client=client)
        return ("post", f"/queries/{qid}/answer", {"answer": "Matte black"}, 200)
    qid = _query(ws, answered=True, client=client)
    return ("patch", f"/queries/{qid}/answer", {"answer": "Matte black"}, 200)


_ANSWER_WRITES = ["answer", "edit-answer"]


@pytest.mark.parametrize("name", _ANSWER_WRITES)
def test_a_hard_lock_refuses_answering_for_everyone(ws, name):
    route = _answer_route(ws, name)
    expected = _hard_lock(ws)
    admin, _ = _user(ws["wid"], "admin")

    before = _query_state(ws)
    for client in (ws["drafter"], admin):
        r = _send(client, route)
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == expected
    assert _query_state(ws) == before, "a refused answer must change and log nothing"

    _unlock(ws)
    assert _send(ws["drafter"], route).status_code == 200


@pytest.mark.parametrize("name", _ANSWER_WRITES)
def test_a_controlled_lock_refuses_a_non_owner_answer_but_not_the_owner_or_a_manager(ws, name):
    route = _answer_route(ws, name)
    owner, _owner_id, expected = _controlled_lock(ws)
    foreman, _ = _user(ws["wid"], "editor")           # list:write, but not the owner

    before = _query_state(ws)
    for client in (ws["drafter"], foreman):
        r = _send(client, route)
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == expected
    assert _query_state(ws) == before

    assert _send(owner, route).status_code == 200
    manager, _ = _user(ws["wid"], "manager")
    # A second answer to the same query would be ALREADY_ANSWERED, so the manager
    # gets a query of their own, set up by the manager (asking is open under a
    # Controlled Lock, but pre-answering for an edit is not).
    assert _send(manager, _answer_route(ws, name, client=manager)).status_code == 200


@pytest.mark.parametrize("name", _ANSWER_WRITES)
def test_the_approval_lock_does_not_stop_answering(ws, name):
    route = _answer_route(ws, name)
    _set_item(ws, "status = 'APPROVED'")
    assert _send(ws["drafter"], route).status_code == 200


def test_asking_is_refused_by_a_hard_lock_and_nothing_is_written(ws):
    expected = _hard_lock(ws)
    viewer, _ = _user(ws["wid"], "viewer")

    before = _query_state(ws)
    r = viewer.post(f"/items/{ws['item']}/queries", json={"question": "Any update?"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == expected
    assert _query_state(ws) == before

    _unlock(ws)
    assert viewer.post(f"/items/{ws['item']}/queries",
                       json={"question": "Any update?"}).status_code == 201


def test_asking_is_not_stopped_by_a_controlled_or_approval_lock(ws):
    """Anyone with `list:read` may put a question to the lock's owner."""
    viewer, _ = _user(ws["wid"], "viewer")
    _controlled_lock(ws)
    r = viewer.post(f"/items/{ws['item']}/queries", json={"question": "Who has this?"})
    assert r.status_code == 201, r.text

    _set_item(ws, "status = 'APPROVED'")
    r = viewer.post(f"/items/{ws['item']}/queries", json={"question": "Still approved?"})
    assert r.status_code == 201, r.text


def test_an_unlocked_item_and_a_sticky_owner_do_not_block_answering(ws):
    qid = _query(ws)
    _owner, owner_id = _user(ws["wid"], "drafter", "Olive Owner")
    _set_item(ws, "item_locked = false, cutlist_owner_id = :o", o=owner_id)
    r = ws["drafter"].post(f"/queries/{qid}/answer", json={"answer": "Fine"})
    assert r.status_code == 200, r.text


def test_query_reads_are_never_gated(ws):
    _query(ws)
    _hard_lock(ws)
    viewer, _ = _user(ws["wid"], "viewer")
    assert viewer.get(f"/items/{ws['item']}/queries").status_code == 200


def test_unknown_item_and_query_ids_stay_404_under_a_hard_lock(ws):
    _hard_lock(ws)
    c = ws["drafter"]
    assert c.post("/items/999999/queries", json={"question": "x"}).status_code == 404
    assert c.post("/queries/999999/answer", json={"answer": "x"}).status_code == 404
    assert c.patch("/queries/999999/answer", json={"answer": "x"}).status_code == 404


# ======================================================================== QC ===

def test_qc_records_are_deliberately_not_lock_checked(ws):
    """Production-floor work on items that are already approved or claimed: a Hard,
    Approval or Controlled Lock must not stop a defect being raised."""
    foreman, _ = _user(ws["wid"], "editor")
    _controlled_lock(ws)
    _set_item(ws, "status = 'APPROVED'")
    r = foreman.post(f"/items/{ws['item']}/qc/defects", json={"description": "Chipped edge"})
    assert r.status_code == 201, r.text
