import {expect, Page, test} from "@playwright/test";
import {writeFile} from "node:fs/promises";

type DocumentSummary = {
  id: string;
  title: string;
  family: string;
  lifecycleState: string;
  reviewStatus: string;
  createdAt: string;
  thumbnailUrl?: string;
  folderPaths?: string[];
};

type DocumentDetail = DocumentSummary & {
  pages: Array<{pageNumber: number; imageUrl?: string}>;
  assets: Array<{id: string; assetRole: string; mimeType: string; assetUrl: string; sha256?: string}>;
  fields: unknown[];
  lineItems: unknown[];
  extractions: unknown[];
  relationships: unknown[];
  tags: string[];
};

const apiOrigin = "http://localhost:8000";
const webOrigin = "http://localhost:4173";
const csrfToken = "phase1-browser-csrf";

const uploadedDocument: DocumentSummary = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "phase1-browser-fixture",
  family: "uncategorized",
  lifecycleState: "active",
  reviewStatus: "needs_review",
  createdAt: "2026-04-25T12:00:00Z",
  thumbnailUrl: "/api/v1/assets/22222222-2222-4222-8222-222222222222",
  folderPaths: [],
};

const existingDocument: DocumentSummary = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  title: "Existing Warranty",
  family: "warranty",
  lifecycleState: "active",
  reviewStatus: "needs_review",
  createdAt: "2026-04-25T11:00:00Z",
  thumbnailUrl: "/api/v1/assets/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  folderPaths: ["/Home"],
};

test("Phase 1 Inbox to Viewer workflow uses protected asset URLs", async ({page, context}, testInfo) => {
  const documents = [existingDocument];
  await context.addCookies([
    {name: "structura_session", value: "phase1-session", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"},
  ]);
  await mockStructuraApi(page, documents);

  await page.goto("/");
  await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();
  await expect(page.getByRole("row", {name: /Existing Warranty/})).toBeVisible();

  const uploadPath = testInfo.outputPath("phase1-browser-fixture.pdf");
  await writeFile(uploadPath, "%PDF-1.7\n% Phase 1 browser fixture\n%%EOF\n");
  await page.locator(".top-command input[type='file']").setInputFiles(uploadPath);
  await expect(page.getByRole("row", {name: /phase1-browser-fixture/})).toBeVisible();

  await page.getByRole("row", {name: /phase1-browser-fixture/}).click();
  await expect(page.locator(".inspector")).toContainText("phase1-browser-fixture");
  await expect(page.locator(".inspector")).toContainText("SHA-256");
  await page.screenshot({path: testInfo.outputPath("inbox-playwright-screenshot.png"), fullPage: true});

  await page.locator(".page-heading").getByRole("button", {name: "Open Viewer"}).click();
  await expect(page.getByRole("heading", {name: "Document Viewer"})).toBeVisible();
  await expect(page.locator(".rendered-page img")).toHaveAttribute(
    "src",
    `${apiOrigin}/api/v1/assets/33333333-3333-4333-8333-333333333333`,
  );
  await expect(page.getByRole("link", {name: "Download original"})).toHaveAttribute(
    "href",
    `${apiOrigin}/api/v1/assets/44444444-4444-4444-8444-444444444444`,
  );
  await page.screenshot({path: testInfo.outputPath("viewer-playwright-screenshot.png"), fullPage: true});

  await page.getByRole("button", {name: "Back to Inbox"}).click();
  await expect(page.getByRole("heading", {name: "Document Operations"})).toBeVisible();
});

async function mockStructuraApi(page: Page, documents: DocumentSummary[]) {
  await page.route(`${apiOrigin}/api/v1/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const corsHeaders = {
      "Access-Control-Allow-Credentials": "true",
      "Access-Control-Allow-Headers": "accept,content-type,x-csrf-token",
      "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
      "Access-Control-Allow-Origin": webOrigin,
    };

    if (request.method() === "OPTIONS") {
      await route.fulfill({status: 204, headers: corsHeaders});
      return;
    }

    if (url.pathname === "/api/v1/auth/session") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {displayName: "Phase 1 Reviewer", email: "phase1@example.com", isAuthenticated: true},
      });
      return;
    }

    if (url.pathname === "/api/v1/documents" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {items: documents, total: documents.length},
      });
      return;
    }

    if (url.pathname === "/api/v1/documents" && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(csrfToken);
      if (!documents.some((document) => document.id === uploadedDocument.id)) {
        documents.unshift(uploadedDocument);
      }
      await route.fulfill({
        status: 202,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {jobId: "55555555-5555-4555-8555-555555555555", status: "queued"},
      });
      return;
    }

    if (url.pathname === `/api/v1/documents/${uploadedDocument.id}`) {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: uploadedDetail(),
      });
      return;
    }

    if (url.pathname === `/api/v1/documents/${existingDocument.id}`) {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: existingDetail(),
      });
      return;
    }

    if (url.pathname.startsWith("/api/v1/assets/")) {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "image/svg+xml", "Cache-Control": "private, no-store", ...corsHeaders},
        body: previewSvg(url.pathname.includes("4444") ? "Original asset" : "Preview asset"),
      });
      return;
    }

    await route.fulfill({status: 404, headers: corsHeaders, body: "not found"});
  });
}

function uploadedDetail(): DocumentDetail {
  return {
    ...uploadedDocument,
    pages: [{pageNumber: 1, imageUrl: "/api/v1/assets/33333333-3333-4333-8333-333333333333"}],
    assets: [
      {
        id: "44444444-4444-4444-8444-444444444444",
        assetRole: "original",
        mimeType: "application/pdf",
        assetUrl: "/api/v1/assets/44444444-4444-4444-8444-444444444444",
        sha256: "d".repeat(64),
      },
      {
        id: "33333333-3333-4333-8333-333333333333",
        assetRole: "page_image",
        mimeType: "image/svg+xml",
        assetUrl: "/api/v1/assets/33333333-3333-4333-8333-333333333333",
      },
    ],
    fields: [],
    lineItems: [],
    extractions: [],
    relationships: [],
    tags: [],
  };
}

function existingDetail(): DocumentDetail {
  return {
    ...existingDocument,
    pages: [{pageNumber: 1, imageUrl: "/api/v1/assets/cccccccc-cccc-4ccc-8ccc-cccccccccccc"}],
    assets: [
      {
        id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        assetRole: "original",
        mimeType: "application/pdf",
        assetUrl: "/api/v1/assets/dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        sha256: "a".repeat(64),
      },
    ],
    fields: [],
    lineItems: [],
    extractions: [],
    relationships: [],
    tags: ["Home"],
  };
}

function previewSvg(label: string): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="960" height="1240" viewBox="0 0 960 1240">
    <rect width="960" height="1240" fill="#f7f9fc"/>
    <rect x="120" y="90" width="720" height="1060" rx="8" fill="#fff" stroke="#cbd5e1"/>
    <text x="180" y="220" font-family="Arial" font-size="38" fill="#182235">${label}</text>
  </svg>`;
}
