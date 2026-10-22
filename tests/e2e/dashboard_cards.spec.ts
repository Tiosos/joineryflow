import { expect, test } from "@playwright/test";

import { login } from "./helpers";

// Q633: a dashboard card opens the items it counted (Tracking's All projects scope). The spec reads
// whatever the card says now and checks the list shows that many, so it changes nothing and does not
// depend on what an earlier spec left.
const CARDS = [
  { label: "Overdue Items", filter: "overdue" },
  { label: "In Optimisation", filter: "in_optimisation" },
  { label: "Awaiting Install", filter: "awaiting_install" },
];

for (const { label, filter } of CARDS) {
  test(`the "${label}" card opens exactly the items it counted`, async ({ page }) => {
    await login(page);
    const card = page.locator('[data-testid="metric-card"]', { hasText: label });
    await expect(card).toBeVisible();
    const counted = Number((await card.locator("div").nth(1).innerText()).trim());
    const href = await card.getAttribute("href");
    expect(href).toBe(`/tracking?scope=all&filter=${filter}`);

    await page.goto(href!);
    await expect(page.getByTestId("tracking-all-projects")).toBeVisible();
    await expect(page.getByTestId("tracking-all-count")).toHaveText(String(counted));
    await expect(page.locator('[data-testid^="tracking-all-row-"]')).toHaveCount(counted);
  });
}
