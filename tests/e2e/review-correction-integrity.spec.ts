import {expect, test} from "@playwright/test";

import {coerceCorrectionValue} from "../../apps/web/src/reviewActions";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {seededFieldCandidates, seededReviewTasks} from "./support/structuraFixtures";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Mocked correction regressions are local-only.");

test("typed correction parsing rejects silent coercion and precision loss", () => {
  for (const [value, type] of [
    ["abc", "money"], ["1e3", "money"], ["$1,234.50", "money"], ["1.234,50", "money"],
    ["", "number"], ["NaN", "number"], ["Infinity", "number"], ["12junk", "number"],
    ["1.23456", "number"], ["100000000000000", "number"], ["12345678901234.1234", "number"],
    ["12garbage", "integer"], ["1.5", "integer"], ["9007199254740993", "integer"],
    ["perhaps", "boolean"],
    ["2026-02-30", "date"], ["2025-02-29", "date"], ["09/07/2026", "date"],
    ["2026-09-07T14:30:00", "datetime"], ["2026-09-07T14:30:00-00:00", "datetime"],
    ["2026-09-07T14:30:00.1234567Z", "datetime"], ["2026-09-07T14:30:00+01:60", "datetime"],
    ['{"paid":', "json"], ['{"amount": 1e400}', "json"],
  ]) expect(() => coerceCorrectionValue(value, type, "USD")).toThrow();
  expect(coerceCorrectionValue("0", "money", "USD").value).toEqual({amount: 0, currency: "USD"});
  expect(coerceCorrectionValue("-12.3456", "money", "EUR").value).toEqual({amount: -12.3456, currency: "EUR"});
  expect(coerceCorrectionValue("false", "boolean").value).toBe(false);
  expect(coerceCorrectionValue("no", "boolean").value).toBe(false);
  expect(coerceCorrectionValue("true", "boolean").value).toBe(true);
  expect(coerceCorrectionValue("-12", "integer").value).toBe(-12);
  expect(coerceCorrectionValue("2024-02-29", "date").value).toBe("2024-02-29");
  expect(coerceCorrectionValue("2026-09-07T14:30:00.123456-04:00", "datetime").value)
    .toBe("2026-09-07T14:30:00.123456-04:00");
  expect(coerceCorrectionValue('{"paid": false, "items": [0, null]}', "json").value)
    .toEqual({paid: false, items: [0, null]});
  expect(coerceCorrectionValue("null", "json").value).toBe(null);
});

for (const [kind, value, expected] of [
  ["date", "2024-02-29", "2024-02-29"],
  ["datetime", "2026-09-07T14:30:00.123456-04:00", "2026-09-07T14:30:00.123456-04:00"],
  ["json", '{"paid":false,"items":[0,null]}', {paid: false, items: [0, null]}],
] as const) {
  test(`${kind} editor sends typed JSON and preserves the exact loaded revision`, async ({page}) => {
    const candidate = {...seededFieldCandidates()[0], valueType: kind, value};
    const revision = "2026-09-07T10:11:12.123456Z";
    await page.route("**/api/v1/documents/*/field-candidates?*", (route) => route.fulfill({json: {items: [candidate]}}));
    await page.route("**/api/v1/documents/*/canonical-fields", (route) => route.fulfill({json: {items: [{
      ...candidate, id: "canonical", sourceKind: "human", reviewStatus: "user_corrected", updatedAt: revision,
    }]}}));
    const mutations: unknown[] = [];
    await page.route("**/api/v1/documents/*/review-actions", async (route) => {
      mutations.push(route.request().postDataJSON());
      await route.fulfill({status: 409, json: {detail: "This field changed since it was loaded."}});
    });
    await page.goto("/");
    await page.getByRole("button", {name: /Review Queue/}).click();
    await page.getByLabel("Corrected value").fill(value);
    await page.getByLabel("Correction note").fill("Keep my draft after a conflict.");
    await page.getByRole("button", {name: "Correct field", exact: true}).click();
    await expect(page.locator(".review-status")).toContainText("changed since it was loaded");
    expect(mutations).toHaveLength(1);
    expect(mutations[0]).toMatchObject({newValue: expected, expectedUpdatedAt: revision});
    await expect(page.getByLabel("Corrected value")).toHaveValue(value);
    await expect(page.getByLabel("Correction note")).toHaveValue("Keep my draft after a conflict.");
  });
}

