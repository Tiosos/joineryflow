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
    await expect(modal.getByTestId("po-email")).toHaveAttribute("href", new RegExp(`mailto:sam${stamp}%40supplier.test`));
    // ticked staff become real Cc addresses (from the Orderbook-gated staff list)
    await expect(modal.getByTestId("po-email")).not.toHaveAttribute("href", /cc=/);
    await modal.getByTestId("po-staff").getByRole("checkbox").first().check();
    await expect(modal.getByTestId("po-email")).toHaveAttribute("href", /[?&]cc=[^&]*%40/);

    // invoice details: ticking Invoiced on a line opens the Invoice Details window
    await modal.getByTestId("po-line-invoiced").first().click();
    const win = page.getByTestId("invoice-window");
    await win.getByTestId("inv-invoice_number").fill(`INV-${stamp}`);
    await win.getByTestId("inv-invoice_number").blur();
    await win.getByTestId("inv-close").click();
    await expect(win).toHaveCount(0);
    await expect(modal.getByTestId("po-invoice-row")).toContainText(`INV-${stamp}`);

    // documents
    for (const [path, type] of [["pdf", /pdf/], ["excel", /spreadsheetml/]] as const) {
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
    await page.getByTestId("po-cancel").click();
    await page.getByTestId("confirm-dialog-confirm").click();
    await expect(page.getByTestId("po-error")).toContainText("Remove the invoices first");   // a PO with invoices stays
    await page.getByTestId("po-invoice-open").click();
    await page.getByTestId("inv-delete").click();
    await page.getByTestId("confirm-dialog-confirm").click();
    await expect(page.getByTestId("po-invoice-row")).toHaveCount(0);
    await page.getByTestId("po-cancel").click();
    await page.getByTestId("confirm-dialog-confirm").click();
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

test("the Supplier list edits a supplier's contacts: add, change, delete", async ({ page }) => {
  const stamp = Date.now();
  await login(page, BUYER);
  const made = await page.request.post("/api/suppliers", { data: { name: `Contacts Co ${stamp}`, category: "Other" } });
  expect(made.ok()).toBe(true);
  await page.goto("/orderbook");
  await page.getByTestId("orders-suppliers").click();
  const modal = page.getByTestId("supplier-modal");
  await modal.getByPlaceholder("Search name or contact").fill(`Contacts Co ${stamp}`);
  const row = modal.getByTestId("supplier-row");
  await expect(row).toHaveCount(1);
  await row.getByTestId("supplier-edit").click();
  const box = modal.getByTestId("supplier-contacts");
  await expect(box).toContainText("No contacts yet");

  await box.getByTestId("supplier-contact-add").click();
  await box.getByTestId("supplier-contact-name").fill(`Sam ${stamp}`);
  await box.getByTestId("supplier-contact-email").fill("not-an-email");
  await box.getByTestId("supplier-contact-save").click();
  await expect(box.getByRole("alert")).toContainText("email");
  await box.getByTestId("supplier-contact-email").fill(`sam${stamp}@supplier.test`);
  await box.getByTestId("supplier-contact-save").click();
  const contact = box.getByTestId("supplier-contact").filter({ hasText: `Sam ${stamp}` });
  await expect(contact).toContainText(`sam${stamp}@supplier.test`);

  await contact.getByTestId("supplier-contact-edit").click();
  await box.getByTestId("supplier-contact-mobile").fill("0400 000 000");
  await box.getByTestId("supplier-contact-save").click();
  await expect(contact).toContainText("0400 000 000");

  await contact.getByTestId("supplier-contact-delete").click();
  await expect(contact).toHaveCount(0);
  await expect(box).toContainText("No contacts yet");
});

test("a bad ?po= link can be closed, and Po only sends the orders the view shows", async ({ page }) => {
  const stamp = Date.now();
  await login(page, BUYER);

  await page.goto("/orderbook?po=999999999");
  await expect(page.getByTestId("po-load-state")).toContainText("Could not load");
  await page.getByTestId("po-done").click();
  await expect(page.getByTestId("po-load-state")).toHaveCount(0);
  await expect(page).not.toHaveURL(/po=/);

  const vendors = (await (await page.request.get("/api/suppliers")).json()) as { suppliers: { vendor_id: number; name: string }[] };
  const v = vendors.suppliers[0];
  const order = (await (await page.request.post("/api/orders", {
    data: { vendor_id: v.vendor_id, description: `Hidden tick ${stamp}`, category: "Board", total_amount: "5.00" },
  })).json()) as { po_id: number };
  try {
    await page.goto(`/orderbook?supplier=${encodeURIComponent(v.name)}`);
    const row = page.getByTestId("order-row").filter({ hasText: `Hidden tick ${stamp}` });
    await row.getByTestId("order-check").check();
    await expect(page.getByTestId("orders-po")).toContainText("Po (1)");
    await page.getByTestId("orders-view-rto").click();         // Approved and not ordered: hides the Pending order
    await expect(row).toHaveCount(0);
    await expect(page.getByTestId("orders-po")).toBeDisabled();
    await expect(page.getByTestId("orders-po")).not.toContainText("(1)");
  } finally {
    await page.request.delete(`/api/orders/${order.po_id}`);
  }
});

test("the PO panel saves what was typed when it closes, restores an emptied date, and keeps focus", async ({ page }) => {
  const stamp = Date.now();
  await login(page, BUYER);
  const vendors = (await (await page.request.get("/api/suppliers")).json()) as { suppliers: { vendor_id: number; name: string }[] };
  const v = vendors.suppliers[0];
  const order = (await (await page.request.post("/api/orders", {
    data: { vendor_id: v.vendor_id, description: `Panel edit ${stamp}`, category: "Board", total_amount: "5.00" },
  })).json()) as { po_id: number };
  let docId: number | null = null;
  try {
    await page.goto(`/orderbook?supplier=${encodeURIComponent(v.name)}`);
    const row = page.getByTestId("order-row").filter({ hasText: `Panel edit ${stamp}` });
    await row.getByTestId("order-check").check();
    await page.getByTestId("orders-po").click();
    const modal = page.getByTestId("po-modal");
    await expect(modal).toBeVisible();
    docId = Number(new URL(page.url()).searchParams.get("po"));

    // an accessible modal: focus is inside it, Tab never leaves it
    await expect(modal).toHaveAttribute("aria-modal", "true");
    await expect(async () => {
      expect(await page.evaluate(() => !!document.activeElement?.closest('[data-testid="po-modal"]'))).toBe(true);
    }).toPass();
    for (let i = 0; i < 70; i++) await page.keyboard.press("Tab");
    expect(await page.evaluate(() => !!document.activeElement?.closest('[data-testid="po-modal"]'))).toBe(true);
    for (let i = 0; i < 70; i++) await page.keyboard.press("Shift+Tab");
    expect(await page.evaluate(() => !!document.activeElement?.closest('[data-testid="po-modal"]'))).toBe(true);

    // an emptied Date ordered goes back to the saved date, with the reason
    const saved = await modal.getByTestId("po-date_ordered").inputValue();
    expect(saved).not.toBe("");
    await modal.getByTestId("po-date_ordered").fill("");
    await modal.getByTestId("po-memo").focus();                       // blur the date box
    await expect(modal.getByTestId("po-date_ordered")).toHaveValue(saved);
    await expect(modal.getByTestId("po-error")).toContainText("cannot be empty");

    // typed text is saved by Esc, without clicking out of the box first
    await modal.getByTestId("po-memo").fill(`typed ${stamp}`);
    await page.keyboard.press("Escape");
    await expect(modal).toHaveCount(0);
    const d = await (await page.request.get(`/api/purchase-orders/${docId}`)).json();
    expect(d.memo).toBe(`typed ${stamp}`);

    // focus goes back to what opened the panel: the row's PO link (the Po button is off by now)
    const link = row.getByTestId("order-po-link");
    await link.focus();
    await page.keyboard.press("Enter");
    await expect(modal).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(modal).toHaveCount(0);
    await expect(link).toBeFocused();
  } finally {
    if (docId) await page.request.post(`/api/purchase-orders/${docId}/cancel`);
    await page.request.delete(`/api/orders/${order.po_id}`);
  }
});
