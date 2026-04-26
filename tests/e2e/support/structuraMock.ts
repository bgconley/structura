import {expect, Page} from "@playwright/test";

import {
  apiOrigin,
  createFolder,
  createTag,
  csrfToken,
  DocumentOrganizationWrite,
  ensureUploadedDocument,
  Folder,
  previewSvg,
  seededDocuments,
  seededFolders,
  seededTags,
  summaryFromDetail,
  Tag,
  updateDocumentOrganization,
  webOrigin,
} from "./structuraFixtures";

export {apiOrigin, csrfToken} from "./structuraFixtures";

export async function mockStructuraApi(page: Page) {
  const documents = seededDocuments();
  const folders = seededFolders();
  const tags = seededTags();

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
        json: {displayName: "Phase Reviewer", email: "phase@example.com", isAuthenticated: true},
      });
      return;
    }

    if (url.pathname === "/api/v1/folders" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {items: folders},
      });
      return;
    }

    if (url.pathname === "/api/v1/folders" && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(csrfToken);
      const folder = createFolder(request.postDataJSON() as Partial<Folder>, folders.length);
      folders.push(folder);
      await route.fulfill({
        status: 201,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: folder,
      });
      return;
    }

    if (url.pathname === "/api/v1/tags" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {items: tags},
      });
      return;
    }

    if (url.pathname === "/api/v1/tags" && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(csrfToken);
      const tag = createTag(request.postDataJSON() as Partial<Tag>, tags.length);
      tags.push(tag);
      await route.fulfill({
        status: 201,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: tag,
      });
      return;
    }

    if (url.pathname === "/api/v1/documents" && request.method() === "GET") {
      const query = url.searchParams.get("q")?.toLowerCase() ?? "";
      const folderId = url.searchParams.get("folderId");
      const items = Array.from(documents.values())
        .filter((document) => !query || document.title.toLowerCase().includes(query))
        .filter((document) => !folderId || document.folderIds.includes(folderId))
        .map(summaryFromDetail);
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {items, total: items.length},
      });
      return;
    }

    if (url.pathname === "/api/v1/documents" && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(csrfToken);
      ensureUploadedDocument(documents);
      await route.fulfill({
        status: 202,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {jobId: "55555555-5555-4555-8555-555555555555", status: "queued"},
      });
      return;
    }

    const organizationMatch = url.pathname.match(/^\/api\/v1\/documents\/([^/]+)\/organization$/);
    if (organizationMatch && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(csrfToken);
      const document = documents.get(organizationMatch[1]);
      if (!document) {
        await route.fulfill({status: 404, headers: corsHeaders, body: "not found"});
        return;
      }
      const result = updateDocumentOrganization(
        document,
        request.postDataJSON() as DocumentOrganizationWrite,
        folders,
        tags,
      );
      if (!result.ok) {
        await route.fulfill({
          status: 422,
          headers: {"Content-Type": "application/json", ...corsHeaders},
          json: {detail: result.error},
        });
        return;
      }
      documents.set(result.document.id, result.document);
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: result.document,
      });
      return;
    }

    const parseDebugMatch = url.pathname.match(/^\/api\/v1\/documents\/([^/]+)\/parse-debug$/);
    if (parseDebugMatch && request.method() === "GET") {
      const document = documents.get(parseDebugMatch[1]);
      await route.fulfill({
        status: document ? 200 : 404,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: document
          ? {
              document: {
                id: document.id,
                title: document.title,
                pageCount: document.pages.length,
                metadata: {phase3: {parseStatus: "succeeded"}},
              },
              artifacts: [
                {
                  id: "99999999-9999-4999-8999-999999999999",
                  assetRole: "docling_json",
                  assetUrl: "/api/v1/assets/99999999-9999-4999-8999-999999999999",
                  modelName: "docling-fixture",
                  modelVersion: "phase3",
                  sha256: "9".repeat(64),
                },
              ],
              pages: [
                {
                  pageNumber: 1,
                  imageUrl: document.pages[0]?.imageUrl,
                  textPreview: "Phase 3 canonical parse text for browser diagnostics.",
                },
              ],
              elements: [{id: "element-1", elementType: "paragraph"}],
              tables: [{id: "table-1", tableIndex: 1}],
              chunks: [{id: "chunk-1", chunkIndex: 1}],
              jobs: [{jobId: "job-1", jobType: "docling_convert", status: "succeeded"}],
            }
          : {detail: "Document not found"},
      });
      return;
    }

    const detailMatch = url.pathname.match(/^\/api\/v1\/documents\/([^/]+)$/);
    if (detailMatch && request.method() === "GET") {
      const document = documents.get(detailMatch[1]);
      await route.fulfill({
        status: document ? 200 : 404,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: document ?? {detail: "Document not found"},
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

  return {documents, folders, tags};
}
