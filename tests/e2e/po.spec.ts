import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const BUYER = "mina.klee@hartwood.test"; // purchase officer

test("orders are put on a PO, edited there, invoiced and the PO cancelled", async ({ page }) => {
  const stamp = Date.now();
  await login(page, BUYER);
  const vendors = (await (await page.request.get("/api/suppliers")).json()) as {
    suppliers: { vendor_id: number; name: string }[];
  };
  const vendor = vendors.suppliers[0];
  const made: { po_id: number; po_number: string }[] = [];
  for (const [i, cost] of ["100.00", "50.00"].entries()) {
    const r = await page.request.post("/api/orders", {
      data: {
        vendor_id: vendor.vendor_id, description: `PO spec ${stamp} ${i}`, category: "Board",
        quantity: 1, unit_cost: cost, total_amount: cost,
      },
    });
    expect(r.ok()).toBe(true);
    made.push(await r.json());
  }
  let docId: number | null = null;
  try {
    await page.goto(`/orderbook?supplier=${encodeURIComponent(vendor.name)}`);
    const rows = page.getByTestId("order-row").filter({ hasText: `PO spec ${stamp}` });
    await expect(rows).toHaveCount(2);
    await expect(page.getByTestId("orders-po")).toBeDisabled();
    await rows.nth(0).getByTestId("order-check").check();
    await rows.nth(1).getByTestId("order-check").check();
    await page.getByTestId("orders-po").click();

    const modal = page.getByTestId("po-modal");
    await expect(modal).toBeVisible();
    docId = Number(new URL(page.url()).searchParams.get("po"));
    expect(docId).toBeGreaterThan(0);
    await expect(modal.getByTestId("po-line")).toHaveCount(2);
    await expect(modal.getByTestId("po-total-ex")).toHaveText("$150.00");
    await expect(modal.getByTestId("po-total-inc")).toHaveText("$165.00");

    // header: reference no. is typed by hand
    await modal.getByTestId("po-reference_no").fill(`REF-${stamp}`);
    await modal.getByTestId("po-reference_no").blur();
    await expect(async () => {
      const d = await (await page.request.get(`/api/purchase-orders/${docId}`)).json();
      expect(d.reference_no).toBe(`REF-${stamp}`);
    }).toPass();

    // delivery charge is a real order
    await modal.getByTestId("po-delivery").fill("45.00");
    await modal.getByTestId("po-add-delivery").click();
    await expect(modal.getByTestId("po-line")).toHaveCount(3);
    await expect(modal.getByTestId("po-total-ex")).toHaveText("$195.00");

    // supplier contact, then the mail link carries its address
    await modal.getByTestId("po-contact-add").click();
    await modal.getByTestId("po-contact-name").fill(`Sam ${stamp}`);
    await modal.getByTestId("po-contact-email").fill(`sam${stamp}@supplier.test`);
    await modal.getByTestId("po-contact-save").click();
    const contact = modal.getByTestId("po-contact").filter({ hasText: `Sam ${stamp}` });
    await contact.getByRole("checkbox").check();
    await expect(modal.getByTestId("po-email")).toHaveAttribute("href", new RegExp(`mailto:sam${stamp}@supplier.test`));

    // invoice details
    await modal.getByTestId("po-invoice-add").click();
    await modal.getByTestId("po-invoice-line").selectOption({ index: 1 });
    await modal.getByTestId("po-invoice-number").fill(`INV-${stamp}`);
    await modal.getByTestId("po-invoice-save").click();
    await expect(modal.getByTestId("po-invoice-row")).toContainText(`INV-${stamp}`);

    // documents
    for (const [path, type] of [["pdf", /pdf/], ["authorisation-form", /pdf/], ["excel", /spreadsheetml/]] as const) {
      const r = await page.request.get(`/api/purchase-orders/${docId}/${path}`);
      expect(r.ok()).toBe(true);
      expect(r.headers()["content-type"]).toMatch(type);
    }

    // the order list shows the PO number, and an order on a PO has Open PO in its pop-up
    await modal.getByTestId("po-done").click();
    await expect(modal).toHaveCount(0);
    await expect(rows.nth(0).getByTestId("order-po-link")).toBeVisible();

    // cancelling the PO frees its orders
    await rows.nth(0).getByTestId("order-po-link").click();
    page.once("dialog", d => void d.accept());
    await page.getByTestId("po-cancel").click();
    await expect(page.getByTestId("po-modal").getByText("Cancelled", { exact: true })).toBeVisible();
    await page.getByTestId("po-done").click();
    await expect(rows.nth(0).getByTestId("order-po-link")).toHaveCount(0);
  } finally {
    if (docId) await page.request.post(`/api/purchase-orders/${docId}/cancel`);
    for (const o of made) await page.request.delete(`/api/orders/${o.po_id}`);
  }
});

test("Create PO! in the order pop-up puts that order on a PO, then opens it", async ({ page }) => {
  const stamp = Date.now();
  await login(page, BUYER);
  const vendors = (await (await page.request.get("/api/suppliers")).json()) as { suppliers: { vendor_id: number }[] };
  const r = await page.request.post("/api/orders", {
    data: { vendor_id: vendors.suppliers[0].vendor_id, description: `PO pop-up ${stamp}`, category: "Board", total_amount: "20.00" },
  });
  const order = (await r.json()) as { po_id: number; po_number: string };
  let docId: number | null = null;
  try {
    await page.goto(`/orderbook?order=${order.po_number}`);
    await page.getByTestId("order-create-po").click();
    await expect(page.getByTestId("po-modal")).toBeVisible();
    docId = Number(new URL(page.url()).searchParams.get("po"));
    await expect(page.getByTestId("po-line")).toHaveCount(1);
    await page.getByTestId("po-done").click();
    await page.goto(`/orderbook?order=${order.po_number}`);
    await expect(page.getByTestId("order-create-po")).toContainText("Open PO");
  } finally {
    if (docId) await page.request.post(`/api/purchase-orders/${docId}/cancel`);
    await page.request.delete(`/api/orders/${order.po_id}`);
  }
});
