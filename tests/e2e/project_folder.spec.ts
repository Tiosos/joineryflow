import { test, expect } from "@playwright/test";
import { login } from "./helpers";

// Q640: a project has one plain link to its folder, set on the project page and shown in Tracking's Info
// pop-up. Runs in a project of its own.
test("a manager sets a project's folder link and Tracking's Info pop-up opens it", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const pid = (await (await page.request.post("/api/projects", {
    data: { project_code: `PF-${stamp}`, name: `Folder ${stamp}` },
  })).json()).id as number;
  const url = `https://hartwood.example/sites/jobs/PF-${stamp}`;

  await page.goto(`/projects/${pid}`);
  const box = page.getByText("Project folder (link)").locator("xpath=following-sibling::input");
  await box.fill("javascript:alert(1)");
  await box.blur();
  await expect(page.getByText("Save failed")).toBeVisible();          // only a web link is accepted
  await expect(page.getByTestId("project-folder-link")).toHaveCount(0);

  await box.fill(url);
  await box.blur();
  await expect(page.getByTestId("project-folder-link")).toHaveAttribute("href", url);

  await page.goto(`/tracking?project_id=${pid}`);
  await page.getByRole("button", { name: "Info", exact: true }).click();
  const link = page.getByTestId("project-folder-link");
  await expect(link).toHaveAttribute("href", url);
  await expect(link).toHaveAttribute("target", "_blank");
});
