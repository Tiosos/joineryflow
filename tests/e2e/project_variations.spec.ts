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
