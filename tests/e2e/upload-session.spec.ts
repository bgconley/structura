import {expect, test, type Page} from "@playwright/test";
import {apiOrigin, csrfToken, mockStructuraApi} from "./support/structuraMock";
import {installUploadAttemptMock} from "./support/uploadAttemptMock";
import {uploadActor, uploadId} from "./support/uploadAttemptFixture";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Upload lifetime tests require controlled session/transfer outcomes.");
const content = {name: "private-original.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7\n% Original private bytes\n%%EOF")};
const picker = (page: Page) => page.locator(".top-command input[type=file]");
const queue = (page: Page) => page.getByRole("dialog", {name: "Upload files"});
function gate() { let release!: () => void; const promise = new Promise<void>((resolve) => {release = resolve;}); return {promise, release}; }
async function signOut(page: Page) {
  await queue(page).getByRole("button", {name: "Close uploads", exact: true}).click();
  await page.getByLabel("Account: Upload Reviewer").click();
  await page.getByRole("button", {name: "Sign out", exact: true}).click();
  await expect(page.getByRole("button", {name: "Sign in", exact: true})).toBeVisible();
}
async function signIn(page: Page) {
  await page.getByRole("textbox", {name: "Email"}).fill("upload@example.com");
  await page.getByLabel("Password").fill("correct-password");
  await page.getByRole("button", {name: "Sign in", exact: true}).click();
  await expect(page.getByLabel("Account: Upload Reviewer")).toBeVisible();
}
async function sessions(page: Page) {
  const state = {authenticated: true, actor: {...uploadActor}, generation: 1};
  await page.route(`${apiOrigin}/api/v1/auth/session`, async (route) => {
    const method = route.request().method();
    if (method === "DELETE") { state.authenticated = false; return route.fulfill({status: 204}); }
    if (method === "POST") { state.authenticated = true; state.generation++; }
    if (!state.authenticated) return route.fulfill({status: 401, json: {detail: "Not authenticated"}});
    await route.fulfill({status: method === "POST" ? 201 : 200, json: {...state.actor, sessionId: uploadId(900 + state.generation),
      isAuthenticated: true, displayName: "Upload Reviewer", email: "upload@example.com",
      sessionCookieName: "structura_session", csrfCookieName: "structura_csrf"}});
  });
  return state;
}
test.beforeEach(async ({page, context}) => {
  await context.addCookies([{name: "structura_session", value: "upload-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"}]);
  await mockStructuraApi(page);
});

test("same actor signs in again, explicitly checks and replaces an unfinished generation", async ({page}) => {
  await sessions(page);
  const state = await installUploadAttemptMock(page, {csrf: csrfToken});
  const pending = gate(); state.beforeContent = () => pending.promise;
  await page.goto("/inbox"); await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(content);
  await expect.poll(() => state.contents.length).toBe(1);
  const attempt = [...state.attempts.values()][0];
  const originalTransfer = attempt.currentTransferId, revision = attempt.revision;
  await signOut(page);
  expect(await page.evaluate(() => Object.values(sessionStorage).join(" "))).not.toContain(content.name);
  expect(state.cancelled).toHaveLength(0);
  await signIn(page);
  await page.getByRole("button", {name: "Uploads (1 need attention)", exact: true}).click();
  await expect(queue(page)).toContainText("Previous upload"); await expect(queue(page)).not.toContainText(content.name);
  await queue(page).getByRole("button", {name: "Check upload outcome", exact: true}).click();
  await expect(queue(page)).toContainText("Select the original file");
  expect(state.contents).toHaveLength(1);
  await queue(page).getByLabel("Select original file").setInputFiles(content);
  await expect(queue(page)).toContainText("Unfinished transfer needs an explicit replacement");
  expect(state.contents).toHaveLength(1);
  state.beforeContent = null;
  await queue(page).getByRole("button", {name: "Replace unfinished transfer", exact: true}).click();
  await expect(queue(page)).toContainText("Upload accepted");
  expect(state.contents[1]).toMatchObject({uploadId: attempt.uploadId, revision, replaced: originalTransfer});
  expect(state.contents[1].body).toEqual(content.buffer);
  expect(attempt.currentTransferId).not.toBe(originalTransfer);
  pending.release();
  await expect(queue(page).getByText("Upload accepted", {exact: true})).toHaveCount(1);
});

