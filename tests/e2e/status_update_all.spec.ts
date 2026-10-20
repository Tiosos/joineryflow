import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * Status pop-up "Update Status To All": one status + note for every live joinery item of the
 * project, after a count confirm; a Hard-Locked item is skipped and listed. Own project (§3).
 */

test("Update Status To All changes every item in the project after a count confirm", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const made = await page.request.post("/api/projects", {
    data: { project_code: `UA-${stamp}`, name: `Update all ${stamp}` },
  });
  expect(made.status()).toBe(201);
  const pid = (await made.json()).id as number;
  const ids: number[] = [];
  for (const n of [1, 2, 3]) {
    const r = await page.request.post(`/api/projects/${pid}/items`, {
      data: { description: `All ${n} ${stamp}`, code: null, qty: 1 },
    });
    expect(r.status()).toBe(201);
    ids.push((await r.json()).id as number);
  }
  expect((await page.request.post(`/api/items/${ids[2]}/hard-lock`)).status()).toBe(200);
  const status = async (id: number) => (await (await page.request.get(`/api/items/${id}`)).json()).status as string;

  await page.goto(`/tracking?project_id=${pid}`);
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: `All 1 ${stamp}` });
  await row.getByRole("button", { name: "Open status detail" }).click();
  const all = page.getByTestId("status-update-all");
  await expect(all).toBeDisabled();                                   // needs a note first
  await page.getByLabel("HOLD").check();
  await page.getByPlaceholder("Description of Status Change...").fill("Client paused the whole job");
  await expect(all).toBeEnabled();

  // The confirm names the count; Cancel changes nothing.
  await all.click();
  await expect(page.getByRole("alertdialog", { name: "Set 3 items to HOLD?" })).toBeVisible();
  await page.getByTestId("confirm-dialog-cancel").click();
  expect(await status(ids[0])).not.toBe("HOLD");

  await all.click();
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(page.getByText("2 updated · 1 skipped (locked:")).toBeVisible({ timeout: 30_000 });
  expect(await status(ids[0])).toBe("HOLD");
  expect(await status(ids[1])).toBe("HOLD");
  expect(await status(ids[2])).not.toBe("HOLD");                      // the Hard Lock held
});
