import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test("the Catalog grid shows a material's product type, edits it and filters by it", async ({ page }) => {
  const stamp = Date.now();
  await login(page);
  const type = `Type${stamp}`;
  const mk = async (suffix: string, product_type: string | null) =>
    ((await (await page.request.post("/api/catalog/hardware-materials", {
      data: { sku: `ty-${stamp}-${suffix}`, description: `Typed ${suffix} ${stamp}`, product_type },
    })).json()) as { material_id: number }).material_id;
  const a = await mk("a", type);
  const b = await mk("b", null);
  const typeOf = async (id: number) =>
    ((await (await page.request.get("/api/catalog/hardware-materials")).json()) as
      { rows: { material_id: number; product_type: string | null }[] })
      .rows.find(r => r.material_id === id)!.product_type;
  try {
    await page.goto("/catalog?tab=hardware");
    const rowA = page.locator("tr").filter({ has: page.locator(`input[value="Typed a ${stamp}"]`) });
    await expect(rowA.getByLabel("Type")).toHaveValue(type);

    await page.getByLabel("Type filter").selectOption(type);       // only the typed row is left
    await expect(page.locator(`input[value="Typed a ${stamp}"]`)).toBeVisible();
    await expect(page.locator(`input[value="Typed b ${stamp}"]`)).toHaveCount(0);
    await page.getByLabel("Type filter").selectOption("");

    const rowB = page.locator("tr").filter({ has: page.locator(`input[value="Typed b ${stamp}"]`) });
    await rowB.getByLabel("Type").fill(`${type}B`);
    await rowB.getByLabel("Type").blur();
    await expect.poll(() => typeOf(b)).toBe(`${type}B`);
    await rowB.getByLabel("Type").fill("");                        // empty clears it
    await rowB.getByLabel("Type").blur();
    await expect.poll(() => typeOf(b)).toBeNull();
  } finally {
    for (const id of [a, b]) await page.request.post(`/api/catalog/hardware-materials/${id}/archive`);
  }
});
