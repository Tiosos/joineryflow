"""Material Take routes (plan tasks B2–B5; spec §4, §6, §8)."""
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
        s.execute(text("TRUNCATE board_inventory, board_materials, "
                       + ", ".join(TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _sql(sql, **p):
    s = SessionLocal()
    try:
        r = s.execute(text(sql), p)
        out = r.scalar() if r.returns_rows else None
        s.commit()
        return out
    finally:
        s.close()


def _workspace():
    return _sql("INSERT INTO workspace(slug, name) VALUES (:s, 'MT') RETURNING id",
                s=f"mt-{uuid.uuid4().hex[:8]}")


def _client(wid, role):
    email = f"{role}-{uuid.uuid4().hex[:6]}@x.test"
    _sql("INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)"
         " VALUES (:w, :e, 'U', :p, :r)", w=wid, e=email, p=hash_password("pw"), r=role)
    slug = _sql("SELECT slug FROM workspace WHERE id = :w", w=wid)
    c = TestClient(app)
    assert c.post("/auth/login", json={"workspace_slug": slug, "email": email,
                                       "password": "pw"}).status_code == 200
    return c


def _item(wid, *, parts=((2000, 600, 4),), related=False):
    pid = _sql("INSERT INTO projects(project_code, name, workspace_id) VALUES ('MT', :n, :w)"
               " RETURNING project_id", n=f"MT {uuid.uuid4().hex[:6]}", w=wid)  # name is UNIQUE
    iid = _sql("""INSERT INTO items(num, project_id, description, status)
                  VALUES (nextval('joinery_number_seq'), :p, 'Vanity', 'LIVE') RETURNING item_id""", p=pid)
    bid = _sql("INSERT INTO board_materials(code, description, sku, workspace_id)"
               " VALUES (:c, '18mm MDF', :c, :w) RETURNING material_id", c=f"MT-{iid}", w=wid)
    _sql("INSERT INTO board_inventory(workspace_id, material_id, len_mm, wid_mm, qty_on_hand)"
         " VALUES (:w, :b, 2440, 1220, 5)", w=wid, b=bid)
    mid = _sql("INSERT INTO modules(item_id, module_no) VALUES (:i, 1) RETURNING module_id", i=iid)
    for ln, wd, qty in parts:
        _sql("INSERT INTO parts(module_id, qty, len_mm, wid_mm, board_material_id)"
             " VALUES (:m, :q, :l, :d, :b)", m=mid, q=qty, l=ln, d=wd, b=bid)
    rp = None
    if related:
        rp = _sql("""INSERT INTO items(num, project_id, description, status, row_type,
                                       parent_item_id, related_part_type_key)
                     VALUES (nextval('joinery_number_seq'), :p, 'Frame', 'LIVE', 'related_part',
                             :i, 'metal') RETURNING item_id""", p=pid, i=iid)
    return {"item": iid, "module": mid, "board": bid, "related": rp}


@pytest.fixture
def ws():
    wid = _workspace()
    return {"id": wid, "drafter": _client(wid, "drafter"), "item": _item(wid)}


def _generate(c, iid):
    r = c.post(f"/items/{iid}/material-take/generate")
    assert r.status_code == 201, r.text
    return r.json()["take_id"]


# --- B2: generate + draft CRUD ----------------------------------------------

def test_generate_creates_draft_v1(ws):
    c, iid = ws["drafter"], ws["item"]["item"]
    tid = _generate(c, iid)
    cur = c.get(f"/items/{iid}/material-take").json()
    assert cur["draft"]["take_id"] == tid and cur["draft"]["version"] == 1
    [line] = cur["draft"]["lines"]
    assert (line["unit"], line["qty_generated"], line["source"]) == ("sheet", "1.62", "generated")
    assert cur["approved"] is None and cur["outdated"] is False


def test_second_generate_is_409_with_existing_id(ws):
    c, iid = ws["drafter"], ws["item"]["item"]
    tid = _generate(c, iid)
    r = c.post(f"/items/{iid}/material-take/generate")
    assert r.status_code == 409 and r.json()["detail"] == {"code": "DRAFT_EXISTS", "take_id": tid}


def test_related_part_has_no_take(ws):
    item = _item(ws["id"], related=True)
    r = ws["drafter"].post(f"/items/{item['related']}/material-take/generate")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "RELATED_PART_HAS_NO_TAKE"


def test_wastage_rederives_qty_and_logs_both(ws):
    c, iid = ws["drafter"], ws["item"]["item"]
    tid = _generate(c, iid)
    lid = c.get(f"/items/{iid}/material-take").json()["draft"]["lines"][0]["line_id"]
    assert c.patch(f"/material-takes/{tid}/lines/{lid}", json={"wastage_pct": "10"}).status_code == 204
    line = c.get(f"/items/{iid}/material-take").json()["draft"]["lines"][0]
    assert (line["wastage_pct"], line["qty"]) == ("10", "1.79")   # 1.62 × 1.10 = 1.782 → up
    assert _sql("SELECT count(*) FROM audit_log WHERE event = 'material_take.line_edit'") == 1
    assert _sql("SELECT count(*) FROM item_edit_log WHERE item_id = :i AND field LIKE 'material_take.%'",
                i=iid) == 2   # wastage_pct + qty


def test_generated_line_material_is_read_only(ws):
    c, iid = ws["drafter"], ws["item"]["item"]
    tid = _generate(c, iid)
    lid = c.get(f"/items/{iid}/material-take").json()["draft"]["lines"][0]["line_id"]
    r = c.patch(f"/material-takes/{tid}/lines/{lid}", json={"unit": "m2"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "GENERATED_FIELD_READ_ONLY"


def test_manual_other_line_add_and_remove(ws):
    c, iid = ws["drafter"], ws["item"]["item"]
    tid = _generate(c, iid)
    r = c.post(f"/material-takes/{tid}/lines",
               json={"description": "Edge tape white 22mm", "unit": "m", "qty": "14.5"})
    assert r.status_code == 201
    lid = r.json()["line_id"]
    lines = c.get(f"/items/{iid}/material-take").json()["draft"]["lines"]
    assert {(l["source"], l["material_type"]) for l in lines} == {("generated", "BOARD"),
                                                                  ("manual", "OTHER")}
    assert c.delete(f"/material-takes/{tid}/lines/{lid}").status_code == 204
    assert len(c.get(f"/items/{iid}/material-take").json()["draft"]["lines"]) == 1


def test_other_line_cannot_carry_a_material_id(ws):
    tid = _generate(ws["drafter"], ws["item"]["item"])
    r = ws["drafter"].post(f"/material-takes/{tid}/lines",
                           json={"description": "x", "unit": "each", "qty": "1", "material_id": 5})
    assert r.status_code == 422


def test_regenerate_keeps_manual_lines(ws):
    c, it = ws["drafter"], ws["item"]
    tid = _generate(c, it["item"])
    c.post(f"/material-takes/{tid}/lines", json={"description": "Edge tape", "unit": "m", "qty": "5"})
    _sql("INSERT INTO parts(module_id, qty, len_mm, wid_mm, board_material_id)"
         " VALUES (:m, 4, 2000, 600, :b)", m=it["module"], b=it["board"])
    assert c.post(f"/material-takes/{tid}/regenerate").status_code == 204
    lines = {l["source"]: l for l in c.get(f"/items/{it['item']}/material-take").json()["draft"]["lines"]}
    assert lines["generated"]["qty_generated"] == "3.23" and lines["manual"]["description"] == "Edge tape"


# --- B3: approve + immutability ----------------------------------------------

def test_approve_freezes_and_supersedes(ws):
    c, iid = ws["drafter"], ws["item"]["item"]
    t1 = _generate(c, iid)
    assert c.post(f"/material-takes/{t1}/approve").status_code == 204
    lid = c.get(f"/items/{iid}/material-take").json()["approved"]["lines"][0]["line_id"]
    r = c.patch(f"/material-takes/{t1}/lines/{lid}", json={"qty": "9"})
    assert r.status_code == 409 and r.json()["detail"] == {"code": "TAKE_NOT_DRAFT", "status": "approved"}
    t2 = _generate(c, iid)
    c.post(f"/material-takes/{t2}/approve")
    hist = c.get(f"/items/{iid}/material-takes").json()
    assert [(h["version"], h["status"]) for h in hist] == [(2, "approved"), (1, "superseded")]


@pytest.mark.parametrize("role,code", [("drafter", 204), ("manager", 204), ("admin", 204),
                                       ("editor", 403), ("viewer", 403), ("purchase_officer", 403)])
def test_approve_needs_list_approve(ws, role, code):
    tid = _generate(ws["drafter"], ws["item"]["item"])
    assert _client(ws["id"], role).post(f"/material-takes/{tid}/approve").status_code == code


@pytest.mark.parametrize("role", ["editor", "viewer", "purchase_officer", "estimator"])
def test_edit_needs_drafter(ws, role):
    assert _client(ws["id"], role).post(
        f"/items/{ws['item']['item']}/material-take/generate").status_code == 403


def test_purchase_officer_can_read(ws):
    _generate(ws["drafter"], ws["item"]["item"])
    r = _client(ws["id"], "purchase_officer").get(f"/items/{ws['item']['item']}/material-take")
    assert r.status_code == 200 and r.json()["draft"] is not None


def test_one_draft_per_item_is_a_db_rule(ws):
    tid = _generate(ws["drafter"], ws["item"]["item"])
    uid = _sql("SELECT created_by FROM material_take WHERE take_id = :t", t=tid)
    with pytest.raises(Exception, match="uniq_take_draft"):
        _sql("INSERT INTO material_take(item_id, version, status, generated_at, created_by)"
             " VALUES (:i, 9, 'draft', now(), :u)", i=ws["item"]["item"], u=uid)


# --- B4: drift + review -----------------------------------------------------

def _approved(c, iid):
    tid = _generate(c, iid)
    c.post(f"/material-takes/{tid}/approve")
    return tid


def test_adding_a_part_marks_the_take_outdated(ws):
    c, it = ws["drafter"], ws["item"]
    _approved(c, it["item"])
    assert c.get(f"/items/{it['item']}/material-take").json()["outdated"] is False
    _sql("INSERT INTO parts(module_id, qty, len_mm, wid_mm, board_material_id)"
         " VALUES (:m, 1, 600, 600, :b)", m=it["module"], b=it["board"])
    assert c.get(f"/items/{it['item']}/material-take").json()["outdated"] is True


def test_adjusting_an_approved_takes_own_lines_is_not_drift(ws):
    """Manual lines and adjusted qty never count as drift — only what the
    generator would now say differently."""
    c, iid = ws["drafter"], ws["item"]["item"]
    tid = _generate(c, iid)
    lid = c.get(f"/items/{iid}/material-take").json()["draft"]["lines"][0]["line_id"]
    c.patch(f"/material-takes/{tid}/lines/{lid}", json={"wastage_pct": "15"})
    c.post(f"/material-takes/{tid}/lines", json={"description": "Edge tape", "unit": "m", "qty": "3"})
    c.post(f"/material-takes/{tid}/approve")
    assert c.get(f"/items/{iid}/material-take").json()["outdated"] is False


def test_full_review_opens_the_next_version(ws):
    c, it = ws["drafter"], ws["item"]
    t1 = _approved(c, it["item"])
    _sql("INSERT INTO parts(module_id, qty, len_mm, wid_mm, board_material_id)"
         " VALUES (:m, 4, 2000, 600, :b)", m=it["module"], b=it["board"])
    r = c.post(f"/material-takes/{t1}/reviews", json={"outcome": "full", "note": "new carcass"})
    assert r.status_code == 201 and r.json()["new_take_id"]
    cur = c.get(f"/items/{it['item']}/material-take").json()
    assert cur["draft"]["version"] == 2 and cur["draft"]["lines"][0]["qty_generated"] == "3.23"
    assert cur["approved"]["take_id"] == t1   # still in force until v2 is approved


def test_no_impact_review_opens_nothing(ws):
    c, iid = ws["drafter"], ws["item"]["item"]
    t1 = _approved(c, iid)
    r = c.post(f"/material-takes/{t1}/reviews", json={"outcome": "no_impact"})
    assert r.status_code == 201 and r.json()["new_take_id"] is None
    assert _sql("SELECT outcome FROM material_take_review WHERE take_id = :t", t=t1) == "no_impact"


def test_review_only_on_an_approved_take(ws):
    tid = _generate(ws["drafter"], ws["item"]["item"])
    r = ws["drafter"].post(f"/material-takes/{tid}/reviews", json={"outcome": "full"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "TAKE_NOT_APPROVED"


# --- B5: workspace isolation --------------------------------------------------

def test_other_workspace_sees_404_never_403(ws):
    tid = _generate(ws["drafter"], ws["item"]["item"])
    outsider = _client(_workspace(), "admin")
    iid = ws["item"]["item"]
    for method, path, body in [
        ("get", f"/items/{iid}/material-take", None),
        ("get", f"/items/{iid}/material-takes", None),
        ("post", f"/items/{iid}/material-take/generate", None),
        ("post", f"/material-takes/{tid}/regenerate", None),
        ("post", f"/material-takes/{tid}/lines", {"description": "x", "unit": "m", "qty": "1"}),
        ("post", f"/material-takes/{tid}/approve", None),
        ("post", f"/material-takes/{tid}/reviews", {"outcome": "full"}),
    ]:
        r = getattr(outsider, method)(path, **({"json": body} if body else {}))
        assert r.status_code == 404, (method, path, r.status_code)


def test_a_failed_edit_log_write_rolls_back_the_audit_row(ws, monkeypatch):
    """audit_log and item_edit_log land in one transaction or not at all."""
    from app.material_takes import queries

    def boom(*a, **k):
        raise RuntimeError("edit log down")

    monkeypatch.setattr(queries, "write_edit_log", boom)
    with pytest.raises(RuntimeError):
        ws["drafter"].post(f"/items/{ws['item']['item']}/material-take/generate")
    assert _sql("SELECT count(*) FROM audit_log WHERE event LIKE 'material_take.%'") == 0
    assert _sql("SELECT count(*) FROM material_take") == 0
