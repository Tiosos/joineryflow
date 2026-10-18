import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("Solid Timber has its own tab and table: fields, picture, and the Solid Timber type tab", async ({ page }) => {
  const stamp = Date.now();
  await login(page);
  const type = `Timber${stamp}`;
  const desc = `Oak board ${stamp}`;
  const created = (await (await page.request.post("/api/catalog/timber-materials", {
    data: { sku: `tb-${stamp}`, description: desc, product_type: type, colour: "Natural", grain: "Straight",
            thickness_mm: 32, width_mm: 140, length_mm: 2400 },
  })).json()) as { material_id: number };
  const mid = created.material_id;
  const field = async (k: string) =>
    ((await (await page.request.get(`/api/catalog/timber-materials/${mid}`)).json()) as Record<string, unknown>)[k];
  try {
    await page.goto("/catalog?tab=timber");
    const row = page.locator("tr").filter({ has: page.locator(`input[value="${desc}"]`) });
    await expect(row.getByLabel("Colour")).toHaveValue("Natural");
    await expect(row.getByLabel("Length (mm)")).toHaveValue("2400");

    await row.getByLabel("Rating").fill("A");
    await row.getByLabel("Rating").blur();
    await expect.poll(() => field("rating")).toBe("A");
    await row.getByLabel("Width (mm)").fill("");                 // empty clears it
    await row.getByLabel("Width (mm)").blur();
    await expect.poll(() => field("width_mm")).toBeNull();

    await row.getByLabel("Product image").setInputFiles({ name: "t.png", mimeType: "image/png", buffer: PNG });
    await expect(row.getByTestId("board-image")).toBeVisible();
    await expect.poll(() => field("has_image")).toBe(true);

    await page.goto(`/catalog?ptype=${type}`);                   // the type tab lists it from the Solid Timber table
    await expect(page.getByTestId("type-group-timber")).toBeVisible();
    await expect(page.locator(`input[value="${desc}"]`)).toBeVisible();
  } finally {
    await page.request.post(`/api/catalog/timber-materials/${mid}/archive`);
  }
});
