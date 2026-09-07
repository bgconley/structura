import {expect, test} from "@playwright/test";

import {canonicalFieldForCandidate, referenceCandidate} from "../../apps/web/src/reviewActions";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {seededFieldCandidates, seededReviewTasks} from "./support/structuraFixtures";
import {reviewAuthorityFixture} from "./support/reviewAuthorityFixture";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Mocked decision regressions are local-only.");

test.beforeEach(async ({context, page}) => {
  await context.addCookies([
    {name: "structura_session", value: "decision-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page);
});

const revision = "2026-09-07T10:11:12.123456Z";

const actionLabels = {confirm_field: "Accept candidate", correct_field: "Correct field", reject_field: "Reject field"};
for (const action of ["confirm_field", "correct_field", "reject_field"] as const) {
  test(`${action} sends the exact matching ordinal revision and preserves state on conflict`, async ({page}) => {
    const candidate = {...seededFieldCandidates()[0], ordinal: 2};
    const task = {...seededReviewTasks()[0], metadata: {candidateId: candidate.id, ordinal: 2}};
    const canonical = {
      ...candidate, id: "canonical-current", value: {amount: 999, currency: "USD"},
      sourceKind: "human", reviewStatus: "user_corrected", updatedAt: revision,
    };
    await page.route("**/api/v1/review-tasks?*", (route) => route.fulfill({json: {items: [task]}}));
    await page.route("**/api/v1/review-tasks/*", (route) => route.fulfill({json: task}));
    await page.route("**/api/v1/documents/*/field-candidates?*", (route) => route.fulfill({json: {items: [
      {...candidate, id: "11111111-1111-4111-8111-111111111111", ordinal: 1, value: {amount: 111, currency: "USD"}},
      candidate,
    ]}}));
    await page.route("**/api/v1/documents/*/canonical-fields", (route) => route.fulfill({json: reviewAuthorityFixture(candidate.documentId, [
      {...canonical, id: "other-ordinal", ordinal: 1, updatedAt: "2026-09-07T09:00:00Z"},
      canonical,
    ])}));
    const mutations: Record<string, unknown>[] = [];
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/api/v1/documents/*/review-actions", async (route) => {
      mutations.push(route.request().postDataJSON());
      await route.fulfill({status: 409, json: {detail: "This field changed since it was loaded. Reload it before saving your decision."}});
    });
    await page.goto("/");
    await page.getByRole("button", {name: /Review Queue/}).click();
    await page.getByLabel("Reject note").fill("Keep this decision note.");
    await expect(page.getByRole("button", {name: "Accept candidate", exact: true}).first()).toBeDisabled();
    if (action === "correct_field") await page.getByLabel("Corrected value").fill("1000");
    await page.getByRole("button", {name: actionLabels[action], exact: true}).last().click();
    await expect(page.locator(".review-status")).toContainText("changed since it was loaded");
    expect(mutations).toHaveLength(1);
    expect(mutations[0]).toMatchObject({actionType: action, expectedUpdatedAt: revision});
    if (action === "reject_field") expect(mutations[0].metadata).toEqual({ordinal: 2});
    if (action === "correct_field") expect(mutations[0].metadata).toMatchObject({ordinal: 2, candidateId: candidate.id});
    await expect(page.locator(".canonical-summary")).toContainText("USD 999");
    await expect(page.getByLabel("Reject note")).toHaveValue("Keep this decision note.");
    expect(errors).toEqual([]);
  });

  test(`${action} uses an explicit absent-field revision for the first decision`, async ({page}) => {
    await page.route("**/api/v1/documents/*/canonical-fields", (route) => route.fulfill({json: reviewAuthorityFixture(seededFieldCandidates()[0].documentId)}));
    const mutation = page.waitForRequest((request) => request.method() === "POST" && request.url().endsWith("/review-actions"));
    await page.goto("/");
    await page.getByRole("button", {name: /Review Queue/}).click();
    if (action === "correct_field") await page.getByLabel("Corrected value").fill("1000");
    await page.getByRole("button", {name: actionLabels[action], exact: true}).click();
    expect((await mutation).postDataJSON()).toMatchObject({actionType: action, expectedUpdatedAt: null,
      expectedDecisionRevision: null, expectedPathGuardRevision: null});
  });
}

test("a canonical row without its revision cannot enable a destructive decision", async ({page}) => {
  const candidate = seededFieldCandidates()[0];
  await page.route("**/api/v1/documents/*/canonical-fields", (route) => route.fulfill({json: reviewAuthorityFixture(candidate.documentId, [{
    ...candidate, id: "canonical-missing-revision", sourceKind: "human", reviewStatus: "user_confirmed",
  }])}));
  await page.goto("/");
  await page.getByRole("button", {name: /Review Queue/}).click();
  await expect(page.getByRole("button", {name: "Accept candidate", exact: true})).toBeDisabled();
  await expect(page.getByRole("button", {name: "Reject field", exact: true})).toBeDisabled();
});

test("canonical revision selection cannot cross document or ordinal boundaries", () => {
  const candidate = seededFieldCandidates()[0];
  const canonical = {...candidate, sourceKind: "human", reviewStatus: "user_confirmed", updatedAt: revision};
  expect(canonicalFieldForCandidate([
    {...canonical, documentId: "another-document"}, {...canonical, ordinal: 2},
  ], {...candidate, ordinal: 1})).toBeUndefined();
});

for (const metadata of [
  {candidateId: "missing-candidate", ordinal: 1},
  {candidateId: seededFieldCandidates()[0].id, ordinal: 2},
]) {
  test(`unavailable or inconsistent explicit task reference disables field decisions: ${metadata.candidateId}/${metadata.ordinal}`, async ({page}) => {
    const task = {...seededReviewTasks()[0], metadata};
    await page.route("**/api/v1/review-tasks?*", (route) => route.fulfill({json: {items: [task]}}));
    await page.route("**/api/v1/review-tasks/*", (route) => route.fulfill({json: task}));
    await page.goto("/");
    await page.getByRole("button", {name: /Review Queue/}).click();
    for (const name of Object.values(actionLabels)) {
      await expect(page.getByRole("button", {name, exact: true})).toBeDisabled();
    }
  });
}

test("explicit task identity validates document, path and ordinal; legacy identity selects ordinal one", () => {
  const candidate = seededFieldCandidates()[0];
  const task = {...seededReviewTasks()[0], metadata: {candidateId: candidate.id, ordinal: 1}};
  for (const item of [
    {...candidate, documentId: "other-document"},
    {...candidate, fieldPath: "invoice.other_field"},
    {...candidate, ordinal: 2},
  ]) expect(referenceCandidate(task, [item])).toBeUndefined();
  expect(referenceCandidate({...task, metadata: {ordinal: "1"}}, [candidate])).toBeUndefined();
  expect(referenceCandidate({...task, metadata: {}}, [{...candidate, ordinal: 2}, candidate])).toEqual(candidate);
});
