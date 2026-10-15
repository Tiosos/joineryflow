import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const BUYER = "mina.klee@hartwood.test"; // purchase officer
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");

test("the order pop-up's Delivery, Stock, Tracking, Supplier, Cutlists and ADMIN tabs and the product image", async ({ page }) => {
  const stamp = Date.now();
  await login(page, BUYER);
  const vendors = (await (await page.request.get("/api/suppliers")).json()) as { suppliers: { vendor_id: number; name: string }[] };
  const vendor = vendors.suppliers[0];
  const order = (await (await page.request.post("/api/orders", {
    data: { vendor_id: vendor.vendor_id, description: `Tabs ${stamp}`, category: "Board", quantity: 6, unit_cost: "10.00",
      total_amount: "60.00", product_code: `TG_${stamp}`, stock_tracked: true },
  })).json()) as { po_id: number; po_number: string };
  await page.goto(`/orderbook?order=${order.po_number}`);
  const detail = page.getByTestId("order-detail");
  await expect(detail).toBeVisible();

  // Product image (HOME tab): a picture per order
  await detail.getByTestId("order-image-file").setInputFiles({ name: "p.png", mimeType: "image/png", buffer: PNG });
  await expect(detail.getByTestId("order-image")).toBeVisible();
  await detail.getByTestId("order-image-remove").click();
  await expect(detail.getByTestId("order-image")).toHaveCount(0);

  // Delivery log: partial deliveries sum up and the remainder is worked out
  await detail.getByTestId("order-tab-Delivery").click();
  await detail.getByTestId("delivery-new-qty").fill("4");
  await detail.getByTestId("delivery-add").click();
  await expect(detail.getByTestId("delivery-row")).toHaveCount(1);
  await expect(detail.getByTestId("delivery-sum")).toHaveText("4");
  await expect(detail.getByTestId("delivery-remaining")).toHaveText("2");
  await detail.getByTestId("delivery-new-qty").fill("2");
  await detail.getByTestId("delivery-add").click();
  await expect(detail.getByTestId("delivery-remaining")).toHaveText("0");
  await detail.getByTestId("delivery-docket-file").first().setInputFiles({ name: "docket.pdf", mimeType: "application/pdf", buffer: PDF });
  const href = await detail.getByTestId("delivery-docket-link").getAttribute("href");
  expect((await (await page.request.get(href!)).body()).subarray(0, 4).toString()).toBe("%PDF");
  await detail.getByTestId("delivery-received-by").fill("JOEF");
  await detail.getByTestId("delivery-received-by").blur();
  await expect(async () => {
    const o = await (await page.request.get(`/api/orders/${order.po_id}`)).json();
    expect(o.received_by).toBe("JOEF");
  }).toPass();
  await detail.getByTestId("delivery-remove").first().click();
  await expect(detail.getByTestId("delivery-row")).toHaveCount(1);

  // Stock, Tracking, Supplier, Cutlists
  await detail.getByTestId("order-tab-Stock").click();
  await expect(detail.getByTestId("stock-row")).toContainText(`Tabs ${stamp}`);
  await detail.getByTestId("order-tab-Tracking").click();
  await expect(detail.getByTestId("tracking-none")).toBeVisible();
  await detail.getByTestId("order-tab-Supplier").click();
  await expect(detail.getByTestId("supplier-name")).toHaveText(vendor.name);
  await detail.getByTestId("order-tab-Cutlists").click();
  await expect(detail.getByTestId("cutlists-no-product")).toBeVisible();

  // ADMIN: cancelling asks why; the date, the person and the reason show on the tab
  await detail.getByTestId("order-tab-ADMIN").click();
  await expect(detail.getByTestId("admin-cancelled-at")).toHaveText("");
  await detail.getByTestId("order-status-select").selectOption("Cancelled");
  await expect(detail.getByTestId("order-cancel-confirm")).toBeDisabled();
  await detail.getByTestId("order-cancel-reason").fill(`Spec ${stamp}`);
  await detail.getByTestId("order-cancel-confirm").click();
  await expect(detail.getByTestId("admin-cancel-reason")).toHaveText(`Spec ${stamp}`);
  await expect(detail.getByTestId("admin-cancelled-by")).toHaveText("Mina Klee");
  await expect(detail.getByTestId("admin-cancelled-at")).not.toHaveText("");

  // a closed order's log and picture are read-only
  await detail.getByTestId("order-tab-Delivery").click();
  await expect(detail.getByTestId("delivery-add-row")).toHaveCount(0);
});
