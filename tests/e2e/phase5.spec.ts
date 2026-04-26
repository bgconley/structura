import {expect, test} from "@playwright/test";

import {csrfToken, mockStructuraApi} from "./support/structuraMock";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Mocked browser tests are local-only.");

test.beforeEach(async ({context, page}) => {
  await context.addCookies([
    {name: "structura_session", value: "phase5-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page);
});

test("Phase 5 search runs hybrid retrieval with filters, snippets, explanations, and evidence jump", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button", {name: /Search/}).click();

  await expect(page.getByRole("heading", {name: "Corpus Search"})).toBeVisible();
  await expect(page.getByText("Why these results")).toBeVisible();

  await page.getByLabel("Corpus search query").fill("claim ABC123 where I may still owe money");
  await page.getByLabel("Search mode").selectOption("hybrid");
  await page.getByLabel("Document family filter").selectOption("medical_eob");
  await expect(page.getByText("Family: medical_eob")).toBeVisible();
  await page.getByRole("button", {name: "Search corpus"}).click();

  await expect(page.getByRole("button", {name: /Anthem medical EOB/})).toBeVisible();
  await expect(page.locator(".search-result-list")).toContainText("Claim ABC123");
  await expect(page.locator(".search-result-list")).toContainText("matched by lexical rank");
  await expect(page.getByText("medical_eob: 1")).toBeVisible();
  await expect(page).toHaveScreenshot("phase5-corpus-search.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.02,
  });

  await page.getByRole("button", {name: "Save search"}).click();
  await expect(page.getByText(/Saved search:/)).toBeVisible();

  await page
    .locator(".search-result-card")
    .filter({hasText: "Anthem medical EOB"})
    .getByRole("button", {name: "Jump to evidence"})
    .click();
  await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Claim ABC123");
  await expect(page.getByLabel("Evidence highlight")).toBeVisible();
});

test("Phase 5 search preserves filters in an actionable empty state", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button", {name: /Search/}).click();

  await page.getByLabel("Corpus search query").fill("no matching phase5 fixture");
  await page.getByLabel("Document family filter").selectOption("warranty");
  await page.getByRole("button", {name: "Search corpus"}).click();

  await expect(page.getByText("No matching documents")).toBeVisible();
  await expect(page.getByText("Active filters: warranty")).toBeVisible();
});
