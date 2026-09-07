import {expect, test} from "@playwright/test";
import {mockStructuraApi} from "./support/structuraMock";
import {existingDocument} from "./support/structuraFixtures";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Calendar fixtures use the isolated Vite and mocked API harness.");

for (const [timezoneId, firstInstant, lateInstant] of [
  ["America/Los_Angeles", "Apr 19, 2026", "Apr 20, 2026"],
  ["America/New_York", "Apr 19, 2026", "Apr 20, 2026"],
  ["UTC", "Apr 20, 2026", "Apr 20, 2026"],
  ["Pacific/Kiritimati", "Apr 20, 2026", "Apr 21, 2026"],
]) {
  test.describe(timezoneId, () => {
    test.use({timezoneId, locale: "en-US"});

    test("source dates agree in table, filing editor and Viewer without shifting timestamps", async ({page}) => {
      await mockStructuraApi(page);
      await page.goto("/inbox");
      const row = page.getByRole("row", {name: /Existing Warranty/});
      await expect(row.locator('[data-label="Date"]')).toHaveText("Apr 20, 2026");
      await expect(page.getByLabel("Document date", {exact: true})).toHaveValue("2026-04-20");
      await page.goto(`/documents/${existingDocument.id}`);
      await expect(page.locator(".fact-row").filter({has: page.getByText("Date", {exact: true})}))
        .toContainText("Apr 20, 2026");

      // Import the real formatter in the browser so Intl uses this context's
      // timezone, not the test runner's host timezone.
      const formatted = await page.evaluate(async (modulePath) => {
        const {formatDate} = await import(modulePath);
        return {
          zone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          dates: ["2024-02-29", "2000-02-29", "2026-03-08", "2026-11-01", "0001-01-01"].map(formatDate),
          invalid: [undefined, "", "garbage", "2025-02-29", "2100-02-29", "2026-02-30", "2026-13-01", "0000-01-01"].map(formatDate),
          instants: ["2026-04-20T00:30:00Z", "2026-04-20T20:30:00Z"].map(formatDate),
        };
      }, "/src/format.ts");
      expect(formatted.zone).toBe(timezoneId);
      expect(formatted.dates).toEqual(["Feb 29, 2024", "Feb 29, 2000", "Mar 8, 2026", "Nov 1, 2026", "Jan 1, 1"]);
      expect(formatted.invalid).toEqual(Array(8).fill("-"));
      expect(formatted.instants).toEqual([firstInstant, lateInstant]);
    });
  });
}
