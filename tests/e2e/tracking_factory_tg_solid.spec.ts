import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * Migration 0053: Tracking shows the factory each item is made in, and the Tg Solid chip filters on
 * the per-item tag. The seed puts the Pantry tower (K-102) at TG, tagged Tg Solid, and the Master
 * ensuite vanity (B-201) at SI, both in TRT-014, which no other spec edits.
 */
test("the Factory column and the Tg Solid chip", async ({ page }) => {
  await login(page);
  const list = await (await page.request.get("/api/projects")).json();
  const trt = (list.projects as { id: number; project_code: string }[]).find((p) => p.project_code === "TRT-014");
  expect(trt).toBeTruthy();

  await page.goto(`/tracking?project_id=${trt!.id}`);
  const rows = page.locator('[data-testid="tracking-row"]');
  await expect(rows.first()).toBeVisible();
  const row = (text: string) => rows.filter({ hasText: text });

  await expect(page.getByRole("columnheader", { name: "Factory" })).toBeVisible();
  await expect(row("Pantry tower")).toContainText("TG");
  await expect(row("Master ensuite vanity")).toContainText("SI");

  const chip = page.getByRole("button", { name: "Tg Solid", exact: true });
  await expect(chip).toBeEnabled();                         // no longer a parked, disabled chip
  const before = await rows.count();
  expect(before).toBeGreaterThan(1);
  await chip.click();
  await expect(rows).toHaveCount(1);                        // only the tagged item
  await expect(row("Pantry tower")).toHaveCount(1);
  await chip.click();                                       // off again
  await expect(rows).toHaveCount(before);
});
