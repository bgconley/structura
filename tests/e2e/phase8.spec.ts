import {expect, test} from "@playwright/test";

import {csrfToken, mockStructuraApi} from "./support/structuraMock";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Mocked browser tests are local-only.");

test.beforeEach(async ({context, page}) => {
  await context.addCookies([
    {name: "structura_session", value: "phase8-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page);
});

test("Phase 8 difficult-document visual retrieval and review cues are visible", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button", {name: /Search/}).click();

  await page.getByLabel("Corpus search query").fill("handwritten degraded intake");
  await page.getByLabel("Search mode").selectOption("visual");
  await expect(page.getByText("Visual: On")).toBeVisible();
  await page.getByRole("button", {name: "Search corpus"}).click();

  await expect(page.locator(".search-result-card").filter({hasText: "Handwritten repair intake"})).toBeVisible();
  await expect(page.locator(".search-result-list")).toContainText("visual match");
  await expect(page.locator(".search-result-list")).toContainText("review uncertainty visible");

  await page
    .locator(".search-result-card")
    .filter({hasText: "Handwritten repair intake"})
    .getByRole("button", {name: "Jump to evidence"})
    .click();
  await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
  await expect(page.getByText("Difficult document")).toBeVisible();
  await expect(page.getByRole("note")).toContainText("handwriting detected");
  await expect(page.getByText("Visual retrieval eligible")).toBeVisible();

  await page.getByRole("button", {name: "R Review Queue"}).click();
  await expect(page.getByRole("heading", {name: "Review Queue"})).toBeVisible();
  await expect(page.getByText("document_quality")).toBeVisible();
  await expect(page.getByText("Difficult document requires review")).toBeVisible();

  await expect(page).toHaveScreenshot("phase8-difficult-documents.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.02,
  });
});
