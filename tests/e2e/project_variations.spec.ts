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
    await page.getByPlaceholder("Selling price impact (+/-) *").fill(amount);
    await page.getByPlaceholder("Reason *").fill("E2E reason");
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
  await page.getByPlaceholder("Selling price impact (+/-) *").fill("40");
  await page.getByPlaceholder("Reason *").fill("E2E reason");
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
  await page.getByPlaceholder("Selling price impact (+/-) *").fill("300");
  await page.getByPlaceholder("Reason *").fill("E2E reason");
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

// Q611: number, reason, who asked and when, cost and time impact, and the decision history.
test("a variation shows its number, reason, requester, impacts and history", async ({ page }) => {
  const pid = await convertedProject(page);
  const current = page.getByText("Contract Value (current)").locator("xpath=following-sibling::div");

  await login(page, "noa.lindqvist@hartwood.test");
  await page.goto(`/projects/${pid}`);
  await page.getByRole("button", { name: "+ Add variation" }).click();
  await page.getByPlaceholder("Description *").fill("Pantry shelves");
  await page.getByPlaceholder("Selling price impact (+/-) *").fill("500");
  await page.getByPlaceholder("Reason *").fill("Builder asked for two more");
  await page.getByPlaceholder("Requested by").fill("Builder: J. Smith");
  await page.getByLabel("Requested on").fill("2026-10-01");
  await page.getByPlaceholder("Cost impact (+/-)").fill("320");
  await page.getByPlaceholder("Time impact (days)").fill("-2");
  await page.getByRole("button", { name: "Add", exact: true }).click();

  const row = page.getByTestId("variation-row").filter({ hasText: "Pantry shelves" });
  await expect(row).toContainText("VAR-001");
  await expect(row.getByTestId("variation-details")).toContainText(
    "Reason: Builder asked for two more · Requested by Builder: J. Smith on 2026-10-01 · Cost impact $320.00 · Time impact -2 d",
  );
  await expect(row.getByTestId("variation-history")).toContainText("Added by");
  await expect(current).toHaveText("$1,000.00");                       // a Draft counts nothing, cost or price

  await login(page);
  await page.goto(`/projects/${pid}`);
  const mrow = page.getByTestId("variation-row").filter({ hasText: "Pantry shelves" });
  await mrow.getByRole("button", { name: "Approve" }).click();
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(mrow.getByTestId("variation-history")).toContainText("Approved by");
  await expect(current).toHaveText("$1,500.00");                       // the selling-price impact only

  await page.getByRole("button", { name: "+ Add variation" }).click();   // numbers run on within the project
  await page.getByPlaceholder("Description *").fill("Second");
  await page.getByPlaceholder("Selling price impact (+/-) *").fill("10");
  await expect(page.getByRole("button", { name: "Add", exact: true })).toBeDisabled();   // a reason is required
  await page.getByPlaceholder("Reason *").fill("Because");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByTestId("variation-row").filter({ hasText: "Second" })).toContainText("VAR-002");
});

// Q617/Q613: a Draft variation waits in the bell of the manager who decides it, and leaves when decided.
test("a draft variation appears in a manager's bell and leaves it once approved", async ({ page }) => {
  const pid = await convertedProject(page);
  const code = (await (await page.request.get(`/api/projects/${pid}`)).json()).project_code as string;

  await login(page, "noa.lindqvist@hartwood.test");
  expect(
    (await page.request.post(`/api/projects/${pid}/contract/variations`, {
      data: { description: "Bell variation", amount_delta: "75", reason: "E2E reason" },
    })).status(),
  ).toBe(201);
  await page.goto("/dashboard");
  await page.getByTestId("notification-bell").click();
  await expect(page.getByTestId("variations-waiting")).toHaveCount(0);      // the drafter does not decide it

  await login(page);
  await page.goto("/dashboard");
  await page.getByTestId("notification-bell").click();
  const entry = page.getByTestId("variation-waiting").filter({ hasText: `VAR-001 · ${code}` });
  await expect(entry).toContainText("Bell variation");
  await expect(page.getByTestId("notification-bell")).toHaveAttribute("aria-label", /need attention/);
  await entry.click();
  await expect(page).toHaveURL(new RegExp(`/projects/${pid}$`));

  await page.getByTestId("variation-row").filter({ hasText: "Bell variation" }).getByRole("button", { name: "Approve" }).click();
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(page.getByTestId("variation-status")).toHaveText("Approved");
  await page.goto("/dashboard");
  await page.getByTestId("notification-bell").click();
  await expect(page.getByTestId("variation-waiting").filter({ hasText: `VAR-001 · ${code}` })).toHaveCount(0);
});
