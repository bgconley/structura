import {FormEvent, startTransition, useDeferredValue, useEffect, useState} from "react";

import {configureSecurityCookieNames, csrfToken, fetchJson} from "./api";
import {AutomationWorkbench} from "./components/AutomationWorkbench";
import {Inbox} from "./components/Inbox";
import {LoginScreen} from "./components/LoginScreen";
import {ReviewQueue} from "./components/ReviewQueue";
import {RelationshipWorkspace} from "./components/RelationshipWorkspace";
import {SearchResults} from "./components/SearchResults";
import {Sidebar} from "./components/Sidebar";
import {TopCommand} from "./components/TopCommand";
import {Viewer} from "./components/Viewer";
import {
  createFolder,
  createTag,
  listFolders,
  listTags,
  updateDocumentOrganization,
} from "./organizationApi";
import {getParseDebug} from "./parseDebugApi";
import {createSavedSearch, runSearch} from "./searchApi";
import {getCurrentSemanticAnnotation} from "./semanticAnnotationApi";
import type {
  DocumentDetail,
  DocumentListResponse,
  DocumentOrganizationWrite,
  DocumentSummary,
  EvidenceTarget,
  Folder,
  ParseDebugView,
  SearchRequest,
  SearchResponse,
  SemanticAnnotationManifest,
  SessionInfo,
  Tag,
  ViewMode,
} from "./types";

