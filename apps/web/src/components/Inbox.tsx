import {useState} from "react";
import type {DocumentDetail, DocumentOrganizationWrite, DocumentSummary, Folder, Tag} from "../types";
import {DocumentInspector} from "./DocumentInspector";
import {DocumentTable} from "./DocumentTable";
import {InboxMetrics} from "./InboxMetrics";
import {OrganizationRail} from "./OrganizationRail";
import {PipelineSummary} from "./PipelineSummary";

export function Inbox({
  documents,
  total,
  selectedId,
  selected,
  detail,
  error,
  activeFilter,
  setActiveFilter,
  setSelectedId,
  openViewer,
  uploadFile,
  folders,
  tags,
  activeFolderId,
  onSelectFolder,
  onCreateFolder,
  onCreateTag,
  onSaveOrganization,
}: {
  documents: DocumentSummary[];
  total: number;
  selectedId: string | null;
  selected: DocumentSummary | DocumentDetail | null;
  detail: DocumentDetail | null;
  error: string | null;
  activeFilter: string;
  setActiveFilter: (filter: string) => void;
  setSelectedId: (id: string) => void;
  openViewer: () => void;
  uploadFile: (file: File | undefined) => Promise<void>;
  folders: Folder[];
  tags: Tag[];
  activeFolderId: string | null;
  onSelectFolder: (folderId: string | null) => void;
  onCreateFolder: (name: string, folderKind: "manual" | "smart") => Promise<void>;
  onCreateTag: (name: string) => Promise<void>;
  onSaveOrganization: (documentId: string, payload: DocumentOrganizationWrite) => Promise<void>;
}) {
  // Navigation already records the originating action for Back focus restoration.
  // Reveal that action's panel when returning from the dedicated source step.
  const [narrowPanel, setNarrowPanel] = useState<"documents" | "details">(() =>
    window.history.state?.structura?.focusId === "inbox-details-open-viewer" ? "details" : "documents");
  return (
    <section className="home-grid" data-narrow-panel={narrowPanel}>
      <nav className="inbox-panel-switch" aria-label="Inbox panels">
        <button type="button" aria-pressed={narrowPanel === "documents"} onClick={() => {
          setNarrowPanel("documents");
          requestAnimationFrame(() => document.getElementById(`document-row-${selectedId}`)?.focus());
        }}>Documents</button>
        <button type="button" aria-pressed={narrowPanel === "details"} disabled={!detail}
          onClick={() => setNarrowPanel("details")}>Selected document details</button>
      </nav>
      <div className="workspace">
        <div className="page-heading">
          <div>
            <h1>Document Operations</h1>
            <p>Overview of document review, filing, and trust state.</p>
          </div>
          <button id="inbox-open-viewer" type="button" onClick={openViewer} disabled={!detail}>
            Open Viewer
          </button>
        </div>
        <OrganizationRail
          folders={folders}
          tags={tags}
          activeFolderId={activeFolderId}
          onSelectFolder={onSelectFolder}
          onCreateFolder={onCreateFolder}
          onCreateTag={onCreateTag}
        />
        <InboxMetrics
          documents={documents}
          total={total}
          activeFilter={activeFilter}
          setActiveFilter={setActiveFilter}
        />
        {error ? <div className="inline-error">{error}</div> : null}
        <DocumentTable
          documents={documents}
          selectedId={selectedId}
          setSelectedId={setSelectedId}
          uploadFile={uploadFile}
        />
        <PipelineSummary
          documents={documents}
          total={total}
          previewed={documents.filter((document) => document.thumbnailUrl).length}
        />
      </div>
      <DocumentInspector
        selected={selected}
        detail={detail}
        openViewer={openViewer}
        folders={folders}
        tags={tags}
        onSaveOrganization={onSaveOrganization}
      />
    </section>
  );
}
