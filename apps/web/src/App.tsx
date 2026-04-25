import {FormEvent, startTransition, useDeferredValue, useEffect, useState} from "react";

import {csrfToken, fetchJson} from "./api";
import {Inbox} from "./components/Inbox";
import {LoginScreen} from "./components/LoginScreen";
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
import type {
  DocumentDetail,
  DocumentListResponse,
  DocumentOrganizationWrite,
  DocumentSummary,
  Folder,
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
  const [viewMode, setViewMode] = useState<ViewMode>("inbox");
  const [activeFilter, setActiveFilter] = useState("All");
  const [query, setQuery] = useState("");
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
      return;
    }
    void loadDetail(selectedId);
  }, [selectedId, session?.isAuthenticated]);

  async function bootstrap() {
    try {
      const current = await fetchJson<SessionInfo>("/api/v1/auth/session");
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

  async function loadDetail(documentId: string) {
    try {
      setDetail(await fetchJson<DocumentDetail>(`/api/v1/documents/${documentId}`));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load document detail");
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    try {
      await fetchJson<SessionInfo>("/api/v1/auth/session", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          method: "password",
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
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
      <Sidebar total={total} />
      <main className="app-main">
        <TopCommand
          query={query}
          setQuery={setQuery}
          isUploading={isUploading}
          uploadFile={uploadFile}
        />
        {viewMode === "viewer" && selected ? (
          <Viewer
            document={detail}
            summary={selectedSummary}
            onBack={() => setViewMode("inbox")}
            folders={folders}
            tags={tags}
            onSaveOrganization={handleSaveOrganization}
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
            setSelectedId={setSelectedId}
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
