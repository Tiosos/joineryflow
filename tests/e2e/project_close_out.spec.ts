import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * Close-out checks are advisory (2026-10-22): the dialog lists what is still open and asks for a
 * reason, but the project closes. A project with nothing open closes on a plain confirm.
 *
 * Builds its own projects through the API (a closed project cannot be reopened for another
 * run), so it passes on a second run against the same database.
 */
test("closing a project with open things lists them and asks for a reason", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const api = async (method: "get" | "post", path: string, data?: object) => {
    const r = await page.request[method](`/api${path}`, data ? { data } : undefined);
    expect(r.status(), `${method} ${path}`).toBeLessThan(300);
    return r.json();
  };
  const pid = (await api("post", "/projects", { project_code: `CO-${stamp}`, name: `Close out ${stamp}` })).id as number;
  await api("post", `/projects/${pid}/items`, { description: `Close out item ${stamp}` });

  await page.goto(`/projects/${pid}`);
  await page.getByRole("button", { name: "Close out" }).click();
  await expect(page.getByTestId("close-out-open")).toContainText("1 item not installed");
  const confirm = page.getByTestId("confirm-dialog-confirm");
  await expect(confirm).toBeDisabled();                       // a reason is asked for
  await page.getByTestId("confirm-dialog-reason").fill("Client signed off");
  await confirm.click();
  await expect(page.getByRole("button", { name: "Closed" })).toBeVisible();
  expect((await api("get", `/projects/${pid}`)).status).toBe("Closed");
});

test("a project with nothing open closes on a plain confirm", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const r = await page.request.post("/api/projects", { data: { project_code: `CN-${stamp}`, name: `Close clean ${stamp}` } });
  const pid = (await r.json()).id as number;

  await page.goto(`/projects/${pid}`);
  await page.getByRole("button", { name: "Close out" }).click();
  await expect(page.getByTestId("close-out-open")).toHaveCount(0);
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(page.getByRole("button", { name: "Closed" })).toBeVisible();
});
