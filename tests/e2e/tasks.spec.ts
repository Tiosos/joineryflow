import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

/**
 * Tasks (Plan V1 §10, Q524): a task assigned to me waits in the bell until it is done, "My tasks"
 * lists it, and the item editor's Tasks tab creates and cancels them. Own project and item
 * (CLAUDE.md §3: nothing is added to ALF-001); every task a spec makes is finished or cancelled.
 */

async function fixture(page: Page, label: string) {
  const stamp = Date.now();
  const made = await page.request.post("/api/projects", {
    data: { project_code: `TK-${stamp}`, name: `Tasks ${label} ${stamp}` },
  });
  expect(made.status()).toBe(201);
  const pid = (await made.json()).id as number;
  const created = await page.request.post(`/api/projects/${pid}/items`, {
    data: { description: `Tasks ${label} ${stamp}`, code: null, qty: 1 },
  });
  expect(created.status()).toBe(201);
  return { stamp, pid, itemId: (await created.json()).id as number };
}

async function openBell(page: Page) {
  await expect(async () => {
    await page.getByTestId("notification-bell").click();
    await expect(page.getByRole("menu")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 20_000 });
}

test("a task assigned to me waits in the bell, opens My tasks, and finishing it clears the bell", async ({ page }) => {
  await login(page);
  const me = (await (await page.request.get("/api/auth/me")).json()).id as number;
  const { stamp, itemId } = await fixture(page, "bell");
  const title = `Chase the hinge supplier ${stamp}`;
  const made = await page.request.post("/api/tasks", {
    data: { title, assignee_id: me, item_id: itemId, due_date: "2030-01-31" },
  });
  expect(made.status()).toBe(201);
  const taskId = (await made.json()).task_id as number;
  try {
    await page.goto("/dashboard");
    await openBell(page);
    const entry = page.getByTestId("task-open").filter({ hasText: title });
    await expect(entry).toContainText("Due 2030-01-31");
    await entry.click();

    await expect(page).toHaveURL(new RegExp(`/tasks\\?task=${taskId}`), { timeout: 30_000 });
    const row = page.locator(`[data-testid="task-row"][data-task-id="${taskId}"]`);
    await expect(row).toBeVisible({ timeout: 30_000 });
    await expect(row).toContainText("For");

    await row.getByRole("combobox", { name: /Status of/ }).selectOption("done");
    await expect(row).toHaveCount(0, { timeout: 30_000 }); // My tasks lists only what is still to do

    await page.getByRole("button", { name: "Done", exact: true }).click();
    await expect(page.locator(`[data-testid="task-row"][data-task-id="${taskId}"]`)).toBeVisible();

    await openBell(page);
    await expect(page.getByTestId("task-open").filter({ hasText: title })).toHaveCount(0);
  } finally {
    await page.request.post(`/api/tasks/${taskId}/status`, { data: { status: "cancelled" } });
  }
});

test("the item editor's Tasks tab adds a task, and cancelling asks first", async ({ page }) => {
  await login(page);
  const { stamp, itemId } = await fixture(page, "tab");
  const title = `Order the plinth ${stamp}`;

  await page.goto(`/items/${itemId}?tab=tasks`);
  await expect(page.getByTestId("task-panel")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("tasks-empty")).toBeVisible();

  await page.getByTestId("task-new").click();
  await page.getByLabel("Task title").fill(title);
  await page.getByLabel("Due date").fill("2030-02-01");
  await page.getByRole("button", { name: "Add task" }).click();
  const row = page.getByTestId("task-row").filter({ hasText: title });
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(row).toContainText("2030-02-01");
  const taskId = Number(await row.getAttribute("data-task-id"));

  // Cancelling asks first: Keep it changes nothing, Cancel task cancels.
  await row.getByRole("combobox", { name: /Status of/ }).selectOption("cancelled");
  await page.getByTestId("confirm-dialog-cancel").click();
  expect((await (await page.request.get(`/api/tasks/${taskId}`)).json()).status).toBe("open");

  await row.getByRole("combobox", { name: /Status of/ }).selectOption("cancelled");
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(async () => {
    expect((await (await page.request.get(`/api/tasks/${taskId}`)).json()).status).toBe("cancelled");
  }).toPass({ timeout: 20_000 });
});
