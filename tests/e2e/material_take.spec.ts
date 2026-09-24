import { test, expect } from "@playwright/test";

/**
 * Sub-project #12 (D3) — Material Take → Material Summary against `make seed`.
 *
 * The seed leaves ALF-001 with approved takes on every item that has parts
 * except one (a draft), a built summary, and one item at take v2 — so the
 * summary opens with a stale line and one missing take.
 */
async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.fill('input[type="email"]', "rin.park@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

test("a drafted take can be adjusted and approved, then summarised", async ({ page }) => {
  await login(page);

  // The seeded draft item is linked from the summary's missing-takes list.
  await page.goto("/projects/1/procurement?tab=summary");
  await expect(page.getByRole("heading", { name: "Material Summary" })).toBeVisible();
  await expect(page.getByText(/may be outdated/)).toBeVisible();
  await page.getByText(/without an approved take/).click();
  const draftLink = page.locator("details a").first();
  const draftHref = await draftLink.getAttribute("href");
  await draftLink.click();
  await expect(page).toHaveURL(/\/items\/\d+\?tab=take/);

  // Draft v1: bump a wastage %, add a manual edging line, approve.
  const wastage = page.getByRole("textbox", { name: /^Wastage for / }).first();
  await wastage.fill("10");
  await wastage.blur();
  await page.getByRole("textbox", { name: "New line description" }).fill("Edge tape white 22mm");
  await page.getByRole("textbox", { name: "New line qty" }).fill("12");
  await page.getByRole("button", { name: "Add line" }).click();
  await expect(page.getByText("Edge tape white 22mm")).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText(/Take v1 · approved/)).toBeVisible();

  // Rebuild: that item leaves the missing list (items with no parts stay on
  // it — they have no take either) and its edging line appears.
  await page.goto("/projects/1/procurement?tab=summary");
  await page.getByRole("button", { name: "Rebuild from approved takes" }).click();
  await expect(page.getByRole("button", { name: /Edge tape white 22mm/ })).toBeVisible();
  await page.getByText(/without an approved take/).click();
  await expect(page.locator(`details a[href="${draftHref}"]`)).toHaveCount(0);
  await expect(page.getByText(/may be outdated/)).toHaveCount(0);
});
