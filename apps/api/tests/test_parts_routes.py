"""Tests for modules + parts CRUD endpoints (Task 17).

6 tests covering the happy paths and auth/workspace guards:
  1. test_create_module_writes_create_log
  2. test_create_part_writes_log_with_field_create
  3. test_patch_part_qty_writes_one_edit_log_row
  4. test_delete_part_writes_delete_log
  5. test_module_in_other_workspace_404
  6. test_editor_403_on_part_patch

Uses the autouse-TRUNCATE pattern from test_items_routes.py.
Seed helpers (_seed_module, _seed_part) mirror patterns from test_items_routes.py.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import TRUNCATE_TABLES

# ── Cleanup fixture ────────────────────────────────────────────────────────────

_EXTRA_TABLES = (
    "parts",
    "modules",
    "item_edit_log",
    "item_status_log",
    "item_stages",
    "item_hardware_lines",
    "project_hardware_catalog",
    "items",
    "board_materials",
    "status_options",
    "stages",
)


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        all_tables = ", ".join(list(_EXTRA_TABLES) + list(TRUNCATE_TABLES))
        s.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


# ── Seed helpers ───────────────────────────────────────────────────────────────


def _seed_refs(db) -> None:
    """Insert status_options reference rows required for items.status FK."""
    for key, order in [("CLEAR", 1), ("HOLD", 2), ("LIVE", 3), ("VOID", 4)]:
        db.execute(
            text(
                "INSERT INTO status_options(status_key, sort_order)"
                " VALUES(:k, :o) ON CONFLICT DO NOTHING"
            ),
            {"k": key, "o": order},
        )
    db.commit()


def _login(role: str = "drafter") -> tuple:
    """Create a fresh workspace + user, return (client, workspace_id, user_id)."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"h-{suffix}"
    email = f"u-{suffix}@example.com"
    db = SessionLocal()
    try:
        _seed_refs(db)
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'H') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, :r)
                RETURNING id
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
        ).scalar()
        db.commit()
    finally:
        db.close()

    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": email, "password": "pw"},
    )
    assert r.status_code == 200, r.text
    return c, wid, uid


def _create_project(db, *, wid: int, uid: int) -> int:
    code = f"HJ-{uuid.uuid4().hex[:8]}"
    pid = db.execute(
        text(
            "INSERT INTO projects(project_code, name, pm_id, workspace_id)"
            " VALUES (:code, 'Test Project', :uid, :wid)"
            " RETURNING project_id"
        ),
        {"code": code, "uid": uid, "wid": wid},
    ).scalar()
    db.commit()
    return pid


def _insert_item(db, *, project_id: int, num: int) -> int:
    iid = db.execute(
        text(
            """
            INSERT INTO items(num, project_id, status, description, code, item_locked)
            VALUES (:num, :pid, 'CLEAR', 'Test item', 'CAB-01', false)
            RETURNING item_id
            """
        ),
        {"num": num, "pid": project_id},
    ).scalar()
    db.commit()
    return iid


def _seed_module(db, *, item_id: int, module_no: str = "M1", name: str = "Carcass") -> int:
    mid = db.execute(
        text(
            "INSERT INTO modules(item_id, module_no, name)"
            " VALUES (:iid, :mno, :name)"
            " RETURNING module_id"
        ),
        {"iid": item_id, "mno": module_no, "name": name},
    ).scalar()
    db.commit()
    return mid


def _seed_part(db, *, module_id: int, part_name: str = "Side Panel", qty: int = 2) -> int:
    pid = db.execute(
        text(
            "INSERT INTO parts(module_id, qty, part_name)"
            " VALUES (:mid, :qty, :pname)"
            " RETURNING part_id"
        ),
        {"mid": module_id, "qty": qty, "pname": part_name},
    ).scalar()
    db.commit()
    return pid


# ── Test cases ─────────────────────────────────────────────────────────────────


