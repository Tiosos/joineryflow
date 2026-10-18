import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("a Benchtop item shows and edits the benchtop fields, keeps one picture and lists on its type tab", async ({ page }) => {
  const stamp = Date.now();
  await login(page);
  const type = `Bench${stamp}`;
  const desc = `Bench top ${stamp}`;
  const created = (await (await page.request.post("/api/catalog/benchtop-materials", {
    data: { slab_id: `bt-${stamp}`, sku: `bt-${stamp}`, description: desc, product_type: type, colour: "WHITE 200",
            laminate_supplier: "Laminex", thickness_mm: 33, joins: 3 },
  })).json()) as { material_id: number };
  const mid = created.material_id;
  const field = async (k: string) =>
    ((await (await page.request.get(`/api/catalog/benchtop-materials/${mid}`)).json()) as Record<string, unknown>)[k];
  try {
    await page.goto("/catalog?tab=benchtop");
    const row = page.locator("tr").filter({ has: page.locator(`input[value="${desc}"]`) });
    await expect(row.getByLabel("Colour")).toHaveValue("WHITE 200");
    await expect(row.getByLabel("Thickness (mm)")).toHaveValue("33");

    await row.getByLabel("Underside").fill("Aquaban");
    await row.getByLabel("Underside").blur();
    await expect.poll(() => field("underside")).toBe("Aquaban");
    await row.getByLabel("Joins").fill("");                       // empty clears it
    await row.getByLabel("Joins").blur();
    await expect.poll(() => field("joins")).toBeNull();

    await row.getByLabel("Shaped").click();                       // a controlled box: it ticks once the grid reloads
    await expect.poll(() => field("shaped")).toBe(true);
    await expect(row.getByLabel("Shaped")).toBeChecked();

    await row.getByLabel("Product image").setInputFiles({ name: "b.png", mimeType: "image/png", buffer: PNG });
    await expect(row.getByTestId("board-image")).toBeVisible();
    await expect.poll(() => field("has_image")).toBe(true);

    await page.goto(`/catalog?ptype=${type}`);
    await expect(page.getByTestId("type-group-benchtop")).toBeVisible();
    await expect(page.locator(`input[value="${desc}"]`)).toBeVisible();
  } finally {
    await page.request.post(`/api/catalog/benchtop-materials/${mid}/archive`);
  }
});
