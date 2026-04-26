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
  seededCanonicalFields,
  seededFieldCandidates,
  seededFolders,
  seededReviewTasks,
  seededSearchResponse,
  seededTags,
  summaryFromDetail,
  Tag,
  updateDocumentOrganization,
  webOrigin,
} from "./structuraFixtures";

export {apiOrigin, csrfToken} from "./structuraFixtures";

type MockStructuraApiOptions = {
  csrfCookieName?: string;
  sessionCookieName?: string;
  csrfTokenValue?: string;
};

export async function mockStructuraApi(page: Page, options: MockStructuraApiOptions = {}) {
  const documents = seededDocuments();
  const folders = seededFolders();
  const tags = seededTags();
  let reviewTasks = seededReviewTasks();
  let fieldCandidates = seededFieldCandidates();
  const canonicalFields = seededCanonicalFields();
  const expectedCsrfToken = options.csrfTokenValue ?? csrfToken;
  const csrfCookieName = options.csrfCookieName ?? "structura_csrf";
  const sessionCookieName = options.sessionCookieName ?? "structura_session";

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
        json: {
          displayName: "Phase Reviewer",
          email: "phase@example.com",
          isAuthenticated: true,
          sessionCookieName,
          csrfCookieName,
        },
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
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
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
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
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
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
      ensureUploadedDocument(documents);
      await route.fulfill({
        status: 202,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {jobId: "55555555-5555-4555-8555-555555555555", status: "queued"},
      });
      return;
    }

    if (url.pathname === "/api/v1/search" && request.method() === "POST") {
      const payload = request.postDataJSON() as {query?: string; families?: string[]};
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: seededSearchResponse(String(payload.query ?? ""), payload.families?.[0]),
      });
      return;
    }

    if (url.pathname === "/api/v1/saved-searches" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {items: []},
      });
      return;
    }

    if (url.pathname === "/api/v1/saved-searches" && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
      const payload = request.postDataJSON() as {name?: string; queryText?: string};
      await route.fulfill({
        status: 201,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {
          id: "73737373-7373-4373-8373-737373737373",
          name: payload.name ?? "Saved search",
          queryText: payload.queryText ?? "",
          filters: {},
          sort: {},
          createdAt: "2026-04-26T00:00:00Z",
        },
      });
      return;
    }

    if (url.pathname === "/api/v1/review-tasks" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {items: reviewTasks.filter((task) => task.status === "open")},
      });
      return;
    }

    const candidateMatch = url.pathname.match(/^\/api\/v1\/documents\/([^/]+)\/field-candidates$/);
    if (candidateMatch && request.method() === "GET") {
      const fieldPath = url.searchParams.get("fieldPath");
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {
          items: fieldCandidates
            .filter((candidate) => candidate.documentId === candidateMatch[1])
            .filter((candidate) => !fieldPath || candidate.fieldPath === fieldPath),
        },
      });
      return;
    }

    const canonicalMatch = url.pathname.match(/^\/api\/v1\/documents\/([^/]+)\/canonical-fields$/);
    if (canonicalMatch && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {
          items: canonicalFields.filter((field) => field.documentId === canonicalMatch[1]),
        },
      });
      return;
    }

    const reviewActionMatch = url.pathname.match(/^\/api\/v1\/documents\/([^/]+)\/review-actions$/);
    if (reviewActionMatch && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
      const payload = request.postDataJSON() as {
        actionType?: string;
        metadata?: {candidateId?: string};
      };
      if (payload.actionType === "confirm_field" && payload.metadata?.candidateId) {
        fieldCandidates = fieldCandidates.map((candidate) => (
          candidate.id === payload.metadata?.candidateId
            ? {...candidate, status: "promoted"}
            : candidate
        ));
        reviewTasks = reviewTasks.map((task) => ({...task, status: "resolved"}));
      }
      if (payload.actionType === "correct_field") {
        reviewTasks = reviewTasks.map((task) => ({...task, status: "resolved"}));
      }
      if (payload.actionType === "reject_field") {
        fieldCandidates = fieldCandidates.map((candidate) => ({...candidate, status: "rejected"}));
        reviewTasks = reviewTasks.map((task) => ({...task, status: "resolved"}));
      }
      if (payload.actionType === "reclassify_document") {
        reviewTasks = reviewTasks.map((task) => ({...task, status: "resolved"}));
      }
      if (payload.actionType === "mark_done") {
        reviewTasks = reviewTasks.map((task) => ({...task, status: "resolved"}));
      }
      const response = {
        ok: true,
        reviewEventId: "93939393-9393-4393-8393-939393939393",
        ...(payload.actionType === "rerun_extraction"
          ? {jobId: "94949494-9494-4494-8494-949494949494"}
          : {}),
      };
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: response,
      });
      return;
    }

    const organizationMatch = url.pathname.match(/^\/api\/v1\/documents\/([^/]+)\/organization$/);
    if (organizationMatch && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
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
