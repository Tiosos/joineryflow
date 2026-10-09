"""Lock checks on the item attachment slots and the Document Register (Plan V1 §12).

Every write to either — bind / replace / clear a slot, bind / relabel-reorder / unbind
a register document — answers to the item's locks (`assert_item_content_unlocked`):

- Hard Lock: everyone, the owner and admins included.
- Approval Lock (`status = 'APPROVED'`): applies here, unlike status / lifecycle.
- Controlled Lock: anyone but the owner and managers/admins.

None of these writes can be held as a `PatchItemIn` request, so they are refused.
A refused write changes and logs nothing.  Reads are never gated.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .helpers_documents import _client, _sql, _upload, _workspace, reset_disk  # noqa: F401
from .helpers import log_in


@pytest.fixture
def ws(truncate_all):
    truncate_all()
    _sql("INSERT INTO status_options(status_key, sort_order)"
         " VALUES ('APPROVED', 5) ON CONFLICT DO NOTHING")
    w = _workspace(roles=("drafter", "editor", "viewer", "manager", "admin"))
    c = _client(w)                                   # a drafter
    bid = _upload(c)
    assert c.post(f"/items/{w['iid']}/attachments/cv_drawing",
                  json={"file_blob_id": bid}).status_code == 201
    r = c.post(f"/items/{w['iid']}/documents", json={"file_blob_id": bid, "label": "Plan"})
    assert r.status_code == 201, r.text
    w.update(client=c, bid=bid, did=r.json()["document_id"])
    return w


def _routes(ws: dict) -> dict:
    """The five writes: name -> (method, path, json, status when allowed)."""
    iid, did, bid = ws["iid"], ws["did"], ws["bid"]
    return {
        "attachment-bind": ("post", f"/items/{iid}/attachments/floor_plan", {"file_blob_id": bid}, 201),
        "attachment-clear": ("delete", f"/items/{iid}/attachments/cv_drawing", None, 204),
        "document-bind": ("post", f"/items/{iid}/documents", {"file_blob_id": bid, "label": "More"}, 201),
        "document-patch": ("patch", f"/documents/{did}", {"label": "Renamed"}, 200),
        "document-unbind": ("delete", f"/documents/{did}", None, 204),
    }


_NAMES = ["attachment-bind", "attachment-clear", "document-bind", "document-patch", "document-unbind"]


def _send(client, route: tuple):
    method, path, body, _ok = route
    return getattr(client, method)(path, **({"json": body} if body is not None else {}))


def _state(ws: dict) -> tuple:
    """Everything a refused write must leave alone."""
    rows = _sql("SELECT kind, file_blob_id FROM item_attachment WHERE item_id = :i ORDER BY kind",
                {"i": ws["iid"]})
    docs = _sql("SELECT document_id, label, sort_order FROM item_document WHERE item_id = :i"
                " ORDER BY document_id", {"i": ws["iid"]})
    log = _sql("SELECT count(*) AS n FROM item_edit_log WHERE item_id = :i", {"i": ws["iid"]})[0]["n"]
    audit = _sql("SELECT count(*) AS n FROM audit_log WHERE workspace_id = :w"
                 " AND (event LIKE 'item_attachment.%' OR event LIKE 'item.document.%')",
                 {"w": ws["wid"]})[0]["n"]
    return ([tuple(r.values()) for r in rows], [tuple(r.values()) for r in docs], log, audit)


def _set_item(ws: dict, sql: str, **params) -> None:
    _sql(f"UPDATE items SET {sql} WHERE item_id = :i", {"i": ws["iid"], **params})


def _uid(ws: dict, role: str) -> int:
    return _sql("SELECT id FROM app_user WHERE workspace_id = :w AND auth_role = :r",
                {"w": ws["wid"], "r": role})[0]["id"]


def _extra_user(ws: dict, role: str, name: str) -> tuple[TestClient, int]:
    """A second user of `role` in the workspace: (client, user_id)."""
    email = f"{uuid.uuid4().hex[:8]}@{ws['slug']}.test"
    s = SessionLocal()
    try:
        uid = s.execute(
            text("INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)"
                 " VALUES(:w,:e,:n,:p,:r) RETURNING id"),
            {"w": ws["wid"], "e": email, "n": name, "p": hash_password("pw"), "r": role},
        ).scalar()
        s.commit()
    finally:
        s.close()
    c = TestClient(app)
    log_in(ws["slug"], email, client=c)
    return c, uid


@pytest.mark.parametrize("name", _NAMES)
@pytest.mark.parametrize("lock", ["hard", "approval"])
def test_a_hard_or_approval_lock_refuses_every_write(ws, name, lock):
    route = _routes(ws)[name]
    if lock == "hard":
        uid = _uid(ws, "drafter")
        _set_item(ws, "hard_locked_at = now(), hard_locked_by = :u", u=uid)
        expected = {"code": "HARD_LOCKED", "locked_by": uid}
    else:
        _set_item(ws, "status = 'APPROVED'")
        expected = {"code": "APPROVAL_LOCKED"}
    admin = _client(ws, "admin")

    before = _state(ws)
    for client in (ws["client"], admin):            # neither lock has a way round
        r = _send(client, route)
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == expected
    assert _state(ws) == before, "a refused write must change and log nothing"

    _set_item(ws, "hard_locked_at = NULL, hard_locked_by = NULL, status = 'CLEAR'")
    assert _send(ws["client"], route).status_code == route[3]   # the same request goes through


@pytest.mark.parametrize("name", _NAMES)
def test_a_controlled_lock_refuses_a_non_owner_but_not_the_owner_or_a_manager(ws, name):
    route = _routes(ws)[name]
    owner, owner_id = _extra_user(ws, "drafter", "Olive Owner")
    _set_item(ws, "item_locked = true, cutlist_owner_id = :o", o=owner_id)

    before = _state(ws)
    r = _send(ws["client"], route)                  # a different drafter
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == {
        "code": "ITEM_LOCKED", "owner_id": owner_id, "owner_name": "Olive Owner",
    }
    assert _state(ws) == before

    assert _send(owner, route).status_code == route[3]


@pytest.mark.parametrize("name", _NAMES)
def test_a_manager_passes_a_controlled_lock(ws, name):
    _other, owner_id = _extra_user(ws, "drafter", "Olive Owner")
    _set_item(ws, "item_locked = true, cutlist_owner_id = :o", o=owner_id)
    route = _routes(ws)[name]
    assert _send(_client(ws, "manager"), route).status_code == route[3]


@pytest.mark.parametrize("name", ["document-bind", "document-patch", "document-unbind"])
def test_an_editor_is_refused_on_a_register_write_too(ws, name):
    """The register is gated `list:write` alone, so editors may write it — and a
    Controlled Lock refuses them like anyone else who is not the owner."""
    owner, owner_id = _extra_user(ws, "drafter", "Olive Owner")
    _set_item(ws, "item_locked = true, cutlist_owner_id = :o", o=owner_id)
    r = _send(_client(ws, "editor"), _routes(ws)[name])
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ITEM_LOCKED"


@pytest.mark.parametrize("name", _NAMES)
def test_an_unlocked_item_and_a_sticky_owner_do_not_block(ws, name):
    _other, owner_id = _extra_user(ws, "drafter", "Someone")
    # cutlist_owner_id survives an Unlock; only an active item_locked counts
    _set_item(ws, "item_locked = false, cutlist_owner_id = :o", o=owner_id)
    route = _routes(ws)[name]
    assert _send(ws["client"], route).status_code == route[3]


def test_reads_are_never_gated(ws):
    _set_item(ws, "hard_locked_at = now(), hard_locked_by = :u", u=_uid(ws, "drafter"))
    c = ws["client"]
    assert c.get(f"/items/{ws['iid']}/attachments").status_code == 200
    assert c.get(f"/items/{ws['iid']}/documents").status_code == 200


def test_unknown_ids_are_still_404_not_lock_answers(ws):
    _set_item(ws, "hard_locked_at = now(), hard_locked_by = :u", u=_uid(ws, "drafter"))
    c, bid = ws["client"], ws["bid"]
    assert c.post("/items/99999999/attachments/cv_drawing", json={"file_blob_id": bid}).status_code == 404
    assert c.delete("/items/99999999/attachments/cv_drawing").status_code == 404
    assert c.post("/items/99999999/documents", json={"file_blob_id": bid}).status_code == 404
    assert c.patch("/documents/99999999", json={"label": "x"}).status_code == 404
    assert c.delete("/documents/99999999").status_code == 404
