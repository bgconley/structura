import {expect, test} from "@playwright/test";

const liveStackEnabled = process.env.STRUCTURA_E2E_LIVE === "1";
const email = process.env.STRUCTURA_E2E_EMAIL ?? "phase1-live@example.com";
const password = process.env.STRUCTURA_E2E_PASSWORD ?? "Phase1LivePass!2026";

test.describe("Phase 6 live GPU stack", () => {
  test.skip(!liveStackEnabled, "Set STRUCTURA_E2E_LIVE=1 to run against the GPU stack.");

  test("uses automation workbench contacts rules dry-run and watched-folder settings", async ({page}, testInfo) => {
    test.setTimeout(120_000);
    const unique = Date.now().toString();

    await page.goto("/");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", {name: "Sign in"}).click();
    await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();

    await page.getByRole("button", {name: /Automation/}).click();
    await expect(page.getByRole("heading", {name: "Automation Workbench"})).toBeVisible();

    await page.getByLabel("New contact name").fill(`Phase6 Contact ${unique}`);
    await page.getByRole("button", {name: "Create contact"}).click();
    await expect(page.getByRole("button", {name: new RegExp(`Phase6 Contact ${unique}`)})).toBeVisible();

    await page.getByRole("tab", {name: "Rules"}).click();
    await page.getByLabel("Rule name").fill(`Phase6 Rule ${unique}`);
    await page.getByLabel("Condition value").fill("generic");
    await page.getByLabel("Action tag").fill("urgent");
    await page.getByRole("button", {name: "Save rule"}).click();
    const ruleRow = page.locator(".rule-row").filter({hasText: `Phase6 Rule ${unique}`});
    await expect(ruleRow).toBeVisible();
    await ruleRow.getByRole("button", {name: /Dry run/}).click();
    await expect(page.getByLabel("Rule dry-run result").getByText(/Matched \d+ document/)).toBeVisible();

    await page.getByRole("tab", {name: "Watched Folders"}).click();
    await page.getByLabel("Watch path").fill("/srv/structura/imports");
    await page.getByRole("button", {name: "Save watched folder"}).click();
    await expect(page.getByText("/srv/structura/imports")).toBeVisible();

    await page.screenshot({path: testInfo.outputPath("phase6-live-automation.png"), fullPage: true});
  });
});
