"""Per-material order coverage (migration 0051).

Coverage used to be per quote line, so a line was ordered whole or held back whole. Now each
catalog material on a line has its own state — pending, ordered by a run, or ordered by hand
(required note) — and a line is done once none of its materials is pending. The line's own
`orders_generated_at` / `orders_dismissed_*` are derived from its materials.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal

from .helpers_estimating_orders import (
    _bootstrap, _line_flags, _link_supplier, _login_as, _mixed_quote, _po_count, _sql_scalar,
)


pytestmark = pytest.mark.usefixtures("truncate_after")


def _path(rid: int, lid: int, mtype: str, mid: int) -> str:
    return f"/revisions/{rid}/lines/{lid}/materials/{mtype}/{mid}/order-dismissal"


def _materials(c, rid: int, lid: int) -> dict[int, dict]:
    pv = c.get(f"/revisions/{rid}/order-preview").json()
    line = next(l for l in pv["lines"] if l["line_id"] == lid)
    return {m["material_id"]: m for m in line["materials"]}


def _audit(event: str) -> list[dict]:
    s = SessionLocal()
    try:
        return list(s.execute(
            text("SELECT payload FROM audit_log WHERE event = :e ORDER BY id"), {"e": event}
        ).scalars().all())
    finally:
        s.close()


def test_one_material_can_be_ordered_by_hand_and_the_rest_still_orders():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    orphan = ctx["unassigned_board_id"]

    r = c.post(_path(rid, mixed, "BOARD", orphan), json={"reason": "  phoned Plyco  "})
    assert r.status_code == 204, r.text
    m = _materials(c, rid, mixed)[orphan]
    assert m["state"] == "dismissed" and m["orders_dismissed_reason"] == "phoned Plyco"
    assert m["orders_dismissed_by_name"] == "U"
    assert _materials(c, rid, mixed)[ctx["board_id"]]["state"] == "pending"
    assert _line_flags(c, eid, rid)[mixed]["orders_dismissed_at"] is None, "still pending"

    pv = c.get(f"/revisions/{rid}/order-preview").json()
    assert pv["unassigned"] == [], "a dismissed material stops being reported"
    r = c.post(f"/revisions/{rid}/generate-orders")
    assert r.status_code == 200, r.text
    assert r.json()["lines_created"] == 1 and r.json()["uncovered_line_ids"] == []
    # board ordered by a run + orphan by hand: the line is done and reads as generated
    flags = _line_flags(c, eid, rid)[mixed]
    assert flags["orders_generated_at"] is not None and flags["orders_dismissed_at"] is None


def test_a_line_whose_materials_are_all_dismissed_reads_as_dismissed():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    for mid in (ctx["board_id"], ctx["unassigned_board_id"]):
        assert c.post(_path(rid, mixed, "BOARD", mid), json={"reason": f"by hand {mid}"}).status_code == 204
    flags = _line_flags(c, eid, rid)[mixed]
    assert flags["orders_generated_at"] is None
    assert flags["orders_dismissed_at"] is not None
    assert flags["orders_dismissed_reason"].startswith("by hand")
    assert c.post(f"/revisions/{rid}/generate-orders").status_code == 409
    assert _po_count(ctx["wid"]) == 0


def test_undoing_a_material_dismissal_makes_it_pending_and_the_line_pending_again():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    for mid in (ctx["board_id"], ctx["unassigned_board_id"]):
        c.post(_path(rid, mixed, "BOARD", mid), json={"reason": "by hand"})
    assert _line_flags(c, eid, rid)[mixed]["orders_dismissed_at"] is not None

    r = c.delete(_path(rid, mixed, "BOARD", ctx["board_id"]))
    assert r.status_code == 204, r.text
    assert _materials(c, rid, mixed)[ctx["board_id"]]["state"] == "pending"
    assert _line_flags(c, eid, rid)[mixed]["orders_dismissed_at"] is None
    assert c.delete(_path(rid, mixed, "BOARD", ctx["board_id"])).status_code == 409


def test_the_line_level_button_dismisses_only_what_is_still_pending():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    c.post(f"/revisions/{rid}/generate-orders")             # orders the supplied board
    r = c.post(f"/revisions/{rid}/lines/{mixed}/order-dismissal", json={"reason": "rest by phone"})
    assert r.status_code == 204, r.text
    mats = _materials(c, rid, mixed)
    assert mats[ctx["board_id"]]["state"] == "generated"
    assert mats[ctx["unassigned_board_id"]]["state"] == "dismissed"
    flags = _line_flags(c, eid, rid)[mixed]
    assert flags["orders_generated_at"] is not None and flags["orders_dismissed_at"] is None
    assert _po_count(ctx["wid"]) == 1

    # undoing it reopens the dismissed material only — never the one a run ordered
    assert c.delete(f"/revisions/{rid}/lines/{mixed}/order-dismissal").status_code == 204
    mats = _materials(c, rid, mixed)
    assert mats[ctx["board_id"]]["state"] == "generated"
    assert mats[ctx["unassigned_board_id"]]["state"] == "pending"
    assert _line_flags(c, eid, rid)[mixed]["orders_generated_at"] is None
    assert c.delete(f"/revisions/{rid}/lines/{mixed}/order-dismissal").status_code == 409


def test_a_material_a_run_ordered_cannot_be_dismissed():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    c.post(f"/revisions/{rid}/generate-orders")
    r = c.post(_path(rid, mixed, "BOARD", ctx["board_id"]), json={"reason": "x"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ALREADY_GENERATED"
    r = c.delete(_path(rid, mixed, "BOARD", ctx["board_id"]))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "NOT_DISMISSED"


def test_dismissing_the_same_material_twice_is_refused():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    p = _path(rid, mixed, "BOARD", ctx["unassigned_board_id"])
    assert c.post(p, json={"reason": "a"}).status_code == 204
    r = c.post(p, json={"reason": "b"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ALREADY_DISMISSED"


@pytest.mark.parametrize("reason", ["", "   ", "x" * 501])
def test_a_material_dismissal_needs_a_reason_of_1_to_500_characters(reason):
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    r = c.post(_path(rid, mixed, "BOARD", ctx["board_id"]), json={"reason": reason})
    assert r.status_code == 422
    assert _materials(c, rid, mixed)[ctx["board_id"]]["state"] == "pending"


def test_unknown_material_line_revision_and_type_are_refused():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    ok = {"reason": "x"}
    r = c.post(_path(rid, mixed, "BOARD", 999999), json=ok)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "MATERIAL_NOT_ON_LINE"
    r = c.post(_path(rid, 999999, "BOARD", ctx["board_id"]), json=ok)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "LINE_NOT_FOUND"
    assert c.post(_path(999999, mixed, "BOARD", ctx["board_id"]), json=ok).status_code == 404
    assert c.post(_path(rid, mixed, "NOPE", ctx["board_id"]), json=ok).status_code == 422


def test_a_material_dismissal_is_audited_with_its_reason():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    c.post(_path(rid, mixed, "BOARD", ctx["board_id"]), json={"reason": "by phone"})
    c.delete(_path(rid, mixed, "BOARD", ctx["board_id"]))
    (d,) = _audit("estimate.order_material_dismiss")
    assert d["line_id"] == mixed and d["material_id"] == ctx["board_id"] and d["reason"] == "by phone"
    (u,) = _audit("estimate.order_material_undismiss")
    assert u["previous_reason"] == "by phone"


def test_the_generate_audit_row_lists_the_materials_it_ordered():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    c.post(f"/revisions/{rid}/generate-orders")
    (a,) = _audit("estimate.generate_orders")
    assert a["materials_ordered"] == [
        {"line_id": mixed, "material_type": "BOARD", "material_id": ctx["board_id"]}
    ]
    assert a["uncovered_line_ids"] == [mixed] and a["included_line_ids"] == []


def test_the_material_verbs_need_estimating_approve():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    viewer = _login_as(ctx["slug"], "viewer")
    p = _path(rid, mixed, "BOARD", ctx["board_id"])
    assert viewer.post(p, json={"reason": "x"}).status_code == 403
    assert viewer.delete(p).status_code == 403


def test_another_workspaces_revision_is_a_404_for_the_material_verbs():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    other = _bootstrap()["client"]
    p = _path(rid, mixed, "BOARD", ctx["board_id"])
    assert other.post(p, json={"reason": "x"}).status_code == 404
    assert other.delete(p).status_code == 404


def test_the_database_refuses_a_row_that_is_both_ordered_and_dismissed():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    s = SessionLocal()
    try:
        with pytest.raises(IntegrityError):
            s.execute(text(
                "INSERT INTO estimate_line_material_order (line_id, material_type, material_id,"
                " orders_generated_at, orders_dismissed_at, orders_dismissed_reason)"
                " VALUES (:l, 'BOARD', :m, now(), now(), 'x')"
            ), {"l": mixed, "m": ctx["board_id"]})
    finally:
        s.rollback()
        s.close()


def test_deleting_a_line_removes_its_material_rows():
    ctx = _bootstrap()
    c = ctx["client"]
    eid, rid, mixed, _ = _mixed_quote(ctx)
    c.post(_path(rid, mixed, "BOARD", ctx["board_id"]), json={"reason": "x"})
    s = SessionLocal()
    try:
        s.execute(text("DELETE FROM estimate_line WHERE line_id = :l"), {"l": mixed})
        s.commit()
    finally:
        s.close()
    assert _sql_scalar("SELECT count(*) FROM estimate_line_material_order WHERE line_id = :l", l=mixed) == 0
