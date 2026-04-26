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

test("Phase 4 review queue shows candidates, evidence, and correction actions", async ({page}) => {
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
