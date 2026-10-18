import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("Edging has its own tab and table: fields, glued tick, picture, and the Edging type tab", async ({ page }) => {
  const stamp = Date.now();
  await login(page);
  const type = `Edging${stamp}`;
  const desc = `Edge ${stamp}`;
  const created = (await (await page.request.post("/api/catalog/edging-materials", {
    data: { sku: `ed-${stamp}`, description: desc, product_type: type, colour: "Beech", roll_length_m: 100,
            edge_width_mm: 21, edge_thickness_mm: 1 },
  })).json()) as { material_id: number };
  const mid = created.material_id;
  const field = async (k: string) =>
    ((await (await page.request.get(`/api/catalog/edging-materials/${mid}`)).json()) as Record<string, unknown>)[k];
  try {
    await page.goto("/catalog?tab=edging");
    const row = page.locator("tr").filter({ has: page.locator(`input[value="${desc}"]`) });
    await expect(row.getByLabel("Colour")).toHaveValue("Beech");
    await expect(row.getByLabel("Roll length (m)")).toHaveValue("100");

    await row.getByLabel("Width (mm)").fill("22.5");
    await row.getByLabel("Width (mm)").blur();
    await expect.poll(() => field("edge_width_mm")).toBe(22.5);
    await row.getByLabel("Width (mm)").fill("");                 // empty clears it
    await row.getByLabel("Width (mm)").blur();
    await expect.poll(() => field("edge_width_mm")).toBeNull();

    await row.getByLabel("Glued").click();                // a controlled box: it ticks once the grid reloads
    await expect.poll(() => field("glued")).toBe(true);
    await expect(row.getByLabel("Glued")).toBeChecked();

    await row.getByLabel("Product image").setInputFiles({ name: "e.png", mimeType: "image/png", buffer: PNG });
    await expect(row.getByTestId("board-image")).toBeVisible();
    await expect.poll(() => field("has_image")).toBe(true);

    await page.goto(`/catalog?ptype=${type}`);                   // the type tab lists it from the Edging table
    await expect(page.getByTestId("type-group-edging")).toBeVisible();
    await expect(page.locator(`input[value="${desc}"]`)).toBeVisible();
  } finally {
    await page.request.post(`/api/catalog/edging-materials/${mid}/archive`);
  }
});
