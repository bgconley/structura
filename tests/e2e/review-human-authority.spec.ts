import {expect, test, type Page} from "@playwright/test";
import {fieldDecisionPreconditions, parseCanonicalFieldResponse, recordedFieldStatus} from "../../apps/web/src/reviewAuthority";
import type {CanonicalFieldResponse, FieldDecision, FieldPathGuard} from "../../apps/web/src/types";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {seededFieldCandidates, seededReviewTasks} from "./support/structuraFixtures";
import {reviewAuthorityFixture} from "./support/reviewAuthorityFixture";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Controlled authority regressions use explicit review fixtures.");
test.beforeEach(async ({context, page}) => {
  await context.addCookies([{name: "structura_session", value: "authority-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"}]);
  await mockStructuraApi(page);
});

const candidate = {...seededFieldCandidates()[0], ordinal: 2};
const timestamp = "2026-09-07T10:11:12.123456Z";
const decisionRevision = "11111111-1111-4111-8111-111111111111";
const guardRevision = "22222222-2222-4222-8222-222222222222";
const nextRevision = "33333333-3333-4333-8333-333333333333";
const canonical = {...candidate, id: "44444444-4444-4444-8444-444444444444", sourceKind: "human",
  reviewStatus: "user_corrected", updatedAt: timestamp};
const decision: FieldDecision = {id: "55555555-5555-4555-8555-555555555555", documentId: candidate.documentId,
  fieldPath: candidate.fieldPath, ordinal: 2, revision: decisionRevision, disposition: "rejected", origin: "live_review",
  canonicalFieldId: null, reviewEventId: null, actorUserId: null, decidedAt: timestamp, recordedAt: timestamp};
const guard: FieldPathGuard = {id: "66666666-6666-4666-8666-666666666666", documentId: candidate.documentId,
  fieldPath: candidate.fieldPath, revision: guardRevision, status: "active", origin: "legacy_path_rejection",
  reviewEventId: null, actorUserId: null};
const labels = {confirm_field: "Accept candidate", correct_field: "Correct field", reject_field: "Reject field"};

async function review(page: Page, initial: CanonicalFieldResponse | unknown) {
  const task = {...seededReviewTasks()[0], metadata: {candidateId: candidate.id, ordinal: 2}};
  const state = {authority: initial, reads: 0};
  await page.route("**/api/v1/review-tasks?*", (route) => route.fulfill({json: {items: [task]}}));
  await page.route("**/api/v1/review-tasks/*", (route) => route.fulfill({json: task}));
  await page.route("**/api/v1/documents/*/field-candidates?*", (route) => route.fulfill({json: {items: [candidate]}}));
  await page.route("**/api/v1/documents/*/canonical-fields", (route) => {
    state.reads += 1;
    return route.fulfill({json: state.authority});
  });
  await page.goto(`/review?task=${task.id}`);
  return state;
}

for (const action of ["confirm_field", "correct_field", "reject_field"] as const) {
  test(`${action} acknowledges a rejection with no canonical row`, async ({page}) => {
    await review(page, reviewAuthorityFixture(candidate.documentId, [], [decision]));
    await expect(page.locator(".canonical-summary")).toContainText("Human rejected");
    await expect(page.locator(".canonical-summary")).toContainText("No recorded canonical value");
    await expect(page.locator(".canonical-summary")).toContainText("position 2");
    if (action === "correct_field") await page.getByLabel("Corrected value").fill("1000");
    const request = page.waitForRequest((item) => item.method() === "POST" && item.url().endsWith("/review-actions"));
    await page.getByRole("button", {name: labels[action], exact: true}).click();
    expect((await request).postDataJSON()).toMatchObject({actionType: action,
      expectedUpdatedAt: null, expectedDecisionRevision: decisionRevision, expectedPathGuardRevision: null});
  });

  test(`${action} keeps canonical, exact-position and path revisions independent`, async ({page}) => {
    const otherDecision = {...decision, id: "77777777-7777-4777-8777-777777777777", ordinal: 1, revision: nextRevision};
    await review(page, reviewAuthorityFixture(candidate.documentId,
      [{...canonical, id: "88888888-8888-4888-8888-888888888888", ordinal: 1, updatedAt: "2026-09-01T00:00:00Z"}, canonical],
      [otherDecision, {...decision, disposition: "corrected", canonicalFieldId: canonical.id}], [guard]));
    await expect(page.locator(".canonical-summary")).toContainText("other positions remain protected");
    if (action === "correct_field") await page.getByLabel("Corrected value").fill("1000");
    const request = page.waitForRequest((item) => item.method() === "POST" && item.url().endsWith("/review-actions"));
    await page.getByRole("button", {name: labels[action], exact: true}).click();
    expect((await request).postDataJSON()).toMatchObject({actionType: action, expectedUpdatedAt: timestamp,
      expectedDecisionRevision: decisionRevision, expectedPathGuardRevision: guardRevision});
  });
}

