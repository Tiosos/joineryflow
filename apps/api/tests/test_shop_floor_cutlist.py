"""Shop Floor after the cutlist re-key (Plan V1 Q412, migration 0030).

`test_shop_floor_routes.py` gives every item its own cutlist, so it exercises
the pre-re-key behaviour unchanged. This file covers what only a **shared**
cutlist can show:

  Q439/Q562  one completion writes done_date to every linked item, but only
             to those whose own stage order contains that stage
  Q562       the cutlist advances only when EVERY linked item's priors are done
  Q446       undo reverses the whole cutlist
  Q539       an item linked after the completion gains nothing, and loses
             nothing on undo
  Q411/0030  one active assignment per (cutlist, stage), not per item
"""
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.shop_floor import queries as q

from .conftest import TRUNCATE_TABLES

_STAGES = [("DOWN", 4), ("CNC", 5), ("EDGED", 6), ("PAINTED", 7), ("MADE", 8)]


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        s.execute(text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


@pytest.fixture
def shared():
    """One cutlist, three items whose painting flags deliberately disagree."""
    s = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]
        s.execute(text("INSERT INTO status_options(status_key, sort_order)"
                       " VALUES('CLEAR', 1) ON CONFLICT DO NOTHING"))
        for key, order in _STAGES:
            s.execute(
                text("INSERT INTO stages(stage_key, label, sort_order)"
                     " VALUES(:k, :k, :o) ON CONFLICT DO NOTHING"),
                {"k": key, "o": order},
            )
        wid = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'SF WS') RETURNING id"),
            {"s": f"sfc-{suffix}"},
        ).scalar()
        pid = s.execute(
            text("INSERT INTO projects(project_code, name, workspace_id)"
                 " VALUES(:c, 'SF Project', :w) RETURNING project_id"),
            {"c": f"SFC-{suffix}", "w": wid},
        ).scalar()
        cid = s.execute(
            text("INSERT INTO cutlist(project_id, cutlist_no)"
                 " VALUES (:p, nextval('joinery_number_seq')) RETURNING cutlist_id"),
            {"p": pid},
        ).scalar()

        items = {}
        for label, painting_req, paint_last in (
            ("painted_door", True, False),
            ("raw_carcass", False, False),
            ("paint_last_top", True, True),
        ):
            items[label] = s.execute(
                text(
                    """
                    INSERT INTO items(num, project_id, description, status,
                                      painting_req, paint_after_assembly,
                                      cutlist_id, deleted)
                    VALUES (nextval('joinery_number_seq'), :p, :d, 'CLEAR',
                            :pr, :pl, :c, false)
                    RETURNING item_id
                    """
                ),
                {"p": pid, "d": label, "pr": painting_req, "pl": paint_last, "c": cid},
            ).scalar()
        s.commit()
        yield {"workspace_id": wid, "project_id": pid, "cutlist_id": cid, "items": items}
    finally:
        s.close()


def _stage_rows(cutlist_id: int, stage_key: str) -> set[int]:
    """item_ids on the cutlist carrying a done_date for this stage."""
    s = SessionLocal()
    try:
        rows = s.execute(
            text(
                """
                SELECT i.item_id FROM items i
                JOIN item_stages st ON st.item_id = i.item_id
                WHERE i.cutlist_id = :c AND st.stage_key = :s
                  AND st.done_date IS NOT NULL
                """
            ),
            {"c": cutlist_id, "s": stage_key},
        ).scalars().all()
        return set(rows)
    finally:
        s.close()


def test_fan_out_reaches_every_linked_item(shared):
    """Q439: one completion, N item_stages rows."""
    s = SessionLocal()
    try:
        touched = q.fan_out_stage_done(db=s, cutlist_id=shared["cutlist_id"], stage_key="DOWN")
        s.commit()
    finally:
        s.close()
    assert set(touched) == set(shared["items"].values())
    assert _stage_rows(shared["cutlist_id"], "DOWN") == set(shared["items"].values())


def test_fan_out_skips_items_whose_order_excludes_the_stage(shared):
    """Q562: `raw_carcass` has painting_req=false, so it never gets PAINTED."""
    s = SessionLocal()
    try:
        touched = q.fan_out_stage_done(db=s, cutlist_id=shared["cutlist_id"], stage_key="PAINTED")
        s.commit()
    finally:
        s.close()

    expected = {shared["items"]["painted_door"], shared["items"]["paint_last_top"]}
    assert set(touched) == expected
    assert shared["items"]["raw_carcass"] not in touched
    assert _stage_rows(shared["cutlist_id"], "PAINTED") == expected


