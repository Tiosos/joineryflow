"""The Invoice Details window, the Authorisation Form Details window, the payment list and staff photos (0063)."""
import pytest

from .conftest import truncate_fixture
from .helpers import login, login_same_workspace
from .helpers_po import _code, _order, _po, make_ws


@pytest.fixture
def ws():
    return make_ws()


_cleanup = truncate_fixture("po_document", "vendor_contact", "po_invoice", "po_authorisation", "payment_method")

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _method(c, name="Account") -> int:
    r = c.post("/payment-methods", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["payment_method_id"]


def _invoice(ws, order_id, doc_id, **body) -> dict:
    r = ws["buyer"].post(f"/purchase-orders/{doc_id}/invoices",
                         json={"order_id": order_id, "invoice_number": "INV-1", **body})
    assert r.status_code == 201, r.text
    return r.json()["invoices"][-1]


def _upload(c, path, name, data):
    return c.post(path, files={"file": (name, data)})


# ── the payment list ────────────────────────────────────────────────────────────────────────────

def test_payment_methods_are_kept_by_purchase_officer_and_admin(ws):
    c = ws["buyer"]
    m = _method(c, "Account")
    assert _code(c.post("/payment-methods", json={"name": " account "})) == "PAYMENT_METHOD_EXISTS"
    _method(c, "Bill's credit card")
    names = [x["name"] for x in c.get("/payment-methods").json()["payment_methods"]]
    assert names == ["Account", "Bill's credit card"]
    assert c.patch(f"/payment-methods/{m}", json={"name": "Account 30"}).json()["name"] == "Account 30"
    assert c.patch(f"/payment-methods/{m}", json={"is_active": None}).status_code == 422
    drafter, _ = login_same_workspace(ws["wid"], "drafter")
    assert drafter.get("/payment-methods").status_code == 200
    assert drafter.post("/payment-methods", json={"name": "Cash"}).status_code == 403
    assert drafter.patch(f"/payment-methods/{m}", json={"is_active": False}).status_code == 403


# ── the invoice's money ─────────────────────────────────────────────────────────────────────────

def test_gst_is_ten_percent_of_ex_while_auto_and_typed_otherwise(ws):
    a = _order(ws)
    doc = _po(ws, a)["po_document_id"]
    inv = _invoice(ws, a, doc, total_ex="1966.30")
    assert (inv["total_ex"], inv["gst"], inv["total_inc"], inv["gst_auto"]) == ("1966.30", "196.63", "2162.93", True)
    c = ws["buyer"]
    r = c.patch(f"/purchase-orders/{doc}/invoices/{inv['invoice_id']}", json={"gst_auto": False, "gst": "150.00"})
    got = r.json()["invoices"][0]
    assert (got["gst"], got["total_inc"], got["gst_auto"]) == ("150.00", "2116.30", False)
    r = c.patch(f"/purchase-orders/{doc}/invoices/{inv['invoice_id']}", json={"total_ex": "100.00"})
    got = r.json()["invoices"][0]
    assert (got["gst"], got["total_inc"]) == ("150.00", "250.00")  # typed GST stays while untick
    r = c.patch(f"/purchase-orders/{doc}/invoices/{inv['invoice_id']}", json={"gst_auto": True})
    got = r.json()["invoices"][0]
    assert (got["gst"], got["total_inc"]) == ("10.00", "110.00")
    assert c.patch(f"/purchase-orders/{doc}/invoices/{inv['invoice_id']}",
                   json={"gst_auto": None}).status_code == 422


def test_invoice_payment_method_must_be_this_workspaces_and_active(ws):
    a = _order(ws)
    doc = _po(ws, a)["po_document_id"]
    m = _method(ws["buyer"], "Credit card")
    inv = _invoice(ws, a, doc, payment_method_id=m)
    assert inv["payment_method_name"] == "Credit card"
    ws["buyer"].patch(f"/payment-methods/{m}", json={"is_active": False})
    again = ws["buyer"].get(f"/purchase-orders/{doc}").json()["invoices"][0]
    assert again["payment_method_name"] == "Credit card"  # stays on the row that has it
    r = ws["buyer"].post(f"/purchase-orders/{doc}/invoices",
                         json={"order_id": a, "invoice_number": "INV-2", "payment_method_id": m})
    assert r.status_code == 404 and _code(r) == "PAYMENT_METHOD_NOT_FOUND"


# ── the three file boxes ────────────────────────────────────────────────────────────────────────

def test_invoice_files(ws):
    a = _order(ws)
    doc = _po(ws, a)["po_document_id"]
    inv = _invoice(ws, a, doc)["invoice_id"]
    c, base = ws["buyer"], f"/purchase-orders/{doc}/invoices/{inv}/files"
    r = _upload(c, f"{base}/invoice", "inv.pdf", PDF)
    assert r.status_code == 201 and r.json()["invoices"][0]["invoice_doc_mime"] == "application/pdf"
    assert r.json()["invoices"][0]["delivery_doc_mime"] is None
    assert _upload(c, f"{base}/delivery", "dd.png", PNG).status_code == 201
    got = c.get(f"{base}/invoice")
    assert got.status_code == 200 and got.content == PDF and got.headers["content-type"] == "application/pdf"
    assert c.get(f"{base}/non_delivery").status_code == 404
    assert _upload(c, f"{base}/other", "x.pdf", PDF).status_code == 422
    assert _upload(c, f"{base}/invoice", "x.skp", b"\xff\xfe\xff\x0e" + b"0" * 20).status_code == 415
    r = c.delete(f"{base}/invoice")
    assert r.status_code == 200 and r.json()["invoices"][0]["invoice_doc_mime"] is None
    assert c.get(f"{base}/invoice").status_code == 404
    d2 = _po(ws, _order(ws))["po_document_id"]
    i2 = _invoice(ws, c.get(f"/purchase-orders/{d2}").json()["lines"][0]["order_id"], d2)["invoice_id"]
    c.delete(f"/purchase-orders/{d2}/invoices/{i2}")
    assert c.post(f"/purchase-orders/{d2}/cancel").status_code == 200
    r = _upload(c, f"/purchase-orders/{d2}/invoices/{i2}/files/invoice", "inv.pdf", PDF)
    assert r.status_code == 409 and _code(r) == "PO_CANCELLED"


# ── the Authorisation Form Details window ───────────────────────────────────────────────────────

def test_authorisation_details_form_and_signed_copy(ws):
    a = _order(ws, total="27662.19")
    doc = _po(ws, a)["po_document_id"]
    c, base = ws["buyer"], f"/purchase-orders/{doc}/authorisation"
    empty = c.get(base).json()
    assert empty["purchase_order_amount"] == "27662.19" and empty["payment_method_id"] is None
    assert empty["form_created_at"] is None and empty["signed_mime"] is None
    me = c.get("/auth/me").json()["id"]
    m = _method(c, "Deposit")
    body = {"payment_method_id": m, "deposit_pct": "30", "date_required": "2026-10-20", "on_behalf_of_id": me}
    saved = c.put(base, json=body).json()
    assert (saved["payment_method_name"], saved["deposit_pct"], saved["amount_required"]) == ("Deposit", "30.00", None)
    assert _code(c.put(base, json={**body, "amount_required": "100"})) == "DEPOSIT_BOTH"
    assert c.put(base, json={**body, "on_behalf_of_id": 10**9}).status_code == 404
    assert c.get(f"{base}/form").status_code == 404
    r = c.post(f"{base}/form")
    assert r.status_code == 201 and r.json()["form_created_at"] is not None
    form = c.get(f"{base}/form")
    assert form.status_code == 200 and form.content[:4] == b"%PDF"
    r = _upload(c, f"{base}/signed", "signed.png", PNG)
    assert r.status_code == 201 and r.json()["signed_mime"] == "image/png"
    assert c.get(f"{base}/signed").content == PNG
    assert _upload(c, f"{base}/signed", "x.skp", b"\xff\xfe\xff\x0e" + b"0" * 20).status_code == 415
    assert c.delete(f"{base}/signed").json()["signed_mime"] is None
    viewer = ws["viewer"]
    assert viewer.put(base, json=body).status_code == 403 and viewer.post(f"{base}/form").status_code == 403
    c.post(f"/purchase-orders/{doc}/cancel")
    assert c.put(base, json=body).status_code == 409


# ── staff photos ────────────────────────────────────────────────────────────────────────────────

def test_staff_photo_is_set_by_an_admin_and_shown_to_the_orderbook(ws):
    admin, _ = login_same_workspace(ws["wid"], "admin")
    uid = ws["buyer"].get("/auth/me").json()["id"]
    assert not any(s["has_photo"] for s in ws["buyer"].get("/purchase-orders/staff").json()["staff"])
    assert ws["buyer"].put(f"/users/{uid}/photo", files={"file": ("me.png", PNG)}).status_code == 403
    assert admin.put(f"/users/{uid}/photo", files={"file": ("me.pdf", PDF)}).status_code == 415  # images only
    assert admin.put(f"/users/{uid}/photo", files={"file": ("me.png", PNG)}).status_code == 204
    staff = {s["id"]: s for s in ws["buyer"].get("/purchase-orders/staff").json()["staff"]}
    assert staff[uid]["has_photo"] is True
    got = ws["buyer"].get(f"/purchase-orders/staff/{uid}/photo")
    assert got.status_code == 200 and got.content == PNG and got.headers["content-type"] == "image/png"
    assert next(u for u in admin.get("/users").json() if u["id"] == uid)["has_photo"] is True
    assert admin.delete(f"/users/{uid}/photo").status_code == 204
    assert ws["buyer"].get(f"/purchase-orders/staff/{uid}/photo").status_code == 404


# ── another workspace ───────────────────────────────────────────────────────────────────────────

def test_other_workspace_is_404(ws):
    a = _order(ws)
    doc = _po(ws, a)["po_document_id"]
    inv = _invoice(ws, a, doc)["invoice_id"]
    c = ws["buyer"]
    uid = c.get("/auth/me").json()["id"]
    m = _method(c)
    _upload(c, f"/purchase-orders/{doc}/authorisation/signed", "s.png", PNG)
    _upload(c, f"/purchase-orders/{doc}/invoices/{inv}/files/invoice", "i.pdf", PDF)
    ws["admin_a"], _ = login_same_workspace(ws["wid"], "admin")
    ws["admin_a"].put(f"/users/{uid}/photo", files={"file": ("me.png", PNG)})
    other, _, other_uid = login("admin", prefix="po-other")
    ghost = 10**9
    base, gbase = f"/purchase-orders/{doc}", f"/purchase-orders/{ghost}"
    calls = [
        ("get", "/authorisation", None), ("put", "/authorisation", {}), ("post", "/authorisation/form", None),
        ("get", "/authorisation/form", None), ("get", "/authorisation/signed", None),
        ("delete", "/authorisation/signed", None),
        ("get", f"/invoices/{inv}/files/invoice", None), ("delete", f"/invoices/{inv}/files/invoice", None),
    ]
    for method, tail, body in calls:
        real = getattr(other, method)(base + tail, **({"json": body} if body is not None else {}))
        gone = getattr(other, method)(gbase + tail.replace(str(inv), str(ghost)),
                                      **({"json": body} if body is not None else {}))
        assert real.status_code == gone.status_code == 404, (method, tail, real.status_code, gone.status_code)
    for tail, name, data in [("/authorisation/signed", "s.png", PNG), (f"/invoices/{inv}/files/invoice", "i.pdf", PDF)]:
        assert _upload(other, base + tail, name, data).status_code == 404
    assert other.get(f"/purchase-orders/staff/{uid}/photo").status_code == 404
    assert other.put(f"/users/{uid}/photo", files={"file": ("me.png", PNG)}).status_code == 404
    assert other.patch(f"/payment-methods/{m}", json={"name": "x"}).status_code == 404
    # a foreign id in a body
    assert c.put(f"{base}/authorisation", json={"on_behalf_of_id": other_uid}).status_code == 404
    other_m = _method(other, "Theirs")
    assert c.put(f"{base}/authorisation", json={"payment_method_id": other_m}).status_code == 404
    r = c.post(f"{base}/invoices", json={"order_id": a, "invoice_number": "Z", "payment_method_id": other_m})
    assert r.status_code == 404
    assert c.get(f"{base}/authorisation").status_code == 200  # nothing changed