def test_create_module_writes_create_log():
    """POST /items/{id}/modules creates module and writes item_edit_log field='_create_module'."""
    c, wid, uid = _login(role="drafter")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=1)
    finally:
        db.close()

    r = c.post(
        f"/items/{iid}/modules",
        json={"module_no": "M1", "name": "Carcass"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Carcass"

    db = SessionLocal()
    try:
        logs = db.execute(
            text("SELECT field, actor_id FROM item_edit_log WHERE item_id = :iid"),
            {"iid": iid},
        ).mappings().all()
    finally:
        db.close()

    create_logs = [l for l in logs if l["field"] == "_create_module"]
    assert len(create_logs) == 1, f"Expected 1 _create_module log row, got {logs}"
    assert create_logs[0]["actor_id"] == uid


def test_create_part_writes_log_with_field_create():
    """POST /modules/{mid}/parts creates part and writes item_edit_log field='_create_part'."""
    c, wid, uid = _login(role="drafter")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=2)
        mid = _seed_module(db, item_id=iid, module_no="M1")
    finally:
        db.close()

    r = c.post(
        f"/modules/{mid}/parts",
        json={"qty": 1, "part_name": "Top Panel", "len_mm": 600, "wid_mm": 400},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["part_name"] == "Top Panel"
    assert body["qty"] == 1
    assert body["is_rev_c"] is False

    db = SessionLocal()
    try:
        logs = db.execute(
            text("SELECT field FROM item_edit_log WHERE item_id = :iid"),
            {"iid": iid},
        ).mappings().all()
    finally:
        db.close()

    fields = [l["field"] for l in logs]
    assert "_create_part" in fields, f"Expected _create_part in edit log, got {fields}"


def test_patch_part_qty_writes_one_edit_log_row():
    """PATCH /parts/{pid} with qty=5 writes exactly 1 new edit_log row with field='parts.qty'."""
    c, wid, uid = _login(role="drafter")
    db = SessionLocal()
    try:
        pid_proj = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid_proj, num=3)
        mid = _seed_module(db, item_id=iid, module_no="M1")
        part_id = _seed_part(db, module_id=mid, part_name="Side Panel", qty=2)
    finally:
        db.close()

    db = SessionLocal()
    try:
        before_count = db.execute(
            text("SELECT COUNT(*) FROM item_edit_log WHERE item_id = :iid"),
            {"iid": iid},
        ).scalar()
    finally:
        db.close()

    r = c.patch(f"/parts/{part_id}", json={"qty": 5})
    assert r.status_code == 200, r.text
    assert r.json()["qty"] == 5

    db = SessionLocal()
    try:
        after_count = db.execute(
            text("SELECT COUNT(*) FROM item_edit_log WHERE item_id = :iid"),
            {"iid": iid},
        ).scalar()
        qty_logs = db.execute(
            text(
                "SELECT field FROM item_edit_log"
                " WHERE item_id = :iid AND field = 'parts.qty'"
            ),
            {"iid": iid},
        ).mappings().all()
    finally:
        db.close()

    new_rows = after_count - before_count
    assert new_rows == 1, f"Expected exactly 1 new log row, got {new_rows}"
    assert len(qty_logs) == 1, f"Expected 1 parts.qty log row, got {qty_logs}"


def test_delete_part_writes_delete_log():
    """DELETE /parts/{pid} writes _delete_part log row before delete; row persists after."""
    c, wid, uid = _login(role="drafter")
    db = SessionLocal()
    try:
        pid_proj = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid_proj, num=4)
        mid = _seed_module(db, item_id=iid, module_no="M1")
        part_id = _seed_part(db, module_id=mid, part_name="Bottom Panel", qty=1)
    finally:
        db.close()

    r = c.delete(f"/parts/{part_id}")
    assert r.status_code == 204, r.text

    db = SessionLocal()
    try:
        part_row = db.execute(
            text("SELECT 1 FROM parts WHERE part_id = :pid"),
            {"pid": part_id},
        ).first()
        delete_logs = db.execute(
            text(
                "SELECT field FROM item_edit_log"
                " WHERE item_id = :iid AND field = '_delete_part'"
            ),
            {"iid": iid},
        ).mappings().all()
    finally:
        db.close()

    assert part_row is None, "Part should have been deleted"
    assert len(delete_logs) == 1, f"Expected 1 _delete_part log row, got {delete_logs}"


