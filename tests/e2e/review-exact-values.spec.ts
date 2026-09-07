import {expect, test} from "@playwright/test";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {seededFieldCandidates, seededReviewTasks} from "./support/structuraFixtures";
import {reviewAuthorityFixture} from "./support/reviewAuthorityFixture";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Exact read values use controlled fixtures.");

for (const [amount, expected] of [["0.0000", "0.0000"], ["-12.3400", "-12.3400"],
  ["1.2345", "1.2345"], ["99999999999999.9999", "99,999,999,999,999.9999"]]) {
  test(`Review preserves exact canonical money and number ${amount}`, async ({context, page}) => {
    await context.addCookies([{name: "structura_session", value: "exact-read", domain: "localhost", path: "/"},
      {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"}]);
    await mockStructuraApi(page);
    const candidate = seededFieldCandidates()[0];
    const base = {...candidate, sourceKind: "human", reviewStatus: "user_corrected",
      updatedAt: "2026-09-07T01:02:03.123456Z"};
    await page.route("**/api/v1/documents/*/canonical-fields", (route) => route.fulfill({json:
      reviewAuthorityFixture(candidate.documentId, [
        {...base, id: "11111111-1111-4111-8111-111111111111", ordinal: 1, valueType: "money", value: {amount, currency: "EUR"}},
        {...base, id: "22222222-2222-4222-8222-222222222222", ordinal: 2, valueType: "number", value: amount},
      ])}));
    await page.goto(`/review?task=${seededReviewTasks()[0].id}`);
    const history = page.locator(".canonical-summary");
    await expect(history).toContainText(`EUR ${expected}`);
    await expect(history.locator("p").filter({hasText: "position 2"})).toContainText(`${expected} · Accepted value`);
  });
}
