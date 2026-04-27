import {expect, test} from "@playwright/test";

import {csrfToken, mockStructuraApi} from "./support/structuraMock";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Mocked browser tests are local-only.");

test.beforeEach(async ({context, page}) => {
  await context.addCookies([
    {name: "structura_session", value: "phase7-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page);
});

test("Phase 7 relationships, timelines, deadlines, and smart views are actionable", async ({page}) => {
  await page.goto("/");

  await page.locator(".page-heading").getByRole("button", {name: "Open Viewer"}).click();
  await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Related Documents"})).toBeVisible();
  await expect(
    page.locator(".relationship-row").filter({hasText: "Acme repair receipt"}),
  ).toBeVisible();
  await page.locator(".relationship-row").filter({hasText: "Acme repair receipt"}).getByRole("button", {name: "Accept"}).click();
  await expect(page.getByText("Relationship accepted")).toBeVisible();

  await page.getByLabel("Related document").selectOption({label: "Acme repair receipt"});
  await expect(page.getByLabel("Relationship type")).toContainText("amendment to");
  await expect(page.getByLabel("Relationship type")).toContainText("proof of payment for");
  await page.getByLabel("Relationship type").selectOption("related_to");
  await page.getByLabel("Relationship note").fill("Manual packet link");
  await page.getByRole("button", {name: "Save relationship"}).click();
  await expect(page.getByText("Relationship saved")).toBeVisible();

  await page.getByRole("button", {name: /Relationships/}).click();
  await expect(page.getByRole("heading", {name: "Relationship Workbench"})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Open deadlines"})).toBeVisible();
  await expect(page.getByText("Relationship suggestions")).toBeVisible();

  await page.getByRole("button", {name: /Timelines/}).click();
  await expect(page.getByRole("heading", {name: "Document Timelines"})).toBeVisible();
  await expect(page.getByLabel("Timeline scope")).toBeVisible();
  await page.getByLabel("Timeline scope").selectOption("contact");
  await page.getByLabel("Timeline contact").selectOption({label: "Acme Repairs"});
  await page.getByLabel("Timeline scope").selectOption("document");
  await page.getByLabel("Timeline document").selectOption({label: "Existing Warranty"});
  await expect(page.getByText("warranty_expiration")).toBeVisible();

  await page.getByRole("button", {name: /Search/}).click();
  await page.getByLabel("Corpus search query").fill("warranty");
  await page.getByLabel("Relationship filter").selectOption("warranty_for");
  await page.getByLabel("Deadline filter").selectOption("warranty_expiration");
  await page.getByLabel("Has relationships").check();
  await page.getByLabel("Has open deadlines").check();
  await page.getByRole("button", {name: "Search corpus"}).click();
  await expect(page.locator(".facet-block").filter({hasText: "Relationships"})).toBeVisible();
  await expect(page.locator(".facet-block").filter({hasText: "Deadlines"})).toBeVisible();

  await expect(page).toHaveScreenshot("phase7-relationships-timeline.png", {
    fullPage: true,
    maxDiffPixelRatio: 0.02,
  });
});