def test_module_in_other_workspace_404():
    """Workspace B cannot PATCH workspace A's module — must get 404."""
    c_a, wid_a, uid_a = _login(role="drafter")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid_a, uid=uid_a)
        iid = _insert_item(db, project_id=pid, num=5)
        mid = _seed_module(db, item_id=iid, module_no="M1", name="Original")
    finally:
        db.close()

    c_b, _wid_b, _uid_b = _login(role="drafter")
    r = c_b.patch(f"/modules/{mid}", json={"name": "Hijacked"})
    assert r.status_code == 404, r.text


def test_editor_403_on_part_patch():
    """An editor (not drafter/manager/admin) cannot PATCH a part — must get 403."""
    c_drafter, wid, uid_drafter = _login(role="drafter")
    db = SessionLocal()
    try:
        pid_proj = _create_project(db, wid=wid, uid=uid_drafter)
        iid = _insert_item(db, project_id=pid_proj, num=6)
        mid = _seed_module(db, item_id=iid, module_no="M1")
        part_id = _seed_part(db, module_id=mid, part_name="Door", qty=1)
        slug_row = db.execute(
            text("SELECT slug FROM workspace WHERE id = :wid"),
            {"wid": wid},
        ).mappings().first()
        slug = slug_row["slug"]
    finally:
        db.close()

    suffix = uuid.uuid4().hex[:8]
    editor_email = f"editor-{suffix}@example.com"
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'Editor', :p, 'editor')
                """
            ),
            {"w": wid, "e": editor_email, "p": hash_password("pw")},
        )
        db.commit()
    finally:
        db.close()

    c_editor = TestClient(app)
    login_r = c_editor.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": editor_email, "password": "pw"},
    )
    assert login_r.status_code == 200, login_r.text

    r = c_editor.patch(f"/parts/{part_id}", json={"qty": 99})
    assert r.status_code == 403, r.text


# ── Delete-module warning (impact lookup + audit counts) ───────────────────────


def _module_with_threads():
    """A drafter, their workspace, and a module holding 2 parts and threads: two
    live top-level comments, a live reply, and a soft-deleted one (3 are live).
    A second module of the same item carries a comment that must not be counted."""
    c, wid, uid = _login(role="drafter")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=wid * 100 + 1)
        mid = _seed_module(db, item_id=iid, module_no="M1", name="Carcass")
        other = _seed_module(db, item_id=iid, module_no="M2", name="Doors")
        _seed_part(db, module_id=mid, part_name="Side L")
        _seed_part(db, module_id=mid, part_name="Side R")

        def add(module_id, body, parent=None, deleted=False):
            return db.execute(
                text(
                    """
                    INSERT INTO comment(workspace_id, module_id, author_id, body,
                                        parent_comment_id, deleted_at)
                    VALUES (:w, :m, :u, :b, :p, CASE WHEN :d THEN now() END)
                    RETURNING comment_id
                    """
                ),
                {"w": wid, "m": module_id, "u": uid, "b": body, "p": parent, "d": deleted},
            ).scalar()

        first = add(mid, "first")
        add(mid, "second")
        add(mid, "a reply", parent=first)
        add(mid, "soft deleted", deleted=True)
        add(other, "on the other module")
        db.commit()
    finally:
        db.close()
    return c, wid, uid, iid, mid


def test_delete_impact_counts_parts_and_live_comments_of_this_module_only():
    c, _wid, _uid, _iid, mid = _module_with_threads()
    r = c.get(f"/modules/{mid}/delete-impact")
    assert r.status_code == 200, r.text
    assert r.json() == {"parts": 2, "live_comments": 3}


def test_delete_impact_is_zero_for_an_empty_module():
    c, wid, uid = _login(role="drafter")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=wid * 100 + 2)
        mid = _seed_module(db, item_id=iid)
    finally:
        db.close()
    assert c.get(f"/modules/{mid}/delete-impact").json() == {"parts": 0, "live_comments": 0}


def test_delete_impact_has_the_deletes_gate_and_is_workspace_scoped():
    c, _wid, _uid, _iid, mid = _module_with_threads()
    # same gate as DELETE /modules/{mid}: drafter / manager / admin only
    for role in ("editor", "viewer"):
        other, *_ = _login(role=role)
        assert other.get(f"/modules/{mid}/delete-impact").status_code == 403
    # another workspace's drafter cannot see it, and an unknown id is 404 too
    theirs, *_ = _login(role="drafter")
    assert theirs.get(f"/modules/{mid}/delete-impact").status_code == 404
    assert c.get("/modules/99999999/delete-impact").status_code == 404


def test_delete_module_records_what_went_with_it_and_still_answers_204():
    c, wid, _uid, _iid, mid = _module_with_threads()
    r = c.delete(f"/modules/{mid}")
    assert r.status_code == 204, r.text
    db = SessionLocal()
    try:
        payload = db.execute(
            text("SELECT payload FROM audit_log WHERE event = 'module.delete' AND target = :t"),
            {"t": str(mid)},
        ).scalar()
        parts_left = db.execute(
            text("SELECT count(*) FROM parts WHERE module_id = :m"), {"m": mid}
        ).scalar()
        comments_left = db.execute(
            text("SELECT count(*) FROM comment WHERE module_id = :m"), {"m": mid}
        ).scalar()
        other_comments = db.execute(
            text("SELECT count(*) FROM comment WHERE workspace_id = :w"), {"w": wid}
        ).scalar()
    finally:
        db.close()
    assert payload["deleted_parts"] == 2
    assert payload["deleted_comment_count"] == 3        # live only: the soft-deleted one is not counted
    assert parts_left == 0 and comments_left == 0        # the cascade took every row, soft-deleted too
    assert other_comments == 1                           # the other module's thread survives


# ── Lock checks on module delete ───────────────────────────────────────────────


def _login_same_workspace(wid: int, role: str, name: str = "U2") -> tuple:
    """A second user in an existing workspace: (client, user_id)."""
    suffix = uuid.uuid4().hex[:8]
    email = f"u2-{suffix}@example.com"
    db = SessionLocal()
    try:
        slug = db.execute(text("SELECT slug FROM workspace WHERE id = :w"), {"w": wid}).scalar()
        uid = db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, :n, :p, :r) RETURNING id
                """
            ),
            {"w": wid, "e": email, "n": name, "p": hash_password("pw"), "r": role},
        ).scalar()
        db.commit()
    finally:
        db.close()
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    return c, uid


