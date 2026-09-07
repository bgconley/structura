import {expect, test, type Page} from "@playwright/test";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {existingDocument} from "./support/structuraFixtures";
import {installUploadAttemptMock} from "./support/uploadAttemptMock";
import {uploadId} from "./support/uploadAttemptFixture";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Intake boundary cases need controlled policy and outcomes.");
const source = {name: "source.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7\n%%EOF")};
const picker = (page: Page) => page.locator(".top-command input[type=file]");
const queue = (page: Page) => page.getByRole("dialog", {name: "Upload files"});
test.beforeEach(async ({page, context}) => {
  await context.addCookies([{name: "structura_session", value: "intake", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"}]);
  await mockStructuraApi(page);
});

test("an explicit unavailable policy prevents registration and raw transfer", async ({page}) => {
  const state = await installUploadAttemptMock(page); state.policy.available = false;
  await page.goto("/inbox");
  await expect(picker(page)).toBeDisabled();
  await page.getByRole("button", {name: "Bulk Import", exact: true}).click();
  await expect(queue(page)).toContainText("New uploads are currently unavailable");
  await expect(queue(page).getByLabel("Choose files", {exact: true})).toBeDisabled();
  expect(state.registrations).toHaveLength(0); expect(state.contents).toHaveLength(0);
});

test("empty, oversized and queue overflow files do not consume registered operations", async ({page}) => {
  const state = await installUploadAttemptMock(page); state.policy.maxFileBytes = 20; state.policy.actorReservedBytes = 19; state.policy.globalReservedBytes = 18; state.policy.queueReferenceLimit = 3;
  await page.goto("/inbox");
  await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles([{...source, name: "empty.pdf", buffer: Buffer.alloc(0)},
    {...source, name: "too-large.pdf", buffer: Buffer.alloc(21)}, source, {...source, name: "not-queued.pdf"}]);
  await expect(queue(page)).toContainText("Max 18 bytes per file");
  await expect(queue(page)).toContainText("PDF, PNG, JPEG, TIFF, WebP");
  await expect(queue(page)).toContainText("This file is empty");
  await expect(queue(page)).toContainText("exceeds the configured upload");
  await expect(queue(page)).toContainText("1 files were not added");
  await expect(queue(page)).toContainText("1 accepted");
  expect(state.registrations).toHaveLength(1); expect(state.contents[0].body).toEqual(source.buffer);
  expect(state.registrations[0]).toMatchObject({filename: "source.pdf", source: "web_upload", title: "source"});
  await expect(picker(page)).toHaveValue("");
});

test("offline queued files wait for connection without speculative mutations", async ({page}) => {
  const state = await installUploadAttemptMock(page);
  await page.goto("/inbox"); await expect(picker(page)).toBeEnabled();
  await page.evaluate(() => { Object.defineProperty(navigator, "onLine", {configurable: true, value: false}); window.dispatchEvent(new Event("offline")); });
  await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(source);
  await expect(queue(page)).toContainText("You appear to be offline");
  await expect(queue(page)).toContainText("1 queued"); expect(state.registrations).toHaveLength(0);
  await page.evaluate(() => { Object.defineProperty(navigator, "onLine", {configurable: true, value: true}); window.dispatchEvent(new Event("online")); });
  await expect(queue(page)).toContainText("Upload accepted"); expect(state.contents).toHaveLength(1);
});

test("drop intake preserves per-file bytes and records a distinct operation in the same batch", async ({page}) => {
  const state = await installUploadAttemptMock(page);
  await page.goto("/inbox"); await page.getByRole("button", {name: "Bulk Import", exact: true}).click();
  await expect(queue(page).getByLabel("Choose files", {exact: true})).toBeEnabled();
  await queue(page).getByRole("region", {name: "Add files to upload"}).evaluate((element) => {
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(new File(["%PDF-1.7\nFirst"], "first.pdf", {type: "application/pdf"}));
    dataTransfer.items.add(new File(["%PDF-1.7\nSecond"], "second.pdf", {type: "application/pdf"}));
    element.dispatchEvent(new DragEvent("drop", {dataTransfer, bubbles: true, cancelable: true}));
  });
  await expect(queue(page)).toContainText("2 accepted");
  expect(new Set(state.registrations.map((item) => item.clientBatchId)).size).toBe(1);
  expect(new Set(state.registrations.map((item) => item.operationId)).size).toBe(2);
  expect(state.registrations.map((item) => item.source)).toEqual(["bulk_import", "bulk_import"]);
  expect(state.contents.map((item) => item.body.toString())).toEqual(["%PDF-1.7\nFirst", "%PDF-1.7\nSecond"]);
});

test("keeping a duplicate separately requires the exact explicit held decision", async ({page}) => {
  const state = await installUploadAttemptMock(page); state.duplicates = [{documentId: existingDocument.id, title: existingDocument.title}];
  await page.goto("/inbox"); await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(source);
  await expect(queue(page)).toContainText("An exact copy is already recorded");
  const revision = [...state.attempts.values()][0].revision;
  await queue(page).getByRole("button", {name: "Keep as a separate document", exact: true}).click();
  await expect(queue(page)).toContainText("Upload accepted");
  expect(state.decisions).toEqual([{revision, decision: "keep_separate"}]);
  expect([...state.attempts.values()][0].receipt?.documentId).not.toBe(existingDocument.id);
  expect(state.contents).toHaveLength(1);
});

test("a stale duplicate choice is discarded and a refreshed revision needs a fresh choice", async ({page}) => {
  const state = await installUploadAttemptMock(page); state.duplicates = [{documentId: existingDocument.id, title: existingDocument.title}];
  await page.goto("/inbox"); await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(source);
  await queue(page).getByRole("radio", {name: existingDocument.title, exact: true}).check();
  [...state.attempts.values()][0].revision = uploadId(990);
  await queue(page).getByRole("button", {name: "Use selected existing document", exact: true}).click();
  await expect(queue(page)).toContainText("Upload outcome needs checking");
  await queue(page).getByRole("button", {name: "Check upload outcome", exact: true}).click();
  await expect(queue(page).getByRole("button", {name: "Use selected existing document", exact: true})).toBeDisabled();
  await expect(queue(page).getByRole("radio", {name: existingDocument.title, exact: true})).not.toBeChecked();
  expect(state.decisions).toHaveLength(1); expect(state.contents).toHaveLength(1);
});

test("a failed content admission is checked and explicitly retried under the same operation", async ({page}) => {
  const state = await installUploadAttemptMock(page); state.failContent = 503;
  await page.goto("/inbox"); await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(source);
  await expect(queue(page)).toContainText("Upload outcome needs checking");
  state.failContent = 0;
  await queue(page).getByRole("button", {name: "Check upload outcome", exact: true}).click();
  await expect(queue(page)).toContainText("Ready to send"); expect(state.contents).toHaveLength(1);
  await queue(page).getByRole("button", {name: "Send this file", exact: true}).click();
  await expect(queue(page)).toContainText("Upload accepted");
  expect(state.registrations).toHaveLength(1); expect(state.contents).toHaveLength(2);
  expect(state.contents[1].uploadId).toBe(state.contents[0].uploadId);
});
