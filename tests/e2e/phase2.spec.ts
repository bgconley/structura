import {expect, test} from "@playwright/test";

import {csrfToken, mockStructuraApi} from "./support/structuraMock";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Mocked browser tests are local-only.");

test.beforeEach(async ({context, page}) => {
  await context.addCookies([
    {name: "structura_session", value: "phase2-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page);
});

test("Phase 2 folder, tag, and manual filing workflow propagates to list and viewer", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();
  await expect(page.getByRole("treeitem", {name: /Home/})).toBeVisible();
  await expect(page.getByRole("treeitem", {name: /Needs Review/})).toBeDisabled();

  const folderForm = page
    .locator("form.quick-create")
    .filter({has: page.getByPlaceholder("New folder name")});
  await folderForm.getByPlaceholder("New folder name").fill("Claims");
  await folderForm.getByRole("button", {name: "Create"}).click();
  await expect(page.getByRole("treeitem", {name: /Claims/})).toBeVisible();

  const tagForm = page.locator("form.quick-create").filter({has: page.getByPlaceholder("New tag")});
  await tagForm.getByPlaceholder("New tag").fill("deductible");
  await tagForm.getByRole("button", {name: "Create"}).click();
  await expect(page.locator(".tag-cloud")).toContainText("deductible");

  await page.getByRole("row", {name: /Existing Warranty/}).click();
  const inspector = page.locator(".inspector");
  await expect(inspector.getByLabel("Title")).toHaveValue("Existing Warranty");
  await inspector.getByLabel("Title").fill("Filed Warranty Packet");
  await inspector.getByLabel("Document date").fill("2026-04-24");
  await inspector.getByLabel("Filing notes").fill("Phase 2 manual filing note.");
  await inspector.getByLabel("/Claims").check();
  await inspector.getByLabel("Primary folder Claims").check();
  await inspector.getByLabel("deductible").check();
  await inspector.getByRole("button", {name: "Save filing"}).click();

  await expect(page.getByRole("row", {name: /Filed Warranty Packet/})).toBeVisible();
  await expect(page.getByRole("row", {name: /Claims/})).toBeVisible();
  await expect(page.getByRole("row", {name: /deductible/})).toBeVisible();
  await expect(inspector).toContainText("Filed Warranty Packet");
  await expect(inspector).toContainText("Phase 2 manual filing note.");

  await page.getByRole("treeitem", {name: /Claims/}).click();
  await expect(page.getByRole("row", {name: /Filed Warranty Packet/})).toBeVisible();

  await page.locator(".page-heading").getByRole("button", {name: "Open Viewer"}).click();
  await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Filed Warranty Packet"})).toBeVisible();
  await expect(page.locator(".facts-panel")).toContainText("/Claims");
  await expect(page.locator(".facts-panel")).toContainText("deductible");
  await page.screenshot({path: testInfo.outputPath("phase2-filing-workflow.png"), fullPage: true});
});

test("Phase 2 filing surfaces remain reachable on mobile width", async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/");

  await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();
  await expect(page.locator(".organization-rail")).toBeVisible();
  await expect(page.getByPlaceholder("New folder name")).toBeVisible();

  await page.getByRole("row", {name: /Existing Warranty/}).click();
  await expect(page.locator(".inspector")).toContainText("Manual filing");
  await expect(page.locator(".inspector").getByLabel("Title")).toBeVisible();
});