def _set_item(iid: int, sql: str, **params) -> None:
    db = SessionLocal()
    try:
        db.execute(text(f"UPDATE items SET {sql} WHERE item_id = :i"), {"i": iid, **params})
        db.commit()
    finally:
        db.close()


def _module_survives(mid: int) -> bool:
    db = SessionLocal()
    try:
        gone = db.execute(
            text("SELECT count(*) FROM modules WHERE module_id = :m"), {"m": mid}
        ).scalar() == 0
        deleted_audit = db.execute(
            text("SELECT count(*) FROM audit_log WHERE event = 'module.delete' AND target = :t"),
            {"t": str(mid)},
        ).scalar()
        parts = db.execute(
            text("SELECT count(*) FROM parts WHERE module_id = :m"), {"m": mid}
        ).scalar()
        comments = db.execute(
            text("SELECT count(*) FROM comment WHERE module_id = :m"), {"m": mid}
        ).scalar()
    finally:
        db.close()
    if gone:
        return False
    assert deleted_audit == 0, "a refused delete must not be audited as done"
    assert parts == 2 and comments == 4, "nothing may have been deleted"
    return True


def test_hard_locked_item_refuses_module_delete_for_everyone():
    c, wid, uid, iid, mid = _module_with_threads()
    _set_item(iid, "hard_locked_at = now(), hard_locked_by = :u", u=uid)
    admin, _ = _login_same_workspace(wid, "admin")
    for client in (c, admin):                     # even a manager-level authority
        r = client.delete(f"/modules/{mid}")
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == {"code": "HARD_LOCKED", "locked_by": uid}
    assert _module_survives(mid)
    # clearing the lock lets the same delete through
    _set_item(iid, "hard_locked_at = NULL, hard_locked_by = NULL")
    assert c.delete(f"/modules/{mid}").status_code == 204


