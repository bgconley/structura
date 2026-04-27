import {expect, test} from "@playwright/test";

import {writeSimplePdf} from "./support/pdf";

const liveStackEnabled = process.env.STRUCTURA_E2E_LIVE === "1";
const email = process.env.STRUCTURA_E2E_EMAIL ?? "phase1-live@example.com";
const password = process.env.STRUCTURA_E2E_PASSWORD ?? "Phase1LivePass!2026";

test.describe("Phase 8 live GPU stack", () => {
  test.skip(!liveStackEnabled, "Set STRUCTURA_E2E_LIVE=1 to run against the GPU stack.");

  test("uploads a handwriting-signal document and retrieves it with visual search", async ({page}, testInfo) => {
    test.setTimeout(180_000);
    const unique = Date.now().toString();
    const title = `phase8-live-handwritten-${unique}`;
    const filePath = testInfo.outputPath(`${title}.pdf`);
    await writeSimplePdf(filePath, [
      `${title}`,
      "This handwritten degraded intake note is intentionally sparse for Phase 8 visual retrieval.",
      "The content says handwriting so deterministic quality detection flags it for review.",
    ]);

    await page.goto("/");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", {name: "Sign in"}).click();
    await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();

    await page.locator(".top-command input[type='file']").setInputFiles(filePath);
    await expect(page.getByRole("row", {name: new RegExp(title)})).toBeVisible();

    await page.getByRole("button", {name: /Search/}).click();
    await page.getByLabel("Corpus search query").fill(`handwritten degraded ${unique}`);
    await page.getByLabel("Search mode").selectOption("visual");

    const result = page.locator(".search-result-card").filter({hasText: title});
    for (let attempt = 0; attempt < 10; attempt += 1) {
      await page.getByRole("button", {name: "Search corpus"}).click();
      if (await result.isVisible({timeout: 2_000}).catch(() => false)) {
        break;
      }
      await page.waitForTimeout(5_000);
    }
    await expect(result).toBeVisible();
    await expect(result).toContainText("visual");
    await result.getByRole("button", {name: "Jump to evidence"}).click();
    await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
    await expect(page.getByText("Difficult document")).toBeVisible();

    await page.screenshot({path: testInfo.outputPath("phase8-live-difficult-documents.png"), fullPage: true});
  });
});
