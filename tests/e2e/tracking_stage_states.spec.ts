import { test, expect } from "@playwright/test";
import { login } from "./helpers";

// Q591: Overdue / At risk / Delayed come from one server-side definition, and the Tracking chips and
// stage cells show it. Runs in a project of its own.
const day = (n: number) => new Date(Date.now() + n * 86_400_000).toISOString().slice(0, 10);
const ADMIN = "aria.voss@hartwood.test";

test("Tracking's Overdue, At risk and Delayed chips follow the server's stage states", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const pid = (await (await page.request.post("/api/projects", {
    data: { project_code: `SS-${stamp}`, name: `States ${stamp}` },
  })).json()).id as number;
  const mk = async (description: string, stages: Record<string, { due_date?: string; done_date?: string }>) => {
    const r = await page.request.post(`/api/projects/${pid}/items`, { data: { description, code: null, qty: 1 } });
    expect(r.status()).toBe(201);
    const id = (await r.json()).id as number;
    for (const [stage, dates] of Object.entries(stages)) {
      const p = await page.request.patch(`/api/items/${id}/lifecycle/${stage}`, { data: dates });
      expect(p.ok(), `${stage} on ${description}`).toBe(true);
    }
  };
  const late = `Late ${stamp}`, risky = `Risky ${stamp}`, lateDone = `LateDone ${stamp}`, quiet = `Quiet ${stamp}`;
  await mk(late, { CNC: { due_date: day(-1) } });
  await mk(risky, { REQ: { due_date: day(30) }, CNC: { due_date: day(1) } });   // CNC is due soon, REQ is not done
  await mk(lateDone, { CNC: { due_date: day(-3), done_date: day(-1) } });
  await mk(quiet, {});

  await page.goto(`/tracking?project_id=${pid}`);
  const rows = page.locator('[data-testid="tracking-row"]');
  await expect(rows).toHaveCount(4);

  const chip = (name: string) => page.getByRole("button", { name, exact: true });
  await chip("Overdue").click();
  await expect(rows).toHaveCount(1);
  await expect(rows.filter({ hasText: late })).toHaveCount(1);
  await chip("Overdue").click();

  await chip("At risk").click();
  await expect(rows).toHaveCount(1);
  await expect(rows.filter({ hasText: risky })).toHaveCount(1);
  await chip("At risk").click();

  await chip("Delayed").click();
  await expect(rows).toHaveCount(1);
  await expect(rows.filter({ hasText: lateDone })).toHaveCount(1);
  await chip("Delayed").click();
  await expect(rows).toHaveCount(4);

  // the stage cells carry the state as their tooltip, so the tint is the server's, not a date sum
  await expect(rows.filter({ hasText: late }).locator('td[title="Overdue"]')).toHaveCount(1);
  await expect(rows.filter({ hasText: risky }).locator('td[title^="At risk"]')).toHaveCount(1);
  await expect(rows.filter({ hasText: lateDone }).locator('td[title="Done late"]')).toHaveCount(1);

  // and the All projects scope lists the same items (an admin sees every project; ours is among them)
  await page.goto("/tracking?scope=all&filter=at_risk");
  await expect(page.getByTestId("tracking-all-projects")).toBeVisible();
  await expect(page.getByText(`SS-${stamp}`)).toBeVisible();
});

test("an admin sets the At risk window on /it and it is read back", async ({ page }) => {
  await login(page, ADMIN);
  await page.goto("/it");
  const box = page.getByTestId("at-risk-days");
  await expect(box).toHaveValue("3");
  try {
    await box.fill("5");
    await page.getByTestId("save-planning-btn").click();
    await expect(page.getByText(/Saved at/)).toBeVisible();
    await page.reload();
    await expect(page.getByTestId("at-risk-days")).toHaveValue("5");
    await page.getByTestId("at-risk-days").fill("99");
    await page.getByTestId("save-planning-btn").click();
    await expect(page.getByText("Enter a whole number of days from 0 to 90.")).toBeVisible();
  } finally {
    await page.request.patch("/api/workspace/planning", { data: { at_risk_days: 3 } });   // put it back as seeded
  }
});
