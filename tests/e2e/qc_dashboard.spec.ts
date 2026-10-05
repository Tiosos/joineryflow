import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * QC Dashboard (Plan V1 §4.2), against `make seed`'s fixtures. On ALF-001:
 *   - item 1 (cutlist: DOWN in progress) has an open MADE defect and an open
 *     internal rework with no cost;
 *   - item 3 (cutlist: DOWN done) has an open CNC defect;
 *   - item 2 (cutlist: only *assigned*, nothing begun) has an open defect that
 *     is outside the dashboard's scope, so it is reported but not counted.
 * The other seeded projects carry no QC records.
 *
 * Read-only, so unlike estimating / comments it is safe to re-run without
 * re-seeding.
 */
/** The tile's number, exactly: `toContainText("2")` would also pass for "12". */
function count(n: number) {
  return new RegExp(`(?<!\\d)${n}$`);
}

test("the QC tab opens a dashboard counting only cutlists in production", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  await page.getByRole("link", { name: "QC", exact: true }).click();
  await expect(page).toHaveURL(/\/qc$/, { timeout: 30_000 });

  await expect(page.getByTestId("tile-defects")).toHaveText(count(2), { timeout: 30_000 });
  await expect(page.getByTestId("tile-rework")).toHaveText(count(1));
  // the one open rework has no cost yet, and the tile says the total under-counts
  await expect(page.getByTestId("tile-cost")).toContainText("Excludes 1 open rework");

  // by stage: MADE and CNC, each once
  const byStage = page.getByTestId("panel-by-stage");
  await expect(byStage).toContainText("CNC");
  await expect(byStage.getByRole("listitem")).toHaveCount(2);

  // nothing is hidden: the defect on the not-yet-started cutlist is reported
  await expect(page.getByTestId("qc-outside-scope")).toContainText("1 open defect");
});

test("a row drills down to the item's QC tab", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  await page.goto("/qc");
  const itemsPanel = page.getByTestId("panel-items");
  await expect(itemsPanel.locator("tbody tr")).toHaveCount(2, { timeout: 30_000 });

  await itemsPanel.locator("tbody tr").first().getByRole("link").click();
  await expect(page).toHaveURL(/\/items\/\d+\?tab=qc/, { timeout: 30_000 });
  await expect(page.getByText("Small chip on the top edge").or(page.getByText("Saw burn"))).toBeVisible();
});

test("filters narrow every number, are linkable, and clear", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  await page.goto("/qc");
  await expect(page.getByTestId("tile-defects")).toHaveText(count(2), { timeout: 30_000 });

  // a project with no QC records
  await page.getByLabel("Project").selectOption({ label: "TRT-014 — Trentham Heights" });
  await expect(page.getByTestId("tile-defects")).toHaveText(count(0), { timeout: 30_000 });
  await expect(page.getByTestId("panel-by-stage")).toContainText("No open defects");
  await expect(page).toHaveURL(/\/qc\?project=\d+/);

  // the filtered view survives a reload
  await page.reload();
  await expect(page.getByLabel("Project")).not.toHaveValue("");
  await expect(page.getByTestId("tile-defects")).toHaveText(count(0), { timeout: 30_000 });

  // a date range after everything was raised leaves nothing
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByTestId("tile-defects")).toHaveText(count(2), { timeout: 30_000 });
  await page.getByLabel("Raised from").fill("2999-01-01");
  await expect(page.getByTestId("tile-defects")).toHaveText(count(0), { timeout: 30_000 });
});

test("a hand-edited link with an inverted date range opens cleanly instead of on an error", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  await page.goto("/qc?from=2026-09-30&to=2026-09-01");
  await expect(page.getByTestId("tile-defects")).toHaveText(count(2), { timeout: 30_000 });
  // (Next's own route announcer also has role="alert", hence the test id)
  await expect(page.getByTestId("qc-error")).toHaveCount(0);
  await expect(page.getByLabel("Raised from")).toHaveValue("");
});

test("a read-only role sees the tab and the same numbers", async ({ page }) => {
  await login(page, "sam.ito@hartwood.test"); // viewer: qc:read only
  await expect(page.getByRole("link", { name: "QC", exact: true })).toBeVisible();
  await page.goto("/qc");
  await expect(page.getByTestId("tile-defects")).toHaveText(count(2), { timeout: 30_000 });
  // report-only: with no filter set the dashboard has no buttons at all
  await expect(page.getByTestId("qc-dashboard").getByRole("button")).toHaveCount(0);
});
