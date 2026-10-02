"""Marking a quote line "ordered by hand" (migration 0049).

A line Generate Orders holds back — or one the PM simply ordered outside the system —
had no way to leave the quote's "N lines not yet ordered" count. The dismissal is its
own set of columns (not `orders_generated_at`, which means "a run made POs"), needs a
reason, is gated like Generate Orders (`estimating:approve`), and can be undone.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal

from .conftest import TRUNCATE_TABLES
from .test_estimating_generate_orders import (
    _bootstrap, _line_flags, _login_as, _make_quote, _orphan_only_quote,
    _po_count, _sql_scalar, _two_line_quote,
)


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        s.execute(text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _dismiss(c, rid: int, lid: int, reason="ordered by phone from Plyco"):
    return c.post(f"/revisions/{rid}/lines/{lid}/order-dismissal", json={"reason": reason})


def _restore(c, rid: int, lid: int):
    return c.delete(f"/revisions/{rid}/lines/{lid}/order-dismissal")


def _preview_lines(c, rid: int) -> dict[int, dict]:
    r = c.get(f"/revisions/{rid}/order-preview")
    assert r.status_code == 200, r.text
    return {l["line_id"]: l for l in r.json()["lines"]}


def _audit(event: str) -> list[dict]:
    s = SessionLocal()
    try:
        rows = s.execute(
            text("SELECT payload FROM audit_log WHERE event = :e ORDER BY id"), {"e": event}
        ).scalars().all()
        return list(rows)
    finally:
        s.close()


# ----------------------------------------------------------------------------
# what a dismissal does
# ----------------------------------------------------------------------------

def test_a_dismissed_line_is_recorded_and_is_not_ordered_by_a_default_run():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]

    r = _dismiss(c, rid, l1, "  ordered by phone  ")

    assert r.status_code == 204, r.text
    flags = _line_flags(c, quote["estimate_id"], rid)
    assert flags[l1]["orders_dismissed_at"] is not None
    assert flags[l1]["orders_dismissed_reason"] == "ordered by phone"   # trimmed
    assert flags[l1]["orders_dismissed_by_name"] == "U"
    assert flags[l1]["orders_generated_at"] is None, "a dismissal is not a generated order"
    assert flags[l2]["orders_dismissed_at"] is None

    # Preview: listed, never selected, and carrying who / why.
    shown = _preview_lines(c, rid)
    assert shown[l1]["selected"] is False
    assert shown[l1]["orders_dismissed_reason"] == "ordered by phone"
    assert shown[l2]["selected"] is True

    # A default run orders what is left — line 2 alone (3 boards, no hardware).
    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 200, r.text
    assert r.json()["orders_created"] == 1
    po = c.get(f"/orders/{r.json()['po_ids'][0]}").json()
    assert [float(l["quantity"]) for l in po["lines"]] == [3.0]
    assert _po_count(ctx["wid"]) == 1
    assert _line_flags(c, quote["estimate_id"], rid)[l1]["orders_generated_at"] is None


def test_a_dismissed_line_cannot_be_picked_by_id():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    assert _dismiss(c, rid, l1).status_code == 204

    r = c.post(f"/revisions/{rid}/generate-orders", json={"include_line_ids": [l1, l2]})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == {"code": "LINES_DISMISSED", "line_ids": [l1]}
    assert _po_count(ctx["wid"]) == 0, "a refused run creates nothing"
    assert _line_flags(c, quote["estimate_id"], rid)[l2]["orders_generated_at"] is None

    # The preview refuses the same selection, like the run.
    r = c.get(f"/revisions/{rid}/order-preview", params={"include_line_ids": [l1]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "LINES_DISMISSED"


def test_with_every_line_dismissed_there_is_nothing_left_to_generate():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    assert _dismiss(c, rid, l1).status_code == 204
    assert _dismiss(c, rid, l2).status_code == 204

    r = c.post(f"/revisions/{rid}/generate-orders")

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ORDERS_ALREADY_GENERATED"
    assert _po_count(ctx["wid"]) == 0
    assert all(not l["selected"] for l in _preview_lines(c, rid).values())


def test_a_held_back_line_can_be_dismissed_and_stops_blocking_the_quote():
    """The case that prompted this: a line whose only material has no supplier is held
    back forever. Ordered by hand, it should leave the pending set."""
    ctx, c, estimate_id, rid, line_id = _orphan_only_quote()
    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "NOTHING_ORDERABLE"
    assert _preview_lines(c, rid)[line_id]["held_back"] is True

    assert _dismiss(c, rid, line_id, "ordered from CDK direct").status_code == 204

    preview = c.get(f"/revisions/{rid}/order-preview").json()
    assert preview["lines"][0]["selected"] is False
    assert preview["unassigned"] == [], "the dismissed line no longer holds its material 'unassigned'"
    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ORDERS_ALREADY_GENERATED"


def test_undoing_a_dismissal_makes_the_line_orderable_again():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    assert _dismiss(c, rid, l1, "ordered by phone").status_code == 204

    assert _restore(c, rid, l1).status_code == 204

    flags = _line_flags(c, quote["estimate_id"], rid)
    assert flags[l1]["orders_dismissed_at"] is None
    assert flags[l1]["orders_dismissed_reason"] is None
    assert flags[l1]["orders_dismissed_by_name"] is None
    r = c.post(f"/revisions/{rid}/generate-orders")        # both lines again
    assert r.status_code == 200, r.text
    assert sorted(float(l["quantity"]) for l in
                  c.get(f"/orders/{r.json()['po_ids'][0]}").json()["lines"] if l["material_table"] == "board_materials") == [5.0]
    assert _line_flags(c, quote["estimate_id"], rid)[l1]["orders_generated_at"] is not None


def test_dismissing_and_undoing_are_audited_with_the_reason():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    assert _dismiss(c, rid, l1, "ordered by phone").status_code == 204
    assert _restore(c, rid, l1).status_code == 204

    assert _audit("estimate.order_dismiss") == [
        {"revision_id": rid, "line_id": l1, "reason": "ordered by phone"}
    ]
    assert _audit("estimate.order_undismiss") == [
        {"revision_id": rid, "line_id": l1, "previous_reason": "ordered by phone"}
    ]


# ----------------------------------------------------------------------------
# what it refuses
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 501}])
def test_a_reason_is_required_and_bounded(body):
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]

    r = c.post(f"/revisions/{rid}/lines/{l1}/order-dismissal", json=body)

    assert r.status_code == 422, r.text
    assert _line_flags(c, quote["estimate_id"], rid)[l1]["orders_dismissed_at"] is None
    assert _audit("estimate.order_dismiss") == []


def test_a_quote_that_is_not_converted_cannot_have_lines_dismissed():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx)            # won, not converted
    r = _dismiss(c, quote["revision_id"], quote["line_ids"][0])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "NOT_CONVERTED"


def test_a_line_excluded_at_convert_cannot_be_dismissed():
    ctx = _bootstrap()
    c = ctx["client"]
    quote = _make_quote(ctx, second_board_line=True)
    l1, l2 = quote["line_ids"]
    r = c.post(f"/revisions/{quote['revision_id']}/convert", json={"include_line_ids": [l1]})
    assert r.status_code == 200, r.text

    r = _dismiss(c, quote["revision_id"], l2)

    assert r.status_code == 409 and r.json()["detail"]["code"] == "LINE_NOT_IN_HANDOVER"


def test_an_unknown_line_or_one_from_another_revision_is_404():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    other_quote = _make_quote(ctx)      # a second quote in this workspace: a line of another revision

    assert _dismiss(c, rid, 999999).status_code == 404
    r = _dismiss(c, rid, other_quote["line_ids"][0])
    assert r.status_code == 404 and r.json()["detail"]["code"] == "LINE_NOT_FOUND"
    assert _restore(c, rid, 999999).status_code == 404


def test_a_line_a_run_covered_cannot_be_dismissed():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    assert c.post(f"/revisions/{rid}/generate-orders",
                  json={"include_line_ids": [l1]}).status_code == 200

    r = _dismiss(c, rid, l1)

    assert r.status_code == 409 and r.json()["detail"]["code"] == "ALREADY_GENERATED"
    assert _line_flags(c, quote["estimate_id"], rid)[l1]["orders_dismissed_at"] is None


def test_dismissing_twice_and_undoing_what_is_not_dismissed_are_refused():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    assert _dismiss(c, rid, l1, "first").status_code == 204

    r = _dismiss(c, rid, l1, "second")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ALREADY_DISMISSED"
    assert _line_flags(c, quote["estimate_id"], rid)[l1]["orders_dismissed_reason"] == "first"

    r = _restore(c, rid, l2)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "NOT_DISMISSED"


@pytest.mark.parametrize("role", ["viewer", "drafter", "purchase_officer"])
def test_a_role_without_estimating_approve_cannot_dismiss_or_undo(role):
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    other = _login_as(ctx["slug"], role)

    assert _dismiss(other, rid, l1).status_code == 403
    assert _line_flags(c, quote["estimate_id"], rid)[l1]["orders_dismissed_at"] is None
    assert _dismiss(c, rid, l1).status_code == 204
    assert _restore(other, rid, l1).status_code == 403
    assert _line_flags(c, quote["estimate_id"], rid)[l1]["orders_dismissed_at"] is not None


def test_another_workspaces_revision_is_404_for_both_verbs():
    ctx, c, quote, l1, l2 = _two_line_quote()
    rid = quote["revision_id"]
    other = _bootstrap()

    assert _dismiss(other["client"], rid, l1).status_code == 404
    assert _restore(other["client"], rid, l1).status_code == 404
    assert _line_flags(c, quote["estimate_id"], rid)[l1]["orders_dismissed_at"] is None


# ----------------------------------------------------------------------------
# the database says the same thing
# ----------------------------------------------------------------------------

def test_the_database_refuses_a_line_that_is_both_covered_and_dismissed():
    ctx, c, quote, l1, l2 = _two_line_quote()
    s = SessionLocal()
    try:
        with pytest.raises(IntegrityError):
            s.execute(
                text(
                    "UPDATE estimate_line SET orders_generated_at = now(),"
                    " orders_dismissed_at = now(), orders_dismissed_reason = 'x'"
                    " WHERE line_id = :l"
                ),
                {"l": l1},
            )
    finally:
        s.rollback()
        s.close()


def test_the_database_refuses_a_dismissal_without_a_reason_or_with_a_blank_one():
    ctx, c, quote, l1, l2 = _two_line_quote()
    for set_clause in (
        "orders_dismissed_at = now()",                                         # no reason
        "orders_dismissed_at = now(), orders_dismissed_reason = '   '",        # blank
        "orders_dismissed_reason = 'x'",                                        # reason, no time
    ):
        s = SessionLocal()
        try:
            with pytest.raises(IntegrityError):
                s.execute(text(f"UPDATE estimate_line SET {set_clause} WHERE line_id = :l"),
                          {"l": l1})
        finally:
            s.rollback()
            s.close()
    assert _sql_scalar("SELECT orders_dismissed_at FROM estimate_line WHERE line_id = :l",
                       l=l1) is None
