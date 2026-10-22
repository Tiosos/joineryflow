import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * A catalog row's History shows what was paid for its SKU, from the Orderbook (placed orders only).
 *
 * Builds a board of its own and archives it afterwards, so it passes on a second run against the
 * same database. The orders it makes stay, as no order is deleted.
 */
test("a catalog row shows the placed orders for its SKU", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const sku = `E2E-PH-${stamp}`;
  const api = async (method: "get" | "post" | "patch", path: string, data?: object) => {
    const r = await page.request[method](`/api${path}`, data ? { data } : undefined);
    expect(r.status(), `${method} ${path}`).toBeLessThan(300);
    return r.json();
  };
  const listed = await api("get", "/suppliers");
  const plyco = (listed.suppliers ?? listed).find((v: { name: string }) => v.name === "Plyco");
  expect(plyco, "seeded supplier Plyco").toBeTruthy();
  const board = await api("post", "/catalog/board-materials", { code: sku, sku, description: `E2E history board ${stamp}` });
  try {
    const order = (unit: number, qty: number) => api("post", "/orders", {
      vendor_id: plyco.vendor_id, description: "Board", category: "Board", product_code: sku,
      quantity: qty, unit_cost: unit, total_amount: unit * qty,
    });
    const placed = await order(40, 5);
    await api("patch", `/orders/${placed.po_id}`, { date_ordered: "2026-03-01" });
    await order(99, 1);                                       // raised, never placed: not in the history

    await page.goto(`/catalog?tab=board&q=${encodeURIComponent(sku)}`);
    await expect(page.getByRole("columnheader", { name: "Supplier link" })).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("catalog-row-history").click();
    await expect(page.getByTestId("purchase-history-row")).toHaveCount(1);
    await expect(page.getByTestId("purchase-history")).toContainText("Latest paid 40.00");
    await expect(page.getByTestId("purchase-history-row")).toContainText(placed.po_number);
    await expect(page.getByTestId("purchase-history-row")).toContainText("Plyco");
  } finally {
    await page.request.post(`/api/catalog/board-materials/${board.material_id}/archive`);
  }
});
