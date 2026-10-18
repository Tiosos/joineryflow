import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test("the Catalog has a tab per product type, listing that type's items from every table", async ({ page }) => {
  const stamp = Date.now();
  await login(page);
  const type = `Tab${stamp}`;
  const hw = ((await (await page.request.post("/api/catalog/hardware-materials", {
    data: { sku: `tt-${stamp}-h`, description: `Tab hw ${stamp}`, product_type: type },
  })).json()) as { material_id: number }).material_id;
  const bd = ((await (await page.request.post("/api/catalog/board-materials", {
    data: { sku: `tt-${stamp}-b`, code: `TT-${stamp}`, description: `Tab board ${stamp}`, product_type: type },
  })).json()) as { material_id: number }).material_id;
  try {
    await page.goto("/catalog");
    await page.getByRole("button", { name: new RegExp(`^${type} \\(2\\)`) }).click();
    await expect(page.locator(`input[value="Tab hw ${stamp}"]`)).toBeVisible();
    await expect(page.locator(`input[value="Tab board ${stamp}"]`)).toBeVisible();
    await expect(page.getByTestId("type-group-hardware")).toBeVisible();
    await expect(page.getByTestId("type-group-board")).toBeVisible();
  } finally {
    await page.request.post(`/api/catalog/hardware-materials/${hw}/archive`);
    await page.request.post(`/api/catalog/board-materials/${bd}/archive`);
  }
});
