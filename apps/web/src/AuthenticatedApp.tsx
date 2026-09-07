import {useEffect, useRef, useState} from "react";
import {ApiError, csrfToken, fetchJson} from "./api";
import {defaultRoute, parseAppRoute, routeLabel, routeUrl, type AppRoute} from "./appRoutes";
import {AutomationWorkbench} from "./components/AutomationWorkbench";
import {Inbox} from "./components/Inbox";
import {ReviewQueue} from "./components/ReviewQueue";
import {RelationshipWorkspace} from "./components/RelationshipWorkspace";
import {SearchResults} from "./components/SearchResults";
import {Sidebar} from "./components/Sidebar";
import {TopCommand} from "./components/TopCommand";
import {Viewer} from "./components/Viewer";
import {createFolder, createTag, listFolders, listTags, updateDocumentOrganization} from "./organizationApi";
import {defaultSearchFilterState} from "./searchFilters";
import {useAppNavigation} from "./useAppNavigation";
import {useCorpusSearch} from "./useCorpusSearch";
import {useDocumentList} from "./useDocumentList";
import {useDocumentWorkspace} from "./useDocumentWorkspace";
import {useKeyedRequest} from "./useKeyedRequest";
import type {DocumentOrganizationWrite, EvidenceTarget, SessionInfo, ViewMode} from "./types";

