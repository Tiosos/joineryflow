import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const BUYER = "mina.klee@hartwood.test"; // purchase officer
const ADMIN = "aria.voss@hartwood.test";
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");

test("the Invoice Details and Authorisation Form windows", async ({ page }) => {
  const stamp = Date.now();
  await login(page, BUYER);
  const vendors = (await (await page.request.get("/api/suppliers")).json()) as { suppliers: { vendor_id: number }[] };
  const order = await (await page.request.post("/api/orders", {
    data: { vendor_id: vendors.suppliers[0].vendor_id, description: `Invoice window ${stamp}`, category: "Board",
      quantity: 14, unit_cost: "140.4500", total_amount: "1966.30" },
  })).json() as { po_id: number };
  const doc = await (await page.request.post("/api/purchase-orders", { data: { order_ids: [order.po_id] } })).json() as { po_document_id: number };
  let methodId: number | null = null;
  try {
    await page.goto(`/orderbook?po=${doc.po_document_id}`);
    const modal = page.getByTestId("po-modal");
    await expect(modal).toBeVisible();

    // ticking Invoiced opens the window, prefilled from the line
    await modal.getByTestId("po-line-invoiced").first().click();
    const win = page.getByTestId("invoice-window");
    await expect(win.getByTestId("inv-qty")).toHaveValue("14");
    await expect(win.getByTestId("inv-total-ex")).toHaveValue("1966.30");
    await expect(win.getByTestId("inv-gst")).toHaveText("196.63");
    await expect(win.getByTestId("inv-total-inc")).toHaveText("2162.93");
    await expect(win.getByTestId("inv-po-no")).toBeVisible();
    await win.getByTestId("inv-invoice_number").fill(`INV-${stamp}`);
    await win.getByTestId("inv-invoice_number").blur();
    await expect(async () => {
      const d = await (await page.request.get(`/api/purchase-orders/${doc.po_document_id}`)).json();
      expect(d.invoices[0].invoice_number).toBe(`INV-${stamp}`);
      expect(d.invoices[0].total_inc).toBe("2162.93");
    }).toPass();

    // the purchase officer adds a payment method of their own to the shared list, and picks it
    await win.getByTestId("inv-method-edit").click();
    await win.getByTestId("inv-method-new").fill(`Spec card ${stamp}`);
    await win.getByTestId("inv-method-add").click();
    await expect(win.getByTestId("inv-method").locator("option", { hasText: `Spec card ${stamp}` })).toHaveCount(1);
    await win.getByTestId("inv-method").selectOption({ label: `Spec card ${stamp}` });
    await expect(async () => {
      const d = await (await page.request.get(`/api/purchase-orders/${doc.po_document_id}`)).json();
      expect(d.invoices[0].payment_method_name).toBe(`Spec card ${stamp}`);
      methodId = d.invoices[0].payment_method_id;
    }).toPass();

    // GST: untick to type your own, tick for 10% of Ex again
    await win.getByTestId("inv-gst-auto").click();
    await win.getByTestId("inv-gst").fill("150.00");
    await win.getByTestId("inv-gst").blur();
    await expect(win.getByTestId("inv-total-inc")).toHaveText("2116.30");
    await win.getByTestId("inv-gst-auto").click();
    await expect(win.getByTestId("inv-gst")).toHaveText("196.63");
    await expect(win.getByTestId("inv-total-inc")).toHaveText("2162.93");

    // the three file boxes
    await win.getByTestId("inv-file-invoice").setInputFiles({ name: "invoice.pdf", mimeType: "application/pdf", buffer: PDF });
    await expect(win.getByTestId("inv-slot-invoice")).toContainText("PDF");
    await win.getByTestId("inv-file-delivery").setInputFiles({ name: "delivery.png", mimeType: "image/png", buffer: PNG });
    await expect(win.getByTestId("inv-slot-delivery").getByRole("img")).toBeVisible();
    await win.getByRole("button", { name: "Remove Invoice Doc" }).click();
    await expect(win.getByTestId("inv-slot-invoice")).not.toContainText("PDF");

    // Close saves; the table row shows the figures and the delivery doc; ADD makes a second invoice
    await win.getByTestId("inv-close").click();
    await expect(win).toHaveCount(0);
    const row = modal.getByTestId("po-invoice-row");
    await expect(row).toContainText(`INV-${stamp}`);
    await expect(row).toContainText("$2162.93");
    await modal.getByTestId("po-line-invoiced").first().click();
    await page.getByTestId("inv-add").click();
    await page.getByTestId("inv-invoice_number").fill(`INV-B-${stamp}`);
    await page.getByTestId("inv-close").click();
    await expect(modal.getByTestId("po-invoice-row")).toHaveCount(2);

    // the Authorisation Form window: deposit % OR amount, Create Form, Signed Form
    await modal.getByTestId("po-auth").click();
    const auth = page.getByTestId("auth-window");
    await expect(auth.getByTestId("auth-amount")).toHaveText("$1966.30");
    await auth.getByTestId("auth-method").selectOption({ label: `Spec card ${stamp}` });
    await auth.getByTestId("auth-deposit-pct").fill("30");
    await auth.getByTestId("auth-amount-required").fill("500");
    await expect(auth.getByTestId("auth-deposit-pct")).toHaveValue("");
    await auth.getByTestId("auth-date").fill("2026-12-01");
    await auth.getByTestId("auth-on-behalf").selectOption({ index: 1 });
    await auth.getByTestId("auth-create").click();
    const link = auth.getByTestId("auth-form-link");
    await expect(link).toBeVisible();
    const pdf = await page.request.get((await link.getAttribute("href"))!);
    expect(pdf.ok()).toBe(true);
    expect((await pdf.body()).subarray(0, 4).toString()).toBe("%PDF");
    await auth.getByTestId("auth-signed-file").setInputFiles({ name: "signed.png", mimeType: "image/png", buffer: PNG });
    await expect(auth.getByTestId("auth-signed-box").getByRole("img")).toBeVisible();
    await auth.getByTestId("auth-close").click();
    await expect(auth).toHaveCount(0);
    const saved = await (await page.request.get(`/api/purchase-orders/${doc.po_document_id}/authorisation`)).json();
    expect(saved.amount_required).toBe("500.00");
    expect(saved.deposit_pct).toBeNull();
    expect(saved.date_required).toBe("2026-12-01");
    expect(saved.form_created_at).not.toBeNull();
  } finally {
    // put back what this spec added: the PO's invoices and the payment method entry
    const d = await (await page.request.get(`/api/purchase-orders/${doc.po_document_id}`)).json();
    for (const i of d.invoices ?? []) await page.request.delete(`/api/purchase-orders/${doc.po_document_id}/invoices/${i.invoice_id}`);
    await page.request.post(`/api/purchase-orders/${doc.po_document_id}/cancel`);
    await page.request.delete(`/api/orders/${order.po_id}`);
    if (methodId) await page.request.patch(`/api/payment-methods/${methodId}`, { data: { is_active: false } });
  }
});

