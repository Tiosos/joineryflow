import { test, expect } from "@playwright/test";
import path from "node:path";

const BASE = (process.env.PW_BASE_URL ?? "http://localhost:3000").replace(
  /\/$/,
  "",
);
const PROD_URL = `${BASE}/login`;
const LEGACY_URL =
  "file://" +
  path.resolve(__dirname, "../../legacy/login.html").replace(/\\/g, "/");

test.describe("Login visual parity", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("production /login renders", async ({ page }) => {
    await page.goto(PROD_URL, { waitUntil: "networkidle" });
    await expect(page.getByText("Welcome back")).toBeVisible();
    await page.screenshot({
      path: "screenshots/login-prod.png",
      fullPage: false,
    });
  });

  test("legacy/login.html renders", async ({ page }) => {
    await page.goto(LEGACY_URL, { waitUntil: "networkidle" });
    await expect(page.getByText("Welcome back")).toBeVisible();
    await page.screenshot({
      path: "screenshots/login-legacy.png",
      fullPage: false,
    });
  });
});
