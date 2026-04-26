import {expect, test} from "@playwright/test";

const liveStackEnabled = process.env.STRUCTURA_E2E_LIVE === "1";
const email = process.env.STRUCTURA_E2E_EMAIL ?? "phase1-live@example.com";
const password = process.env.STRUCTURA_E2E_PASSWORD ?? "Phase1LivePass!2026";

test.describe("Phase 4 live GPU stack", () => {
  test.skip(!liveStackEnabled, "Set STRUCTURA_E2E_LIVE=1 to run against the GPU stack.");

  test("opens the live review queue through the real web/API/DB stack", async ({
    page,
  }, testInfo) => {
    await page.goto("/");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", {name: "Sign in"}).click();
    await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();

    await page.getByRole("button", {name: /Review Queue/}).click();
    await expect(page.getByRole("heading", {name: "Review Queue"})).toBeVisible();
    await expect(page.locator(".review-task-list")).toBeVisible();
    await expect(page.locator(".candidate-panel")).toBeVisible();
    await page.screenshot({path: testInfo.outputPath("phase4-live-review-queue.png"), fullPage: true});
  });
});