test("reordered task responses cannot expose stale decisions under another document", async ({page}) => {
  const [a, b] = seededFieldCandidates();
  const base = seededReviewTasks()[0];
  const tasks = [
    {...base, id: "task-a", documentId: a.documentId, fieldPath: a.fieldPath, rationale: "Task A"},
    {...base, id: "task-b", documentId: b.documentId, fieldPath: b.fieldPath, rationale: "Task B"},
  ];
  let releaseA!: () => void;
  let releaseB!: () => void;
  const waitA = new Promise<void>((resolve) => { releaseA = resolve; });
  const waitB = new Promise<void>((resolve) => { releaseB = resolve; });
  await page.route("**/api/v1/review-tasks?*", (route) => route.fulfill({json: {items: tasks}}));
  await page.route("**/api/v1/documents/*/canonical-fields", (route) => route.fulfill({json: {items: []}}));
  await page.route("**/api/v1/documents/*/field-candidates?*", async (route) => {
    const isA = route.request().url().includes(a.documentId);
    await (isA ? waitA : waitB);
    await route.fulfill({json: {items: [isA ? a : b]}});
  });
  await page.goto("/");
  await page.getByRole("button", {name: /Review Queue/}).click();
  await page.getByRole("button", {name: /Task B/}).click();
  await expect(page.getByRole("button", {name: "Mark reviewed", exact: true})).toBeDisabled();
  await expect(page.getByRole("button", {name: "Accept candidate", exact: true})).toHaveCount(0);
  releaseB();
  await expect(page.getByRole("button", {name: "Correct field", exact: true})).toBeEnabled();
  releaseA();
  await expect(page.locator(".candidate-group h3")).toHaveText(b.fieldPath);
  const request = page.waitForRequest((req) => req.method() === "POST" && req.url().endsWith("/review-actions"));
  await page.getByLabel("Corrected value").fill("0");
  await page.getByRole("button", {name: "Correct field", exact: true}).click();
  expect((await request).postDataJSON()).toMatchObject({documentId: b.documentId, fieldPath: b.fieldPath});
});

test("all review mutations share one pending guard and failed reclassification retains edits", async ({page}) => {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  let mutations = 0;
  await page.route("**/api/v1/documents/*/review-actions", async (route) => {
    mutations += 1;
    await pending;
    await route.fulfill({status: 503, json: {detail: "Try again later."}});
  });
  await page.goto("/");
  await page.getByRole("button", {name: /Review Queue/}).click();
  await expect(page.getByRole("button", {name: "Reclassify", exact: true})).toBeEnabled();
  await page.getByLabel("Document subtype").fill("Retained subtype");
  await page.getByLabel("Reclassification note").fill("Retained reason");
  await page.getByRole("button", {name: "Reclassify", exact: true}).click();
  for (const name of ["Reclassify", "Accept candidate", "Mark reviewed", "Re-run extraction", "Reject field"]) {
    await expect(page.getByRole("button", {name, exact: true})).toBeDisabled();
  }
  await page.locator("form").filter({has: page.getByLabel("Document subtype")}).dispatchEvent("submit");
  expect(mutations).toBe(1);
  release();
  await expect(page.locator(".review-status")).toContainText("Try again later");
  await expect(page.getByLabel("Document subtype")).toHaveValue("Retained subtype");
  await expect(page.getByLabel("Reclassification note")).toHaveValue("Retained reason");
});

test.beforeEach(async ({context, page}) => {
  await context.addCookies([
    {name: "structura_session", value: "correction-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page);
});

test("invalid correction stays in the form and sends no mutation; zero saves exactly", async ({page}) => {
  const mutations: unknown[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/review-actions")) {
      mutations.push(request.postDataJSON());
    }
  });
  await page.goto("/");
  await page.getByRole("button", {name: /Review Queue/}).click();
  await page.getByLabel("Correction note").fill("Keep this explanation.");
  for (const value of ["abc", "1e3", "1,25", "1.23456"]) {
    await page.getByLabel("Corrected value").fill(value);
    await page.getByRole("button", {name: "Correct field", exact: true}).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByLabel("Corrected value")).toHaveValue(value);
    await expect(page.getByLabel("Correction note")).toHaveValue("Keep this explanation.");
    expect(mutations).toEqual([]);
  }
  await page.getByLabel("Corrected value").fill("0");
  await page.getByRole("button", {name: "Correct field", exact: true}).click();
  await expect(page.locator(".review-status")).toContainText("Field corrected");
  expect(mutations).toHaveLength(1);
  expect(mutations[0]).toMatchObject({
    newValue: {amount: 0, currency: "USD"},
    metadata: {valueType: "money", currency: "USD"},
    comment: "Keep this explanation.",
  });
});

test("failed save preserves edits and prevents overlapping correction requests", async ({page}) => {
  let mutations = 0;
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/v1/documents/*/review-actions", async (route) => {
    mutations += 1;
    await pending;
    await route.fulfill({status: 422, json: {detail: "Correction rejected."}});
  });
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/");
  await page.getByRole("button", {name: /Review Queue/}).click();
  await page.getByLabel("Corrected value").fill("12.50");
  await page.getByLabel("Correction note").fill("Retain on failure.");
  await page.getByRole("button", {name: "Correct field", exact: true}).click();
  await expect(page.getByRole("button", {name: "Saving correction…"})).toBeDisabled();
  await page.locator("form").filter({has: page.getByLabel("Corrected value")}).dispatchEvent("submit");
  expect(mutations).toBe(1);
  release();
  await expect(page.getByRole("alert")).toContainText("not saved");
  await expect(page.getByLabel("Corrected value")).toHaveValue("12.50");
  await expect(page.getByLabel("Correction note")).toHaveValue("Retain on failure.");
  await expect(page.getByRole("button", {name: "Correct field", exact: true})).toBeEnabled();
  expect(pageErrors).toEqual([]);
});

test("a candidate for a different document cannot supply the correction type or evidence", async ({page}) => {
  await page.route("**/api/v1/documents/*/field-candidates?*", async (route) => {
    const candidate = seededFieldCandidates()[0];
    await route.fulfill({json: {items: [{...candidate, documentId: "different-document"}]}});
  });
  await page.goto("/");
  await page.getByRole("button", {name: /Review Queue/}).click();
  await expect(page.getByRole("button", {name: "Correct field", exact: true})).toBeDisabled();
});