test("a conflict preserves the draft through refresh and requires the newly loaded decision and guard", async ({page}) => {
  const state = await review(page, reviewAuthorityFixture(candidate.documentId, [canonical],
    [{...decision, disposition: "corrected", canonicalFieldId: canonical.id}], [guard]));
  const sent: Record<string, unknown>[] = [];
  await page.route("**/api/v1/documents/*/review-actions", async (route) => {
    sent.push(route.request().postDataJSON());
    await route.fulfill({status: 409, json: {detail: "This field changed since it was loaded. Reload it before saving your decision."}});
  });
  await page.getByLabel("Corrected value").fill("1234.56");
  await page.getByLabel("Correction note").fill("Preserve this reasoning.");
  await page.getByRole("button", {name: "Correct field", exact: true}).click();
  await expect(page.locator(".review-status")).toContainText("changed since it was loaded");
  for (const name of Object.values(labels)) await expect(page.getByRole("button", {name, exact: true})).toBeDisabled();
  expect(sent).toHaveLength(1);
  state.authority = reviewAuthorityFixture(candidate.documentId, [{...canonical, updatedAt: "2026-09-08T01:02:03.654321Z"}],
    [{...decision, revision: nextRevision}], [{...guard, revision: decisionRevision}]);
  await page.getByRole("button", {name: "Refresh", exact: true}).click();
  await expect(page.getByRole("button", {name: "Correct field", exact: true})).toBeEnabled();
  await expect(page.getByLabel("Corrected value")).toHaveValue("1234.56");
  await expect(page.getByLabel("Correction note")).toHaveValue("Preserve this reasoning.");
  await expect(page.locator(".canonical-summary")).toContainText("Human rejected");
  await page.getByRole("button", {name: "Correct field", exact: true}).click();
  await expect.poll(() => sent.length).toBe(2);
  expect(sent[1]).toMatchObject({newValue: {amount: 1234.56, currency: "USD"},
    expectedUpdatedAt: "2026-09-08T01:02:03.654321Z", expectedDecisionRevision: nextRevision,
    expectedPathGuardRevision: decisionRevision});
});

for (const invalid of ["missing-version", "missing-decisions", "foreign-guard", "duplicate-decision",
  "missing-canonical-binding", "wrong-position-binding", "live-protected-legacy", "live-missing-decision-time"] as const) {
  test(`invalid authority disables field decisions: ${invalid}`, async ({page}) => {
    const envelope = reviewAuthorityFixture(candidate.documentId, [], [decision], [guard]);
    const payload: Record<string, unknown> = {...envelope};
    if (invalid === "missing-version") delete payload.authorityVersion;
    if (invalid === "missing-decisions") delete payload.decisions;
    if (invalid === "foreign-guard") payload.pathGuards = [{...guard, documentId: "ffffffff-ffff-4fff-8fff-ffffffffffff"}];
    if (invalid === "duplicate-decision") payload.decisions = [decision, {...decision, revision: nextRevision}];
    if (invalid === "missing-canonical-binding" || invalid === "wrong-position-binding") {
      payload.decisions = [{...decision, canonicalFieldId: canonical.id}];
      if (invalid === "wrong-position-binding") payload.items = [{...canonical, ordinal: 1}];
    }
    if (invalid === "live-protected-legacy") payload.decisions = [{...decision, disposition: "protected_legacy"}];
    if (invalid === "live-missing-decision-time") payload.decisions = [{...decision, decidedAt: null}];
    let mutations = 0;
    await page.route("**/api/v1/documents/*/review-actions", (route) => {mutations += 1; return route.fulfill({json: {ok: true}});});
    await review(page, payload);
    await expect(page.getByRole("alert")).toContainText("decision history is unavailable or inconsistent");
    for (const name of Object.values(labels)) await expect(page.getByRole("button", {name, exact: true})).toBeDisabled();
    await expect(page.getByRole("button", {name: "Jump to evidence", exact: true})).toBeEnabled();
    expect(mutations).toBe(0);
  });
}

