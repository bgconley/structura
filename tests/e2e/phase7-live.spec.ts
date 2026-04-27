import {expect, test} from "@playwright/test";
import {writeFile} from "node:fs/promises";

const liveStackEnabled = process.env.STRUCTURA_E2E_LIVE === "1";
const email = process.env.STRUCTURA_E2E_EMAIL ?? "phase1-live@example.com";
const password = process.env.STRUCTURA_E2E_PASSWORD ?? "Phase1LivePass!2026";

test.describe("Phase 7 live GPU stack", () => {
  test.skip(!liveStackEnabled, "Set STRUCTURA_E2E_LIVE=1 to run against the GPU stack.");

  test("creates a manual relationship and opens the relationship timeline workspace", async ({page}, testInfo) => {
    test.setTimeout(120_000);
    const unique = Date.now().toString();
    const firstTitle = `phase7-live-warranty-${unique}`;
    const secondTitle = `phase7-live-receipt-${unique}`;
    const firstPath = testInfo.outputPath(`${firstTitle}.pdf`);
    const secondPath = testInfo.outputPath(`${secondTitle}.pdf`);
    await writeFile(firstPath, `%PDF-1.7\n% ${firstTitle}\n%%EOF\n`);
    await writeFile(secondPath, `%PDF-1.7\n% ${secondTitle}\n%%EOF\n`);

    await page.goto("/");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", {name: "Sign in"}).click();
    await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();

    await page.locator(".top-command input[type='file']").setInputFiles(firstPath);
    await expect(page.getByRole("row", {name: new RegExp(firstTitle)})).toBeVisible();
    await page.locator(".top-command input[type='file']").setInputFiles(secondPath);
    await expect(page.getByRole("row", {name: new RegExp(secondTitle)})).toBeVisible();

    await page.getByRole("row", {name: new RegExp(firstTitle)}).click();
    await page.locator(".page-heading").getByRole("button", {name: "Open Viewer"}).click();
    await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
    await page.getByLabel("Related document").selectOption({label: secondTitle});
    await page.getByLabel("Relationship type").selectOption("warranty_for");
    await page.getByLabel("Relationship note").fill(`Phase 7 live link ${unique}`);
    await page.getByRole("button", {name: "Save relationship"}).click();
    await expect(page.getByText("Relationship saved")).toBeVisible();
    await expect(page.getByText(secondTitle)).toBeVisible();

    await page.getByRole("button", {name: /Relationships/}).click();
    await expect(page.getByRole("heading", {name: "Relationship Workbench"})).toBeVisible();
    await expect(page.getByText(secondTitle)).toBeVisible();
    await page.getByRole("button", {name: /Timelines/}).click();
    await expect(page.getByRole("heading", {name: "Document Timelines"})).toBeVisible();
    await expect(page.getByText("warranty_for")).toBeVisible();

    await page.screenshot({path: testInfo.outputPath("phase7-live-relationships.png"), fullPage: true});
  });
});
