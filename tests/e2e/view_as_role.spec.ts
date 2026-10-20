import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/** /it "View as role": a read-only grid from the live system groups. Changes nothing. */

test("View as role shows what each role's group grants", async ({ page }) => {
  await login(page, "aria.voss@hartwood.test");                // the seeded admin: /it is admin-only
  await page.goto("/it");
  const select = page.getByTestId("view-as-role-select");
  await expect(select).toBeVisible({ timeout: 30_000 });
  const cell = (m: string, a: string) => page.getByTestId(`view-as-role-${m}-${a}`);
  const yes = async (m: string, a: string) => expect(cell(m, a)).toHaveAttribute("aria-label", `${m} ${a}: yes`);
  const no = async (m: string, a: string) => expect(cell(m, a)).toHaveAttribute("aria-label", `${m} ${a}: no`);

  await select.selectOption("viewer");
  await yes("tracking", "read");
  await no("tracking", "write");
  await no("it_management", "read");
  await expect(page.getByTestId("view-as-role-tabs")).toContainText("IT page: no");

  await select.selectOption("purchase_officer");
  await yes("orderbook", "approve");

  await select.selectOption("drafter");
  await yes("orderbook", "write");
  await no("orderbook", "approve");

  await select.selectOption("admin");
  await yes("it_management", "write");
  await expect(page.getByTestId("view-as-role-tabs")).toContainText("IT page: yes");
});
