import {expect, test} from "@playwright/test";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {installLineReviewMock, lineHistoryEntry, lineId} from "./support/lineItemAuthorityMock";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Line review uses controlled candidate/authority versions.");
test.beforeEach(async ({context, page}) => {
  await context.addCookies([{name: "structura_session", value: "line-review", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"}]);
  await mockStructuraApi(page);
});

test("explicit add displays every exact EOB amount and does not depend on field authority", async ({page}) => {
  const state = await installLineReviewMock(page);
  await page.route("**/api/v1/documents/*/canonical-fields", (route) => route.fulfill({json: {items: []}}));
  await page.goto(`/review?task=${state.tasks[0].id}`);
  const panel = page.getByRole("region", {name: "Line-item review", exact: true});
  await expect(panel).toContainText("BilledEUR 99,999,999,999,999.9999");
  await expect(panel).toContainText("AllowedEUR 220.1234");
  await expect(panel).toContainText("Plan paidEUR 100.1134");
  await expect(panel).toContainText("Patient responsibilityEUR 120.0100");
  await expect(panel).toContainText("EUR 0.0000"); await expect(panel).toContainText("EUR -12.3400");
  await panel.getByRole("button", {name: "Add as a separate line", exact: true}).click();
  await expect(panel.getByRole("region", {name: "Review line decision"})).toContainText("recorded line 26");
  expect(state.requests).toHaveLength(0);
  await panel.getByLabel("Decision comment").fill("I checked all four EOB amounts");
  await panel.getByRole("button", {name: "Add this line", exact: true}).click();
  await expect(panel).toContainText("Line decision saved");
  expect(state.requests).toHaveLength(1);
  expect(state.requests[0]).toMatchObject({operation: "create", target: {ordinal: 26, canonicalLineItemId: null},
    source: {candidateId: state.candidates[0].id, expectedCandidateDecisionRevision: null}, comment: "I checked all four EOB amounts"});
  await expect(panel).toContainText("Selected as recorded line 26");
  await expect(panel.getByRole("button", {name: "Add as a separate line", exact: true})).toHaveCount(0);
  await panel.getByRole("button", {name: "Open selected recorded line", exact: true}).click();
  await expect(page.getByRole("tab", {name: "Line items (26)", exact: true})).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("region", {name: "Canonical line items", exact: true})).toContainText("21–26 of 26 line items");
});

test("replacement chooses a recognizable row beyond page one; rejecting another same-ordinal proposal leaves it selected", async ({page}) => {
  const state = await installLineReviewMock(page);
  await page.goto(`/review?task=${state.tasks[0].id}`);
  await page.getByRole("button", {name: "Replace a recorded line…", exact: true}).click();
  await page.getByRole("navigation", {name: "replacement targets pages"}).getByLabel("Page").selectOption("3");
  await page.getByRole("button", {name: "Review replacement of line 25", exact: true}).click();
  await expect(page.getByRole("region", {name: "Current recorded value"})).toContainText("Recorded service 25");
  await expect(page.getByRole("region", {name: "Proposed replacement value"})).toContainText("Office evaluation");
  await page.getByRole("button", {name: "Save replacement", exact: true}).click();
  await expect(page.getByRole("region", {name: "Line-item review"})).toContainText("Line decision saved");
  const accepted = structuredClone(state.authority.items[24]);
  await page.getByRole("button", {name: /Aggregate alternative/}).click();
  await page.getByRole("button", {name: "Reject this proposal", exact: true}).click();
  await page.getByRole("button", {name: "Confirm proposal rejection", exact: true}).click();
  await expect(page.getByRole("region", {name: "Line-item review"})).toContainText("Line decision saved");
  expect(state.authority.items[24]).toEqual(accepted);
  expect(state.requests.map((item) => item.operation)).toEqual(["replace", "reject_candidate"]);
});

test("conflict preserves the comment and prior target without silently refreshing save authority", async ({page}) => {
  const state = await installLineReviewMock(page); state.failSave = 409;
  await page.goto(`/review?task=${state.tasks[0].id}`);
  await page.getByRole("button", {name: "Add as a separate line", exact: true}).click();
  await page.getByLabel("Decision comment").fill("Keep this review note");
  await page.getByRole("button", {name: "Add this line", exact: true}).click();
  await expect(page.getByRole("region", {name: "Line-item review"}).getByRole("alert")).toContainText("Your comment is preserved");
  state.failSave = 0; state.candidates[0].description = "New source value after conflict";
  await page.getByRole("button", {name: "Reload line details", exact: true}).click();
  await expect(page.getByLabel("Decision comment")).toHaveValue("Keep this review note");
  await expect(page.getByRole("button", {name: "Add this line", exact: true})).toBeDisabled();
  await expect(page.getByRole("region", {name: "Line-item review"})).toContainText("New source value after conflict");
  expect(state.requests).toHaveLength(1);
  await page.getByRole("button", {name: "Add as a separate line", exact: true}).click();
  await page.getByRole("button", {name: "Add this line", exact: true}).click();
  await expect(page.getByRole("region", {name: "Line-item review"})).toContainText("Line decision saved");
  expect(state.requests).toHaveLength(2);
});

test("unconfirmed response reconciles the committed source assignment before another save", async ({page}) => {
  const state = await installLineReviewMock(page); state.loseResponse = true;
  await page.goto(`/review?task=${state.tasks[0].id}`);
  await page.getByRole("button", {name: "Add as a separate line", exact: true}).click();
  await page.getByRole("button", {name: "Add this line", exact: true}).click();
  await expect(page.getByRole("region", {name: "Line-item review"})).toContainText("The save could not be confirmed");
  state.loseResponse = false;
  await page.getByRole("button", {name: "Reload line details", exact: true}).click();
  await expect(page.getByRole("region", {name: "Line-item review"})).toContainText("Selected as recorded line 26");
  await expect(page.getByRole("button", {name: "Add as a separate line", exact: true})).toHaveCount(0);
  await page.getByRole("button", {name: "Decision history", exact: true}).click();
  await page.getByRole("region", {name: "Line decision history"}).locator("summary").click();
  await expect(page.getByRole("region", {name: "After this decision"})).toContainText("EUR 220.1234");
  expect(state.requests).toHaveLength(1);
});

test("a confirmed save followed by read failure is reported as saved and never reposted", async ({page}) => {
  const state = await installLineReviewMock(page);
  await page.goto(`/review?task=${state.tasks[0].id}`);
  await page.getByRole("button", {name: "Add as a separate line", exact: true}).click();
  state.failRead = true;
  await page.getByRole("button", {name: "Add this line", exact: true}).click();
  await expect(page.getByRole("region", {name: "Line-item review"})).toContainText("Saved; latest details could not be loaded");
  await expect(page.getByRole("button", {name: "Add this line", exact: true})).toHaveCount(0);
  expect(state.requests).toHaveLength(1);
});

test("source Viewer return preserves the exact reviewed destination and memory-only comment", async ({page}) => {
  const state = await installLineReviewMock(page);
  await page.goto(`/review?task=${state.tasks[0].id}`);
  await page.getByRole("button", {name: "Add as a separate line", exact: true}).click();
  await page.getByLabel("Decision comment").fill("Return to this exact proposal");
  await page.getByRole("button", {name: `Evidence for line_item_candidates.${state.candidates[0].id}, page 1`, exact: true}).click();
  await expect(page).toHaveURL(/\/documents\//);
  await page.getByRole("button", {name: "Back to Review Queue", exact: true}).click();
  await expect(page.getByLabel("Decision comment")).toHaveValue("Return to this exact proposal");
  await expect(page.getByRole("region", {name: "Review line decision"})).toContainText("recorded line 26");
  await expect(page.getByRole("button", {name: "Add this line", exact: true})).toBeEnabled();
  expect(await page.evaluate(() => Object.values(localStorage).join(" ") + Object.values(sessionStorage).join(" "))).not.toContain("Return to this exact proposal");
});

test("selected line remains withdrawable after its source candidate disappears", async ({page}) => {
  const state = await installLineReviewMock(page);
  await page.goto(`/review?task=${state.tasks[0].id}`);
  await page.getByRole("button", {name: "Add as a separate line", exact: true}).click();
  await page.getByRole("button", {name: "Add this line", exact: true}).click();
  await expect(page.getByRole("region", {name: "Line-item review"})).toContainText("Line decision saved");
  state.candidates.splice(0, 1); state.authority.items[25].selectedCandidateId = null; state.authority.sourceAssignments[0].currentlySelected = false;
  await page.goto(`/documents/${state.documentId}`);
  await page.getByRole("tab", {name: "Line items (26)", exact: true}).click();
  await page.getByRole("navigation", {name: "line items pages"}).getByLabel("Page").selectOption("3");
  await page.getByRole("button", {name: "Review line 26 and history", exact: true}).click();
  await page.getByRole("button", {name: "Remove from accepted lines…", exact: true}).click();
  await page.getByRole("button", {name: "Confirm removal from accepted lines", exact: true}).click();
  await expect(page.getByRole("region", {name: "Canonical line items", exact: true})).toContainText("Removed from accepted lines");
  expect(state.requests[1]).toMatchObject({operation: "reject_selected", target: {ordinal: 26}});
  expect(state.requests[1]).not.toHaveProperty("source");
});

for (const width of [1440, 1280, 390]) test(`line review actions and exact values stay readable at ${width}px`, async ({page}, testInfo) => {
  const state = await installLineReviewMock(page);
  await page.setViewportSize({width, height: 960});
  await page.goto(`/review?task=${state.tasks[0].id}`);
  const add = page.getByRole("button", {name: "Add as a separate line", exact: true});
  await add.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("button", {name: "Add this line", exact: true})).toBeEnabled();
  await expect(page.getByLabel("Decision comment")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("region", {name: "Line-item review", exact: true}).screenshot({path: testInfo.outputPath(`proposed-line-review-${width}-${process.platform}.png`)});
});

test("late proposal responses cannot replace a different selected task", async ({page}) => {
  const state = await installLineReviewMock(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => {release = resolve;});
  await page.route(`**/line-item-candidates?candidateId=${state.candidates[0].id}`, async (route) => {
    await held; await route.fulfill({json: {authorityVersion: "line_item_authority.v1", documentId: state.documentId, items: [state.candidates[0]]}});
  });
  await page.goto(`/review?task=${state.tasks[0].id}`);
  await expect(page.getByText("Loading line authority and source details…", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: /Aggregate alternative/}).click();
  await expect(page.getByRole("article", {name: "Source proposal"})).toContainText("Aggregate alternative");
  release();
  await expect(page.getByRole("article", {name: "Source proposal"}).getByRole("heading", {level: 4})).toHaveText("Aggregate alternative");
  expect(state.requests).toHaveLength(0);
});

test("duplicate submission is blocked while the first save is pending", async ({page}) => {
  const state = await installLineReviewMock(page);
  let release!: () => void, arrived!: () => void;
  const held = new Promise<void>((resolve) => {release = resolve;}), started = new Promise<void>((resolve) => {arrived = resolve;});
  let posts = 0;
  await page.route("**/line-item-decisions", async (route) => { posts++; arrived(); await held; await route.fallback(); });
  await page.goto(`/review?task=${state.tasks[0].id}`);
  await page.getByRole("button", {name: "Add as a separate line", exact: true}).click();
  await page.getByRole("button", {name: "Add this line", exact: true}).evaluate((button: HTMLButtonElement) => {button.click(); button.click();});
  await started;
  await expect(page.getByRole("button", {name: "Saving decision…", exact: true})).toBeDisabled();
  expect(posts).toBe(1); release();
  await expect(page.getByRole("region", {name: "Line-item review"})).toContainText("Line decision saved");
  expect(state.requests).toHaveLength(1);
});

test("protected original slot can only be restored through its explicit replacement", async ({page}) => {
  const state = await installLineReviewMock(page);
  const item = state.authority.items[0]; item.selected = false;
  Object.assign(state.authority.decisions[0], {origin: "legacy_current_line", disposition: "protected_legacy", decisionEventId: null, decidedAt: null});
  state.candidates[0].sourceAssignment = {state: "assigned", sourceCandidateId: state.candidates[0].id, canonicalLineItemId: item.id,
    target: {lineItemType: item.lineItemType, ordinal: item.ordinal}, currentlySelected: false};
  state.authority.sourceAssignments.push(state.candidates[0].sourceAssignment); state.candidates[0].suggestedVacantTarget = null;
  await page.goto(`/review?task=${state.tasks[0].id}`);
  await expect(page.getByRole("button", {name: "Add as a separate line", exact: true})).toHaveCount(0);
  await page.getByRole("button", {name: "Replace a recorded line…", exact: true}).click();
  await expect(page.getByRole("region", {name: "Choose a recorded line to replace"}).getByRole("article")).toHaveCount(1);
  await page.getByRole("button", {name: "Review replacement of line 1", exact: true}).click();
  expect(state.requests).toHaveLength(0);
  await page.getByRole("button", {name: "Save replacement", exact: true}).click();
  await expect(page.getByRole("region", {name: "Line-item review"})).toContainText("Line decision saved");
  expect(state.requests[0]).toMatchObject({operation: "replace", target: {canonicalLineItemId: item.id, expectedLineDecisionRevision: lineId(501)}});
});

test("history exposes all immutable events beyond its first page", async ({page}) => {
  const state = await installLineReviewMock(page);
  const item = state.authority.items[0];
  state.history.push(...Array.from({length: 25}, (_, index) => ({...lineHistoryEntry(item), id: lineId(3000 + index), comment: `Retained event ${index + 1}`})));
  await page.goto(`/documents/${state.documentId}`);
  await page.getByRole("tab", {name: "Line items (25)", exact: true}).click();
  await page.getByRole("button", {name: "Review line 1 and history", exact: true}).click();
  await page.getByRole("button", {name: "Decision history", exact: true}).click();
  const history = page.getByRole("region", {name: "Line decision history"});
  await expect(history.locator("summary")).toHaveCount(20);
  await history.getByRole("button", {name: "Load earlier decisions", exact: true}).click();
  await expect(history.locator("summary")).toHaveCount(25);
  await history.locator("summary").last().click();
  await expect(history).toContainText("Retained event 25");
  await expect(history).toContainText("Deleted reviewer");
});

test("logout and account replacement clear sensitive line draft and chosen revisions", async ({page}) => {
  const state = await installLineReviewMock(page);
  await page.goto(`/review?task=${state.tasks[0].id}`);
  await page.getByRole("button", {name: "Add as a separate line", exact: true}).click();
  await page.getByLabel("Decision comment").fill("Private first-account review");
  await page.getByLabel("Account: Phase Reviewer", {exact: true}).click();
  await page.getByRole("button", {name: "Sign out", exact: true}).click();
  await expect(page.getByRole("button", {name: "Sign in", exact: true})).toBeVisible();
  await page.route("**/api/v1/auth/session", (route) => route.fulfill({json: {sessionId: lineId(5001), userId: lineId(5002), householdId: lineId(5003),
    displayName: "Second reviewer", email: "second@example.com", isAuthenticated: true, sessionCookieName: "structura_session", csrfCookieName: "structura_csrf"}}));
  await page.getByLabel("Email", {exact: true}).fill("second@example.com");
  await page.getByLabel("Password", {exact: true}).fill("test-password");
  await page.getByRole("button", {name: "Sign in", exact: true}).click();
  await expect(page.getByLabel("Decision comment")).toHaveValue("");
  await expect(page.getByRole("button", {name: "Add this line", exact: true})).toHaveCount(0);
  expect(state.requests).toHaveLength(0);
});

test("a denied line reload removes retained source values, comment, and save intent", async ({page}) => {
  const state = await installLineReviewMock(page);
  await page.goto(`/review?task=${state.tasks[0].id}`);
  await page.getByRole("button", {name: "Add as a separate line", exact: true}).click();
  await page.getByLabel("Decision comment").fill("Sensitive document note");
  await page.route("**/canonical-line-items", (route) => route.fulfill({status: 403, json: {detail: "Document access is unavailable."}}));
  await page.getByRole("button", {name: "Reload line details", exact: true}).click();
  const panel = page.getByRole("region", {name: "Line-item review", exact: true});
  await expect(panel.getByRole("alert")).toContainText("Document access is unavailable");
  await expect(panel.getByRole("article", {name: "Source proposal"})).toHaveCount(0);
  await expect(page.getByLabel("Decision comment")).toHaveValue("");
  await expect(page.getByRole("button", {name: "Add this line", exact: true})).toHaveCount(0);
  expect(state.requests).toHaveLength(0);
});
