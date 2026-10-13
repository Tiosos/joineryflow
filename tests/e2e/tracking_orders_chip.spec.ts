import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * Tracking's Orders chip keeps the items that have an order in any state (Draft and Pending count),
 * on the item itself or on one of its related parts. Runs in a project of its own.
 */
test("the Orders chip keeps items that have an order, and none of the others", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const pid = (await (await page.request.post("/api/projects", {
    data: { project_code: `OC-${stamp}`, name: `Orders chip ${stamp}` },
  })).json()).id as number;
  const mk = async (description: string) => {
    const r = await page.request.post(`/api/projects/${pid}/items`, { data: { description, code: null, qty: 1 } });
    expect(r.status()).toBe(201);
    return (await r.json()).id as number;
  };
  const ordered = `Ordered ${stamp}`, plain = `Plain ${stamp}`;
  const orderedId = await mk(ordered);
  await mk(plain);

  const vendors = (await (await page.request.get("/api/suppliers")).json()) as { suppliers: { vendor_id: number }[] };
  const order = await page.request.post("/api/orders", {
    data: { vendor_id: vendors.suppliers[0].vendor_id, item_id: orderedId, description: `Chip order ${stamp}`, category: "Board" },
  });
  expect(order.ok()).toBe(true);
  const orderId = ((await order.json()) as { po_id: number }).po_id;
  try {
    await page.goto(`/tracking?project_id=${pid}`);
    const rows = page.locator('[data-testid="tracking-row"]');
    await expect(rows).toHaveCount(2);

    const chip = page.getByRole("button", { name: "Orders", exact: true });
    await expect(chip).toBeEnabled();
    await chip.click();
    await expect(rows).toHaveCount(1);
    await expect(rows.filter({ hasText: ordered })).toHaveCount(1);
    await chip.click();                                    // off again
    await expect(rows).toHaveCount(2);
  } finally {
    await page.request.delete(`/api/orders/${orderId}`);
  }
});
