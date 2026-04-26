import {expect, test} from "@playwright/test";

import {csrfToken, mockStructuraApi} from "./support/structuraMock";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Mocked browser tests are local-only.");

test.beforeEach(async ({context, page}) => {
  await context.addCookies([
    {name: "structura_session", value: "phase6-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page);
});

test("Phase 6 automation workbench manages contacts, rules, watcher settings, and suggestions", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button", {name: /Automation/}).click();

  await expect(page.getByRole("heading", {name: "Automation Workbench"})).toBeVisible();
  await expect(page.getByRole("tab", {name: "Contacts"})).toBeVisible();
  await expect(page.getByRole("button", {name: /Acme Repairs/})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Duplicate contact suggestions"})).toBeVisible();

  await page.getByLabel("Contact search").fill("Aetna");
  await expect(page.getByRole("button", {name: /Aetna Health/})).toBeVisible();
  await page.getByRole("button", {name: /Aetna Health/}).click();
  await expect(page.getByText("payerId")).toBeVisible();
  await expect(page.getByText("Linked documents", {exact: true})).toBeVisible();

  await page.getByLabel("New contact name").fill("Delta Dental");
  await page.getByRole("button", {name: "Create contact"}).click();
  await expect(page.getByRole("button", {name: /Delta Dental/})).toBeVisible();

  await page.getByRole("tab", {name: "Rules"}).click();
  await page.getByLabel("Rule name").fill("Medical EOB filing");
  await page.getByLabel("Condition field").selectOption("document_family");
  await page.getByLabel("Condition operator").selectOption("eq");
  await page.getByLabel("Condition value").fill("medical_eob");
  await page.getByLabel("Action type").selectOption("add_tag");
  await page.getByLabel("Action value").fill("insurance");
  await page.getByRole("button", {name: "Save rule"}).click();
  const newRule = page.locator(".rule-row").filter({hasText: "Medical EOB filing"});
  await expect(newRule).toBeVisible();
  await newRule.getByRole("button", {name: /Dry run/}).click();
  await expect(page.getByText("Matched 1 document").first()).toBeVisible();
  await expect(page.getByLabel("Rule dry-run result").getByText("document_family eq medical_eob")).toBeVisible();
  await expect(page.getByLabel("Rule dry-run result").getByRole("heading", {name: "Proposed actions"})).toBeVisible();
  await expect(page.getByLabel("Rule dry-run result").getByRole("heading", {name: "Blocked actions"})).toBeVisible();

  await page.getByRole("tab", {name: "Suggestions"}).click();
  await expect(page.getByText("Suggested filing")).toBeVisible();
  await expect(page.getByRole("heading", {name: "Suggestion explanation"}).first()).toBeVisible();
  await page.locator(".suggestion-row").filter({hasText: "Anthem medical EOB"}).getByRole("button", {name: "Accept suggestion"}).click();
  await expect(page.getByText("Suggestion accepted")).toBeVisible();
  await page.locator(".suggestion-row").filter({hasText: "Aetna duplicate EOB"}).getByRole("button", {name: "Reject"}).click();
  await expect(page.getByText("Suggestion rejected")).toBeVisible();
  await page.locator(".suggestion-row").filter({hasText: "Deferred EOB follow-up"}).getByRole("button", {name: "Defer"}).click();
  await expect(page.getByText("Suggestion deferred")).toBeVisible();

  await page.getByRole("tab", {name: "Watched Folders"}).click();
  await expect(page.getByText("Allowed intake root")).toBeVisible();
  await expect(page.getByLabel("Recursive import")).toBeVisible();
  await page.getByLabel("Watch path").fill("/srv/structura/imports/incoming");
  await page.getByRole("button", {name: "Save watched folder"}).click();
  await expect(page.getByText("/srv/structura/imports/incoming", {exact: true})).toBeVisible();
  await expect(page.getByRole("button", {name: /Pause watcher/}).first()).toBeVisible();

  await page.setViewportSize({width: 390, height: 900});
  await expect(page.getByRole("heading", {name: "Automation Workbench"})).toBeVisible();

  await expect(page).toHaveScreenshot("phase6-automation-workbench.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.02,
  });
});
