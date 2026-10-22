import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * "No catalog match" lists material orders whose product code is blank or not a catalog SKU, and an
 * order leaves it once its code is a real SKU. Builds its own order and board (the board is
 * archived afterwards, the order stays as no order is deleted), so it passes on a second run.
 */
test("an order with a mistyped product code is listed until its code is a catalog SKU", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const sku = `E2E-UM-${stamp}`;
  const api = async (method: "get" | "post" | "patch", path: string, data?: object) => {
    const r = await page.request[method](`/api${path}`, data ? { data } : undefined);
    expect(r.status(), `${method} ${path}`).toBeLessThan(300);
    return r.json();
  };
  const listed = await api("get", "/suppliers");
  const plyco = (listed.suppliers ?? listed).find((v: { name: string }) => v.name === "Plyco");
  const board = await api("post", "/catalog/board-materials", { code: sku, sku, description: `E2E unmatched board ${stamp}` });
  try {
    const order = await api("post", "/orders", {
      vendor_id: plyco.vendor_id, description: `E2E unmatched ${stamp}`, category: "Board",
      product_code: `${sku}-TYPO`, quantity: 1, unit_cost: 10, total_amount: 10,
    });

    await page.goto("/orderbook?view=unmatched");
    await expect(page.getByTestId("orders-view-unmatched")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText(order.po_number)).toBeVisible();

    await api("patch", `/orders/${order.po_id}`, { product_code: sku });   // the typo is fixed
    await page.reload();
    await expect(page.getByTestId("orders-view-unmatched")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText(order.po_number)).toHaveCount(0);
  } finally {
    await page.request.post(`/api/catalog/board-materials/${board.material_id}/archive`);
  }
});