def test_approved_item_refuses_module_delete_until_status_moves_off_approved():
    c, _wid, _uid, iid, mid = _module_with_threads()
    db = SessionLocal()
    try:
        db.execute(
            text("INSERT INTO status_options(status_key, sort_order) VALUES ('APPROVED', 5)"
                 " ON CONFLICT DO NOTHING")
        )
        db.commit()
    finally:
        db.close()
    _set_item(iid, "status = 'APPROVED'")
    r = c.delete(f"/modules/{mid}")
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == {"code": "APPROVAL_LOCKED"}
    assert _module_survives(mid)
    _set_item(iid, "status = 'CLEAR'")
    assert c.delete(f"/modules/{mid}").status_code == 204


def test_controlled_lock_refuses_a_non_owner_but_not_the_owner_or_a_manager():
    c, wid, uid, iid, mid = _module_with_threads()          # `c` is a drafter, not the owner
    owner_client, owner_id = _login_same_workspace(wid, "drafter", name="Olive Owner")
    _set_item(iid, "item_locked = true, cutlist_owner_id = :o", o=owner_id)

    r = c.delete(f"/modules/{mid}")
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == {
        "code": "ITEM_LOCKED", "owner_id": owner_id, "owner_name": "Olive Owner",
    }
    assert _module_survives(mid)

    # the read-only impact lookup is not gated by any lock
    assert c.get(f"/modules/{mid}/delete-impact").status_code == 200

    # a manager can decide lock requests, so can delete
    manager, _ = _login_same_workspace(wid, "manager")
    assert manager.delete(f"/modules/{mid}").status_code == 204

    # ...and so can the owner (on a second module of the same still-locked item)
    db = SessionLocal()
    try:
        other = _seed_module(db, item_id=iid, module_no="M3", name="Drawers")
    finally:
        db.close()
    assert owner_client.delete(f"/modules/{other}").status_code == 204


def test_a_sticky_owner_without_an_active_lock_does_not_block_delete():
    c, wid, _uid, iid, mid = _module_with_threads()
    _other, owner_id = _login_same_workspace(wid, "drafter")
    # cutlist_owner_id survives an Unlock (sticky claim); only item_locked matters
    _set_item(iid, "item_locked = false, cutlist_owner_id = :o", o=owner_id)
    assert c.delete(f"/modules/{mid}").status_code == 204


# ── Lock checks on the other module and part writes ────────────────────────────


def _write_routes(iid: int, mid: int, part_id: int) -> dict:
    """The five module/part writes besides DELETE /modules/{mid}: name -> (method,
    path, json, status expected when nothing forbids it)."""
    return {
        "create_module": ("post", f"/items/{iid}/modules", {"module_no": "M9", "name": "New"}, 201),
        "patch_module": ("patch", f"/modules/{mid}", {"name": "Renamed"}, 200),
        "create_part": ("post", f"/modules/{mid}/parts", {"part_name": "Extra", "qty": 1}, 201),
        "patch_part": ("patch", f"/parts/{part_id}", {"qty": 9}, 200),
        "delete_part": ("delete", f"/parts/{part_id}", None, 204),
    }


_ROUTE_NAMES = ["create_module", "patch_module", "create_part", "patch_part", "delete_part"]


def _send(client, route: tuple):
    method, path, body, _ok = route
    return getattr(client, method)(path, **({"json": body} if body is not None else {}))


def _state(iid: int, wid: int) -> tuple:
    """Everything a refused write must leave alone."""
    db = SessionLocal()
    try:
        return (
            db.execute(text("SELECT count(*), max(name) FROM modules WHERE item_id = :i"), {"i": iid}).one(),
            db.execute(
                text("SELECT count(*), sum(qty) FROM parts WHERE module_id IN"
                     " (SELECT module_id FROM modules WHERE item_id = :i)"), {"i": iid}
            ).one(),
            db.execute(text("SELECT count(*) FROM item_edit_log WHERE item_id = :i"), {"i": iid}).scalar(),
            db.execute(
                text("SELECT count(*) FROM audit_log WHERE workspace_id = :w"
                     " AND (event LIKE 'module.%' OR event LIKE 'part.%')"), {"w": wid}
            ).scalar(),
        )
    finally:
        db.close()


