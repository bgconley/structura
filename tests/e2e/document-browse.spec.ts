import {expect, test, type Page} from "@playwright/test";
import {parseAppRoute, routeUrl, type InboxRoute} from "../../apps/web/src/appRoutes";
import {browseRequestPath, documentSorts, inboxStates} from "../../apps/web/src/documentBrowse";
import {documentBrowseResponse, type BrowseFacts} from "./support/documentBrowseMock";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {existingDocument, seededDocuments, seededFolders, type DocumentDetail} from "./support/structuraFixtures";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Controlled browse regressions use a mock corpus.");
test.beforeEach(async ({context, page}) => {
  await context.addCookies([{name: "structura_session", value: "browse-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"}]);
  await mockStructuraApi(page);
});

async function corpus(page: Page, count = 207) {
  const base = seededDocuments().get(existingDocument.id)!;
  const documents: DocumentDetail[] = Array.from({length: count}, (_, index) => ({...structuredClone(base),
    id: `10000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    title: `Record ${String(index).padStart(3, "0")}`, family: "generic",
    createdAt: new Date(Date.UTC(2026, 7, 1, 0, 0, Math.floor(index / 3))).toISOString(),
    documentDate: index % 5 === 0 ? null : `2026-07-${String(index % 28 + 1).padStart(2, "0")}`,
    reviewStatus: index % 7 === 0 ? "needs_review" : "unreviewed",
    folderIds: index % 2 === 0 ? [] : [seededFolders()[0].id],
    folderPaths: index % 2 === 0 ? [] : ["/Home"], fields: [], lineItems: [], extractions: [], relationships: [],
  }));
  const facts = Object.fromEntries(documents.map((document, index) => [document.id, {
    awaiting_classification: index % 9 === 0, low_confidence: index % 11 === 0,
    duplicates: index % 13 === 0, has_extraction: index % 17 === 0, text_searchable: index % 3 === 0,
  } satisfies BrowseFacts]));
  const requests: URL[] = [];
  const state = {error: 0, delayState: "", wait: Promise.resolve(), documents, facts, requests};
  await page.route(/\/api\/v1\/documents(?:\?.*)?$/, async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const url = new URL(route.request().url()); requests.push(url);
    if (url.searchParams.get("inboxState") === state.delayState) await state.wait;
    if (state.error) return route.fulfill({status: state.error, json: {detail: "Document service unavailable"}});
    await route.fulfill({json: documentBrowseResponse(url.searchParams, documents, seededFolders(), facts)});
  });
  await page.route(/\/api\/v1\/documents\/[\da-f-]+$/, async (route) => {
    const id = new URL(route.request().url()).pathname.split("/").at(-1);
    const document = documents.find((item) => item.id === id);
    if (!document) return route.fallback();
    await route.fulfill({json: document});
  });
  return state;
}

const rows = (page: Page) => page.locator(".document-table tbody tr");

test("Inbox browse choices round-trip and reject ambiguous pagination before requesting data", () => {
  for (const state of inboxStates) for (const sort of documentSorts) {
    const route: InboxRoute = {view: "inbox", query: "A & B", folderId: existingDocument.id,
      documentId: existingDocument.id, inboxState: state.value, sort: sort.value, offset: 150, limit: 25};
    const parsed = parseAppRoute(routeUrl(route));
    expect(parsed.view).toBe("inbox");
    if (parsed.view !== "inbox") throw new Error("Inbox codec rejected a supported choice");
    expect(browseRequestPath(parsed)).toBe(browseRequestPath(route));
    expect(parsed.documentId).toBe(route.documentId);
  }
  for (const query of ["offset=-1", "offset=1.1", "offset=01", "offset=9007199254740992",
    "limit=0", "limit=201", "offset=1&offset=2", "state=imagined", "sort=relevance"]) {
    expect(parseAppRoute(`/inbox?${query}`).view).toBe("unavailable");
  }
});

test("all state chips request server membership and retain complete counts", async ({page}) => {
  const state = await corpus(page);
  await page.goto("/inbox");
  for (const filter of inboxStates) {
    await page.locator(`#inbox-state-${filter.value}`).click();
    const params = new URLSearchParams({inboxState: filter.value});
    const expected = documentBrowseResponse(params, state.documents, seededFolders(), state.facts);
    await expect(rows(page)).toHaveCount(expected.items.length);
    await expect.poll(async () => rows(page).evaluateAll((items) => items.map((row) => row.id.replace("document-row-", "")))).toEqual(expected.items.map((item) => item.id));
    await expect(page.locator(`#inbox-state-${filter.value}`)).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#inbox-state-all")).toHaveText("All 207");
    await expect(page.getByRole("navigation", {name: "Primary"}).getByRole("button", {name: /Inbox/}).locator("small")).toHaveText("207");
    expect(state.requests.at(-1)?.searchParams.get("inboxState") ?? "all").toBe(filter.value);
  }
});

test("page, sort, selected identity and Viewer return survive Back and refresh", async ({page}) => {
  const state = await corpus(page);
  await page.goto(`/inbox?document=${state.documents[0].id}`);
  await expect(page.locator(".selected-document-context")).toContainText("outside the current page");
  await page.getByRole("button", {name: "Next page", exact: true}).click();
  await expect(page).toHaveURL(/offset=50/);
  await expect(page.getByRole("navigation", {name: "Document pages"})).toContainText("51–100 of 207 documents");
  await rows(page).first().click();
  const selectedId = new URL(page.url()).searchParams.get("document")!;
  const title = state.documents.find((item) => item.id === selectedId)!.title;
  await expect(page.locator(".inspector")).toContainText(title);
  await page.locator(".page-heading").getByRole("button", {name: "Open Viewer", exact: true}).click();
  await page.getByRole("button", {name: "Back to Inbox", exact: true}).click();
  await expect(page).toHaveURL(/offset=50/);
  await expect(page.locator(`#document-row-${selectedId}`)).toHaveAttribute("aria-selected", "true");
  await page.reload();
  await expect(page.locator(`#document-row-${selectedId}`)).toHaveAttribute("aria-selected", "true");
  await page.getByRole("combobox", {name: "Sort documents", exact: true}).selectOption("title_asc");
  await expect(page).not.toHaveURL(/offset=/);
  await expect(page.locator(".selected-document-context")).toContainText(title);
  await page.goBack();
  await expect(page).toHaveURL(/offset=50/);
  await expect(page.getByRole("combobox", {name: "Sort documents", exact: true})).toHaveValue("uploaded_desc");
  await page.getByLabel("Documents per page").selectOption("25");
  await expect(rows(page)).toHaveCount(25);
  await expect(page).toHaveURL(/limit=25/);
  await expect(page).not.toHaveURL(/offset=/);
});

test("empty, failed and out-of-range pages keep constraints and offer explicit recovery", async ({page}) => {
  const state = await corpus(page);
  await page.goto(`/inbox?document=${state.documents[0].id}&offset=500`);
  await expect(page.getByRole("heading", {name: "This document page is unavailable"})).toBeVisible();
  await expect(rows(page)).toHaveCount(0);
  await page.getByRole("button", {name: "Open last page", exact: true}).click();
  await expect(rows(page)).toHaveCount(7);
  await expect(page).toHaveURL(/offset=200/);
  await page.getByRole("textbox", {name: "Search documents", exact: true}).fill("no-such-document");
  await expect(page.getByRole("heading", {name: "No matching documents", exact: true})).toBeVisible();
  await expect(page.locator(".selected-document-context")).toContainText(state.documents[0].title);
  await page.getByRole("button", {name: "Clear Inbox filters", exact: true}).click();
  await expect(rows(page)).toHaveCount(50);
  state.error = 403;
  await page.getByRole("button", {name: "Refresh documents", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Documents unavailable", exact: true})).toBeVisible();
  await expect(page.getByRole("heading", {name: "No matching documents", exact: true})).toHaveCount(0);
  await expect(page.locator("#inbox-state-all")).toHaveText("All —");
  await expect(rows(page)).toHaveCount(0);
  state.error = 0;
  await page.getByRole("button", {name: "Retry document list", exact: true}).click();
  await expect(rows(page)).toHaveCount(50);
  await page.goto("/inbox?offset=-1");
  await expect(page.getByRole("alert")).toContainText("invalid pagination");
});

test("a superseded filter response cannot replace newer rows or count explanations", async ({page}) => {
  const state = await corpus(page);
  let release!: () => void;
  state.delayState = "needs_review"; state.wait = new Promise<void>((resolve) => {release = resolve;});
  await page.goto("/inbox");
  await expect(rows(page)).toHaveCount(50);
  await page.locator("#inbox-state-needs_review").click();
  await expect.poll(() => state.requests.some((url) => url.searchParams.get("inboxState") === "needs_review")).toBe(true);
  await expect(rows(page)).toHaveCount(0);
  await expect(page.locator("#inbox-state-all")).toHaveText("All —");
  await page.locator("#inbox-state-unfiled").click();
  await expect(rows(page)).toHaveCount(50);
  const ids = await rows(page).evaluateAll((items) => items.map((row) => row.id));
  release();
  await page.waitForTimeout(150);
  await expect(page.locator("#inbox-state-unfiled")).toHaveAttribute("aria-pressed", "true");
  expect(await rows(page).evaluateAll((items) => items.map((row) => row.id))).toEqual(ids);
});

test("upload selects the returned document identity even when the title already exists", async ({page}) => {
  const state = await corpus(page);
  const uploaded = {...structuredClone(state.documents[0]), id: "ffffffff-ffff-4fff-8fff-ffffffffffff", createdAt: "2026-09-07T00:00:00Z"};
  await page.route(/\/api\/v1\/documents(?:\?.*)?$/, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    state.documents.push(uploaded);
    await route.fulfill({status: 202, json: {jobId: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", status: "queued", documentId: uploaded.id}});
  });
  await page.goto(`/inbox?document=${state.documents[0].id}&offset=200&state=unfiled`);
  await page.locator(".top-command input[type=file]").setInputFiles({name: "same-title.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7")});
  await expect(page).toHaveURL((url) => url.pathname === "/inbox" && url.search === `?document=${uploaded.id}`);
  await expect(page.locator(`#document-row-${uploaded.id}`)).toHaveAttribute("aria-selected", "true");
  await page.locator(".page-heading").getByRole("button", {name: "Open Viewer", exact: true}).click();
  await expect(page).toHaveURL((url) => url.pathname === `/documents/${uploaded.id}`);
});

test("a late accepted upload offers its exact document without replacing a newer browse query", async ({page}) => {
  const state = await corpus(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {release = resolve;});
  const uploaded = {...structuredClone(state.documents[0]), id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd"};
  await page.route(/\/api\/v1\/documents(?:\?.*)?$/, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await pending; state.documents.push(uploaded);
    await route.fulfill({status: 202, json: {jobId: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", status: "queued", documentId: uploaded.id}});
  });
  await page.goto(`/inbox?document=${state.documents[0].id}`);
  await expect(rows(page)).toHaveCount(50);
  await page.locator(".top-command input[type=file]").setInputFiles({name: "delayed.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7")});
  await page.getByRole("textbox", {name: "Search documents", exact: true}).fill("Record 010");
  release();
  await expect(page.getByRole("button", {name: "Open uploaded document", exact: true})).toBeVisible();
  await expect(page).toHaveURL(/q=Record\+010/);
  await expect(rows(page)).toHaveCount(1);
  await page.getByRole("button", {name: "Open uploaded document", exact: true}).click();
  await expect(page).toHaveURL((url) => url.pathname === "/inbox" && url.search === `?document=${uploaded.id}`);
  await expect(page.locator(".inspector")).toContainText(uploaded.title);
});

test("a failed late upload is visible outside Inbox and the same file can be retried", async ({page}) => {
  const state = await corpus(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {release = resolve;});
  let attempts = 0;
  await page.route(/\/api\/v1\/documents(?:\?.*)?$/, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    attempts += 1;
    if (attempts === 1) {
      await pending;
      return route.fulfill({status: 503, json: {detail: "Storage temporarily unavailable"}});
    }
    await route.fulfill({status: 202, json: {jobId: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
      status: "queued", documentId: state.documents[0].id}});
  });
  await page.goto(`/documents/${state.documents[0].id}`);
  await expect(page.getByRole("button", {name: "Back to Inbox", exact: true})).toBeVisible();
  const upload = page.locator(".top-command input[type=file]");
  const file = {name: "retry.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7")};
  await upload.setInputFiles(file);
  await expect.poll(() => attempts).toBe(1);
  await page.getByRole("navigation", {name: "Primary"}).getByRole("button", {name: "Search", exact: true}).click();
  await expect(page).toHaveURL(/\/search\?submitted=false$/);
  release();
  await expect(page.getByRole("alert")).toContainText("Upload failed. Storage temporarily unavailable");
  await expect(page).toHaveURL(/\/search\?submitted=false$/);
  await expect(upload).toBeEnabled();
  await expect(upload).toHaveValue("");
  await expect(page.getByRole("button", {name: "Open uploaded document", exact: true})).toHaveCount(0);
  await upload.setInputFiles(file);
  await expect.poll(() => attempts).toBe(2);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page).toHaveURL((url) => url.pathname === "/inbox" && url.search === `?document=${state.documents[0].id}`);
});

for (const width of [1440, 1280, 390]) test(`browse controls and keyboard pagination fit ${width}px`, async ({page}, testInfo) => {
  await page.setViewportSize({width, height: 960});
  await corpus(page);
  await page.goto("/inbox");
  await expect(rows(page)).toHaveCount(50);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const next = page.getByRole("button", {name: "Next page", exact: true});
  await next.focus(); await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/offset=50/);
  const box = await next.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(32);
  expect(box?.height).toBeGreaterThanOrEqual(width === 390 ? 40 : 32);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({path: testInfo.outputPath(`proposed-browse-${width}.png`)});
});
