import {expect, test} from "@playwright/test";

import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {documentBrowseResponse} from "./support/documentBrowseMock";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Mocked status regressions are local-only.");

test("missing observations never claim healthy services or fabricated queue counts", async ({context, page}) => {
  await context.addCookies([
    {name: "structura_session", value: "status-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page);
  await page.goto("/");
  const health = page.getByRole("region", {name: "Machine health"});
  await expect(health).toContainText("Backup status unknown");
  await expect(health).toContainText("Storage status unknown");
  await expect(health).toContainText("Worker status unknown");
  await expect(page.getByText("Hybrid search ready", {exact: true})).toHaveCount(0);
  await expect(page.getByText("2 workers active", {exact: true})).toHaveCount(0);
  await expect(page.getByRole("button", {name: /Review Queue/}).locator("b")).toHaveCount(0);
  await expect(page.getByRole("columnheader", {name: "Document State"})).toBeVisible();
  await expect(page.locator("tbody tr").first().locator("td").last()).toHaveText("active");
  await expect(page.getByText("Ingested", {exact: true})).toHaveCount(0);

  await page.route(/\/api\/v1\/documents(?:\?.*)?$/, async (route) => {
    await route.fulfill({json: documentBrowseResponse(new URLSearchParams(), [])});
  });
  await page.reload();
  const inboxNavigation = page.getByRole("navigation", {name: "Primary"}).getByRole("button", {name: /Inbox/});
  await expect(inboxNavigation).toContainText("Inbox");
  await expect(inboxNavigation.locator("small")).toHaveText("0");
  await expect(page.getByText("0 documents displayed", {exact: true})).toBeVisible();
});