def _fixture_with_part():
    c, wid, uid, iid, mid = _module_with_threads()
    db = SessionLocal()
    try:
        part_id = db.execute(
            text("SELECT min(part_id) FROM parts WHERE module_id = :m"), {"m": mid}
        ).scalar()
    finally:
        db.close()
    return c, wid, uid, iid, mid, part_id


def _approve_status_exists() -> None:
    db = SessionLocal()
    try:
        db.execute(text("INSERT INTO status_options(status_key, sort_order) VALUES ('APPROVED', 5)"
                        " ON CONFLICT DO NOTHING"))
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("name", _ROUTE_NAMES)
@pytest.mark.parametrize("lock", ["hard", "approval"])
def test_locked_item_refuses_every_module_and_part_write(name, lock):
    c, wid, uid, iid, mid, part_id = _fixture_with_part()
    route = _write_routes(iid, mid, part_id)[name]
    if lock == "hard":
        _set_item(iid, "hard_locked_at = now(), hard_locked_by = :u", u=uid)
        expected = {"code": "HARD_LOCKED", "locked_by": uid}
    else:
        _approve_status_exists()
        _set_item(iid, "status = 'APPROVED'")
        expected = {"code": "APPROVAL_LOCKED"}
    admin, _ = _login_same_workspace(wid, "admin")

    before = _state(iid, wid)
    for client in (c, admin):                       # a Hard / Approval Lock has no way round
        r = _send(client, route)
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == expected
    assert _state(iid, wid) == before, "a refused write must change and log nothing"

    # once the lock is cleared the same request goes through
    _set_item(iid, "hard_locked_at = NULL, hard_locked_by = NULL, status = 'CLEAR'")
    assert _send(c, route).status_code == route[3]


@pytest.mark.parametrize("name", _ROUTE_NAMES)
def test_controlled_lock_refuses_a_non_owner_on_every_module_and_part_write(name):
    c, wid, uid, iid, mid, part_id = _fixture_with_part()
    routes = _write_routes(iid, mid, part_id)
    owner_client, owner_id = _login_same_workspace(wid, "drafter", name="Olive Owner")
    _set_item(iid, "item_locked = true, cutlist_owner_id = :o", o=owner_id)

    before = _state(iid, wid)
    r = _send(c, routes[name])
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == {
        "code": "ITEM_LOCKED", "owner_id": owner_id, "owner_name": "Olive Owner",
    }
    assert _state(iid, wid) == before

    # the owner passes — and so does a manager
    assert _send(owner_client, routes[name]).status_code == routes[name][3]


@pytest.mark.parametrize("name", _ROUTE_NAMES)
def test_a_manager_passes_a_controlled_lock_on_every_module_and_part_write(name):
    c, wid, uid, iid, mid, part_id = _fixture_with_part()
    routes = _write_routes(iid, mid, part_id)
    _other, owner_id = _login_same_workspace(wid, "drafter")
    _set_item(iid, "item_locked = true, cutlist_owner_id = :o", o=owner_id)
    manager, _ = _login_same_workspace(wid, "manager")
    assert _send(manager, routes[name]).status_code == routes[name][3]


def test_an_unlocked_item_and_a_sticky_owner_do_not_block_module_and_part_writes():
    c, wid, uid, iid, mid, part_id = _fixture_with_part()
    _other, owner_id = _login_same_workspace(wid, "drafter")
    # cutlist_owner_id survives an Unlock; only an active item_locked counts
    _set_item(iid, "item_locked = false, cutlist_owner_id = :o", o=owner_id)
    for name, route in _write_routes(iid, mid, part_id).items():
        assert _send(c, route).status_code == route[3], name


def test_unknown_ids_are_still_404_not_lock_answers():
    c, wid, uid, iid, mid, part_id = _fixture_with_part()
    _set_item(iid, "hard_locked_at = now(), hard_locked_by = :u", u=uid)
    assert c.post("/items/99999999/modules", json={"module_no": "X"}).status_code == 404
    assert c.patch("/modules/99999999", json={"name": "x"}).status_code == 404
    assert c.post("/modules/99999999/parts", json={"qty": 1}).status_code == 404
    assert c.patch("/parts/99999999", json={"qty": 1}).status_code == 404
    assert c.delete("/parts/99999999").status_code == 404
