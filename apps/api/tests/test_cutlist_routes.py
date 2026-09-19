"""Cutlist entity routes (Plan V1 §B, migration 0027).

Covers the four rules the query layer enforces that no CHECK constraint can:

  Q411  an item links to at most one cutlist  -> 409 ITEM_HAS_CUTLIST
  Q444  a cutlist belongs to one project      -> 409 WRONG_PROJECT
  Q417  a related part gets no cutlist number -> 409 RELATED_PART
  Q539  linking to a cutlist with completed stages does NOT backfill

plus Q410 (several items may share one cutlist), Q442/Q443 (the number is
system-allocated from the company-wide sequence and never supplied by the
caller) and workspace isolation.
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
        # TRUNCATE_TABLES already names `projects` and `items`, and CASCADE from
        # `projects` reaches `cutlist` (verified) — no extra names needed.
        s.execute(
            text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE")
        )
        s.commit()
    finally:
        s.close()


def _make_item(db, *, project_id: int, description: str,
               row_type: str = "joinery_item", parent_item_id: int | None = None,
               part_type: str | None = None) -> int:
    return db.execute(
        text(
            """
            INSERT INTO items(num, project_id, description, status, row_type,
                              parent_item_id, related_part_type_key)
            VALUES (nextval('joinery_number_seq'), :p, :d, 'CLEAR', :rt, :par, :pt)
            RETURNING item_id
            """
        ),
        {"p": project_id, "d": description, "rt": row_type,
         "par": parent_item_id, "pt": part_type},
    ).scalar()


@pytest.fixture
def ctx():
    """Workspace + two projects + a drafter client, plus a second workspace."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"cl-{suffix}"
    db = SessionLocal()
    try:
        db.execute(
            text("INSERT INTO status_options(status_key, sort_order)"
                 " VALUES('CLEAR', 1) ON CONFLICT DO NOTHING")
        )
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'Cutlist WS') RETURNING id"),
            {"s": slug},
        ).scalar()
        other_wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'Other WS') RETURNING id"),
            {"s": f"{slug}-other"},
        ).scalar()
        email, pw = f"d-{suffix}@example.com", "pw"
        db.execute(
            text(
                "INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)"
                " VALUES (:w, :e, 'Drafter', :p, 'drafter')"
            ),
            {"w": wid, "e": email, "p": hash_password(pw)},
        )
        pid = db.execute(
            text("INSERT INTO projects(project_code, name, workspace_id)"
                 " VALUES(:c, 'Project One', :w) RETURNING project_id"),
            {"c": f"C1-{suffix}", "w": wid},
        ).scalar()
        pid2 = db.execute(
            text("INSERT INTO projects(project_code, name, workspace_id)"
                 " VALUES(:c, 'Project Two', :w) RETURNING project_id"),
            {"c": f"C2-{suffix}", "w": wid},
        ).scalar()
        other_pid = db.execute(
            text("INSERT INTO projects(project_code, name, workspace_id)"
                 " VALUES(:c, 'Foreign', :w) RETURNING project_id"),
            {"c": f"C3-{suffix}", "w": other_wid},
        ).scalar()

        item_a = _make_item(db, project_id=pid, description="unit A")
        item_b = _make_item(db, project_id=pid, description="unit B")
        item_other_project = _make_item(db, project_id=pid2, description="other project")
        item_other_ws = _make_item(db, project_id=other_pid, description="other workspace")
        related = _make_item(db, project_id=pid, description="brass rail",
                             row_type="related_part", parent_item_id=item_a,
                             part_type="metal")
        db.commit()
    finally:
        db.close()

    c = TestClient(app)
    r = c.post("/auth/login",
               json={"workspace_slug": slug, "email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {
        "client": c, "pid": pid, "pid2": pid2,
        "item_a": item_a, "item_b": item_b,
        "item_other_project": item_other_project,
        "item_other_ws": item_other_ws, "related": related,
    }


def _create(ctx, name="Kitchen run", pid=None):
    r = ctx["client"].post(
        f"/projects/{pid or ctx['pid']}/cutlists", json={"name": name}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_allocates_a_number_the_caller_never_supplies(ctx):
    """Q442/Q443: system-allocated from the company-wide sequence."""
    first = _create(ctx, "First")
    second = _create(ctx, "Second")

    assert first["cutlist_no"] != second["cutlist_no"]
    assert second["cutlist_no"] > first["cutlist_no"]
    assert first["item_count"] == 0
    assert first["name"] == "First"


def test_several_items_share_one_cutlist(ctx):
    """Q410: sharing is the point of the entity."""
    cl = _create(ctx)
    for iid in (ctx["item_a"], ctx["item_b"]):
        r = ctx["client"].post(f"/cutlists/{cl['cutlist_id']}/items", json={"item_id": iid})
        assert r.status_code == 200, r.text

    detail = ctx["client"].get(f"/cutlists/{cl['cutlist_id']}").json()
    assert detail["item_count"] == 2
    assert {i["item_id"] for i in detail["items"]} == {ctx["item_a"], ctx["item_b"]}


def test_second_cutlist_for_one_item_is_refused(ctx):
    """Q411 — and the 409 names the cutlist already held."""
    first, second = _create(ctx, "First"), _create(ctx, "Second")
    ctx["client"].post(f"/cutlists/{first['cutlist_id']}/items",
                       json={"item_id": ctx["item_a"]})

    r = ctx["client"].post(f"/cutlists/{second['cutlist_id']}/items",
                           json={"item_id": ctx["item_a"]})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "ITEM_HAS_CUTLIST"
    assert detail["cutlist_id"] == first["cutlist_id"]
    assert detail["cutlist_no"] == first["cutlist_no"]


def test_relinking_to_the_same_cutlist_is_idempotent(ctx):
    cl = _create(ctx)
    for _ in range(2):
        r = ctx["client"].post(f"/cutlists/{cl['cutlist_id']}/items",
                               json={"item_id": ctx["item_a"]})
        assert r.status_code == 200, r.text
    assert ctx["client"].get(f"/cutlists/{cl['cutlist_id']}").json()["item_count"] == 1


def test_item_from_another_project_is_refused(ctx):
    """Q444: a cutlist belongs to exactly one project."""
    cl = _create(ctx)
    r = ctx["client"].post(f"/cutlists/{cl['cutlist_id']}/items",
                           json={"item_id": ctx["item_other_project"]})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "WRONG_PROJECT"


def test_related_part_cannot_hold_a_cutlist(ctx):
    """Q417: its Tracking row shows an order number, not a cutlist number."""
    cl = _create(ctx)
    r = ctx["client"].post(f"/cutlists/{cl['cutlist_id']}/items",
                           json={"item_id": ctx["related"]})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "RELATED_PART"


def test_item_from_another_workspace_is_not_found(ctx):
    cl = _create(ctx)
    r = ctx["client"].post(f"/cutlists/{cl['cutlist_id']}/items",
                           json={"item_id": ctx["item_other_ws"]})
    assert r.status_code == 404


def test_linking_does_not_backfill_completed_stages(ctx):
    """Q539: the late joiner stays blank and catches up at the next completion."""
    cl = _create(ctx)
    ctx["client"].post(f"/cutlists/{cl['cutlist_id']}/items", json={"item_id": ctx["item_a"]})

    db = SessionLocal()
    try:
        db.execute(
            text("INSERT INTO stages(stage_key, label, sort_order)"
                 " VALUES('DOWN','Down',4) ON CONFLICT DO NOTHING")
        )
        db.execute(
            text("INSERT INTO item_stages(item_id, stage_key, done_date)"
                 " VALUES(:i, 'DOWN', CURRENT_DATE)"),
            {"i": ctx["item_a"]},
        )
        db.commit()
    finally:
        db.close()

    ctx["client"].post(f"/cutlists/{cl['cutlist_id']}/items", json={"item_id": ctx["item_b"]})

    db = SessionLocal()
    try:
        late_rows = db.execute(
            text("SELECT COUNT(*) FROM item_stages WHERE item_id = :i"),
            {"i": ctx["item_b"]},
        ).scalar()
    finally:
        db.close()
    assert late_rows == 0


def test_unlink_returns_the_item_to_no_cutlist(ctx):
    cl = _create(ctx)
    ctx["client"].post(f"/cutlists/{cl['cutlist_id']}/items", json={"item_id": ctx["item_a"]})

    r = ctx["client"].delete(f"/cutlists/{cl['cutlist_id']}/items/{ctx['item_a']}")
    assert r.status_code == 204
    assert ctx["client"].get(f"/cutlists/{cl['cutlist_id']}").json()["item_count"] == 0

    # unlinking twice is a 409, not a silent success
    again = ctx["client"].delete(f"/cutlists/{cl['cutlist_id']}/items/{ctx['item_a']}")
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "NOT_LINKED"


def test_delete_is_refused_while_items_are_linked(ctx):
    cl = _create(ctx)
    ctx["client"].post(f"/cutlists/{cl['cutlist_id']}/items", json={"item_id": ctx["item_a"]})

    r = ctx["client"].delete(f"/cutlists/{cl['cutlist_id']}")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "HAS_ITEMS"

    ctx["client"].delete(f"/cutlists/{cl['cutlist_id']}/items/{ctx['item_a']}")
    assert ctx["client"].delete(f"/cutlists/{cl['cutlist_id']}").status_code == 204


def test_patch_renames_but_cannot_change_the_number(ctx):
    cl = _create(ctx, "Before")
    r = ctx["client"].patch(f"/cutlists/{cl['cutlist_id']}", json={"name": "After"})
    assert r.status_code == 200
    assert r.json()["name"] == "After"
    # cutlist_no is not an input anywhere; the schema ignores it
    r2 = ctx["client"].patch(f"/cutlists/{cl['cutlist_id']}", json={"cutlist_no": 1})
    assert r2.status_code == 200
    assert r2.json()["cutlist_no"] == cl["cutlist_no"]


def test_list_is_scoped_to_the_project(ctx):
    _create(ctx, "In project one")
    _create(ctx, "Also project one")
    _create(ctx, "In project two", pid=ctx["pid2"])

    one = ctx["client"].get(f"/projects/{ctx['pid']}/cutlists").json()
    two = ctx["client"].get(f"/projects/{ctx['pid2']}/cutlists").json()
    assert len(one["cutlists"]) == 2
    assert len(two["cutlists"]) == 1


# ── C2: what the Tracking CUTLIST column actually shows (Q438 / Q568) ─────────


def _tracking(ctx) -> dict[int, dict]:
    r = ctx["client"].get(f"/projects/{ctx['pid']}/items")
    assert r.status_code == 200, r.text
    return {row["id"]: row for row in r.json()["items"]}


def test_tracking_shows_the_shared_cutlist_number_not_the_item_id(ctx):
    """Q438/Q568 — the bug this task existed to fix.

    Q540 gave every migrated item a cutlist numbered as itself, so reading
    `items.num` into the CUTLIST column looked correct until a cutlist was
    genuinely shared.  Then the second item's row showed its own Item ID.
    """
    cl = _create(ctx)
    for iid in (ctx["item_a"], ctx["item_b"]):
        assert ctx["client"].post(
            f"/cutlists/{cl['cutlist_id']}/items", json={"item_id": iid}
        ).status_code == 200

    rows = _tracking(ctx)
    a, b = rows[ctx["item_a"]], rows[ctx["item_b"]]

    assert a["cutlist_no"] == b["cutlist_no"] == cl["cutlist_no"], (
        "both rows carry the shared cutlist's number"
    )
    assert a["item_number"] != b["item_number"], "their Item IDs stay distinct"
    assert b["item_number"] != b["cutlist_no"], (
        "the second item's own number is NOT its cutlist number"
    )
    assert a["cutlist_id"] == b["cutlist_id"] == cl["cutlist_id"]


def test_tracking_leaves_the_cutlist_number_empty_until_one_is_assigned(ctx):
    """Q440: an item may hold no cutlist indefinitely."""
    row = _tracking(ctx)[ctx["item_a"]]
    assert row["cutlist_no"] is None
    assert row["cutlist_id"] is None
    assert row["item_number"] is not None, "it still has an Item ID"


def test_the_stage_strip_stays_per_item_on_a_shared_cutlist(ctx):
    """Q441 + Q539: one shared cutlist, but each row's strip is its own.

    The late joiner's earlier stages stay blank (Q539), so two rows on the same
    cutlist legitimately differ — which is only visible because Tracking reads
    `item_stages` per row rather than joining the cutlist.
    """
    cl = _create(ctx)
    assert ctx["client"].post(
        f"/cutlists/{cl['cutlist_id']}/items", json={"item_id": ctx["item_a"]}
    ).status_code == 200

    db = SessionLocal()
    try:
        db.execute(
            text("INSERT INTO stages(stage_key, label, sort_order)"
                 " VALUES('DOWN','Down',4) ON CONFLICT DO NOTHING")
        )
        db.execute(
            text("INSERT INTO item_stages(item_id, stage_key, done_date)"
                 " VALUES(:i, 'DOWN', CURRENT_DATE)"),
            {"i": ctx["item_a"]},
        )
        db.commit()
    finally:
        db.close()

    assert ctx["client"].post(
        f"/cutlists/{cl['cutlist_id']}/items", json={"item_id": ctx["item_b"]}
    ).status_code == 200

    rows = _tracking(ctx)
    a, b = rows[ctx["item_a"]], rows[ctx["item_b"]]
    assert a["cutlist_no"] == b["cutlist_no"], "same cutlist"
    assert a["stages"].get("DOWN", {}).get("done_date") is not None
    assert "DOWN" not in b["stages"], (
        "the late joiner's strip is blank — it is not borrowed from the cutlist"
    )
