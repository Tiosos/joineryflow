import { test, expect } from "@playwright/test";

/**
 * Sub-project #10 (E2) — the two behaviours the seed exists to demonstrate:
 *
 *  - **Q420–Q422**: related parts nest under their parent and are *collapsed*
 *    when Tracking first opens.
 *  - **Q417 + Q418**: a related part shows its issued order number where a
 *    cutlist number would be, and clicking it opens Orderbook **on that
 *    order** — not merely on the page.
 *
 * Both run against `make seed`'s ALF-001 fixtures: two related parts under
 * ST-CT01, one carrying an issued order (`Corian Stoneworks`) and one carrying
 * none.
 */
async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.fill('input[type="email"]', "rin.park@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

test("related parts are nested and collapsed by default (Q420-Q422)", async ({ page }) => {
  await login(page);
  await page.goto("/tracking?project_id=1");
  await expect(page.locator('[data-testid="tracking-row"]').first()).toBeVisible();

  const rows = page.locator('[data-testid="tracking-row"]');
  const collapsed = await rows.count();
  // The aria-label flips to "Hide related parts" once open, so match on the
  // expanded state instead of the label.
  const toggle = page.locator('button[aria-expanded]').first();
  // The seed puts both related parts under one parent, so exactly one row
  // offers a toggle.
  await expect(page.locator('button[aria-expanded]')).toHaveCount(1);
  await expect(toggle).toHaveAttribute("aria-expanded", "false");

  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  // Both seeded related parts appear beneath their parent.
  await expect(rows).toHaveCount(collapsed + 2);

  // Collapsing again restores the original count.
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(rows).toHaveCount(collapsed);
});

test("a related part's order number opens Orderbook on that order (Q417/Q418)", async ({ page }) => {
  await login(page);
  await page.goto("/tracking?project_id=1");
  await expect(page.locator('[data-testid="tracking-row"]').first()).toBeVisible();
  await page.locator('button[aria-label="Show related parts"]').first().click();

  // One of the two seeded related parts has an issued order; the other has
  // none and so shows nothing here (Q429).
  const orderLink = page.locator('a[href^="/orderbook?order="]').first();
  await expect(orderLink).toBeVisible();
  const poNumber = (await orderLink.innerText()).trim();
  expect(poNumber).toMatch(/^PO-\d{4}-\d{4}$/);

  await orderLink.click();
  await expect(page).toHaveURL(/\/orderbook\?order=/, { timeout: 30_000 });

  // Q418's second clause: the order is *located*, not just navigated to.
  const selected = page.locator('[data-testid="order-row"][data-selected="true"]');
  await expect(selected).toHaveCount(1);
  await expect(selected).toContainText(poNumber);
  await expect(page.locator('[data-testid="order-detail"]')).toContainText(poNumber);

  // Q428: the order carries the PARENT Joinery Item's cutlist number.
  await expect(page.locator('[data-testid="order-detail"]')).toContainText("Cutlist no.");
});

test("Orderbook keeps the procurement-batch queue beside orders (Q504)", async ({ page }) => {
  await login(page);
  await page.goto("/orderbook");
  await expect(page.locator('[data-testid="orders-panel"]')).toBeVisible();

  await page.getByRole("button", { name: "Delivery queue" }).click();
  await expect(page).toHaveURL(/tab=queue/, { timeout: 30_000 });
  await expect(page.locator('[data-testid="orders-panel"]')).toHaveCount(0);
});
