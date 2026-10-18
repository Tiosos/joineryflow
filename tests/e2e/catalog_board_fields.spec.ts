import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("a Board item shows and edits the board fields (UM included) and keeps one picture", async ({ page }) => {
  const stamp = Date.now();
  await login(page);
  const desc = `Board fields ${stamp}`;
  const created = (await (await page.request.post("/api/catalog/board-materials", {
    data: { code: `BF-${stamp}`, sku: `bf-${stamp}`, description: desc, colour: "Tas Oak QTR", hmr: "MR" },
  })).json()) as { material_id: number };
  const mid = created.material_id;
  const field = async (k: string) =>
    ((await (await page.request.get(`/api/catalog/board-materials/${mid}`)).json()) as Record<string, unknown>)[k];
  try {
    await page.goto("/catalog?tab=board");
    const row = page.locator("tr").filter({ has: page.locator(`input[value="${desc}"]`) });
    await expect(row.getByLabel("Colour")).toHaveValue("Tas Oak QTR");
    await expect(row.getByLabel("HMR")).toHaveValue("MR");

    await row.getByLabel("Finish").fill("Veneer");
    await row.getByLabel("Finish").blur();
    await expect.poll(() => field("finish")).toBe("Veneer");
    await row.getByLabel("Finish").fill("");                       // empty clears it
    await row.getByLabel("Finish").blur();
    await expect.poll(() => field("finish")).toBeNull();

    await row.getByLabel("UM").fill("sht");                        // UM (0075; the Laminate tab shows the same grid)
    await row.getByLabel("UM").blur();
    await expect.poll(() => field("um")).toBe("sht");
    await row.getByLabel("UM").fill("");
    await row.getByLabel("UM").blur();
    await expect.poll(() => field("um")).toBeNull();

    await row.getByLabel("Product image").setInputFiles({ name: "b.png", mimeType: "image/png", buffer: PNG });
    await expect(row.getByTestId("board-image")).toBeVisible();
    await expect.poll(() => field("has_image")).toBe(true);
    await row.getByRole("button", { name: "remove" }).click();
    await expect(row.getByTestId("board-image")).toHaveCount(0);
    await expect.poll(() => field("has_image")).toBe(false);
  } finally {
    await page.request.post(`/api/catalog/board-materials/${mid}/archive`);
  }
});
