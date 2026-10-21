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
    // The task the link points at stays pinned, now Done; the list itself holds only what is to do.
    await expect(row.getByRole("combobox", { name: /Status of/ })).toHaveValue("done", { timeout: 30_000 });
    await page.goto("/tasks");
    await expect(page.getByTestId("task-panel")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(`[data-testid="task-row"][data-task-id="${taskId}"]`)).toHaveCount(0);

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

/**
 * Tasks in Global Search (migration 0081). Like search.spec.ts these need Meilisearch and the
 * search-worker: skipped locally on a 503, a failure in CI. The worker indexes asynchronously, so
 * each lookup is retried until the new task shows.
 */
async function skipWithoutSearch(page: Page) {
  const res = await page.request.get("/api/search?q=297830");
  if (res.status() !== 503) return;
  expect(process.env.CI, "Meilisearch is not reachable (503 SEARCH_UNAVAILABLE) in CI").toBeFalsy();
  test.skip(true, "Meilisearch is not reachable (503 SEARCH_UNAVAILABLE)");
}

async function taskTitles(page: Page, q: string, extra = ""): Promise<string[]> {
  const body = await (await page.request.get(`/api/search?q=${encodeURIComponent(q)}${extra}`)).json();
  return (body.hits as { type: string; title: string }[]).filter((h) => h.type === "task").map((h) => h.title);
}

test("a task is found in search, and opening the hit lands on it", async ({ page }) => {
  await login(page);
  await skipWithoutSearch(page);
  const { stamp, itemId } = await fixture(page, "search");
  const word = `Hingeplate${stamp}`;
  const made = await page.request.post("/api/tasks", { data: { title: `Order the ${word}`, item_id: itemId } });
  expect(made.status()).toBe(201);
  const taskId = (await made.json()).task_id as number;
  try {
    await expect(async () => {
      expect(await taskTitles(page, word)).toEqual([`Order the ${word}`]);
    }).toPass({ timeout: 30_000 });

    await page.goto(`/search?q=${word}`);
    await expect(page.getByRole("button", { name: /^Tasks 1$/ })).toBeVisible({ timeout: 30_000 });
    await page.getByText(`Order the ${word}`).first().click();
    await expect(page).toHaveURL(new RegExp(`/tasks\\?task=${taskId}`), { timeout: 30_000 });
    await expect(page.locator(`[data-testid="task-row"][data-task-id="${taskId}"]`)).toBeVisible();
  } finally {
    await page.request.post(`/api/tasks/${taskId}/status`, { data: { status: "cancelled" } });
  }
});

test("a task with no target is found only by its people and managers", async ({ page }) => {
  const DRAFTER = "noa.lindqvist@hartwood.test"; // creates it, assigned to herself
  const EDITOR = "juno.okafor@hartwood.test";    // a colleague who can read Tracking: must not find it
  const MANAGER_EMAIL = "rin.park@hartwood.test";
  await login(page, DRAFTER);
  await skipWithoutSearch(page);
  const word = `Privatehinge${Date.now()}`;
  const me = (await (await page.request.get("/api/auth/me")).json()).id as number;
  const made = await page.request.post("/api/tasks", { data: { title: `Call ${word}`, assignee_id: me } });
  expect(made.status()).toBe(201);
  const taskId = (await made.json()).task_id as number;
  try {
    await expect(async () => {
      expect(await taskTitles(page, word)).toEqual([`Call ${word}`]);       // the creator and assignee
    }).toPass({ timeout: 30_000 });

    await page.context().clearCookies();
    await login(page, MANAGER_EMAIL);
    expect(await taskTitles(page, word)).toEqual([`Call ${word}`]);         // a manager sees every task

    await page.context().clearCookies();
    await login(page, EDITOR);
    expect(await taskTitles(page, word)).toEqual([]);                       // a colleague does not
    expect(await taskTitles(page, word, "&include_archived=true")).toEqual([]);
  } finally {
    await page.context().clearCookies();
    await login(page, DRAFTER);
    await page.request.post(`/api/tasks/${taskId}/status`, { data: { status: "cancelled" } });
  }
});
