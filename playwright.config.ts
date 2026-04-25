import {defineConfig, devices} from "@playwright/test";

const liveStack = process.env.STRUCTURA_E2E_LIVE === "1";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL: liveStack ? process.env.STRUCTURA_E2E_WEB_URL ?? "http://127.0.0.1:3000" : "http://localhost:4173",
    viewport: {width: 1440, height: 960},
    trace: "retain-on-failure",
  },
  webServer: liveStack
    ? undefined
    : {
        command: "VITE_STRUCTURA_API_BASE_URL=http://localhost:8000 npm --workspace apps/web run dev -- --host localhost --port 4173",
        url: "http://localhost:4173",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
  projects: [
    {
      name: "chromium",
      use: {...devices["Desktop Chrome"]},
    },
  ],
});
