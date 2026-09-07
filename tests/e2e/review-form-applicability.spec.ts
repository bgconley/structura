import {expect, test} from "@playwright/test";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {seededReviewTasks} from "./support/structuraFixtures";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Review applicability uses controlled task identities.");
test.beforeEach(async ({context, page}) => {
  await context.addCookies([{name: "structura_session", value: "review-form-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"}]);
  await mockStructuraApi(page);
});

test("document quality review keeps applicable actions and omits canonical field forms", async ({page}) => {
  await page.goto(`/review?task=${seededReviewTasks()[0].id}`);
  await page.getByLabel("Correction note", {exact: true}).fill("Only for the invoice field");
  await page.getByRole("button", {name: /document_quality/}).click();
  await expect(page.locator(".candidate-panel-title")).toContainText("document_quality");
  await expect(page.getByRole("button", {name: "Accept candidate", exact: true})).toBeEnabled();
  await expect(page.getByRole("button", {name: "Jump to evidence", exact: true})).toBeEnabled();
  await expect(page.getByRole("form", {name: "Classify document", exact: true})).toBeVisible();
  await expect(page.getByRole("button", {name: "Mark reviewed", exact: true})).toBeEnabled();
  await expect(page.getByRole("form", {name: "Correct canonical field", exact: true})).toHaveCount(0);
  await expect(page.getByRole("form", {name: "Reject canonical field", exact: true})).toHaveCount(0);
  await expect(page.getByText("Reload this field to obtain its current revision before correcting.", {exact: true})).toHaveCount(0);
  await expect(page.getByLabel("Reject note", {exact: true})).toHaveCount(0);
  await page.getByRole("button", {name: "Mark reviewed", exact: true}).click();
  await expect(page.locator(".review-status")).toContainText("Review task closed");
});

test("unavailable field revision uses a full-width notice outside the correction controls", async ({page}) => {
  await page.route("**/api/v1/documents/*/canonical-fields", (route) => route.fulfill({json: {items: []}}));
  await page.goto(`/review?task=${seededReviewTasks()[0].id}`);
  const form = page.getByRole("form", {name: "Correct canonical field", exact: true});
  const notice = page.locator(".review-decision-notice");
  await expect(notice).toContainText("Reload this field");
  await expect(form.getByText("Reload this field", {exact: false})).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Correct field", exact: true})).toBeDisabled();
  await expect(page.getByRole("button", {name: "Reject field", exact: true})).toBeDisabled();
  const noticeBox = await notice.boundingBox();
  const formBox = await form.boundingBox();
  expect(noticeBox!.width).toBeCloseTo(formBox!.width, 0);
  expect(noticeBox!.y + noticeBox!.height).toBeLessThanOrEqual(formBox!.y);
});
