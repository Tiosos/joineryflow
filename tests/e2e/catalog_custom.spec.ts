import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("a Custom item shows and edits UM and website and keeps one picture", async ({ page }) => {
  const stamp = Date.now();
  await login(page);
  const desc = `Frame ${stamp}`;
  const created = (await (await page.request.post("/api/catalog/custom-made", {
    data: { internal_ref: `cm-${stamp}`, sku: `cm-${stamp}`, description: desc, um: "Tot" },
  })).json()) as { material_id: number };
  const mid = created.material_id;
  const field = async (k: string) =>
    ((await (await page.request.get(`/api/catalog/custom-made/${mid}`)).json()) as Record<string, unknown>)[k];
  try {
    await page.goto("/catalog?tab=custom_made");
    const row = page.locator("tr").filter({ has: page.locator(`input[value="${desc}"]`) });
    await expect(row.getByLabel("UM")).toHaveValue("Tot");
    await row.getByLabel("UM").fill("ea");
    await row.getByLabel("UM").blur();
    await expect.poll(() => field("um")).toBe("ea");
    await row.getByLabel("UM").fill("");                          // empty clears it
    await row.getByLabel("UM").blur();
    await expect.poll(() => field("um")).toBeNull();

    await row.getByLabel("Product image").setInputFiles({ name: "h.png", mimeType: "image/png", buffer: PNG });
    await expect(row.getByTestId("board-image")).toBeVisible();
    await expect.poll(() => field("has_image")).toBe(true);
  } finally {
    await page.request.post(`/api/catalog/custom-made/${mid}/archive`);
  }
});
