import {expect, test} from "@playwright/test";
import {writeFile} from "node:fs/promises";

const liveStackEnabled = process.env.STRUCTURA_E2E_LIVE === "1";
const email = process.env.STRUCTURA_E2E_EMAIL ?? "phase1-live@example.com";
const password = process.env.STRUCTURA_E2E_PASSWORD ?? "Phase1LivePass!2026";

test.describe("Phase 1 live Compose stack", () => {
  test.skip(!liveStackEnabled, "Set STRUCTURA_E2E_LIVE=1 to run against a live Compose stack.");

  test("logs in, uploads a document, and opens the viewer through the real API", async ({page}, testInfo) => {
    const title = `phase1-live-${Date.now()}`;
    const uploadPath = testInfo.outputPath(`${title}.pdf`);
    await writeFile(uploadPath, `%PDF-1.7\n% ${title}\n%%EOF\n`);

    await page.goto("/");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", {name: "Sign in"}).click();

    await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();

    await page.locator(".top-command input[type='file']").setInputFiles(uploadPath);
    await expect(page.getByRole("row", {name: new RegExp(title)})).toBeVisible();

    await page.getByRole("row", {name: new RegExp(title)}).click();
    await expect(page.locator(".inspector")).toContainText(title);
    await expect(page.locator(".inspector")).toContainText("SHA-256");

    await page.locator(".page-heading").getByRole("button", {name: "Open Viewer"}).click();
    await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
    await expect(page.getByRole("link", {name: "Download original"})).toHaveAttribute(
      "href",
      /\/api\/v1\/assets\//,
    );
  });
});
