import {expect, test} from "@playwright/test";
import {recordedValue} from "../../apps/web/src/recordedFactValues";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {existingDocument, receiptDocument, seededDocuments} from "./support/structuraFixtures";
import {mockViewerFacts, viewerFactsData} from "./support/viewerFactsFixture";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Complete facts use controlled persisted-read fixtures.");
test.beforeEach(async ({context, page}) => {
  await context.addCookies([{name: "structura_session", value: "viewer-facts", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"}]);
  await mockStructuraApi(page);
});

test("all recorded fields remain reachable with authority status, exact values and evidence", async ({page}) => {
  const {document} = await mockViewerFacts(page);
  await page.goto(`/documents/${document.id}`);
  const facts = page.getByRole("region", {name: "Recorded facts and line items", exact: true});
  await expect(facts).toContainText("13 accepted of 14 recorded values");
  await expect(facts).not.toContainText("untrusted.detail.only");
  await expect(facts).toContainText("Jan 26, 2026");
  await expect(facts).toContainText('"cleared": null');
  await expect(facts).toContainText("False");
  await expect(facts).toContainText("-12.3400");
  await expect(facts).toContainText("JPY 0.0000");
  await expect(facts).toContainText("2026-09-07T10:11:12.123456-04:00");
  await expect(facts).toContainText("9,223,372,036,854,775,807");
  await expect(facts.locator("article").filter({hasText: "invoice.field_07"})).toContainText("Rejected; excluded");
  await expect(facts).toContainText("invoice.deleted_value · position 2");
  await facts.getByRole("navigation", {name: "recorded fields pages"}).getByRole("button", {name: "Next"}).click();
  await expect(facts).toContainText("11–14 of 14 recorded fields");
  await expect(facts).toContainText("EUR 99,999,999,999,999.9999");
  await facts.getByRole("button", {name: "Evidence for invoice.field_14, position 1, page 3"}).click();
  await expect(page).toHaveURL(/page=3/);
  await expect(page.locator(".evidence-focus")).toContainText("Source for field 14");
  await expect(page.locator(".evidence-highlight")).toHaveCount(0);
});

for (const family of ["invoice", "medical_eob"]) {
  test(`${family} exposes all 25 canonical rows without deriving missing amounts`, async ({page}) => {
    const data = viewerFactsData(); data.document.family = family;
    await mockViewerFacts(page, data);
    await page.goto(`/documents/${data.document.id}`);
    await page.getByRole("tab", {name: "Line items (25)"}).click();
    const rows = page.getByRole("region", {name: "Canonical line items", exact: true});
    if (family === "medical_eob") await expect(rows).toContainText("Missing amounts are not inferred");
    const first = rows.locator("article").first();
    await expect(first).toContainText("EUR 99,999,999,999,999.9999");
    await expect(first).toContainText("EUR -12.3400");
    await expect(first).toContainText("EUR 0.0000");
    await expect(first).toContainText("1.2345");
    await expect(first).toContainText("TaxNot recorded");
    await expect(first).toContainText("Code systemCPT");
    const pager = rows.getByRole("navigation", {name: "line items pages"});
    await pager.getByLabel("Page").selectOption({label: "3"});
    await expect(rows).toContainText("21–25 of 25 line items");
    await expect(rows.locator("article")).toHaveCount(5);
    await expect(rows.locator("article").last()).toContainText("Removed from accepted lines");
    await rows.getByRole("button", {name: "Evidence for line_items.service_line.24, page 3"}).click();
    await expect(page).toHaveURL(/page=3/);
    await expect(page.locator(".evidence-focus")).toContainText("Source for service 24");
    await expect(page.locator(".evidence-highlight")).toHaveCount(0);
    await expect(page.getByRole("tab", {name: "Line items (25)"})).toHaveAttribute("aria-selected", "true");
    await expect(rows).toContainText("21–25 of 25 line items");
  });
}

test("invalid field authority blocks acceptance claims while independent line items stay available", async ({page}) => {
  const data = await mockViewerFacts(page);
  await page.route("**/api/v1/documents/*/canonical-fields", (route) => route.fulfill({json: {items: data.fields}}));
  await page.goto(`/documents/${data.document.id}`);
  await expect(page.getByRole("alert")).toContainText("Field decision history is unavailable");
  await expect(page.locator(".viewer-recorded-fields")).toHaveCount(0);
  await page.getByRole("tab", {name: "Line items (25)"}).click();
  await expect(page.getByRole("region", {name: "Canonical line items"})).toContainText("Selected by human decision");
});

test("unestablished fields and missing evidence stay explicit, and a failed refresh clears old claims", async ({page}) => {
  const data = viewerFactsData();
  data.fields[0].evidence = [];
  data.authority.projection = {...data.authority.projection, state: "unestablished", acceptedFactRevision: 0,
    projectionRevision: 0, acceptedFactsSha256: null, indexedMetadataSha256: null};
  await mockViewerFacts(page, data);
  await page.goto(`/documents/${data.document.id}`);
  const facts = page.getByRole("region", {name: "Recorded fields", exact: true});
  await expect(facts).toContainText("0 accepted of 14 recorded values");
  await expect(facts).toContainText("Accepted facts have not been verified");
  await expect(facts.locator("article").first()).toContainText("No concrete evidence locator");
  await expect(facts.locator("article").first().getByRole("button", {name: /Evidence/})).toHaveCount(0);
  await page.route("**/api/v1/documents/*/canonical-fields", (route) => route.fulfill({status: 403,
    json: {detail: "Permission denied"}}));
  await page.getByRole("button", {name: "Refresh fields", exact: true}).click();
  await expect(page.getByRole("alert")).toContainText("Permission denied");
  await expect(facts).toHaveCount(0);
});

test("evidence keeps the exact repeated field position reachable after navigation", async ({page}) => {
  const data = viewerFactsData();
  data.fields[0].fieldPath = "invoice.repeated";
  data.fields[13].fieldPath = "invoice.repeated"; data.fields[13].ordinal = 14;
  await mockViewerFacts(page, data);
  await page.goto(`/documents/${data.document.id}`);
  const facts = page.getByRole("region", {name: "Recorded fields", exact: true});
  await facts.getByRole("button", {name: "Next", exact: true}).click();
  await facts.getByRole("button", {name: "Evidence for invoice.repeated, position 14, page 3"}).click();
  await expect(page).toHaveURL(/page=3/);
  await expect(facts).toContainText("11–14 of 14 recorded fields");
  await expect(facts).toContainText("invoice.repeated · position 14");
});

test("line items bound to another document cannot be displayed", async ({page}) => {
  const data = viewerFactsData(); data.lines[0].documentId = receiptDocument.id;
  await mockViewerFacts(page, data);
  await page.goto(`/documents/${data.document.id}`);
  await page.getByRole("tab", {name: "Line items", exact: true}).click();
  await expect(page.getByRole("alert")).toContainText("Line-item authority is unavailable or inconsistent");
  await expect(page.locator(".viewer-line-items article")).toHaveCount(0);
});

test("missing original and hash metadata produce truthful Viewer trust states", async ({page}) => {
  const data = viewerFactsData(); data.document.assets = [];
  await mockViewerFacts(page, data);
  await page.goto(`/documents/${data.document.id}`);
  await expect(page.locator(".trust-line").filter({hasText: "Original asset unavailable"})).toBeVisible();
  await expect(page.locator(".trust-line").filter({hasText: "SHA-256 not recorded"})).toBeVisible();
  await expect(page.locator(".trust-line").filter({hasText: "Document review: needs review"})).toBeVisible();
  await expect(page.getByText("The protected original is available.", {exact: false})).toHaveCount(0);
  data.document.assets = [{id: "original", assetRole: "original", mimeType: "application/pdf", assetUrl: "/api/v1/assets/original"}];
  await page.reload();
  await expect(page.locator(".trust-line").filter({hasText: "Original asset recorded"})).toBeVisible();
  await expect(page.locator(".trust-line").filter({hasText: "SHA-256 not recorded"})).toBeVisible();
});

test("a late authority response cannot place another document's fields in Viewer", async ({page}) => {
  await mockViewerFacts(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {release = resolve;});
  await page.route(`**/api/v1/documents/${existingDocument.id}/canonical-fields`, async (route) => {
    await pending; await route.fulfill({json: viewerFactsData().authority});
  });
  await page.goto(`/documents/${existingDocument.id}`);
  await expect(page.getByText("Loading field decisions…")).toBeVisible();
  await page.getByRole("navigation", {name: "Primary"}).getByRole("button", {name: /Inbox/}).click();
  await page.getByRole("row").filter({hasText: receiptDocument.title}).click();
  await page.getByRole("button", {name: "Open Viewer", exact: true}).click();
  release();
  await expect(page.locator(".viewer-card-title h2")).toHaveText(seededDocuments().get(receiptDocument.id)!.title);
  await expect(page.locator(".viewer-recorded-fields")).not.toContainText("invoice.field_14");
});

for (const width of [1440, 1280, 390]) {
  test(`recorded fact navigation is keyboard accessible without page overflow at ${width}px`, async ({page}, testInfo) => {
    const {document} = await mockViewerFacts(page);
    await page.setViewportSize({width, height: 960});
    await page.goto(`/documents/${document.id}`);
    const tab = page.getByRole("tab", {name: "Fields", exact: true});
    await tab.focus(); await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", {name: "Line items (25)"})).toBeFocused();
    await expect(page.getByRole("tab", {name: "Line items (25)"})).toHaveAttribute("aria-selected", "true");
    const rows = page.getByRole("region", {name: "Canonical line items", exact: true});
    await rows.getByRole("navigation", {name: "line items pages"}).getByRole("button", {name: "Next"}).click();
    await expect(rows.getByRole("list", {name: "line items", exact: true})).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole("region", {name: "Recorded facts and line items", exact: true}).screenshot({path: testInfo.outputPath(`proposed-viewer-line-items-${width}-${process.platform}.png`)});
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path: testInfo.outputPath(`proposed-viewer-overview-${width}-${process.platform}.png`)});
  });
}

test("exact display formatting keeps typed JSON null and never invents a currency", () => {
  expect(recordedValue(null, "json")).toBe("null");
  expect(recordedValue("0.0000", "money")).toBe("Currency unspecified 0.0000");
  expect(recordedValue("99999999999999.9999", "number")).toBe("99,999,999,999,999.9999");
  expect(recordedValue("9223372036854775807", "integer")).toBe("9,223,372,036,854,775,807");
  expect(recordedValue("2026-02-30", "date")).toBe("2026-02-30");
});