test("unestablished accepted facts remain reviewable without claiming verification", async ({page}) => {
  const envelope = reviewAuthorityFixture(candidate.documentId);
  envelope.projection = {...envelope.projection, state: "unestablished", acceptedFactRevision: 0,
    projectionRevision: 0, acceptedFactsSha256: null, indexedMetadataSha256: null};
  await review(page, envelope);
  await expect(page.locator(".canonical-summary")).toContainText("Accepted facts have not been verified");
  await expect(page.getByRole("button", {name: "Accept candidate", exact: true})).toBeEnabled();
});

for (const kind of ["observation", "line_item"] as const) {
  test(`missing field authority does not block an independent ${kind} decision`, async ({page}) => {
    const item = {id: "99999999-9999-4999-8999-999999999999", documentId: candidate.documentId,
      fieldName: "note", valueType: "string", value: "Review this observation", sourceEngine: "docling",
      lineItemType: "service", ordinal: 1, description: "Review this service", evidence: []};
    const task = {...seededReviewTasks()[0], taskType: `${kind}_review`, fieldPath: undefined,
      metadata: kind === "observation" ? {observationId: item.id} : {lineItemCandidateId: item.id}};
    await page.route("**/api/v1/review-tasks?*", (route) => route.fulfill({json: {items: [task]}}));
    await page.route("**/api/v1/review-tasks/*", (route) => route.fulfill({json: task}));
    await page.route("**/api/v1/documents/*/canonical-fields", (route) => route.fulfill({json: {items: []}}));
    await page.route(`**/api/v1/documents/*/${kind === "observation" ? "observation" : "line-item"}-candidates?*`,
      (route) => route.fulfill({json: {items: [item]}}));
    await page.goto(`/review?task=${task.id}`);
    const request = page.waitForRequest((item) => item.method() === "POST" && item.url().endsWith("/review-actions"));
    await page.getByRole("button", {name: kind === "observation" ? "Accept observation" : "Accept line item", exact: true}).click();
    expect((await request).postDataJSON().actionType).toBe(`accept_${kind}`);
  });
}

test("resolved guards and another position cannot supply an exact field revision or accepted value", () => {
  const envelope = parseCanonicalFieldResponse(reviewAuthorityFixture(candidate.documentId, [canonical],
    [{...decision, ordinal: 1}], [{...guard, status: "resolved"}]), candidate.documentId);
  expect(fieldDecisionPreconditions(envelope, candidate)).toEqual({expectedUpdatedAt: timestamp,
    expectedDecisionRevision: null, expectedPathGuardRevision: null});
  expect(fieldDecisionPreconditions(envelope, {...candidate, documentId: "different-document"})).toBeNull();
  expect(recordedFieldStatus({...envelope, decisions: [decision]}, canonical)).toContain("Rejected");
  expect(recordedFieldStatus({...envelope, decisions: [], pathGuards: [guard]}, canonical)).toBe("Not selected as an accepted fact");
  expect(() => parseCanonicalFieldResponse({...envelope, decisions: [{...decision, revision: "missing"}]}, candidate.documentId)).toThrow();
});