export default function App() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [activeFolderId, setActiveFolderId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [evidenceTarget, setEvidenceTarget] = useState<EvidenceTarget | null>(null);
  const [parseDebug, setParseDebug] = useState<ParseDebugView | null>(null);
  const [parseDebugError, setParseDebugError] = useState<string | null>(null);
  const [isParseDebugLoading, setIsParseDebugLoading] = useState(false);
  const [semanticAnnotation, setSemanticAnnotation] = useState<SemanticAnnotationManifest | null>(null);
  const [semanticAnnotationError, setSemanticAnnotationError] = useState<string | null>(null);
  const [isSemanticAnnotationLoading, setIsSemanticAnnotationLoading] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("inbox");
  const [activeFilter, setActiveFilter] = useState("All");
  const [query, setQuery] = useState("");
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [isSearchLoading, setIsSearchLoading] = useState(false);
  const [searchStatus, setSearchStatus] = useState<string | null>(null);
  const deferredQuery = useDeferredValue(query);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    if (!session?.isAuthenticated) {
      return;
    }
    void loadDocuments(deferredQuery, activeFolderId);
  }, [activeFolderId, deferredQuery, session?.isAuthenticated]);

  useEffect(() => {
    if (!selectedId || !session?.isAuthenticated) {
      setDetail(null);
      setParseDebug(null);
      setParseDebugError(null);
      setSemanticAnnotation(null);
      setSemanticAnnotationError(null);
      return;
    }
    let cancelled = false;
    setDetail(null);
    setParseDebug(null);
    setParseDebugError(null);
    setSemanticAnnotation(null);
    setSemanticAnnotationError(null);
    void (async () => {
      try {
        const next = await fetchJson<DocumentDetail>(`/api/v1/documents/${selectedId}`);
        if (!cancelled) {
          setDetail(next);
        }
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "Unable to load document detail");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, session?.isAuthenticated]);

  async function handleLoadParseDebug(documentId: string) {
    setIsParseDebugLoading(true);
    setParseDebugError(null);
    try {
      setParseDebug(await getParseDebug(documentId));
    } catch (exc) {
      setParseDebug(null);
      setParseDebugError(exc instanceof Error ? exc.message : "Unable to load parse debug");
    } finally {
      setIsParseDebugLoading(false);
    }
  }

  async function handleLoadSemanticAnnotation(documentId: string) {
    setIsSemanticAnnotationLoading(true);
    setSemanticAnnotationError(null);
    try {
      const response = await getCurrentSemanticAnnotation(documentId, "smart");
      setSemanticAnnotation(response.current);
      if (!response.current) {
        setSemanticAnnotationError("No Smart Parse manifest has been persisted yet.");
      }
    } catch (exc) {
      setSemanticAnnotation(null);
      setSemanticAnnotationError(
        exc instanceof Error ? exc.message : "Unable to load semantic annotation",
      );
    } finally {
      setIsSemanticAnnotationLoading(false);
    }
  }

  async function bootstrap() {
    try {
      const current = await fetchJson<SessionInfo>("/api/v1/auth/session");
      configureSecurityCookieNames(current);
      setSession(current);
      await Promise.all([loadDocuments("", activeFolderId), loadOrganization()]);
    } catch {
      setSession(null);
    } finally {
      setIsLoading(false);
    }
  }

  async function loadDocuments(search: string, folderId: string | null) {
    const params = new URLSearchParams();
    if (search.trim()) {
      params.set("q", search.trim());
    }
    if (folderId) {
      params.set("folderId", folderId);
    }
    const payload = await fetchJson<DocumentListResponse>(
      `/api/v1/documents${params.size ? `?${params}` : ""}`,
    );
    setDocuments(payload.items);
    setTotal(payload.total);
    startTransition(() => {
      setSelectedId((current) => current ?? payload.items[0]?.id ?? null);
    });
  }

  async function loadOrganization() {
    const [folderItems, tagItems] = await Promise.all([listFolders(), listTags()]);
    setFolders(folderItems);
    setTags(tagItems);
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    try {
      const created = await fetchJson<SessionInfo>("/api/v1/auth/session", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          method: "password",
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      configureSecurityCookieNames(created);
      await bootstrap();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Sign-in failed");
    }
  }

  async function uploadFile(file: File | undefined) {
    if (!file) {
      return;
    }
    const body = new FormData();
    body.set("file", file);
    body.set("source", "web_upload");
    body.set("suppliedTitle", file.name.replace(/\.[^.]+$/, ""));
    setIsUploading(true);
    setError(null);
    try {
      await fetchJson("/api/v1/documents", {
        method: "POST",
        headers: {"X-CSRF-Token": csrfToken()},
        body,
      });
      await loadDocuments(deferredQuery, activeFolderId);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleSelectFolder(folderId: string | null) {
    setActiveFolderId(folderId);
    setEvidenceTarget(null);
  }

  async function handleCreateFolder(name: string, folderKind: "manual" | "smart") {
    const trimmed = name.trim();
    if (!trimmed) {
      return;
    }
    await createFolder({
      folderKind,
      name: trimmed,
      ...(folderKind === "smart" ? {savedQuery: {review_status: ["needs_review"]}} : {}),
    });
    await loadOrganization();
  }

  async function handleCreateTag(name: string) {
    const trimmed = name.trim();
    if (!trimmed) {
      return;
    }
    await createTag({name: trimmed});
    await loadOrganization();
  }

  async function handleSaveOrganization(
    documentId: string,
    payload: DocumentOrganizationWrite,
  ) {
    const updated = await updateDocumentOrganization(documentId, payload);
    setDetail(updated);
    await loadDocuments(deferredQuery, activeFolderId);
  }

  async function reloadSelectedDocument(documentId: string | null = selectedId) {
    if (!documentId) {
      return;
    }
    const next = await fetchJson<DocumentDetail>(`/api/v1/documents/${documentId}`);
    setDetail(next);
    await loadDocuments(deferredQuery, activeFolderId);
  }

  function openDocument(documentId: string, target?: EvidenceTarget) {
    setEvidenceTarget(target ?? null);
    setParseDebug(null);
    setParseDebugError(null);
    setSemanticAnnotation(null);
    setSemanticAnnotationError(null);
    if (documentId === selectedId) {
      setDetail(null);
      void (async () => {
        try {
          setDetail(await fetchJson<DocumentDetail>(`/api/v1/documents/${documentId}`));
        } catch (exc) {
          setError(exc instanceof Error ? exc.message : "Unable to load document detail");
        }
      })();
    } else {
      setSelectedId(documentId);
    }
    setViewMode("viewer");
  }

  async function handleSearch(payload?: SearchRequest) {
    const target: SearchRequest = payload ?? {
      query,
      mode: "hybrid",
      includeDebug: true,
    };
    setViewMode("search");
    if (!target.query.trim()) {
      return;
    }
    setIsSearchLoading(true);
    setError(null);
    setSearchStatus(null);
    try {
      const next = await runSearch(target);
      setSearchResponse(next);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Search failed");
      setSearchResponse(null);
    } finally {
      setIsSearchLoading(false);
    }
  }

  async function handleSaveSearch(payload: SearchRequest) {
    if (!payload.query.trim()) {
      setSearchStatus("Enter a search query before saving.");
      return;
    }
    try {
      const saved = await createSavedSearch({
        name: `Search: ${payload.query.trim().slice(0, 72)}`,
        queryText: payload.query.trim(),
        filters: {
          mode: payload.mode ?? "hybrid",
          families: payload.families ?? [],
          folderIds: payload.folderIds ?? [],
          tags: payload.tags ?? [],
          reviewStatuses: payload.reviewStatuses ?? [],
          reviewedOnly: payload.reviewedOnly ?? false,
          dateFrom: payload.dateFrom ?? null,
          dateTo: payload.dateTo ?? null,
          amountMin: payload.amountMin ?? null,
          amountMax: payload.amountMax ?? null,
          sensitivity: payload.sensitivity ?? [],
          primaryFolderOnly: payload.primaryFolderOnly ?? false,
        },
      });
      setSearchStatus(`Saved search: ${saved.name}`);
    } catch (exc) {
      setSearchStatus(exc instanceof Error ? exc.message : "Unable to save search.");
    }
  }

  const selectedSummary = documents.find((document) => document.id === selectedId) ?? documents[0];
  const selected = detail ?? selectedSummary ?? null;

  if (isLoading) {
    return <div className="boot-screen">Loading Structura...</div>;
  }

  if (!session?.isAuthenticated) {
    return <LoginScreen error={error} onSubmit={handleLogin} />;
  }

  return (
    <div className="app-shell">
      <Sidebar
        total={total}
        active={viewMode}
        onNavigate={(view) => setViewMode(view)}
      />
      <main className="app-main">
        <TopCommand
          query={query}
          setQuery={setQuery}
          onSubmitSearch={() => void handleSearch()}
          isUploading={isUploading}
          uploadFile={uploadFile}
        />
        {viewMode === "automation" ? (
          <AutomationWorkbench />
        ) : viewMode === "relationships" || viewMode === "timelines" ? (
          <RelationshipWorkspace
            mode={viewMode}
            documents={documents}
            onOpenDocument={(documentId) => openDocument(documentId)}
          />
        ) : viewMode === "review" ? (
          <ReviewQueue
            onOpenDocument={openDocument}
          />
        ) : viewMode === "search" ? (
          <SearchResults
            query={query}
            setQuery={setQuery}
            response={searchResponse}
            isLoading={isSearchLoading}
            error={error}
            status={searchStatus}
            folders={folders}
            tags={tags}
            onSubmit={handleSearch}
            onSaveSearch={handleSaveSearch}
            onOpenDocument={openDocument}
          />
        ) : viewMode === "viewer" && selected ? (
          <Viewer
            document={detail}
            summary={selectedSummary}
            evidenceTarget={evidenceTarget}
            onBack={() => setViewMode("inbox")}
            onOpenReview={() => setViewMode("review")}
            folders={folders}
            tags={tags}
            onSaveOrganization={handleSaveOrganization}
            documents={documents}
            onOpenDocument={openDocument}
            onRelationshipsChanged={() => reloadSelectedDocument(selectedId)}
            parseDebug={parseDebug}
            parseDebugError={parseDebugError}
            isParseDebugLoading={isParseDebugLoading}
            onLoadParseDebug={handleLoadParseDebug}
            semanticAnnotation={semanticAnnotation}
            semanticAnnotationError={semanticAnnotationError}
            isSemanticAnnotationLoading={isSemanticAnnotationLoading}
            onLoadSemanticAnnotation={handleLoadSemanticAnnotation}
          />
        ) : (
          <Inbox
            documents={documents}
            total={total}
            selectedId={selectedId}
            selected={selected}
            detail={detail}
            error={error}
            activeFilter={activeFilter}
            setActiveFilter={setActiveFilter}
            setSelectedId={(documentId) => {
              setEvidenceTarget(null);
              setSelectedId(documentId);
            }}
            openViewer={() => setViewMode("viewer")}
            uploadFile={uploadFile}
            folders={folders}
            tags={tags}
            activeFolderId={activeFolderId}
            onSelectFolder={handleSelectFolder}
            onCreateFolder={handleCreateFolder}
            onCreateTag={handleCreateTag}
            onSaveOrganization={handleSaveOrganization}
          />
        )}
      </main>
    </div>
  );
}
