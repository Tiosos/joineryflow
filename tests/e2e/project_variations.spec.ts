import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

// Q608: a drafter's variation is a Draft that does not count; a manager approves or rejects it.
// Runs on a project of its own (converted from an estimate this spec makes), so a re-run is clean.
async function convertedProject(page: Page): Promise<number> {
  await login(page, "kai.ngata@hartwood.test");
  const api = async (path: string, data?: object) => {
    const r = await page.request.post(`/api${path}`, data ? { data } : undefined);
    expect(r.status(), path).toBeLessThan(300);
    return r.json();
  };
  const customer = await api("/customers", { name: `E2E variations ${Date.now()}` });
  const estimate = await api("/estimates", { customer_id: customer.customer_id, title: `E2E variations ${Date.now()}` });
  const rid = estimate.current_revision_id as number;
  await api(`/revisions/${rid}/lines`, { description: "E2E line", qty: 1 });
  for (let i = 0; i < 10; i++) await api(`/revisions/${rid}/advance`);
  await api(`/revisions/${rid}/accept`);
  const res = await api(`/revisions/${rid}/convert`, { contract_value: "1000.00" });
  return res.project_id as number;
}

test("a drafter's variation waits for a manager, who approves one and rejects another", async ({ page }) => {
  const pid = await convertedProject(page);
  const current = page.getByText("Contract Value (current)").locator("xpath=following-sibling::div");

  await login(page, "noa.lindqvist@hartwood.test");
  await page.goto(`/projects/${pid}`);
  await page.getByRole("button", { name: "+ Add variation" }).click();
  await expect(page.getByText("Added as a draft until a manager approves it")).toBeVisible();
  for (const [name, amount] of [["Extra shelf", "250"], ["Wrong colour", "90"]]) {
    await page.getByPlaceholder("Description *").fill(name);
    await page.getByPlaceholder("Amount (+/-) *").fill(amount);
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByTestId("variation-row").filter({ hasText: name })).toBeVisible();
    if (name === "Extra shelf") await page.getByRole("button", { name: "+ Add variation" }).click();
  }
  const shelf = page.getByTestId("variation-row").filter({ hasText: "Extra shelf" });
  await expect(shelf.getByTestId("variation-status")).toHaveText("Draft");
  await expect(current).toHaveText("$1,000.00");                       // a Draft does not count
  await expect(shelf.getByRole("button", { name: "Approve" })).toHaveCount(0);   // a drafter cannot decide
  await expect(shelf.getByRole("button", { name: "Edit" })).toBeVisible();       // but may edit their own

  await login(page);
  await page.goto(`/projects/${pid}`);
  await page.getByTestId("variation-row").filter({ hasText: "Extra shelf" }).getByRole("button", { name: "Approve" }).click();
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(page.getByTestId("variation-row").filter({ hasText: "Extra shelf" }).getByTestId("variation-status")).toHaveText("Approved");
  await expect(current).toHaveText("$1,250.00");

  await page.getByTestId("variation-row").filter({ hasText: "Wrong colour" }).getByRole("button", { name: "Reject" }).click();
  await page.getByTestId("confirm-dialog").locator("textarea").fill("Not in scope");   // confirm waits for a reason
  await page.getByTestId("confirm-dialog-confirm").click();
  const wrong = page.getByTestId("variation-row").filter({ hasText: "Wrong colour" });
  await expect(wrong.getByTestId("variation-status")).toHaveText("Rejected");
  await expect(wrong).toContainText("Not in scope");
  await expect(current).toHaveText("$1,250.00");                       // a rejected one never counts
});

// Q609: a variation may name the Joinery Items it touches; none ticked is a project-level variation.
test("a variation is linked to items when added and its draft links can be changed", async ({ page }) => {
  const pid = await convertedProject(page);
  const stamp = Date.now();
  await login(page);
  for (const name of [`Vanity ${stamp}`, `Wardrobe ${stamp}`]) {
    const r = await page.request.post(`/api/projects/${pid}/items`, { data: { description: name } });
    expect(r.status(), name).toBeLessThan(300);
  }

  await login(page, "noa.lindqvist@hartwood.test");
  await page.goto(`/projects/${pid}`);
  await page.getByRole("button", { name: "+ Add variation" }).click();
  await page.getByPlaceholder("Description *").fill("Linked change");
  await page.getByPlaceholder("Amount (+/-) *").fill("40");
  await page.getByTestId("variation-item-picker").getByLabel(new RegExp(`Vanity ${stamp}`)).check();
  await page.getByRole("button", { name: "Add", exact: true }).click();

  const row = page.getByTestId("variation-row").filter({ hasText: "Linked change" });
  await expect(row.getByTestId("variation-items")).toContainText(`Vanity ${stamp}`);

  await row.getByRole("button", { name: "Items" }).click();
  await row.getByTestId("variation-item-picker").getByLabel(new RegExp(`Vanity ${stamp}`)).uncheck();
  await row.getByTestId("variation-item-picker").getByLabel(new RegExp(`Wardrobe ${stamp}`)).check();
  await row.getByRole("button", { name: "Save items" }).click();
  await expect(row.getByTestId("variation-items")).toContainText(`Wardrobe ${stamp}`);
  await expect(row.getByTestId("variation-items")).not.toContainText(`Vanity ${stamp}`);
});

// Q610: a manager voids an Approved variation with a reason; it stays listed but stops counting.
test("a manager voids an approved variation and the contract value drops it", async ({ page }) => {
  const pid = await convertedProject(page);
  const current = page.getByText("Contract Value (current)").locator("xpath=following-sibling::div");

  await login(page);
  await page.goto(`/projects/${pid}`);
  await page.getByRole("button", { name: "+ Add variation" }).click();
  await page.getByPlaceholder("Description *").fill("Added twice");
  await page.getByPlaceholder("Amount (+/-) *").fill("300");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const row = page.getByTestId("variation-row").filter({ hasText: "Added twice" });
  await expect(row.getByTestId("variation-status")).toHaveText("Approved");   // a manager's own is Approved at once
  await expect(current).toHaveText("$1,300.00");

  await row.getByRole("button", { name: "Void" }).click();
  await page.getByTestId("confirm-dialog").locator("textarea").fill("Entered twice");
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(row.getByTestId("variation-status")).toHaveText("Voided");
  await expect(row).toContainText("Entered twice");
  await expect(row.getByRole("button", { name: "Void" })).toHaveCount(0);      // final
  await expect(current).toHaveText("$1,000.00");

  await login(page, "noa.lindqvist@hartwood.test");                           // a drafter has no Void button
  await page.goto(`/projects/${pid}`);
  await expect(page.getByTestId("variation-row").filter({ hasText: "Added twice" })
    .getByRole("button", { name: "Void" })).toHaveCount(0);
});