test("another actor sees no recovered names or receipts and cannot inherit a duplicate choice", async ({page}) => {
  const auth = await sessions(page);
  const state = await installUploadAttemptMock(page); state.duplicates = [{documentId: uploadId(600), title: "Private existing copy"}];
  await page.goto("/inbox"); await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(content);
  await expect(queue(page)).toContainText("Private existing copy");
  await signOut(page);
  auth.actor = {userId: uploadId(700), householdId: uploadId(701)};
  await signIn(page);
  await page.getByRole("button", {name: "Uploads (0)", exact: true}).click();
  await expect(queue(page)).not.toContainText(content.name); await expect(queue(page)).not.toContainText("Private existing copy");
  await expect(queue(page).getByRole("button", {name: "Check uncertain uploads", exact: true})).toBeDisabled();
  expect(state.contents).toHaveLength(1); expect(state.decisions).toHaveLength(0);
  await expect(queue(page).getByRole("article")).toHaveCount(0);
});

test("cancel all stops unsent registration and uses server cancellation for active transfers", async ({page}) => {
  const state = await installUploadAttemptMock(page);
  const pending = gate(); state.beforeContent = () => pending.promise;
  await page.goto("/inbox");
  await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(Array.from({length: 20}, (_, index) => ({...content, name: `cancel-${index}.pdf`})));
  await expect.poll(() => state.contents.length).toBe(2);
  await queue(page).getByRole("button", {name: "Cancel unaccepted uploads", exact: true}).click();
  await expect(queue(page)).toContainText("20 cancelled");
  expect(state.cancelled).toHaveLength(2); expect(state.registrations).toHaveLength(2); expect(state.contents).toHaveLength(2);
  pending.release();
  await expect(queue(page).getByText("Upload accepted", {exact: true})).toHaveCount(0);
});

test("acceptance winning cancellation remains an accepted immutable receipt", async ({page}) => {
  const state = await installUploadAttemptMock(page); state.acceptBeforeCancel = true;
  const pending = gate(); state.beforeContent = () => pending.promise;
  await page.goto("/inbox"); await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(content);
  await expect.poll(() => state.contents.length).toBe(1);
  await queue(page).getByRole("button", {name: "Cancel upload", exact: true}).click();
  await expect(queue(page)).toContainText("Upload accepted");
  await expect(queue(page).getByText("Upload cancelled", {exact: true})).toHaveCount(0);
  expect(state.cancelled).toHaveLength(1); expect(state.contents).toHaveLength(1);
  pending.release();
});

test("a lost cancellation response is unknown until the registered operation is read", async ({page}) => {
  const state = await installUploadAttemptMock(page);
  const pending = gate(); state.beforeContent = () => pending.promise;
  await page.route("**/api/v1/uploads/*", async (route) => {
    if (route.request().method() === "DELETE") return route.abort();
    await route.fallback();
  });
  await page.goto("/inbox"); await expect(picker(page)).toBeEnabled(); await picker(page).setInputFiles(content);
  await expect.poll(() => state.contents.length).toBe(1);
  await queue(page).getByRole("button", {name: "Cancel upload", exact: true}).click();
  await expect(queue(page)).toContainText("Upload outcome needs checking");
  await expect(queue(page).getByText("Upload cancelled", {exact: true})).toHaveCount(0);
  await queue(page).getByRole("button", {name: "Check upload outcome", exact: true}).click();
  await expect(queue(page)).toContainText("Unfinished transfer needs an explicit replacement");
  expect(state.contents).toHaveLength(1);
  pending.release();
});
