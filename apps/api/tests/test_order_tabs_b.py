"""The order pop-up's tabs, part 2 (0065): Glass C price calculator, Timber order form, TGSolid production rows."""
import pytest

from .conftest import truncate_fixture
from .helpers import login, login_same_workspace
from .helpers_po import _code, _order, make_ws

_cleanup = truncate_fixture("order_tg_run", "order_glass_calc", "order_timber_form", "glass_rate")


@pytest.fixture
def ws():
    return make_ws()


def _rate(c, kind, name, rate, um, supplier_no="1221") -> int:
    r = c.post("/glass-rates", json={"kind": kind, "name": name, "rate": rate, "um": um, "supplier_no": supplier_no})
    assert r.status_code == 201, r.text
    return r.json()["glass_rate_id"]


def _put(c, oid, body):
    r = c.put(f"/orders/{oid}/glass-calc", json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ── Glass C ─────────────────────────────────────────────────────────────────────────────────────

def test_glass_calc_works_out_the_old_screens_figures(ws):
    c = ws["buyer"]
    silver = _rate(c, "glass", "6mm Silver Float", "43.00", "m2")
    clear = _rate(c, "glass", "4mm Clear Float", "37.07", "m2")
    fpar = _rate(c, "process", "4-6mm FPAR", "3.23", "Lm")
    notch = _rate(c, "process", "Notch Out", "6.46", "ea")
    a = _order(ws, description="1471 x 1000 x 6 - Silver glass splashback")
    out = c.get(f"/orders/{a}/glass-calc").json()
    assert out["suggested_size"] == {"length_mm": 1471, "width_mm": 1000, "thick_mm": 6}
    assert out["total"] == "0.00" and all(not ln["ticked"] and ln["cost"] == "0.00" for ln in out["lines"])
    out = _put(c, a, {"length_mm": 1471, "width_mm": 1000, "thick_mm": 6, "selection": {
        str(silver): {"qty": "1", "ticked": True}, str(fpar): {"qty": "1", "ticked": True},
        str(notch): {"qty": "5", "ticked": False}}})
    by = {ln["name"]: ln for ln in out["lines"]}
    assert by["6mm Silver Float"]["cost"] == "63.25" and by["4-6mm FPAR"]["cost"] == "15.96"
    assert by["Notch Out"]["cost"] == "0.00" and by["Notch Out"]["qty"] == "5"      # a qty typed before the tick is kept
    assert by["4mm Clear Float"]["ticked"] is False
    assert out["total"] == "79.22"                      # from the unrounded sum, as the old screen: 63.253 + 15.964
    assert out["area_m2"] == "1.4710" and out["perimeter_m"] == "4.9420"
    out = _put(c, a, {"length_mm": 1471, "width_mm": 1000, "selection": {str(notch): {"qty": "5", "ticked": True}}})
    assert {ln["name"]: ln["cost"] for ln in out["lines"]}["Notch Out"] == "32.30" and out["total"] == "32.30"
    assert out["thick_mm"] is None
    # Clear All
    assert _put(c, a, {"length_mm": 1471, "width_mm": 1000, "selection": {}})["total"] == "0.00"
    assert clear  # keep the rate used by the list above
    # no size: m2 / Lm rates cost nothing, each rates still cost
    out = _put(c, a, {"selection": {str(silver): {"ticked": True}, str(notch): {"ticked": True, "qty": "2"}}})
    assert out["area_m2"] is None and out["total"] == "12.92"


def test_glass_rates_are_kept_by_purchase_officer_and_admin(ws):
    c = ws["buyer"]
    rid = _rate(c, "glass", "8mm Clear", "115.32", "m2")
    r = c.post("/glass-rates", json={"kind": "glass", "name": " 8MM clear ", "rate": "1", "um": "m2"})
    assert r.status_code == 409 and _code(r) == "GLASS_RATE_EXISTS"
    assert c.patch(f"/glass-rates/{rid}", json={"rate": "120", "supplier_no": "9"}).json()["rate"] == "120.0000"
    assert c.patch(f"/glass-rates/{rid}", json={"rate": None}).status_code == 422
    assert c.post("/glass-rates", json={"kind": "glass", "name": "Bad", "rate": "-1", "um": "m2"}).status_code == 422
    drafter, _ = login_same_workspace(ws["wid"], "drafter")
    assert drafter.get("/glass-rates").status_code == 200
    assert drafter.post("/glass-rates", json={"kind": "glass", "name": "X", "rate": "1", "um": "m2"}).status_code == 403
    assert drafter.patch(f"/glass-rates/{rid}", json={"is_active": False}).status_code == 403
    a = _order(ws)
    _put(c, a, {"length_mm": 1000, "width_mm": 1000, "selection": {str(rid): {"ticked": True}}})
    c.patch(f"/glass-rates/{rid}", json={"is_active": False})
    names = [ln["name"] for ln in c.get(f"/orders/{a}/glass-calc").json()["lines"]]
    assert names == ["8mm Clear"]                        # a switched-off rate stays while it is ticked
    b = _order(ws)
    assert c.get(f"/orders/{b}/glass-calc").json()["lines"] == []


def test_glass_calc_refuses_unknown_rates_and_closed_orders(ws):
    c = ws["buyer"]
    rid = _rate(c, "glass", "Float", "10", "m2")
    a = _order(ws)
    r = c.put(f"/orders/{a}/glass-calc", json={"selection": {"999999": {"ticked": True}}})
    assert r.status_code == 404 and _code(r) == "RATE_NOT_FOUND"
    assert c.put(f"/orders/{a}/glass-calc", json={"length_mm": 0}).status_code == 422
    c.patch(f"/orders/{a}", json={"status": "Cancelled"})
    r = c.put(f"/orders/{a}/glass-calc", json={"selection": {str(rid): {"ticked": True}}})
    assert r.status_code == 409 and _code(r) == "ORDER_LOCKED"
    assert c.get(f"/orders/{a}/glass-calc").status_code == 200


# ── Timber ──────────────────────────────────────────────────────────────────────────────────────

def test_timber_form_is_saved_cleared_and_made_into_a_pdf(ws):
    c = ws["buyer"]
    a = _order(ws)
    blank = c.get(f"/orders/{a}/timber").json()
    assert blank["face"] is None and blank["face_by_tg"] is False and blank["has_form"] is False
    body = {"face": "Oak veneer", "back": "Oak veneer", "substrate": "MDF", "substrate_by_tg": True,
            "finished_description": "Pressed panel 2400x1200", "deliver_to": "133-135 Mc Ewan Rd\nHeidelberg Heights",
            "special_instructions": "Wrap each panel"}
    got = c.put(f"/orders/{a}/timber", json=body).json()
    assert got["substrate"] == "MDF" and got["substrate_by_tg"] is True and got["face_by_tg"] is False
    assert c.get(f"/orders/{a}/timber/form").status_code == 404
    made = c.post(f"/orders/{a}/timber/form")
    assert made.status_code == 201 and made.json()["has_form"] is True and made.json()["form_created_at"]
    pdf = c.get(f"/orders/{a}/timber/form")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    cleared = c.put(f"/orders/{a}/timber", json={}).json()        # CLEAR saves empty fields
    assert cleared["face"] is None and cleared["substrate_by_tg"] is False and cleared["has_form"] is True
    c.patch(f"/orders/{a}", json={"status": "Cancelled"})
    r = c.put(f"/orders/{a}/timber", json=body)
    assert r.status_code == 409 and _code(r) == "ORDER_LOCKED"
    assert ws["viewer"].put(f"/orders/{_order(ws)}/timber", json=body).status_code == 403


# ── TGSolid ─────────────────────────────────────────────────────────────────────────────────────

def test_tg_solid_rows(ws):
    c = ws["buyer"]
    a = _order(ws)
    assert c.get(f"/orders/{a}/tg-runs").json() == {"runs": []}
    r = c.post(f"/orders/{a}/tg-runs", json={"production_start": "2026-08-11", "date_made": "2026-08-13", "made_by": "Alex",
                                             "date_ex_factory": "2026-09-03", "location": "#3"})
    assert r.status_code == 201
    run = r.json()["runs"][0]
    assert (run["made_by"], run["location"], run["date_ex_factory"], run["notes"]) == ("Alex", "#3", "2026-09-03", None)
    rid = run["run_id"]
    assert c.patch(f"/orders/{a}/tg-runs/{rid}", json={"notes": "second coat", "date_made": None}).json()["runs"][0]["notes"] == "second coat"
    assert c.get(f"/orders/{a}/tg-runs").json()["runs"][0]["date_made"] is None
    assert c.patch(f"/orders/{a}/tg-runs/{rid + 999}", json={"notes": "x"}).status_code == 404
    c.post(f"/orders/{a}/tg-runs", json={})
    assert len(c.get(f"/orders/{a}/tg-runs").json()["runs"]) == 2
    assert len(c.delete(f"/orders/{a}/tg-runs/{rid}").json()["runs"]) == 1
    c.patch(f"/orders/{a}", json={"status": "Delivered"})
    r = c.post(f"/orders/{a}/tg-runs", json={"made_by": "Z"})
    assert r.status_code == 409 and _code(r) == "ORDER_LOCKED"


# ── another workspace ───────────────────────────────────────────────────────────────────────────

def test_other_workspace_is_404(ws):
    c = ws["buyer"]
    rid = _rate(c, "glass", "Float", "10", "m2")
    a = _order(ws)
    run = c.post(f"/orders/{a}/tg-runs", json={"made_by": "A"}).json()["runs"][0]["run_id"]
    c.put(f"/orders/{a}/timber", json={"face": "x"})
    other, _, _ = login("admin", prefix="tabsb-other")
    ghost = 10**9
    for method, tail, kw in [
        ("get", "/glass-calc", {}), ("put", "/glass-calc", {"json": {"selection": {}}}),
        ("get", "/timber", {}), ("put", "/timber", {"json": {}}), ("post", "/timber/form", {}), ("get", "/timber/form", {}),
        ("get", "/tg-runs", {}), ("post", "/tg-runs", {"json": {}}),
        ("patch", f"/tg-runs/{run}", {"json": {"notes": "x"}}), ("delete", f"/tg-runs/{run}", {}),
    ]:
        real = getattr(other, method)(f"/orders/{a}{tail}", **kw)
        gone = getattr(other, method)(f"/orders/{ghost}{tail.replace(str(run), str(ghost))}", **kw)
        assert real.status_code == gone.status_code == 404, (method, tail, real.status_code, gone.status_code)
    assert other.patch(f"/glass-rates/{rid}", json={"rate": "1"}).status_code == 404
    assert other.get("/glass-rates").json() == {"rates": []}
    # another workspace's rate in a selection is refused like a missing one
    mine = _order(ws)
    r = c.put(f"/orders/{mine}/glass-calc", json={"selection": {str(_rate(other, "glass", "Theirs", "1", "m2")): {"ticked": True}}})
    assert r.status_code == 404
    assert c.get(f"/orders/{a}/tg-runs").json()["runs"][0]["made_by"] == "A"
