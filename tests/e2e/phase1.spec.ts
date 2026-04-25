import {expect, test} from "@playwright/test";
import {writeFile} from "node:fs/promises";

import {apiOrigin, csrfToken, mockStructuraApi} from "./support/structuraMock";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Mocked browser tests are local-only.");

test("Phase 1 Inbox to Viewer workflow uses protected asset URLs", async ({page, context}, testInfo) => {
  await context.addCookies([
    {name: "structura_session", value: "phase1-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page);

  await page.goto("/");
  await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();
  await expect(page.getByRole("row", {name: /Existing Warranty/})).toBeVisible();

  const uploadPath = testInfo.outputPath("phase1-browser-fixture.pdf");
  await writeFile(uploadPath, "%PDF-1.7\n% Phase 1 browser fixture\n%%EOF\n");
  await page.locator(".top-command input[type='file']").setInputFiles(uploadPath);
  await expect(page.getByRole("row", {name: /phase1-browser-fixture/})).toBeVisible();

  await page.getByRole("row", {name: /phase1-browser-fixture/}).click();
  await expect(page.locator(".inspector")).toContainText("phase1-browser-fixture");
  await expect(page.locator(".inspector")).toContainText("SHA-256");
  await expect(page).toHaveScreenshot("phase1-inbox.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.02,
  });

  await page.locator(".page-heading").getByRole("button", {name: "Open Viewer"}).click();
  await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
  await expect(page.locator(".rendered-page img")).toHaveAttribute(
    "src",
    `${apiOrigin}/api/v1/assets/33333333-3333-4333-8333-333333333333`,
  );
  await expect(page.getByRole("link", {name: "Download original"})).toHaveAttribute(
    "href",
    `${apiOrigin}/api/v1/assets/44444444-4444-4444-8444-444444444444`,
  );
  await expect(page).toHaveScreenshot("phase1-viewer.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.02,
  });

  await page.getByRole("button", {name: "Back to Inbox"}).click();
  await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();
});
