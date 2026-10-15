import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const BUYER = "mina.klee@hartwood.test"; // purchase officer

test("the Orders list shows the old order number beside the PO-year number", async ({ page }) => {
  const stamp = Date.now();
  await login(page, BUYER);
  const vendors = (await (await page.request.get("/api/suppliers")).json()) as { suppliers: { vendor_id: number }[] };
  const order = (await (await page.request.post("/api/orders", {
    data: { vendor_id: vendors.suppliers[0].vendor_id, description: `Order no ${stamp}`, category: "Board",
      order_number: String(stamp).slice(-8), total_amount: "10.00" },
  })).json()) as { po_id: number; po_number: string };
  try {
    await page.goto(`/orderbook?order=${order.po_number}`);
    await expect(page.getByRole("columnheader", { name: "Order no." })).toBeVisible();
    const row = page.getByTestId("order-row").filter({ hasText: order.po_number });
    await expect(row.getByTestId("order-no")).toHaveText(String(stamp).slice(-8));
  } finally {
    await page.request.delete(`/api/orders/${order.po_id}`);
  }
});
