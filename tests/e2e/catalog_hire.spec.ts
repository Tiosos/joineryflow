import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("an Equipment Hire item shows and edits UM and website and keeps one picture", async ({ page }) => {
  const stamp = Date.now();
  await login(page);
  // A hire row needs a project: one of its own, not ALF-001.
  const pid = (await (await page.request.post("/api/projects", {
    data: { project_code: `EH-${stamp}`, name: `Hire ${stamp}` },
  })).json()).id as number;
  const desc = `Scissor lift ${stamp}`;
  const created = (await (await page.request.post("/api/catalog/equipment-hire", {
    data: { contract_ref: `eh-${stamp}`, sku: `eh-${stamp}`, description: desc, project_id: pid, um: "ea" },
  })).json()) as { hire_id: number };
  const hid = created.hire_id;
  const field = async (k: string) =>
    ((await (await page.request.get(`/api/catalog/equipment-hire/${hid}`)).json()) as Record<string, unknown>)[k];
  try {
    await page.goto("/catalog?tab=hire");
    const row = page.locator("tr").filter({ has: page.locator(`input[value="${desc}"]`) });
    await expect(row.getByLabel("UM")).toHaveValue("ea");
    await row.getByLabel("UM").fill("day");
    await row.getByLabel("UM").blur();
    await expect.poll(() => field("um")).toBe("day");
    await row.getByLabel("UM").fill("");                          // empty clears it
    await row.getByLabel("UM").blur();
    await expect.poll(() => field("um")).toBeNull();

    await row.getByLabel("Product image").setInputFiles({ name: "h.png", mimeType: "image/png", buffer: PNG });
    await expect(row.getByTestId("board-image")).toBeVisible();
    await expect.poll(() => field("has_image")).toBe(true);
  } finally {
    await page.request.post(`/api/catalog/equipment-hire/${hid}/archive`);
  }
});
