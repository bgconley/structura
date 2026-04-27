import {expect, Page} from "@playwright/test";

import {
  apiOrigin,
  Contact,
  createContact,
  createFilingRule,
  createFolder,
  createTag,
  createWatchedFolder,
  csrfToken,
  DocumentOrganizationWrite,
  ensureUploadedDocument,
  Folder,
  previewSvg,
  seededCanonicalFields,
  seededContacts,
  seededDocuments,
  seededFilingRules,
  seededFilingSuggestions,
  seededFieldCandidates,
  seededFolders,
  seededDeadlines,
  seededReviewTasks,
  seededRelationships,
  seededSearchResponse,
  seededSmartViews,
  seededTags,
  seededTimeline,
  seededWatchedFolders,
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
  const contacts = seededContacts();
  const filingRules = seededFilingRules();
  let filingSuggestions = seededFilingSuggestions();
  let relationships = seededRelationships();
  const deadlines = seededDeadlines();
  const timeline = seededTimeline();
  const smartViews = seededSmartViews();
  const watchedFolders = seededWatchedFolders();
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
      const payload = request.postDataJSON() as {
        query?: string;
        families?: string[];
        includeVisual?: boolean;
        mode?: string;
      };
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: seededSearchResponse(
          String(payload.query ?? ""),
          payload.families?.[0],
          Boolean(payload.includeVisual || payload.mode === "visual"),
        ),
      });
      return;
    }

    if (url.pathname === "/api/v1/relationships" && request.method() === "GET") {
      const documentId = url.searchParams.get("documentId");
      const status = url.searchParams.get("status");
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {
          items: relationships
            .filter((item) => !documentId || item.documentId === documentId || item.relatedDocumentId === documentId)
            .filter((item) => !status || item.status === status)
            .map((item) => relationshipForDocument(item, documentId ?? item.documentId)),
        },
      });
      return;
    }

    if (url.pathname === "/api/v1/relationships" && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
      const payload = request.postDataJSON() as {
        fromDocumentId: string;
        toDocumentId: string;
        relationshipType: string;
        comment?: string;
      };
      const related = documents.get(payload.toDocumentId);
      const relationship = {
        id: `23272727-2727-4727-8727-${String(relationships.length + 1).padStart(12, "2")}`,
        documentId: payload.fromDocumentId,
        relatedDocumentId: payload.toDocumentId,
        relatedTitle: related?.title ?? "Related document",
        relationshipType: payload.relationshipType,
        status: "confirmed" as const,
        direction: "from" as const,
        confidence: 1,
        sourceEngine: "human",
        evidence: [{pageNumber: 1, sourceEngine: "human", sourceText: payload.comment ?? "Manual relationship."}],
        comment: payload.comment,
        reviewTaskId: null,
        createdAt: "2026-04-26T13:00:00Z",
      };
      relationships = relationships.filter((item) => item.id !== relationship.id);
      relationships.unshift(relationship);
      await route.fulfill({
        status: 201,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: relationship,
      });
      return;
    }

    const relationshipDecisionMatch = url.pathname.match(/^\/api\/v1\/relationships\/([^/]+)\/(accept|reject)$/);
    if (relationshipDecisionMatch && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
      const status = relationshipDecisionMatch[2] === "accept" ? "confirmed" as const : "rejected" as const;
      relationships = relationships.map((item) => (
        item.id === relationshipDecisionMatch[1] ? {...item, status} : item
      ));
      const relationship = relationships.find((item) => item.id === relationshipDecisionMatch[1]);
      await route.fulfill({
        status: relationship ? 200 : 404,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: relationship ?? {detail: "Relationship not found"},
      });
      return;
    }

    if (url.pathname === "/api/v1/deadlines" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {items: deadlines},
      });
      return;
    }

    if (url.pathname === "/api/v1/timeline" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {items: timeline},
      });
      return;
    }

    if (url.pathname === "/api/v1/smart-views" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {items: smartViews},
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

    if (url.pathname === "/api/v1/contacts" && request.method() === "GET") {
      const query = url.searchParams.get("q")?.toLowerCase() ?? "";
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {
          items: contacts.filter((contact) => (
            !query
            || contact.displayName.toLowerCase().includes(query)
            || contact.aliases.some((alias) => alias.toLowerCase().includes(query))
          )),
        },
      });
      return;
    }

    if (url.pathname === "/api/v1/contacts" && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
      const contact = createContact(request.postDataJSON() as Partial<Contact>, contacts.length);
      contacts.unshift(contact);
      await route.fulfill({
        status: 201,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: contact,
      });
      return;
    }

    if (url.pathname === "/api/v1/contact-merge-suggestions" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {items: []},
      });
      return;
    }

    if (url.pathname === "/api/v1/filing-rules" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {items: filingRules},
      });
      return;
    }

    if (url.pathname === "/api/v1/filing-rules" && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
      const rule = createFilingRule(request.postDataJSON(), filingRules.length);
      filingRules.unshift(rule);
      await route.fulfill({
        status: 201,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: rule,
      });
      return;
    }

    const dryRunMatch = url.pathname.match(/^\/api\/v1\/filing-rules\/([^/]+)\/dry-run$/);
    if (dryRunMatch && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {
          items: [{
            runId: "20202020-2020-4620-8620-202020202020",
            ruleId: dryRunMatch[1],
            documentId: "11111111-1111-4111-8111-111111111111",
            matched: true,
            conditions: [
              {
                field: "document_family",
                op: "eq",
                expected: "medical_eob",
                observed: "medical_eob",
                matched: true,
              },
            ],
            proposedActions: [{type: "add_tag", tag: "insurance"}],
            blockedActions: [],
            appliedActions: [],
            reviewRequired: true,
            safetyReasons: ["rule_requires_review", "medical_eob"],
            explanation: {},
          }],
        },
      });
      return;
    }

    if (url.pathname === "/api/v1/filing-suggestions" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {items: filingSuggestions},
      });
      return;
    }

    const acceptSuggestionMatch = url.pathname.match(/^\/api\/v1\/filing-suggestions\/([^/]+)\/accept$/);
    if (acceptSuggestionMatch && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
      filingSuggestions = filingSuggestions.filter((item) => item.runId !== acceptSuggestionMatch[1]);
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {
          runId: acceptSuggestionMatch[1],
          documentId: "11111111-1111-4111-8111-111111111111",
          matched: true,
          conditions: [],
          proposedActions: [],
          blockedActions: [],
          appliedActions: [],
          reviewRequired: false,
          safetyReasons: [],
          explanation: {},
          status: "accepted",
        },
      });
      return;
    }

    const decisionSuggestionMatch = url.pathname.match(
      /^\/api\/v1\/filing-suggestions\/([^/]+)\/(reject|defer)$/,
    );
    if (decisionSuggestionMatch && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
      filingSuggestions = filingSuggestions.filter((item) => item.runId !== decisionSuggestionMatch[1]);
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {ok: true},
      });
      return;
    }

    if (url.pathname === "/api/v1/watched-folders" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {items: watchedFolders},
      });
      return;
    }

    if (url.pathname === "/api/v1/watched-folders" && request.method() === "POST") {
      expect(request.headers()["x-csrf-token"]).toBe(expectedCsrfToken);
      const watched = createWatchedFolder(request.postDataJSON(), watchedFolders.length);
      watchedFolders.unshift(watched);
      await route.fulfill({
        status: 201,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: watched,
      });
      return;
    }

    if (url.pathname === "/api/v1/import-status" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: {
          items: watchedFolders.map((folder) => ({
            watchedFolderId: folder.id,
            path: folder.path,
            enabled: folder.enabled,
            lastScanAt: folder.lastScanAt,
            acceptedCount: 3,
            rejectedCount: 1,
            skippedCount: 2,
          })),
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
      const payload = document
        ? {...document, relationships: relationshipsForDocument(relationships, document.id)}
        : undefined;
      await route.fulfill({
        status: document ? 200 : 404,
        headers: {"Content-Type": "application/json", ...corsHeaders},
        json: payload ?? {detail: "Document not found"},
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

function relationshipsForDocument(
  relationships: ReturnType<typeof seededRelationships>,
  documentId: string,
) {
  return relationships
    .filter((item) => item.status !== "rejected")
    .filter((item) => item.documentId === documentId || item.relatedDocumentId === documentId)
    .map((item) => relationshipForDocument(item, documentId));
}

function relationshipForDocument(
  relationship: ReturnType<typeof seededRelationships>[number],
  documentId: string,
) {
  if (relationship.documentId === documentId) {
    return relationship;
  }
  return {
    ...relationship,
    documentId,
    relatedDocumentId: relationship.documentId,
    relatedTitle: "Existing Warranty",
    direction: "to" as const,
  };
}
