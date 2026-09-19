"""`items.num` comes from one shared sequence (Plan V1 Q541, migration 0027).

Before this, the tree had **two** inconsistent allocators for a single UNIQUE
column:

* `items/queries.py`     — `nextval('items_item_id_seq') + 100000`
* `estimating/queries.py` — `SELECT COALESCE(MAX(num), 0) + 1 FROM items`

The second is a read-then-insert with no lock. Two estimate conversions
running at once both read the same maximum, and the loser dies on
`items_num_key`. These tests pin the fix: every allocation goes through
`joinery_number_seq`, so concurrent callers can never be handed the same
number.

`joinery_number_seq` is a standalone sequence with no owning table, so
`TRUNCATE ... RESTART IDENTITY` does NOT reset it — numbers keep climbing
across the suite, which is what a company-wide counter should do.
"""
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .conftest import TRUNCATE_TABLES


@pytest.fixture
def project_id():
    """A workspace + project for the items to hang off."""
    s = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]
        wid = s.execute(
            text(
                "INSERT INTO workspace(slug, name)"
                " VALUES(:slug, 'Numbering WS') RETURNING id"
            ),
            {"slug": f"num-ws-{suffix}"},
        ).scalar()
        pid = s.execute(
            text(
                "INSERT INTO projects(project_code, name, workspace_id)"
                " VALUES(:code, :name, :wid) RETURNING project_id"
            ),
            {"code": f"NUM-{suffix}", "name": f"Numbering {suffix}", "wid": wid},
        ).scalar()
        s.commit()
        yield pid
    finally:
        s.close()

    s = SessionLocal()
    try:
        s.execute(
            text(f"TRUNCATE items, {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE")
        )
        s.commit()
    finally:
        s.close()


def _insert_with(session, pid, num, description):
    return session.execute(
        text(
            "INSERT INTO items(num, project_id, description, status)"
            " VALUES(:n, :p, :d, 'CLEAR') RETURNING item_id"
        ),
        {"n": num, "p": pid, "d": description},
    ).scalar()


def test_two_conversions_in_flight_both_succeed(project_id):
    """The regression this task exists for.

    Two conversions each take a number BEFORE either inserts — the exact
    interleaving the old `MAX(num) + 1` allocator lost. Both must commit.
    """
    a, b = SessionLocal(), SessionLocal()
    try:
        num_a = a.execute(text("SELECT nextval('joinery_number_seq')")).scalar()
        num_b = b.execute(text("SELECT nextval('joinery_number_seq')")).scalar()

        assert num_a != num_b, "concurrent callers were handed the same number"

        _insert_with(a, project_id, num_a, "conversion A")
        _insert_with(b, project_id, num_b, "conversion B")
        a.commit()
        b.commit()
    finally:
        a.close()
        b.close()

    s = SessionLocal()
    try:
        rows = s.execute(
            text(
                "SELECT COUNT(*) AS total, COUNT(DISTINCT num) AS distinct_nums"
                "  FROM items WHERE project_id = :p"
            ),
            {"p": project_id},
        ).mappings().one()
    finally:
        s.close()

    assert rows["total"] == 2
    assert rows["distinct_nums"] == 2


def test_allocator_never_reissues_a_number(project_id):
    """Successive allocations strictly increase, so none can collide."""
    s = SessionLocal()
    try:
        nums = [
            s.execute(text("SELECT nextval('joinery_number_seq')")).scalar()
            for _ in range(25)
        ]
        s.commit()
    finally:
        s.close()

    assert len(set(nums)) == 25
    assert nums == sorted(nums)


def test_sequence_stays_ahead_of_seeded_numbers(project_id):
    """`make seed` inserts FIXED numbers (290001.., 297830..) so it stays
    idempotent, and it runs AFTER `make migrate`. The seed therefore ends by
    advancing the sequence past what it wrote; without that step the next
    allocation would start far below the seeded rows.
    """
    s = SessionLocal()
    try:
        _insert_with(s, project_id, 297988, "legacy-style seeded row")
        s.commit()

        # the step the seed performs
        s.execute(
            text(
                "SELECT setval('joinery_number_seq', GREATEST("
                "  (SELECT last_value FROM joinery_number_seq),"
                "  COALESCE((SELECT MAX(num) FROM items), 0)))"
            )
        )
        s.commit()

        nxt = s.execute(text("SELECT nextval('joinery_number_seq')")).scalar()
        top = s.execute(text("SELECT MAX(num) FROM items")).scalar()
        s.commit()
    finally:
        s.close()

    assert nxt > top, f"allocator would reissue {nxt}, at or below existing {top}"


def test_seed_setval_is_idempotent(project_id):
    """Re-running `make seed` must never move the sequence backwards."""
    s = SessionLocal()
    try:
        _insert_with(s, project_id, 297500, "seeded")
        s.commit()

        stmt = text(
            "SELECT setval('joinery_number_seq', GREATEST("
            "  (SELECT last_value FROM joinery_number_seq),"
            "  COALESCE((SELECT MAX(num) FROM items), 0)))"
        )
        first = s.execute(stmt).scalar()
        again = s.execute(stmt).scalar()
        third = s.execute(stmt).scalar()
        s.commit()
    finally:
        s.close()

    assert first == again == third
