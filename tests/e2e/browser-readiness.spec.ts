import {expect, test} from "@playwright/test";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {existingDocument} from "./support/structuraFixtures";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Readiness races require controlled responses.");

test.beforeEach(async ({context, page}) => {
  await context.addCookies([
    {name: "structura_session", value: "readiness-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page);
});

test("initial detail completion preserves a search field the user already focused", async ({page}) => {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {release = resolve;});
  await page.route(`**/api/v1/documents/${existingDocument.id}`, async (route) => {
    await pending;
    await route.fallback();
  });
  await page.goto(`/inbox?document=${existingDocument.id}`);
  const search = page.getByPlaceholder("Search receipts, EOBs, warranties, claims, taxes...");
  await search.focus();
  release();
  await expect(page.locator(".inspector h2")).toHaveText(existingDocument.title);
  await expect(search).toBeFocused();
  await search.fill("preserved query");
  await expect(search).toHaveValue("preserved query");
});

test("correction notes wait for the candidate that owns the form", async ({page}) => {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {release = resolve;});
  await page.route("**/api/v1/documents/*/field-candidates?*", async (route) => {
    await pending;
    await route.fallback();
  });
  await page.goto("/review");
  const note = page.getByLabel("Correction note");
  await expect(note).toBeVisible();
  await expect(note).toBeDisabled();
  release();
  await note.fill("This note belongs to the loaded candidate.");
  await page.getByLabel("Corrected value").fill("invalid money");
  await page.getByRole("button", {name: "Correct field", exact: true}).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(note).toHaveValue("This note belongs to the loaded candidate.");
});

test("navigation works when secure-context-only crypto APIs are unavailable", async ({page}) => {
  await page.addInitScript(() => {
    Object.defineProperty(crypto, "randomUUID", {value: undefined});
    Object.defineProperty(crypto, "subtle", {value: undefined});
  });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`/inbox?document=${existingDocument.id}`);
  await page.getByRole("button", {name: "Open Viewer", exact: true}).click();
  await expect(page).toHaveURL(new RegExp(`/documents/${existingDocument.id}`));
  await page.getByRole("button", {name: "Back to Inbox", exact: true}).click();
  const key = await page.evaluate(() => window.history.state.structura.key);
  expect(key).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  expect(errors).toEqual([]);
});
