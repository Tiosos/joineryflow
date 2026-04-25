// preamble:
// callers: Makefile targets `e2e` and `e2e-docker` invoke `playwright test`,
//   which auto-loads this config from cwd `apps/web`.
// glob: testDir points to ../../tests/e2e/*.spec.ts.
// data-shape: reads env PW_BASE_URL (string URL); falls back to host.docker.internal.
// user instruction: "You are implementing Task 29 of the JoineryFlow Foundation
//   plan: a Playwright smoke test that exercises the full login → tabs → logout flow."
// /resume-session

import { defineConfig } from "@playwright/test";

const baseURL = process.env.PW_BASE_URL ?? "http://host.docker.internal:3000";

export default defineConfig({
  testDir: "../../tests/e2e",
  use: {
    baseURL,
    headless: true,
    trace: "retain-on-failure",
  },
  reporter: "list",
  timeout: 90_000,
  retries: 0,
  workers: 1,
});