def test_one_lagging_item_blocks_the_whole_cutlist(shared):
    """Q562: the gate is the union across every linked item."""
    s = SessionLocal()
    try:
        # two of three items have DOWN done
        for label in ("painted_door", "raw_carcass"):
            q.upsert_item_stage_done(db=s, item_id=shared["items"][label], stage_key="DOWN")
        s.commit()
        missing = q.cutlist_prior_stages_done(
            db=s, cutlist_id=shared["cutlist_id"], stage_key="CNC"
        )
        assert missing == ["DOWN"], missing

        # the third catches up
        q.upsert_item_stage_done(db=s, item_id=shared["items"]["paint_last_top"], stage_key="DOWN")
        s.commit()
        assert q.cutlist_prior_stages_done(
            db=s, cutlist_id=shared["cutlist_id"], stage_key="CNC"
        ) == []
    finally:
        s.close()


def test_undo_reverses_the_whole_cutlist(shared):
    """Q446: not one item."""
    s = SessionLocal()
    try:
        q.fan_out_stage_done(db=s, cutlist_id=shared["cutlist_id"], stage_key="DOWN")
        s.commit()
        assert _stage_rows(shared["cutlist_id"], "DOWN") == set(shared["items"].values())

        cleared = q.fan_in_stage_undone(
            db=s, cutlist_id=shared["cutlist_id"], stage_key="DOWN"
        )
        s.commit()
    finally:
        s.close()

    assert set(cleared) == set(shared["items"].values())
    assert _stage_rows(shared["cutlist_id"], "DOWN") == set()


def test_late_joiner_gains_nothing_and_loses_nothing(shared):
    """Q539: linked after the completion, so it has no row to gain or clear."""
    s = SessionLocal()
    try:
        q.fan_out_stage_done(db=s, cutlist_id=shared["cutlist_id"], stage_key="DOWN")
        s.commit()

        late = s.execute(
            text(
                """
                INSERT INTO items(num, project_id, description, status,
                                  painting_req, paint_after_assembly,
                                  cutlist_id, deleted)
                VALUES (nextval('joinery_number_seq'), :p, 'late joiner', 'CLEAR',
                        true, false, :c, false)
                RETURNING item_id
                """
            ),
            {"p": shared["project_id"], "c": shared["cutlist_id"]},
        ).scalar()
        s.commit()

        # it gained nothing from the completion that already happened
        rows = s.execute(
            text("SELECT COUNT(*) FROM item_stages WHERE item_id = :i"), {"i": late}
        ).scalar()
        assert rows == 0

        cleared = q.fan_in_stage_undone(
            db=s, cutlist_id=shared["cutlist_id"], stage_key="DOWN"
        )
        s.commit()
        still = s.execute(
            text("SELECT COUNT(*) FROM item_stages WHERE item_id = :i"), {"i": late}
        ).scalar()
    finally:
        s.close()

    assert late in cleared          # visited
    assert still == 0               # and unchanged


def test_one_active_assignment_per_cutlist_stage(shared):
    """0030's rebuilt partial unique index, on the new key."""
    from sqlalchemy.exc import IntegrityError

    s = SessionLocal()
    try:
        uid = s.execute(
            text(
                "INSERT INTO app_user(workspace_id, email, full_name,"
                " password_hash, auth_role, is_shop_worker)"
                " VALUES (:w, :e, 'W', 'x', 'editor', true) RETURNING id"
            ),
            {"w": shared["workspace_id"], "e": f"w-{uuid.uuid4().hex[:6]}@x.test"},
        ).scalar()
        s.commit()

        q.insert_assignment(
            db=s, cutlist_id=shared["cutlist_id"], stage_key="DOWN",
            worker_id=uid, note=None, assigned_by=uid,
        )
        s.commit()

        with pytest.raises(IntegrityError):
            q.insert_assignment(
                db=s, cutlist_id=shared["cutlist_id"], stage_key="DOWN",
                worker_id=uid, note=None, assigned_by=uid,
            )
            s.commit()
        s.rollback()
    finally:
        s.close()
