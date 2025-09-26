import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4951",
    headless: true,
    actionTimeout: 5_000,
    trace: "on-first-retry",
  },
});
