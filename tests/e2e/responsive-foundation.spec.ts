import {expect, test, type Locator, type Page} from "@playwright/test";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {existingDocument, seededDocuments, summaryFromDetail} from "./support/structuraFixtures";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Responsive edge states use an isolated deterministic corpus.");

async function noPageOverflow(page: Page) {
  expect(await page.evaluate(() => ({content: document.documentElement.scrollWidth, viewport: innerWidth})))
    .toEqual({content: page.viewportSize()!.width, viewport: page.viewportSize()!.width});
}

async function fitsWidth(control: Locator, width: number, minimumHeight = 0) {
  const box = await control.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
  expect(box!.height).toBeGreaterThanOrEqual(minimumHeight);
}

test.beforeEach(async ({page, context}) => {
  await context.addCookies([{name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"}]);
  await mockStructuraApi(page);
});

for (const width of [1440, 1280, 768, 390]) {
  test(`enabled workspaces fit ${width}px and retain their primary actions`, async ({page}, info) => {
    await page.setViewportSize({width, height: width < 760 ? 844 : 960});
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    for (const [path, heading, action] of [
      ["/inbox", "Document Operations", "Open Viewer"],
      ["/search?q=warranty", "Corpus Search", "Search corpus"],
      ["/review", "Review Queue", "Correct field"],
      ["/automation", "Automation Workbench", "Create contact"],
      ["/relationships", "Relationship Workbench", "Generate suggestions"],
      ["/timelines", "Document Timelines", "Generate suggestions"],
      [`/documents/${existingDocument.id}`, "Document Viewer", "Open review"],
    ]) {
      await page.goto(path);
      await expect(page.getByRole("heading", {name: heading, exact: true})).toBeVisible();
      await noPageOverflow(page);
      for (const control of await page.locator(".top-command > .command-button:visible").all()) await fitsWidth(control, width, 32);
      if (path === "/inbox") await expect(page.getByRole("button", {name: action, exact: true})).toBeEnabled();
      if (!path.includes("relationships") && !path.includes("timelines")) {
        await fitsWidth(page.getByRole("button", {name: action, exact: true}), width, 32);
      }
      await page.screenshot({path: info.outputPath(`${heading.toLowerCase().replaceAll(" ", "-")}-${width}.png`), fullPage: width < 1000});
    }
    expect(errors).toEqual([]);
  });
}

test("reference viewport is 1440 × 960 and title/status columns stay readable", async ({page}, info) => {
  expect(page.viewportSize()).toEqual({width: 1440, height: 960});
  const title = "Household warranty and extended service coverage — annual appliance inspection and replacement terms";
  const documents = [...seededDocuments().values()].map((document) => summaryFromDetail(document));
  documents[0].title = title;
  await page.route((url) => url.pathname === "/api/v1/documents", (route) => route.fulfill({headers: {"Access-Control-Allow-Origin": "http://localhost:4173", "Access-Control-Allow-Credentials": "true"}, json: {items: documents, total: documents.length}}));
  await page.goto("/inbox");
  const row = page.getByRole("row", {name: new RegExp(title)});
  await expect(row).toBeVisible();
  expect((await page.locator(".sidebar").boundingBox())!.width).toBe(176);
  expect((await page.locator(".top-command").boundingBox())!.height).toBe(56);
  const readability = await row.locator(".doc-cell strong, .review-chip").evaluateAll((nodes) => nodes.map((node) => {
    const element = node as HTMLElement;
    return {clipped: element.scrollWidth > element.clientWidth || element.scrollHeight > element.clientHeight,
      size: Number.parseFloat(getComputedStyle(element).fontSize)};
  }));
  expect(readability).toEqual([{clipped: false, size: 12}, {clipped: false, size: 11}]);
  await fitsWidth(row.locator(".review-chip"), 1440);
  const scroller = page.getByRole("region", {name: "Document activity, scroll for more columns"});
  await scroller.focus(); await page.keyboard.press("End");
  await noPageOverflow(page);
  await page.screenshot({path: info.outputPath("inbox-long-title-1440.png"), fullPage: true});
});

test("fresh mobile navigation, keyboard search, upload and document return are usable", async ({page}, info) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/inbox");
  await expect(page.getByRole("button", {name: "Open Viewer", exact: true})).toBeEnabled();
  await page.getByRole("link", {name: "Skip to workspace"}).focus();
  await expect(page.getByRole("link", {name: "Skip to workspace"})).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#route-content")).toBeFocused();
  const menu = page.getByRole("button", {name: "Menu", exact: true});
  await menu.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("navigation", {name: "Primary"})).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeFocused();
  await expect(page.getByRole("navigation", {name: "Primary"})).toBeHidden();
  for (const [label, heading] of [["Search", "Corpus Search"], ["Automation", "Automation Workbench"],
    ["Review Queue", "Review Queue"], ["Relationships", "Relationship Workbench"], ["Timelines", "Document Timelines"], ["Inbox", "Document Operations"]]) {
    await menu.click();
    await page.getByRole("navigation", {name: "Primary"}).getByRole("button", {name: new RegExp(`^${label}`)}).click();
    await expect(page.getByRole("heading", {name: heading, exact: true})).toBeVisible();
    await expect(menu).toHaveAttribute("aria-expanded", "false");
  }
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("textbox", {name: "Search documents", exact: true})).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.locator('.top-command input[type="file"]')).toBeFocused();
  const chooser = page.waitForEvent("filechooser"); await page.keyboard.press("Enter");
  await chooser;
  const row = page.getByRole("row", {name: /Existing Warranty/});
  await row.focus(); await page.keyboard.press("Enter");
  await page.getByRole("button", {name: "Selected document details", exact: true}).click();
  await expect(page.getByRole("link", {name: "Skip to workspace"})).not.toBeFocused();
  await expect(page.locator(".inspector")).toBeVisible();
  await noPageOverflow(page);
  await page.screenshot({path: info.outputPath("inbox-details-mobile.png"), fullPage: true});
  await page.locator("#inbox-details-open-viewer").click();
  await page.getByRole("button", {name: "Back to Inbox", exact: true}).click();
  await expect(page.locator(".inspector")).toBeVisible();
  await expect(page.locator("#inbox-details-open-viewer")).toBeFocused();
  await page.getByRole("button", {name: "Documents", exact: true}).click();
  await expect(row).toBeFocused();
  await page.getByRole("button", {name: "Open Viewer", exact: true}).click();
  await page.getByRole("button", {name: "Back to Inbox", exact: true}).click();
  await expect(page.getByRole("button", {name: "Open Viewer", exact: true})).toBeFocused();
  await noPageOverflow(page);
});
