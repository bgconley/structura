import {expect, test} from "@playwright/test";

import {coerceCorrectionValue} from "../../apps/web/src/reviewActions";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {seededFieldCandidates} from "./support/structuraFixtures";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Mocked correction regressions are local-only.");

test("typed correction parsing rejects silent coercion and precision loss", () => {
  for (const [value, type] of [
    ["abc", "money"], ["1e3", "money"], ["$1,234.50", "money"], ["1.234,50", "money"],
    ["", "number"], ["NaN", "number"], ["Infinity", "number"], ["12junk", "number"],
    ["1.23456", "number"], ["100000000000000", "number"], ["12345678901234.1234", "number"],
    ["12garbage", "integer"], ["1.5", "integer"], ["9007199254740993", "integer"],
    ["perhaps", "boolean"],
  ]) expect(() => coerceCorrectionValue(value, type, "USD")).toThrow();
  expect(coerceCorrectionValue("0", "money", "USD").value).toEqual({amount: 0, currency: "USD"});
  expect(coerceCorrectionValue("-12.3456", "money", "EUR").value).toEqual({amount: -12.3456, currency: "EUR"});
  expect(coerceCorrectionValue("false", "boolean").value).toBe(false);
  expect(coerceCorrectionValue("no", "boolean").value).toBe(false);
  expect(coerceCorrectionValue("true", "boolean").value).toBe(true);
  expect(coerceCorrectionValue("-12", "integer").value).toBe(-12);
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
