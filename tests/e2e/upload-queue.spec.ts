import {expect, test, type Page} from "@playwright/test";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {existingDocument, uploadedDocument} from "./support/structuraFixtures";
import {installUploadAttemptMock} from "./support/uploadAttemptMock";
import {uploadId} from "./support/uploadAttemptFixture";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Upload race cases use controlled registered-operation responses.");
test.beforeEach(async ({context, page}) => {
  await context.addCookies([{name: "structura_session", value: "upload-queue", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"}]);
  await mockStructuraApi(page);
});
const file = (name = "source.pdf") => ({name, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7\n% Original test bytes\n%%EOF\n")});
const picker = (page: Page) => page.locator(".top-command input[type=file]");

test("a20-file batch bounds actual transfers and preserves selected document through partial outcomes", async ({page}) => {
  const state = await installUploadAttemptMock(page, {csrf: csrfToken});
  let release!: () => void;
  const held = new Promise<void>((resolve) => {release = resolve;});
  let active = 0, maximum = 0;
  state.beforeContent = async (attempt) => {
    active++; maximum = Math.max(active, maximum); await held;
    if (state.metadata.get(attempt.operationId)?.filename === "source-19.pdf")
      Object.assign(attempt, {state: "rejected", error: {code: "upload_format_mismatch", message: "File signature and metadata disagree."}});
    active--;
  };
  await page.goto(`/inbox?document=${existingDocument.id}`);
  await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(Array.from({length: 20}, (_, index) => file(`source-${index}.pdf`)));
  const queue = page.getByRole("dialog", {name: "Upload files"});
  // A routed response does not emit browser upload progress; never invent 100%.
  await expect(queue.getByText("Sending bytes", {exact: true})).toHaveCount(2);
  await expect.poll(() => state.contents.length).toBe(2);
  expect(state.contents).toHaveLength(2); expect(maximum).toBe(2);
  await expect(queue).toContainText("18 queued");
  release();
  await expect(queue).toContainText("19 accepted"); await expect(queue).toContainText("1 rejected");
  expect(state.contents).toHaveLength(20); expect(maximum).toBeLessThanOrEqual(2);
  expect(new Set(state.registrations.map((item) => item.operationId)).size).toBe(20);
  await queue.getByRole("button", {name: "Close uploads", exact: true}).click();
  await expect(page).toHaveURL((url) => url.pathname === "/inbox" && url.searchParams.get("document") === existingDocument.id);
});

test("accepted receipt opens its exact document and does not redirect an active Viewer", async ({page}) => {
  await page.goto(`/documents/${existingDocument.id}`);
  await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(file());
  const queue = page.getByRole("dialog", {name: "Upload files"});
  await expect(queue).toContainText("Upload accepted");
  await expect(page).toHaveURL((url) => url.pathname === `/documents/${existingDocument.id}`);
  await queue.getByRole("button", {name: "Open document", exact: true}).click();
  await expect(page).toHaveURL((url) => url.pathname === "/inbox" && url.searchParams.get("document") === uploadedDocument.id);
  await expect(page.locator(".inspector")).toContainText(uploadedDocument.title);
});

test("exact duplicate choice is explicit and reuse creates no new processing receipt", async ({page}) => {
  const state = await installUploadAttemptMock(page); state.duplicates = [{documentId: existingDocument.id, title: existingDocument.title}];
  await page.goto("/inbox"); await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(file());
  const queue = page.getByRole("dialog", {name: "Upload files"});
  await expect(queue.getByRole("button", {name: "Use selected existing document", exact: true})).toBeDisabled();
  expect(state.decisions).toHaveLength(0);
  await queue.getByRole("radio", {name: existingDocument.title, exact: true}).check();
  await queue.getByRole("button", {name: "Use selected existing document", exact: true}).click();
  await expect(queue).toContainText("Existing document reused");
  await expect(queue).toContainText("No new processing job was created");
  expect(state.decisions[0]).toMatchObject({decision: "use_existing", documentId: existingDocument.id});
  expect([...state.attempts.values()][0].receipt?.jobId).toBeNull();
});

test("post-commit response loss is checked with GET and never resends accepted bytes", async ({page}) => {
  const state = await installUploadAttemptMock(page); state.loseContentResponse = true;
  await page.goto("/inbox"); await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(file());
  const queue = page.getByRole("dialog", {name: "Upload files"});
  await expect(queue).toContainText("Upload outcome needs checking");
  await queue.getByRole("button", {name: "Check upload outcome", exact: true}).click();
  await expect(queue).toContainText("Upload accepted"); expect(state.contents).toHaveLength(1);
  await expect(queue.getByRole("button", {name: "Check uncertain uploads", exact: true})).toBeDisabled();
  expect(state.contents).toHaveLength(1);
});

test("unknown registration survives refresh without names and refuses changed file metadata", async ({page}) => {
  const state = await installUploadAttemptMock(page); state.loseRegistrationResponse = true;
  await page.goto("/inbox"); await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(file("private-source.pdf"));
  await expect(page.getByRole("dialog", {name: "Upload files"})).toContainText("Upload outcome needs checking");
  const stored = await page.evaluate(() => Object.values(sessionStorage).join(" "));
  expect(stored).not.toContain("private-source"); expect(stored).not.toContain("application/pdf");
  await page.reload(); await page.getByRole("button", {name: "Uploads (1 need attention)", exact: true}).click();
  const queue = page.getByRole("dialog", {name: "Upload files"});
  await expect(queue).toContainText("Previous upload"); await expect(queue).not.toContainText("private-source");
  await queue.getByLabel("Select original file").setInputFiles(file("different.pdf"));
  await expect(queue).toContainText("does not match the previous upload");
  expect(state.registrations).toHaveLength(1);
  await queue.getByLabel("Select original file").setInputFiles(file("private-source.pdf"));
  state.loseRegistrationResponse = false;
  await queue.getByRole("button", {name: "Check upload outcome", exact: true}).click();
  await expect(queue).toContainText("Ready to send"); expect(state.contents).toHaveLength(0);
  await queue.getByRole("button", {name: "Send this file", exact: true}).click();
  await expect(queue).toContainText("Upload accepted");
  expect(new Set(state.registrations.map((item) => item.operationId)).size).toBe(1);
});

test("expired operation recovery is terminal and cannot silently allocate a replacement", async ({page}) => {
  const state = await installUploadAttemptMock(page); state.loseRegistrationResponse = true;
  await page.goto("/inbox"); await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(file());
  const queue = page.getByRole("dialog", {name: "Upload files"});
  await expect(queue).toContainText("Upload outcome needs checking");
  Object.assign([...state.attempts.values()][0], {state: "expired", revision: uploadId(999)}); state.loseRegistrationResponse = false;
  await queue.getByRole("button", {name: "Check upload outcome", exact: true}).click();
  await expect(queue).toContainText("Upload expired");
  await expect(queue.getByRole("button", {name: "Send this file", exact: true})).toHaveCount(0);
  expect(state.contents).toHaveLength(0); expect(state.attempts.size).toBe(1);
});

for (const width of [1440, 1280, 390]) test(`upload choices and keyboard close remain readable at${width}px`, async ({page}, testInfo) => {
  const state = await installUploadAttemptMock(page); state.duplicates = [{documentId: existingDocument.id, title: existingDocument.title}];
  await page.setViewportSize({width, height: 960}); await page.goto("/inbox");
  const trigger = page.getByRole("button", {name: width > 760 ? "Bulk Import" : "Uploads (0)", exact: true});
  await trigger.click();
  const queue = page.getByRole("dialog", {name: "Upload files"});
  await expect(queue.getByLabel("Choose files", {exact: true})).toBeEnabled();
  await queue.getByLabel("Choose files", {exact: true}).setInputFiles(file("Long filename with readable exact duplicate choices.pdf"));
  await expect(queue).toContainText("An exact copy is already recorded");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await queue.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  await queue.screenshot({path: testInfo.outputPath(`proposed-upload-queue-${width}-${process.platform}.png`)});
  const keep = queue.getByRole("button", {name: "Keep as a separate document", exact: true});
  await keep.focus(); await expect(keep).toBeFocused();
  const box = await keep.boundingBox(); expect(box!.y).toBeGreaterThanOrEqual(0); expect(box!.y + box!.height).toBeLessThanOrEqual(961);
  expect(box!.height).toBeGreaterThanOrEqual(width < 700 ? 40 : 32);
  await expect(keep).toBeEnabled();
  await queue.getByText("Previous uploads and recovery", {exact: true}).click();
  await expect(queue).toContainText("Use Check upload outcome to fetch the recorded state");
  await page.keyboard.press("Escape"); await expect(queue).not.toBeVisible();
  await expect(width > 760 ? trigger : page.locator(".upload-queue-trigger")).toBeFocused();
  await expect(page.locator(".upload-queue-trigger .upload-attention")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("a capacity response pauses untouched files across the queue and never repeats attempted content", async ({page}) => {
  const state = await installUploadAttemptMock(page); state.failContent = 429; state.retryAfter = "5";
  await page.clock.install();
  await page.goto("/inbox");
  await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(Array.from({length: 20}, (_, index) => file(`capacity-${index}.pdf`)));
  const queue = page.getByRole("dialog", {name: "Upload files"});
  await expect(queue).toContainText("queue is waiting for server capacity");
  await expect.poll(() => state.contents.length).toBe(2);
  await page.clock.runFor(4000);
  expect(state.registrations).toHaveLength(2); expect(state.contents).toHaveLength(2);
  await expect(queue).toContainText("18 queued");
  state.failContent = 0;
  await page.clock.runFor(1100);
  await expect(queue).toContainText("18 accepted");
  expect(state.registrations).toHaveLength(20); expect(state.contents).toHaveLength(20);
  const first = queue.getByRole("article", {name: "Upload capacity-0.pdf", exact: true});
  await first.getByRole("button", {name: "Check upload outcome", exact: true}).click();
  await expect(first).toContainText("Ready to send"); expect(state.contents).toHaveLength(20);
  await first.getByRole("button", {name: "Send this file", exact: true}).click();
  await expect(first).toContainText("Upload accepted"); expect(state.contents).toHaveLength(21);
});
