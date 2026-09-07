import {expect, test} from "@playwright/test";
import {parseAppRoute, routeUrl, type AppRoute} from "../../apps/web/src/appRoutes";
import {defaultSearchFilterState} from "../../apps/web/src/searchFilters";
import {apiOrigin, csrfToken, mockStructuraApi} from "./support/structuraMock";
import {existingDocument, receiptDocument, seededDocuments, seededReviewTasks} from "./support/structuraFixtures";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Controlled navigation regressions use mocked responses.");

test("current routes round-trip every submitted filter and reject unsafe or ambiguous links", () => {
  const search: AppRoute = {view: "search", query: "A & B / invoice", submitted: true, filters: {
    ...defaultSearchFilterState, mode: "visual", family: "invoice", folderId: existingDocument.id,
    tag: "tax & home", reviewStatus: "needs_review", sensitivity: "financial", relationshipType: "related_to",
    hasRelationships: true, deadlineType: "due_date", hasOpenDeadlines: true, includeVisual: true,
    reviewedOnly: true, dateFrom: "2024-02-29", dateTo: "2026-09-07", amountMin: "0", amountMax: "42.5",
  }};
  expect(parseAppRoute(routeUrl(search))).toEqual(search);
  const viewer: AppRoute = {view: "viewer", documentId: existingDocument.id, page: 2, returnTo: routeUrl(search)};
  expect(parseAppRoute(routeUrl(viewer))).toEqual(viewer);
  for (const path of ["/unknown", "/documents/not-uuid", `/documents/${existingDocument.id}?page=0`,
    `/documents/${existingDocument.id}?page=1.5`, `/documents/${existingDocument.id}?page=9007199254740992`,
    `/documents/${existingDocument.id}?returnTo=https://example.com`,
    `/documents/${existingDocument.id}?returnTo=${encodeURIComponent(`/documents/${receiptDocument.id}`)}`,
    "/inbox?document=", "/review?task=wrong", "/search?q=x&q=y", "/search?includeVisual=maybe",
    "/search?amountMin=1,234", "/search?dateFrom=2026-02-30", "/search?dateFrom=2026-09-07&dateTo=2024-01-01",
    "/search?sensitivity=anything", "/search?mode=unknown", "//example.com/inbox"]) {
    expect(parseAppRoute(path).view, path).toBe("unavailable");
  }
});