test("an admin sets a staff photo and the PO staff list shows it", async ({ page }) => {
  const stamp = Date.now();
  await login(page, ADMIN);
  await page.goto("/it");
  const row = page.getByTestId("staff-photo-row").filter({ hasText: "Mina Klee" });
  await row.getByLabel("Photo for Mina Klee").setInputFiles({ name: "mina.png", mimeType: "image/png", buffer: PNG });
  try {
    await expect(row.locator("img")).toBeVisible();
    const vendors = (await (await page.request.get("/api/suppliers")).json()) as { suppliers: { vendor_id: number }[] };
    const order = await (await page.request.post("/api/orders", {
      data: { vendor_id: vendors.suppliers[0].vendor_id, description: `Photo ${stamp}`, category: "Board", total_amount: "10.00" },
    })).json() as { po_id: number };
    const doc = await (await page.request.post("/api/purchase-orders", { data: { order_ids: [order.po_id] } })).json() as { po_document_id: number };
    try {
      await page.goto(`/orderbook?po=${doc.po_document_id}`);
      await expect(page.getByTestId("po-staff-photo")).toHaveCount(1);
      await expect(page.getByTestId("po-staff-row").filter({ hasText: "Mina Klee" }).getByTestId("po-staff-photo")).toBeVisible();
    } finally {
      await page.request.post(`/api/purchase-orders/${doc.po_document_id}/cancel`);
      await page.request.delete(`/api/orders/${order.po_id}`);
    }
  } finally {
    await page.goto("/it");
    const again = page.getByTestId("staff-photo-row").filter({ hasText: "Mina Klee" });
    if (await again.getByRole("button", { name: "Remove" }).count()) await again.getByRole("button", { name: "Remove" }).click();
    await expect(again.locator("img")).toHaveCount(0);
  }
});
