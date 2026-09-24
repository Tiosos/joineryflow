"""Material Summary routes (plan tasks C1–C3; spec §5, §7; Q582, Q585, Q586)."""
import pytest

from .test_material_take_routes import _client, _cleanup, _item, _sql, _workspace  # noqa: F401


@pytest.fixture
def proj():
    wid = _workspace()
    drafter = _client(wid, "drafter")
    a = _item(wid, parts=((1000, 1000, 1),))        # 1 m²  → 0.34 sheet
    pid = _sql("SELECT project_id FROM items WHERE item_id = :i", i=a["item"])
    return {"w": wid, "c": drafter, "pid": pid, "a": a}


def _second_item(p, *, board, area_parts=((1000, 1000, 1),)):
    """Another item in the same project on the same board material."""
    iid = _sql("""INSERT INTO items(num, project_id, description, status)
                  VALUES (nextval('joinery_number_seq'), :p, 'Tall', 'LIVE') RETURNING item_id""",
               p=p["pid"])
    mid = _sql("INSERT INTO modules(item_id, module_no) VALUES (:i, 1) RETURNING module_id", i=iid)
    for ln, wd, q in area_parts:
        _sql("INSERT INTO parts(module_id, qty, len_mm, wid_mm, board_material_id)"
             " VALUES (:m, :q, :l, :d, :b)", m=mid, q=q, l=ln, d=wd, b=board)
    return iid


def _approve(c, iid):
    tid = c.post(f"/items/{iid}/material-take/generate").json()["take_id"]
    assert c.post(f"/material-takes/{tid}/approve").status_code == 204
    return tid


def _build(c, pid):
    r = c.post(f"/projects/{pid}/material-summary")
    assert r.status_code == 201, r.text
    return r.json()["summary_id"]


def _current(c, pid):
    r = c.get(f"/projects/{pid}/material-summary")
    assert r.status_code == 200, r.text
    return r.json()


# --- C1 ---------------------------------------------------------------------

def test_consolidates_one_line_per_material_rounding_up_once(proj):
    """Q586: two 0.34-sheet items → 1 sheet, not 2."""
    c = proj["c"]
    b = _second_item(proj, board=proj["a"]["board"])
    _approve(c, proj["a"]["item"])
    _approve(c, b)
    _build(c, proj["pid"])
    [line] = _current(c, proj["pid"])["summary"]["lines"]
    assert (line["unit"], line["qty_consolidated"]) == ("sheet", "1")
    assert sorted(s["qty"] for s in line["sources"]) == ["0.34", "0.34"]
    assert {s["take_version"] for s in line["sources"]} == {1}


def test_items_without_an_approved_take_are_listed_not_summed(proj):
    c = proj["c"]
    b = _second_item(proj, board=proj["a"]["board"])
    _approve(c, proj["a"]["item"])
    c.post(f"/items/{b}/material-take/generate")          # draft only
    _build(c, proj["pid"])
    cur = _current(c, proj["pid"])
    assert [m["item_id"] for m in cur["missing_takes"]] == [b]
    assert len(cur["summary"]["lines"][0]["sources"]) == 1


def test_other_lines_group_by_exact_description(proj):
    c = proj["c"]
    b = _second_item(proj, board=proj["a"]["board"])
    for iid, qty in ((proj["a"]["item"], "4"), (b, "6")):
        tid = c.post(f"/items/{iid}/material-take/generate").json()["take_id"]
        c.post(f"/material-takes/{tid}/lines", json={"description": "Edge tape", "unit": "m", "qty": qty})
        c.post(f"/material-takes/{tid}/approve")
    _build(c, proj["pid"])
    other = [l for l in _current(c, proj["pid"])["summary"]["lines"] if l["material_type"] == "OTHER"]
    assert [(l["description"], l["qty_consolidated"]) for l in other] == [("Edge tape", "10")]


def test_no_summary_yet(proj):
    cur = _current(proj["c"], proj["pid"])
    assert cur["summary"] is None and [m["item_id"] for m in cur["missing_takes"]] == [proj["a"]["item"]]


# --- C2 ---------------------------------------------------------------------

def test_new_take_version_makes_the_line_stale(proj):
    c, iid = proj["c"], proj["a"]["item"]
    _approve(c, iid)
    _build(c, proj["pid"])
    assert _current(c, proj["pid"])["summary"]["lines"][0]["stale"] is False
    _approve(c, iid)   # v2
    assert _current(c, proj["pid"])["summary"]["lines"][0]["stale"] is True


def test_hard_deleted_item_makes_the_line_stale(proj):
    c = proj["c"]
    b = _second_item(proj, board=proj["a"]["board"], area_parts=((2000, 1500, 2),))
    _approve(c, proj["a"]["item"])
    _approve(c, b)
    _build(c, proj["pid"])
    _sql("DELETE FROM items WHERE item_id = :i", i=b)       # cascades its take + source rows
    [line] = _current(c, proj["pid"])["summary"]["lines"]
    assert line["stale"] is True and len(line["sources"]) == 1


