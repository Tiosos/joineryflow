import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("Glass has its own tab and table: fields, shaped tick, picture, and the Glass type tab", async ({ page }) => {
  const stamp = Date.now();
  await login(page);
  const type = `Glass${stamp}`;
  const desc = `Pane ${stamp}`;
  const created = (await (await page.request.post("/api/catalog/glass-materials", {
    data: { sku: `gl-${stamp}`, description: desc, product_type: type, colour: "Silver", glass_type: "Float",
            length_mm: 1264, width_mm: 474, thickness_mm: 4 },
  })).json()) as { material_id: number };
  const mid = created.material_id;
  const field = async (k: string) =>
    ((await (await page.request.get(`/api/catalog/glass-materials/${mid}`)).json()) as Record<string, unknown>)[k];
  try {
    await page.goto("/catalog?tab=glass");
    const row = page.locator("tr").filter({ has: page.locator(`input[value="${desc}"]`) });
    await expect(row.getByLabel("Colour")).toHaveValue("Silver");
    await expect(row.getByLabel("Length (mm)")).toHaveValue("1264");

    await row.getByLabel("Power point").fill("2");
    await row.getByLabel("Power point").blur();
    await expect.poll(() => field("power_point")).toBe("2");
    await row.getByLabel("Width (mm)").fill("");                 // empty clears it
    await row.getByLabel("Width (mm)").blur();
    await expect.poll(() => field("width_mm")).toBeNull();

    await row.getByLabel("Shaped").click();                      // a controlled box: it ticks once the grid reloads
    await expect.poll(() => field("shaped")).toBe(true);
    await expect(row.getByLabel("Shaped")).toBeChecked();

    await row.getByLabel("Product image").setInputFiles({ name: "g.png", mimeType: "image/png", buffer: PNG });
    await expect(row.getByTestId("board-image")).toBeVisible();
    await expect.poll(() => field("has_image")).toBe(true);

    await page.goto(`/catalog?ptype=${type}`);                   // the type tab lists it from the Glass table
    await expect(page.getByTestId("type-group-glass")).toBeVisible();
    await expect(page.locator(`input[value="${desc}"]`)).toBeVisible();
  } finally {
    await page.request.post(`/api/catalog/glass-materials/${mid}/archive`);
  }
});
