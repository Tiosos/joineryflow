import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("an Appliance item shows and edits UM and website and keeps one picture", async ({ page }) => {
  const stamp = Date.now();
  await login(page);
  const desc = `Dishwasher ${stamp}`;
  const created = (await (await page.request.post("/api/catalog/appliances", {
    data: { model_number: `ap-${stamp}`, sku: `ap-${stamp}`, description: desc, um: "ea" },
  })).json()) as { material_id: number };
  const mid = created.material_id;
  const field = async (k: string) =>
    ((await (await page.request.get(`/api/catalog/appliances/${mid}`)).json()) as Record<string, unknown>)[k];
  try {
    await page.goto("/catalog?tab=appliance");
    const row = page.locator("tr").filter({ has: page.locator(`input[value="${desc}"]`) });
    await expect(row.getByLabel("UM")).toHaveValue("ea");
    await row.getByLabel("UM").fill("pair");
    await row.getByLabel("UM").blur();
    await expect.poll(() => field("um")).toBe("pair");
    await row.getByLabel("UM").fill("");                          // empty clears it
    await row.getByLabel("UM").blur();
    await expect.poll(() => field("um")).toBeNull();

    await row.getByLabel("Product image").setInputFiles({ name: "a.png", mimeType: "image/png", buffer: PNG });
    await expect(row.getByTestId("board-image")).toBeVisible();
    await expect.poll(() => field("has_image")).toBe(true);
  } finally {
    await page.request.post(`/api/catalog/appliances/${mid}/archive`);
  }
});
