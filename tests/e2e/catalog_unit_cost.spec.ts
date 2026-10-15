import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test("the Catalog grid shows a material's unit cost and edits it", async ({ page }) => {
  const stamp = Date.now();
  await login(page);
  const desc = `Unit cost hinge ${stamp}`;
  const created = (await (await page.request.post("/api/catalog/hardware-materials", {
    data: { sku: `uc-${stamp}`, description: desc, unit_cost: 12.5 },
  })).json()) as { material_id: number };
  const cost = async () =>
    ((await (await page.request.get("/api/catalog/hardware-materials")).json()) as
      { rows: { material_id: number; unit_cost: number | null }[] })
      .rows.find(r => r.material_id === created.material_id)!.unit_cost;
  try {
    await page.goto("/catalog?tab=hardware");
    const row = page.locator("tr").filter({ has: page.locator(`input[value="${desc}"]`) });
    const input = row.getByLabel("Unit cost");
    await expect(input).toHaveValue("12.5");

    await input.fill("13.75");
    await input.blur();
    await expect.poll(cost).toBe(13.75);

    await input.fill("");                                   // an empty cell clears the price
    await input.blur();
    await expect.poll(cost).toBeNull();
  } finally {
    await page.request.post(`/api/catalog/hardware-materials/${created.material_id}/archive`);
  }
});