test.beforeEach(async ({context, page}) => {
  await context.addCookies([
    {name: "structura_session", value: "route-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page);
});

test("search return, browser forward and refresh preserve submitted criteria and source page", async ({page}) => {
  await page.goto("/search?q=handwritten&mode=visual&includeVisual=true&hasRelationships=true&deadlineType=due_date&hasOpenDeadlines=true&amountMin=0");
  const result = page.locator(".search-result-card").filter({hasText: "Handwritten repair intake"});
  await expect(result).toBeVisible();
  await page.getByLabel("Corpus search query").fill("unsubmitted draft");
  await expect(page.locator(".explanation")).toContainText("query = handwritten");
  await expect(page.locator(".explanation")).not.toContainText("unsubmitted draft");
  await result.getByRole("button", {name: "Jump to evidence"}).click();
  await expect(page).toHaveURL(new RegExp(`/documents/${receiptDocument.id}\\?page=1`));
  await page.getByRole("button", {name: "Back to Search", exact: true}).click();
  await expect(page.getByLabel("Corpus search query")).toHaveValue("handwritten");
  await expect(page.getByLabel("Search mode")).toHaveValue("visual");
  await expect(page.getByLabel("Has relationships")).toBeChecked();
  await expect(result).toBeVisible();
  await page.goForward();
  await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", {name: receiptDocument.title, exact: true})).toBeVisible();
  await expect(page.locator(".rendered-page img")).toHaveAttribute("alt", `Preview of ${receiptDocument.title} page 1`);
  await expect(page.locator(".evidence-focus")).toHaveCount(0);
});

for (const status of [403, 404]) {
  test(`direct document ${status} never displays a different inbox document`, async ({page}) => {
    await page.route(`**/api/v1/documents/${receiptDocument.id}`, (route) => route.fulfill({status, json: {detail: "Not found"}}));
    await page.goto(`/documents/${receiptDocument.id}?page=1`);
    await expect(page.getByRole("alert")).toContainText("unavailable or you no longer have access");
    await expect(page.getByRole("heading", {name: existingDocument.title, exact: true})).toHaveCount(0);
    await expect(page.locator(".rendered-page")).toHaveCount(0);
  });
}

test("valid document with an absent page reports the requested page without showing page one", async ({page}) => {
  await page.goto(`/documents/${existingDocument.id}?page=99`);
  await expect(page.getByRole("alert")).toHaveText("Page 99 is not available in this document.Open page 1");
  await expect(page.locator(".rendered-page img, .rendered-page iframe")).toHaveCount(0);
  await page.getByRole("button", {name: "Open page 1", exact: true}).click();
  await expect(page).toHaveURL(new RegExp("page=1$"));
  await expect(page.locator(".rendered-page img")).toBeVisible();
});

test("a late document response cannot replace the document opened next", async ({page}) => {
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => {release = resolve;});
  let started = false;
  await page.route(`**/api/v1/documents/${receiptDocument.id}`, async (route) => {
    started = true; await delayed;
    await route.fulfill({json: seededDocuments().get(receiptDocument.id)});
  });
  await page.goto(`/documents/${receiptDocument.id}`);
  await expect.poll(() => started).toBe(true);
  await page.getByRole("navigation", {name: "Primary"}).getByRole("button", {name: /Inbox/}).click();
  await page.getByRole("button", {name: "Open Viewer", exact: true}).click();
  await expect(page.locator(".viewer-card-title h2")).toHaveText(existingDocument.title);
  release();
  await page.waitForTimeout(150);
  await expect(page.locator(".viewer-card-title h2")).toHaveText(existingDocument.title);
  await expect(page).toHaveURL(new RegExp(existingDocument.id));
});

test("exact review link loads a task outside the backlog and preserves it through Viewer return", async ({page}) => {
  const task = {...seededReviewTasks()[0], id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", rationale: "Exact task beyond page one"};
  await page.route(`**/api/v1/review-tasks/${task.id}`, (route) => route.fulfill({json: task}));
  await page.goto(`/review?task=${task.id}`);
  await expect(page.getByRole("button", {name: "Correct field", exact: true})).toBeEnabled();
  await expect(page.getByRole("button", {name: /Exact task beyond page one/})).toHaveClass("selected");
  await page.getByRole("button", {name: "Open document", exact: true}).click();
  await page.getByRole("button", {name: "Back to Review Queue", exact: true}).click();
  await expect(page).toHaveURL(new RegExp(`task=${task.id}`));
  await expect(page.getByRole("button", {name: /Exact task beyond page one/})).toHaveClass("selected");
});

test("missing or completed exact tasks never permit fallback decisions", async ({page}) => {
  const task = {...seededReviewTasks()[0], status: "resolved"};
  await page.route(`**/api/v1/review-tasks/${task.id}`, (route) => route.fulfill({json: task}));
  await page.goto(`/review?task=${task.id}`);
  await expect(page.getByText("This task is resolved.", {exact: false})).toBeVisible();
  await expect(page.getByRole("button", {name: "Correct field", exact: true})).toBeDisabled();
  await page.goto("/review?task=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
  await expect(page.getByRole("alert")).toContainText("review task is unavailable");
  await expect(page.getByRole("button", {name: "Accept candidate", exact: true})).toHaveCount(0);
});

test("document-context review requests a filtered backlog", async ({page}) => {
  const request = page.waitForRequest((req) => req.url().includes("/review-tasks?") && req.url().includes(`documentId=${receiptDocument.id}`));
  await page.goto(`/documents/${receiptDocument.id}`);
  await page.getByRole("button", {name: "Open review", exact: true}).click();
  await request;
  await expect(page).toHaveURL(new RegExp(`document=${receiptDocument.id}`));
  await expect(page.locator(".review-task-list")).not.toContainText("invoice.total_amount");
});

test("unknown app links have an explicit recovery instead of rendering Inbox under the wrong URL", async ({page}) => {
  await page.goto("/this-page-does-not-exist");
  await expect(page.getByRole("heading", {name: "Page unavailable"})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Document Operations"})).toHaveCount(0);
  await page.getByRole("button", {name: "Open Inbox", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();
});

test("out-of-order list and search requests retain the latest query's identity", async ({page}) => {
  let releaseList!: () => void;
  let releaseSearch!: () => void;
  const waitList = new Promise<void>((resolve) => {releaseList = resolve;});
  const waitSearch = new Promise<void>((resolve) => {releaseSearch = resolve;});
  let oldListStarted = false;
  let oldSearchStarted = false;
  await page.route("**/api/v1/documents?*", async (route) => {
    const query = new URL(route.request().url()).searchParams.get("q");
    if (query === "older") {oldListStarted = true; await waitList;}
    await route.fulfill({json: {items: [query === "older" ? existingDocument : receiptDocument], total: 1}});
  });
  await page.route("**/api/v1/search", async (route) => {
    const payload = route.request().postDataJSON();
    if (payload.query === "older") {oldSearchStarted = true; await waitSearch;}
    await route.fulfill({json: {items: [{documentId: receiptDocument.id, title: `${payload.query} result`, rank: 1}]}});
  });
  await page.goto("/inbox");
  const global = page.getByPlaceholder("Search receipts, EOBs, warranties, claims, taxes...");
  await global.fill("older");
  await expect.poll(() => oldListStarted).toBe(true);
  await global.fill("newer");
  await expect(page.locator(".document-panel tbody")).toContainText(receiptDocument.title);
  releaseList();
  await page.waitForTimeout(100);
  await expect(page.locator(".document-panel tbody")).not.toContainText(existingDocument.title);
  await global.fill("older");
  await global.press("Enter");
  await expect.poll(() => oldSearchStarted).toBe(true);
  await global.fill("newer");
  await global.press("Enter");
  await expect(page.locator(".search-result-list")).toContainText("newer result");
  releaseSearch();
  await page.waitForTimeout(100);
  await expect(page.locator(".search-result-list")).not.toContainText("older result");
  await expect(page.locator(".explanation")).toContainText("query = newer");
});

test("late parse diagnostics and filing saves cannot publish under another selected document", async ({page}) => {
  let release!: () => void;
  const wait = new Promise<void>((resolve) => {release = resolve;});
  let parseStarted = false;
  let saveStarted = false;
  await page.route(`**/api/v1/documents/${receiptDocument.id}/parse-debug`, async (route) => {
    parseStarted = true; await wait;
    await route.fulfill({json: {document: {id: receiptDocument.id}, artifacts: [], pages: [{pageNumber: 1, textPreview: "PRIVATE OLD PARSE"}], elements: [], tables: [], chunks: [], jobs: []}});
  });
  await page.route(`**/api/v1/documents/${receiptDocument.id}/organization`, async (route) => {
    if (route.request().method() === "OPTIONS") return route.fallback();
    saveStarted = true; await wait;
    await route.fulfill({json: {...seededDocuments().get(receiptDocument.id), title: "PRIVATE OLD SAVE"}});
  });
  await page.goto(`/documents/${receiptDocument.id}`);
  await page.locator(".parse-debug-panel").getByRole("button", {name: "Load", exact: true}).click();
  await page.getByRole("button", {name: "Save filing", exact: true}).click();
  await expect.poll(() => parseStarted && saveStarted).toBe(true);
  await page.getByRole("navigation", {name: "Primary"}).getByRole("button", {name: /Inbox/}).click();
  await page.getByRole("button", {name: "Open Viewer", exact: true}).click();
  await expect(page.locator(".viewer-card-title h2")).toHaveText(existingDocument.title);
  release();
  await page.waitForTimeout(100);
  await expect(page.locator(".viewer-card-title h2")).toHaveText(existingDocument.title);
  await expect(page.getByText("PRIVATE OLD PARSE")).toHaveCount(0);
  await expect(page.getByText("PRIVATE OLD SAVE")).toHaveCount(0);
});

test("sign-in retains an authorized document deep link and its selected page", async ({page}) => {
  let authenticated = false;
  const headers = {"Access-Control-Allow-Origin": "http://localhost:4173", "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Headers": "accept,content-type,x-csrf-token", "Access-Control-Allow-Methods": "GET,POST,OPTIONS"};
  await page.route(`${apiOrigin}/api/v1/auth/session`, async (route) => {
    if (route.request().method() === "OPTIONS") return route.fulfill({status: 204, headers});
    if (route.request().method() === "POST") authenticated = true;
    await route.fulfill(authenticated ? {status: 201, headers, json: {displayName: "Route Reviewer", email: "route@example.com",
      isAuthenticated: true, csrfCookieName: "structura_csrf", sessionCookieName: "structura_session"}}
      : {status: 401, headers, json: {detail: "Not authenticated"}});
  });
  const document = seededDocuments().get(existingDocument.id)!;
  await page.route(`**/api/v1/documents/${existingDocument.id}`, (route) => route.fulfill({json: {
    ...document, pages: [...document.pages, {...document.pages[0], pageNumber: 2}],
  }}));
  await page.goto(`/documents/${existingDocument.id}?page=2`);
  await page.getByRole("textbox", {name: "Email"}).fill("route@example.com");
  await page.getByLabel("Password").fill("minimum8");
  await page.getByRole("button", {name: "Sign in", exact: true}).click();
  await expect(page.locator(".rendered-page img")).toHaveAttribute("alt", `Preview of ${existingDocument.title} page 2`);
  await expect(page).toHaveURL(new RegExp("page=2$"));
});

test("keyboard-selected Inbox document and focus survive Viewer back", async ({page}, info) => {
  await page.goto("/inbox");
  const row = page.locator(`#document-row-${receiptDocument.id}`);
  await row.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".inspector h2")).toHaveText(receiptDocument.title);
  const open = page.getByRole("button", {name: "Open Viewer", exact: true});
  await open.click();
  await page.getByRole("button", {name: "Back to Inbox", exact: true}).click();
  await expect(open).toBeFocused();
  await expect(row).toHaveAttribute("aria-selected", "true");
  await page.screenshot({path: info.outputPath("route-inbox-return.png"), fullPage: true});
});
