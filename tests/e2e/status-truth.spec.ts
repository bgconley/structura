import {expect, test} from "@playwright/test";
import {documentBrowseResponse} from "./support/documentBrowseMock";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {seededFolders} from "./support/structuraFixtures";
import {mockViewerFacts, viewerFactsData} from "./support/viewerFactsFixture";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Status semantics require controlled missing and declared review states.");
test.beforeEach(async ({context, page}) => {
  await context.addCookies([{name: "structura_session", value: "status-truth", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"}]);
  await mockStructuraApi(page);
});

const states = [
  ["unreviewed", "Unreviewed", "neutral"], ["needs_review", "Needs Review", "amber"],
  ["rejected", "Rejected", "rejected"], ["auto_accepted", "Auto accepted", "green"],
  ["user_confirmed", "User confirmed", "green"], ["user_corrected", "User corrected", "green"],
  ["future_review_state", "Review status unknown", "neutral"], ["", "Review status unknown", "neutral"],
] as const;

for (const [state, label, tone] of states) {
  test(`document review ${state || "missing"} is truthful in table, inspector and Viewer`, async ({page}) => {
    const data = viewerFactsData(); data.document.reviewStatus = state;
    await mockViewerFacts(page, data);
    await page.route(/\/api\/v1\/documents(?:\?.*)?$/, (route) => route.fulfill({json:
      documentBrowseResponse(new URL(route.request().url()).searchParams, [data.document], seededFolders())}));
    await page.goto(`/inbox?document=${data.document.id}`);
    const row = page.getByRole("row").filter({hasText: data.document.title});
    await expect(row.locator(".review-chip")).toHaveText(label);
    await expect(page.locator(".inspector .review-chip")).toHaveText(label);
    await expect(row.locator(".review-chip")).toHaveClass(`review-chip ${tone}`);
    const badge = await row.locator(".review-chip").boundingBox();
    const cell = await row.locator('[data-label="Review Status"]').boundingBox();
    expect(badge!.x + badge!.width).toBeLessThanOrEqual(cell!.x + cell!.width);
    await page.locator(".page-heading").getByRole("button", {name: "Open Viewer", exact: true}).click();
    await expect(page.locator(".facts-panel > .review-chip")).toHaveText(label);
    await expect(page.locator(".facts-panel > .review-chip")).toHaveClass(`review-chip ${tone}`);
    await expect(page.locator(".trust-line").filter({hasText: `Document review: ${label.toLowerCase()}`})).toBeVisible();
    // Document review status does not override independently selected field facts.
    await expect(page.getByRole("region", {name: "Recorded fields", exact: true})).toContainText("13 accepted of 14 recorded values");
  });
}

test("unknown runtime and absent extraction metadata never claim work or text sufficiency", async ({page}) => {
  const data = viewerFactsData(); data.document.extractions = [];
  data.document.counterpartyDisplay = undefined;
  data.document.qualitySummary = {reviewRequired: false, visualEmbeddingEligible: false};
  await mockViewerFacts(page, data);
  await page.goto(`/documents/${data.document.id}`);
  await expect(page.locator(".top-command .status-chip").filter({hasText: "Inference routing unreported"})).toHaveClass("status-chip neutral");
  await expect(page.getByText("No cloud inference", {exact: true})).toHaveCount(0);
  await expect(page.locator(".viewer-card-title .status-chip").filter({hasText: "No extraction recorded"})).toHaveClass("status-chip neutral");
  await expect(page.getByText("Extraction pending", {exact: true})).toHaveCount(0);
  await expect(page.locator(".facts-panel .fact-row").filter({hasText: "Counterparty"})).toContainText("Not recorded");
  const visual = page.locator(".trust-line").filter({hasText: "Visual indexing not indicated"});
  await expect(visual).toBeVisible();
  await expect(visual.locator(".ok")).toHaveCount(0);
  await expect(page.getByText("Text retrieval sufficient", {exact: true})).toHaveCount(0);
  for (const width of [1440, 1280, 390]) {
    await page.setViewportSize({width, height: 960});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});
