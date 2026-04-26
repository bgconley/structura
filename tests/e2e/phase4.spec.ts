import {expect, test} from "@playwright/test";

import {csrfToken, mockStructuraApi} from "./support/structuraMock";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Mocked browser tests are local-only.");

test.beforeEach(async ({context, page}) => {
  await context.addCookies([
    {name: "structura_session", value: "phase4-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page);
});

test("Phase 4 review queue accepts a candidate", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button", {name: /Review Queue/}).click();

  await expect(page.getByRole("heading", {name: "Review Queue"})).toBeVisible();
  await expect(page.getByRole("button", {name: /invoice.total_amount/})).toBeVisible();
  await expect(page.locator(".candidate-panel")).toContainText("USD 1042.15");
  await expect(page.locator(".candidate-panel")).toContainText("evidence page 1");

  await page.getByRole("button", {name: "Accept candidate"}).click();
  await expect(page.locator(".review-status")).toContainText("Candidate accepted");
  await expect(page).toHaveScreenshot("phase4-review-queue.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.02,
  });
});

test("Phase 4 review queue corrects a field", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button", {name: /Review Queue/}).click();

  await page.getByLabel("Corrected value").fill("1042.20");
  await page.getByLabel("Correction note").fill("Corrected from statement total.");
  await page.getByRole("button", {name: "Correct field"}).click();

  await expect(page.locator(".review-status")).toContainText("Field corrected");
});

test("Phase 4 review queue rejects a field", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button", {name: /Review Queue/}).click();

  await page.getByLabel("Reject note").fill("Candidate does not match source.");
  await page.getByRole("button", {name: "Reject field"}).click();

  await expect(page.locator(".review-status")).toContainText("Field rejected");
});

test("Phase 4 review queue reclassifies a document", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button", {name: /Review Queue/}).click();

  await page.getByLabel("Document family").selectOption("receipt");
  await page.getByLabel("Reclassification note").fill("Receipt layout and total line match.");
  await page.getByRole("button", {name: "Reclassify"}).click();

  await expect(page.locator(".review-status")).toContainText("Document classification updated");
});

test("Phase 4 review queue jumps to evidence in the viewer", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button", {name: /Review Queue/}).click();

  await page.getByRole("button", {name: "Jump to evidence"}).click();

  await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
  await expect(page.getByRole("status")).toContainText("invoice.total_amount");
  await expect(page.getByLabel("Evidence highlight")).toBeVisible();
});
