import {expect, test} from "@playwright/test";

import {csrfToken, mockStructuraApi} from "./support/structuraMock";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Mocked browser tests are local-only.");

test.beforeEach(async ({context, page}) => {
  await context.addCookies([
    {name: "structura_session", value: "phase3-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page);
});

test("Phase 3 parse debug surface loads canonical artifact diagnostics on demand", async ({page}) => {
  await page.goto("/");
  await page.getByRole("row", {name: /Existing Warranty/}).click();
  await page.locator(".page-heading").getByRole("button", {name: "Open Viewer"}).click();

  await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
  await page.locator(".parse-debug-panel").getByRole("button", {name: "Load"}).click();

  const debug = page.locator(".parse-debug-panel");
  await expect(debug).toContainText("Artifacts 1");
  await expect(debug).toContainText("Pages 1");
  await expect(debug).toContainText("Chunks 1");
  await expect(debug).toContainText("Current artifact: docling_json");
  await expect(debug).toContainText("Phase 3 canonical parse text");
  await expect(debug).toContainText("docling_convert succeeded");
});
