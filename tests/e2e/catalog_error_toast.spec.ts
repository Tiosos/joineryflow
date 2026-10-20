import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/** A failed Catalog save shows a notice toast (dismissable), not a native alert box. */

test("a refused Catalog save shows a toast, not a browser alert", async ({ page }) => {
  const stamp = Date.now();
  await login(page);
  const desc = `Toast hinge ${stamp}`;
  const created = (await (await page.request.post("/api/catalog/hardware-materials", {
    data: { sku: `ct-${stamp}`, description: desc, unit_cost: 5 },
  })).json()) as { material_id: number };
  const native: string[] = [];
  page.on("dialog", (d) => { native.push(d.message()); void d.dismiss(); });
  try {
    await page.goto("/catalog?tab=hardware");
    const row = page.locator("tr").filter({ has: page.locator(`input[value="${desc}"]`) });
    const input = row.getByLabel("Unit cost");
    await expect(input).toHaveValue("5");

    await page.route("**/api/catalog/hardware-materials/*", (route) =>
      route.request().method() === "PATCH" ? route.fulfill({ status: 500, body: "boom" }) : route.continue());
    await input.fill("9");
    await input.blur();

    const toast = page.getByTestId("undo-toast");
    await expect(toast).toContainText("Could not save the change");
    expect(native).toEqual([]);                              // no browser alert box
    await toast.getByRole("button", { name: "Dismiss" }).click();
    await expect(toast).toHaveCount(0);
  } finally {
    await page.unroute("**/api/catalog/hardware-materials/*");
    await page.request.post(`/api/catalog/hardware-materials/${created.material_id}/archive`);
  }
});
