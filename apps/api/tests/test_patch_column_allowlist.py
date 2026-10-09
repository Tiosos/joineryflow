"""Patch functions interpolate column names into `UPDATE ... SET`, so each lists the columns
it may write (`sql_columns.require_columns`). A key outside the list is refused before any SQL
runs. Request schemas already stop a client sending one, so these call the query functions."""
import pytest

from app.auth.sessions import AuthUser
from app.db import SessionLocal
from app.material_takes import queries as take_q
from app.qc import queries as qc_q
from app.sql_columns import require_columns

from .helpers import login
from .helpers_material_take import _cleanup, _client, _item, _sql, _workspace  # noqa: F401


def test_require_columns_accepts_a_subset_and_names_the_unknown():
    require_columns({"a": 1}, frozenset({"a", "b"}))
    with pytest.raises(ValueError, match="not a patchable column: status, zzz"):
        require_columns(["zzz", "status", "a"], frozenset({"a"}))


@pytest.fixture
def qc_ctx(truncate_all):
    c, wid, uid = login("manager", prefix="al")
    pid = _sql("INSERT INTO projects(project_code, name, workspace_id) VALUES ('AL', 'AL', :w)"
               " RETURNING project_id", w=wid)
    iid = _sql("""INSERT INTO items(num, project_id, description, status)
                  VALUES (nextval('joinery_number_seq'), :p, 'Vanity', 'CLEAR') RETURNING item_id""", p=pid)
    return {"c": c, "wid": wid, "uid": uid, "iid": iid}


def _call(fn, ctx, id_kw, id_, changes):
    db = SessionLocal()
    try:
        return fn(db, workspace_id=ctx["wid"], actor_id=ctx["uid"], changes=changes, **{id_kw: id_})
    finally:
        db.rollback()
        db.close()


def test_patch_defect_refuses_a_column_outside_its_list(qc_ctx):
    r = qc_ctx["c"].post(f"/items/{qc_ctx['iid']}/qc/defects", json={"description": "chip"})
    did = r.json()["defect_id"]
    with pytest.raises(ValueError, match="status"):
        _call(qc_q.patch_defect, qc_ctx, "defect_id", did, {"description": "x", "status": "resolved"})
    assert qc_ctx["c"].get(f"/items/{qc_ctx['iid']}/qc/defects").json()[0]["status"] == "open"


def test_patch_checklist_item_refuses_a_column_outside_its_list(qc_ctx):
    r = qc_ctx["c"].post(f"/items/{qc_ctx['iid']}/qc/checklist", json={"label": "Doors hang"})
    cid = r.json()["checklist_item_id"]
    with pytest.raises(ValueError, match="item_id"):
        _call(qc_q.patch_checklist_item, qc_ctx, "checklist_item_id", cid, {"item_id": 999})


def test_patch_rework_refuses_a_column_outside_its_list(qc_ctx):
    r = qc_ctx["c"].post(f"/items/{qc_ctx['iid']}/qc/rework",
                         json={"kind": "internal", "cause": "x", "scope": "y"})
    rid = r.json()["rework_id"]
    with pytest.raises(ValueError, match="status"):
        _call(qc_q.patch_rework, qc_ctx, "rework_id", rid, {"cause": "z", "status": "closed"})


def test_patch_take_line_refuses_a_column_outside_its_list():
    wid = _workspace()
    c = _client(wid, "drafter")
    iid = _item(wid)["item"]
    tid = c.post(f"/items/{iid}/material-take/generate").json()["take_id"]
    line = c.get(f"/items/{iid}/material-take").json()["draft"]["lines"][0]
    uid = _sql("SELECT id FROM app_user WHERE workspace_id = :w LIMIT 1", w=wid)
    actor = AuthUser(id=uid, workspace_id=wid, email="x", full_name="x", auth_role="drafter")
    db = SessionLocal()
    try:
        with pytest.raises(ValueError, match="source"):
            take_q.patch_line(db, tid, line["line_id"], wid, actor, {"note": "n", "source": "manual"})
    finally:
        db.rollback()
        db.close()
    assert c.get(f"/items/{iid}/material-take").json()["draft"]["lines"][0]["source"] == "generated"
