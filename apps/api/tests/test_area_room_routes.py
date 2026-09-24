"""Areas and Rooms (Plan V1 Q454/Q455/Q457/Q458/Q552, migration 0026).

What these pin down:

  Q457  areas are created per project, not drawn from a workspace library
  Q552  a room is nested under an area, enforced by the composite FK
  Q455  setting area/room ALSO writes the legacy stage / rm_no / rm_desc,
        which stay populated until a later migration drops them (Q435)
  Q458  moving room is allowed and lands in item_edit_log
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import TRUNCATE_TABLES


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        extra = ("item_edit_log", "item_stages", "items", "room", "area", "status_options")
        s.execute(
            text(f"TRUNCATE {', '.join(list(extra) + list(TRUNCATE_TABLES))}"
                 " RESTART IDENTITY CASCADE")
        )
        s.commit()
    finally:
        s.close()


@pytest.fixture
def ctx():
    suffix = uuid.uuid4().hex[:8]
    slug = f"ar-{suffix}"
    db = SessionLocal()
    try:
        db.execute(text("INSERT INTO status_options(status_key, sort_order)"
                        " VALUES('CLEAR',1) ON CONFLICT DO NOTHING"))
        wid = db.execute(
            text("INSERT INTO workspace(slug,name) VALUES(:s,'AR WS') RETURNING id"),
            {"s": slug},
        ).scalar()
        email, pw = f"d-{suffix}@x.test", "pw"
        db.execute(
            text("INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)"
                 " VALUES(:w,:e,'Drafter',:p,'drafter')"),
            {"w": wid, "e": email, "p": hash_password(pw)},
        )
        pid = db.execute(
            text("INSERT INTO projects(project_code,name,workspace_id)"
                 " VALUES(:c,'AR Project',:w) RETURNING project_id"),
            {"c": f"AR-{suffix}", "w": wid},
        ).scalar()
        pid2 = db.execute(
            text("INSERT INTO projects(project_code,name,workspace_id)"
                 " VALUES(:c,'AR Other',:w) RETURNING project_id"),
            {"c": f"AR2-{suffix}", "w": wid},
        ).scalar()
        iid = db.execute(
            text("""INSERT INTO items(num, project_id, description, status)
                    VALUES (nextval('joinery_number_seq'), :p, 'Vanity', 'CLEAR')
                    RETURNING item_id"""),
            {"p": pid},
        ).scalar()
        db.commit()
    finally:
        db.close()

    c = TestClient(app)
    assert c.post("/auth/login",
                  json={"workspace_slug": slug, "email": email, "password": pw}
                  ).status_code == 200
    return {"client": c, "pid": pid, "pid2": pid2, "iid": iid}


def _area(ctx, name="Stage 1", pid=None) -> int:
    r = ctx["client"].post(f"/projects/{pid or ctx['pid']}/areas", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["area_id"]


def _room(ctx, area_id, rm_no="057", rm_desc="Dirty Utilities") -> int:
    r = ctx["client"].post(f"/areas/{area_id}/rooms",
                           json={"rm_no": rm_no, "rm_desc": rm_desc})
    assert r.status_code == 201, r.text
    return r.json()["room_id"]


def _item(ctx) -> dict:
    return ctx["client"].get(f"/items/{ctx['iid']}").json()


def _cols(iid: int) -> dict:
    db = SessionLocal()
    try:
        return dict(db.execute(
            text("SELECT stage, rm_no, rm_desc, area_id, room_id"
                 " FROM items WHERE item_id = :i"),
            {"i": iid},
        ).mappings().first())
    finally:
        db.close()


def test_areas_are_created_per_project(ctx):
    """Q457 — one job's 'Stage 1' has nothing to do with another's."""
    a1 = _area(ctx, "Stage 1")
    a2 = _area(ctx, "Stage 1", pid=ctx["pid2"])
    assert a1 != a2

    listed = ctx["client"].get(f"/projects/{ctx['pid']}/areas").json()
    assert [a["name"] for a in listed["areas"]] == ["Stage 1"]
    assert listed["areas"][0]["area_id"] == a1


def test_a_duplicate_name_hands_back_the_existing_area(ctx):
    a = _area(ctx, "Stage 1")
    r = ctx["client"].post(f"/projects/{ctx['pid']}/areas", json={"name": "Stage 1"})
    assert r.status_code == 409
    assert r.json()["detail"] == {"code": "AREA_EXISTS", "area_id": a}


def test_rooms_nest_under_their_area(ctx):
    """Q552 — the list nests them, and the same number may repeat in another area."""
    a1, a2 = _area(ctx, "Stage 1"), _area(ctx, "Stage 2")
    _room(ctx, a1, "057", "Dirty Utilities")
    _room(ctx, a2, "057", "Different area, same number")

    areas = ctx["client"].get(f"/projects/{ctx['pid']}/areas").json()["areas"]
    by_name = {a["name"]: a for a in areas}
    assert [r["rm_no"] for r in by_name["Stage 1"]["rooms"]] == ["057"]
    assert [r["rm_no"] for r in by_name["Stage 2"]["rooms"]] == ["057"]


def test_setting_area_and_room_also_writes_the_legacy_columns(ctx):
    """Q455 + Q435 — 25 read sites still use stage / rm_no / rm_desc."""
    a = _area(ctx, "Joinery Lab")
    r = _room(ctx, a, "068", "Bacterial Room")

    resp = ctx["client"].patch(f"/items/{ctx['iid']}", json={"area_id": a, "room_id": r})
    assert resp.status_code == 200, resp.text

    cols = _cols(ctx["iid"])
    assert cols["area_id"] == a and cols["room_id"] == r
    assert cols["stage"] == "Joinery Lab"
    assert cols["rm_no"] == "068"
    assert cols["rm_desc"] == "Bacterial Room"


def test_a_room_from_another_area_is_refused(ctx):
    """Q552 — the composite FK would reject it; the route explains instead."""
    a1, a2 = _area(ctx, "Stage 1"), _area(ctx, "Stage 2")
    foreign = _room(ctx, a2, "101")

    r = ctx["client"].patch(f"/items/{ctx['iid']}",
                            json={"area_id": a1, "room_id": foreign})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "BAD_ROOM"
    assert _cols(ctx["iid"])["area_id"] is None, "nothing was written"


def test_a_room_without_an_area_is_refused(ctx):
    a = _area(ctx, "Stage 1")
    room = _room(ctx, a, "057")
    r = ctx["client"].patch(f"/items/{ctx['iid']}", json={"room_id": room})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ROOM_WITHOUT_AREA"


def test_an_area_from_another_project_is_refused(ctx):
    foreign = _area(ctx, "Stage 1", pid=ctx["pid2"])
    r = ctx["client"].patch(f"/items/{ctx['iid']}", json={"area_id": foreign})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "BAD_AREA"


def test_moving_room_is_allowed_and_audited(ctx):
    """Q458 — yes, with audit. It rides item_edit_log, which already exists."""
    a = _area(ctx, "Stage 1")
    first, second = _room(ctx, a, "057", "Dirty Utilities"), _room(ctx, a, "102", "PC2 Holding")

    ctx["client"].patch(f"/items/{ctx['iid']}", json={"area_id": a, "room_id": first})
    ctx["client"].patch(f"/items/{ctx['iid']}", json={"room_id": second})

    assert _cols(ctx["iid"])["room_id"] == second
    assert _cols(ctx["iid"])["rm_no"] == "102"

    log = [e for e in _item(ctx)["edit_log"] if e["field"] == "room"]
    assert log, "the move is in the item's history"
    assert log[0]["old_value"] == "057 · Dirty Utilities"
    assert log[0]["new_value"] == "102 · PC2 Holding"


def test_moving_area_clears_the_room_it_left_behind(ctx):
    """The old room belonged to the old area — the composite FK forbids the pair."""
    a1, a2 = _area(ctx, "Stage 1"), _area(ctx, "Stage 2")
    room = _room(ctx, a1, "057", "Dirty Utilities")
    ctx["client"].patch(f"/items/{ctx['iid']}", json={"area_id": a1, "room_id": room})

    r = ctx["client"].patch(f"/items/{ctx['iid']}", json={"area_id": a2})
    assert r.status_code == 200, r.text

    cols = _cols(ctx["iid"])
    assert cols["area_id"] == a2
    assert cols["room_id"] is None
    assert cols["rm_no"] is None and cols["rm_desc"] is None
    assert cols["stage"] == "Stage 2"


def test_area_counts_include_only_joinery_items(ctx):
    a = _area(ctx, "Stage 1")
    ctx["client"].patch(f"/items/{ctx['iid']}", json={"area_id": a})
    areas = ctx["client"].get(f"/projects/{ctx['pid']}/areas").json()["areas"]
    assert areas[0]["item_count"] == 1