export function AuthenticatedApp({session, onSignOut, sessionError}: {
  session: SessionInfo;
  onSignOut: () => Promise<void>;
  sessionError: string | null;
}) {
  const navigation = useAppNavigation();
  const {route, entry, navigate} = navigation;
  const previousRoutes = useRef(new Map<string, AppRoute>());
  if (route.view !== "viewer" && route.view !== "unavailable") previousRoutes.current.set(route.view, route);
  const inboxRoute = previousRoutes.current.get("inbox");
  const inboxQuery = inboxRoute?.view === "inbox" ? inboxRoute.query ?? "" : "";
  const folderId = inboxRoute?.view === "inbox" ? inboxRoute.folderId : undefined;
  const list = useDocumentList(inboxQuery, folderId);
  const organization = useKeyedRequest("organization", async () => {
    const [folders, tags] = await Promise.all([listFolders(), listTags()]);
    return {folders, tags};
  });
  const folders = organization.data?.folders ?? [];
  const tags = organization.data?.tags ?? [];
  const selectedId = route.view === "viewer" || route.view === "inbox" ? route.documentId ?? null : null;
  const workspace = useDocumentWorkspace(selectedId, entry.key);
  const search = useCorpusSearch(route.view === "search" ? route : null, entry.key);
  const [globalQuery, setGlobalQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("All");
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedSummary = list.documents.find((document) => document.id === selectedId);
  const detail = workspace.detail.data;
  const selected = workspace.detail.error ? null : detail ?? selectedSummary ?? null;
  const currentSelection = useRef(selectedId);
  currentSelection.current = selectedId;

  useEffect(() => {
    if (route.view === "inbox" && !route.documentId && !list.loading && list.documents[0]) {
      navigate({...route, documentId: list.documents[0].id}, {replace: true});
    }
  }, [route, list.loading, list.documents]);

  useEffect(() => {
    const ready = route.view === "viewer" ? !workspace.detail.loading
      : route.view === "search" ? !search.loading : route.view === "inbox" ? !list.loading && !workspace.detail.loading : true;
    if (route.view !== "review") navigation.restore(ready);
  });

  function navigateView(view: Exclude<ViewMode, "viewer">) {
    navigate(previousRoutes.current.get(view) ?? defaultRoute(view));
  }

  function openDocument(documentId: string, target?: EvidenceTarget) {
    const returnTo = route.view === "viewer" ? route.returnTo : routeUrl(route);
    navigate({view: "viewer", documentId, page: target?.pageNumber ?? 1, returnTo}, {evidence: target});
  }

  async function uploadFile(file: File | undefined) {
    if (!file) return;
    const body = new FormData();
    body.set("file", file);
    body.set("source", "web_upload");
    body.set("suppliedTitle", file.name.replace(/\.[^.]+$/, ""));
    setIsUploading(true);
    setError(null);
    try {
      await fetchJson("/api/v1/documents", {method: "POST", headers: {"X-CSRF-Token": csrfToken()}, body});
      await list.reload();
    } catch (exc) { setError(exc instanceof Error ? exc.message : "Upload failed"); }
    finally { setIsUploading(false); }
  }

  async function handleCreateFolder(name: string, folderKind: "manual" | "smart") {
    if (!name.trim()) return;
    await createFolder({folderKind, name: name.trim(),
      ...(folderKind === "smart" ? {savedQuery: {review_status: ["needs_review"]}} : {})});
    await organization.reload();
  }
  async function handleCreateTag(name: string) {
    if (!name.trim()) return;
    await createTag({name: name.trim()});
    await organization.reload();
  }
  async function handleSaveOrganization(documentId: string, payload: DocumentOrganizationWrite) {
    await updateDocumentOrganization(documentId, payload);
    if (currentSelection.current === documentId) await workspace.detail.reload();
    await list.reload();
  }
  async function reloadSelectedDocument() {
    await Promise.all([workspace.detail.reload(), list.reload()]);
  }
  async function submitSearch() {
    const next: AppRoute = route.view === "search"
      ? {view: "search", query: search.query, filters: {...search.filters}, submitted: true}
      : {view: "search", query: route.view === "inbox" ? inboxQuery : globalQuery,
        filters: {...defaultSearchFilterState}, submitted: true};
    if (routeUrl(next) === routeUrl(route)) await search.reload();
    else navigate(next);
  }
  const commandQuery = route.view === "search" ? search.query : route.view === "inbox" ? inboxQuery : globalQuery;
  function setCommandQuery(value: string) {
    if (route.view === "search") search.setQuery(value);
    else if (route.view === "inbox") navigate({...route, query: value, documentId: undefined}, {replace: true});
    else setGlobalQuery(value);
  }
  const returnRoute = route.view === "viewer" ? parseAppRoute(route.returnTo) : defaultRoute("inbox");

  return (
    <div className="app-shell">
      <Sidebar total={list.total} active={route.view} onNavigate={navigateView} />
      <main className="app-main">
        <TopCommand session={session} onSignOut={onSignOut} sessionError={sessionError}
          query={commandQuery} setQuery={setCommandQuery} onSubmitSearch={() => void submitSearch()}
          isUploading={isUploading} uploadFile={uploadFile} />
        <div id="route-content" tabIndex={-1}>
          {route.view === "unavailable" ? (
            <RouteNotice message={route.message} onBack={() => navigate(defaultRoute("inbox"))} />
          ) : route.view === "automation" ? <AutomationWorkbench />
          : route.view === "relationships" || route.view === "timelines" ? (
            <RelationshipWorkspace mode={route.view} documents={list.documents} onOpenDocument={openDocument} />
          ) : route.view === "review" ? (
            <ReviewQueue onReady={() => navigation.restore(true)} selectedTaskId={route.taskId} documentId={route.documentId}
              onSelectTask={(taskId) => navigate({...route, taskId}, {replace: true})} onOpenDocument={openDocument} />
          ) : route.view === "search" ? (
            <SearchResults query={search.query} setQuery={search.setQuery} filters={search.filters}
              setFilters={search.setFilters} submitted={search.submitted} response={search.data}
              isLoading={search.loading} error={search.error?.message ?? null} status={search.status}
              folders={folders} tags={tags} onSubmit={submitSearch} onSaveSearch={search.save} onOpenDocument={openDocument} />
          ) : route.view === "viewer" ? (
            workspace.detail.loading ? <RouteNotice message="Loading document…" loading />
            : !detail ? <RouteNotice message={documentError(workspace.detail.error)}
              onRetry={() => void workspace.detail.reload()} onBack={() => navigation.returnTo(returnRoute)} backLabel={`Back to ${routeLabel(returnRoute)}`} />
            : <Viewer document={detail} evidenceTarget={navigation.evidenceTarget} pageNumber={route.page}
              onPageChange={(page) => navigate({...route, page}, {replace: true})}
              onBack={() => navigation.returnTo(returnRoute)} backLabel={`Back to ${routeLabel(returnRoute)}`}
              onOpenReview={() => navigate({view: "review", documentId: detail.id})}
              folders={folders} tags={tags} onSaveOrganization={handleSaveOrganization}
              documents={list.documents} onOpenDocument={openDocument} onRelationshipsChanged={reloadSelectedDocument}
              parseDebug={workspace.parse.data} parseDebugError={workspace.parse.error?.message ?? null}
              isParseDebugLoading={workspace.parse.loading} onLoadParseDebug={workspace.loadParse}
              semanticAnnotation={workspace.semantic.data} semanticAnnotationError={workspace.semantic.error?.message ?? null}
              isSemanticAnnotationLoading={workspace.semantic.loading} onLoadSemanticAnnotation={workspace.loadSemantic} />
          ) : (
            <Inbox documents={list.documents} total={list.total} selectedId={selectedId} selected={selected} detail={detail}
              error={workspace.detail.error ? documentError(workspace.detail.error) : list.error?.message ?? organization.error?.message ?? error}
              activeFilter={activeFilter} setActiveFilter={setActiveFilter}
              setSelectedId={(documentId) => navigate({view: "inbox", query: inboxQuery, folderId, documentId}, {replace: true})}
              openViewer={() => { if (selectedId && detail) openDocument(selectedId); }}
              uploadFile={uploadFile} folders={folders} tags={tags} activeFolderId={folderId ?? null}
              onSelectFolder={(nextFolderId) => navigate({view: "inbox", query: inboxQuery, folderId: nextFolderId ?? undefined})}
              onCreateFolder={handleCreateFolder} onCreateTag={handleCreateTag} onSaveOrganization={handleSaveOrganization} />
          )}
        </div>
      </main>
    </div>
  );
}

function documentError(error: Error | null): string {
  if (error instanceof ApiError && (error.status === 404 || error.status === 403)) return "This document is unavailable or you no longer have access.";
  return error?.message ?? "This document is unavailable.";
}
function RouteNotice({message, loading, onRetry, onBack, backLabel = "Open Inbox"}: {
  message: string; loading?: boolean; onRetry?: () => void; onBack?: () => void; backLabel?: string;
}) {
  return <section className="search-workbench"><h1>{loading ? "Loading" : "Page unavailable"}</h1>
    <p role={loading ? "status" : "alert"}>{message}</p>
    {onRetry ? <button type="button" onClick={onRetry}>Retry</button> : null}
    {onBack ? <button type="button" onClick={onBack}>{backLabel}</button> : null}
  </section>;
}