def test_nest_sheets_come_from_the_latest_cut_plan(proj):
    c = proj["c"]
    _approve(c, proj["a"]["item"])
    sku = _sql("SELECT sku FROM board_materials WHERE material_id = :b", b=proj["a"]["board"])
    for n in (1, 2):   # an older plan, then the current one with 3 sheets
        plan = _sql("INSERT INTO cut_plan(workspace_id, project_id, name) VALUES (:w, :p, :n) RETURNING id",
                    w=proj["w"], p=proj["pid"], n=f"nest {n}")
        for s in range(n + 1 if n == 2 else 1):
            _sql("INSERT INTO cut_sheet(cut_plan_id, sheet_no, material_sku) VALUES (:c, :s, :k)",
                 c=plan, s=s + 1, k=sku)
    _build(c, proj["pid"])
    assert _current(c, proj["pid"])["summary"]["lines"][0]["nest_sheets"] == 3


def test_nest_sku_may_be_a_cv_code(proj):
    """The seed's nest names its sheets by Cabinet Vision code (`18-PB`),
    resolved through cv_material_mapping — not by catalog SKU."""
    c = proj["c"]
    _approve(c, proj["a"]["item"])
    uid = _sql("SELECT id FROM app_user WHERE workspace_id = :w LIMIT 1", w=proj["w"])
    _sql("""INSERT INTO cv_material_mapping(workspace_id, cv_code, target_material_table,
                                            target_material_id, created_by)
            VALUES (:w, 'CV-18', 'board_materials', :b, :u)""", w=proj["w"], b=proj["a"]["board"], u=uid)
    plan = _sql("INSERT INTO cut_plan(workspace_id, project_id, name) VALUES (:w, :p, 'cv nest') RETURNING id",
                w=proj["w"], p=proj["pid"])
    for n in (1, 2):
        _sql("INSERT INTO cut_sheet(cut_plan_id, sheet_no, material_sku) VALUES (:c, :n, 'CV-18')", c=plan, n=n)
    _build(c, proj["pid"])
    assert _current(c, proj["pid"])["summary"]["lines"][0]["nest_sheets"] == 2


def test_on_order_comes_from_the_batch_rollup(proj):
    c = proj["c"]
    _approve(c, proj["a"]["item"])
    _sql("""INSERT INTO procurement_batches(project_id, material_type, material_id, supplier,
                                            qty_ordered, qty_received)
            VALUES (:p, 'BOARD', :b, 'Laminex', 5, 0)""", p=proj["pid"], b=proj["a"]["board"])
    _build(c, proj["pid"])
    line = _current(c, proj["pid"])["summary"]["lines"][0]
    assert (line["qty_on_order"], line["qty_received"]) == ("5.00", "0.00")  # numeric(…,2)


# --- C3 ---------------------------------------------------------------------

def test_confirm_fills_unset_lines_and_freezes(proj):
    c = proj["c"]
    _approve(c, proj["a"]["item"])
    sid = _build(c, proj["pid"])
    lid = _current(c, proj["pid"])["summary"]["lines"][0]["line_id"]
    manager = _client(proj["w"], "manager")
    assert manager.post(f"/material-summaries/{sid}/confirm").status_code == 204
    s = _current(c, proj["pid"])["summary"]
    assert s["status"] == "confirmed" and s["lines"][0]["qty_confirmed"] == "1"
    r = c.patch(f"/material-summaries/{sid}/lines/{lid}", json={"qty_confirmed": "2"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "SUMMARY_CONFIRMED"


def test_pm_override_survives_confirm(proj):
    c = proj["c"]
    _approve(c, proj["a"]["item"])
    sid = _build(c, proj["pid"])
    lid = _current(c, proj["pid"])["summary"]["lines"][0]["line_id"]
    assert c.patch(f"/material-summaries/{sid}/lines/{lid}",
                   json={"qty_confirmed": "2", "note": "offcut risk"}).status_code == 204
    c.post(f"/material-summaries/{sid}/confirm")
    line = _current(c, proj["pid"])["summary"]["lines"][0]
    assert (line["qty_confirmed"], line["note"]) == ("2", "offcut risk")
    assert _sql("SELECT count(*) FROM audit_log WHERE event LIKE 'material_summary.%'") == 3


@pytest.mark.parametrize("role,build,confirm", [
    ("drafter", 201, 204), ("manager", 201, 204), ("editor", 403, 403),
    ("purchase_officer", 403, 403), ("viewer", 403, 403)])
def test_roles(proj, role, build, confirm):
    _approve(proj["c"], proj["a"]["item"])
    u = _client(proj["w"], role)
    assert u.get(f"/projects/{proj['pid']}/material-summary").status_code == 200
    assert u.post(f"/projects/{proj['pid']}/material-summary").status_code == build
    sid = _build(proj["c"], proj["pid"])
    assert u.post(f"/material-summaries/{sid}/confirm").status_code == confirm


def test_history_and_isolation(proj):
    c = proj["c"]
    _approve(c, proj["a"]["item"])
    s1, s2 = _build(c, proj["pid"]), _build(c, proj["pid"])
    assert [h["summary_id"] for h in c.get(f"/projects/{proj['pid']}/material-summaries").json()] == [s2, s1]
    outsider = _client(_workspace(), "admin")
    assert outsider.get(f"/projects/{proj['pid']}/material-summary").status_code == 404
    assert outsider.post(f"/projects/{proj['pid']}/material-summary").status_code == 404
    assert outsider.post(f"/material-summaries/{s2}/confirm").status_code == 404
