import {expect, test} from "@playwright/test";

import {writeSimplePdf} from "./support/pdf";

const liveStackEnabled = process.env.STRUCTURA_E2E_LIVE === "1";
const email = process.env.STRUCTURA_E2E_EMAIL ?? "phase1-live@example.com";
const password = process.env.STRUCTURA_E2E_PASSWORD ?? "Phase1LivePass!2026";

test.describe("Phase 2 live GPU stack", () => {
  test.skip(!liveStackEnabled, "Set STRUCTURA_E2E_LIVE=1 to run against the GPU stack.");

  test("files a document with folders and tags through the real web/API/DB stack", async ({
    page,
  }, testInfo) => {
    const unique = Date.now().toString();
    const sourceTitle = `phase2-live-${unique}`;
    const filedTitle = `Filed Live ${unique}`;
    const folderName = `Live Claims ${unique}`;
    const tagName = `live-tag-${unique}`;
    const uploadPath = testInfo.outputPath(`${sourceTitle}.pdf`);
    await writeSimplePdf(uploadPath, [sourceTitle, "Phase 2 live filing smoke document."]);

    await page.goto("/");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", {name: "Sign in"}).click();
    await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();

    const folderForm = page
      .locator("form.quick-create")
      .filter({has: page.getByPlaceholder("New folder name")});
    await folderForm.getByPlaceholder("New folder name").fill(folderName);
    await folderForm.getByRole("button", {name: "Create"}).click();
    await expect(page.getByRole("treeitem", {name: new RegExp(folderName)})).toBeVisible();

    const tagForm = page.locator("form.quick-create").filter({has: page.getByPlaceholder("New tag")});
    await tagForm.getByPlaceholder("New tag").fill(tagName);
    await tagForm.getByRole("button", {name: "Create"}).click();
    await expect(page.locator(".tag-cloud")).toContainText(tagName);

    await page.locator(".top-command input[type='file']").setInputFiles(uploadPath);
    await expect(page.getByRole("row", {name: new RegExp(sourceTitle)})).toBeVisible();

    await page.getByRole("row", {name: new RegExp(sourceTitle)}).click();
    const inspector = page.locator(".inspector");
    await expect(inspector.getByLabel("Title")).toHaveValue(sourceTitle);
    await inspector.getByLabel("Title").fill(filedTitle);
    await inspector.getByLabel("Document date").fill("2026-04-24");
    await inspector.getByLabel("Filing notes").fill("Live GPU Phase 2 manual filing.");
    await inspector.getByLabel(`/${folderName}`).check();
    await inspector.getByLabel(`Primary folder ${folderName}`).check();
    await inspector.getByLabel(tagName).check();
    await inspector.getByRole("button", {name: "Save filing"}).click();

    await expect(page.getByRole("row", {name: new RegExp(filedTitle)})).toBeVisible();
    await expect(page.getByRole("row", {name: new RegExp(folderName)})).toBeVisible();
    await expect(page.getByRole("row", {name: new RegExp(tagName)})).toBeVisible();

    await page.getByRole("treeitem", {name: new RegExp(folderName)}).click();
    await expect(page.getByRole("row", {name: new RegExp(filedTitle)})).toBeVisible();

    await page.locator(".page-heading").getByRole("button", {name: "Open Viewer"}).click();
    await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
    await expect(page.getByRole("heading", {name: filedTitle})).toBeVisible();
    await expect(page.locator(".facts-panel")).toContainText(`/${folderName}`);
    await expect(page.locator(".facts-panel")).toContainText(tagName);
    await page.screenshot({path: testInfo.outputPath("phase2-live-gpu-workflow.png"), fullPage: true});
  });
});
