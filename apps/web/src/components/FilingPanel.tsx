import {useEffect, useState} from "react";

import type {DocumentDetail, DocumentOrganizationWrite, Folder, Tag} from "../types";

export function FilingPanel({
  document,
  folders,
  tags,
  onSave,
}: {
  document: DocumentDetail | null;
  folders: Folder[];
  tags: Tag[];
  onSave: (documentId: string, payload: DocumentOrganizationWrite) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [documentDate, setDocumentDate] = useState("");
  const [filingNotes, setFilingNotes] = useState("");
  const [folderIds, setFolderIds] = useState<string[]>([]);
  const [primaryFolderId, setPrimaryFolderId] = useState<string | null>(null);
  const [tagNames, setTagNames] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setTitle(document?.title ?? "");
    setDocumentDate(document?.documentDate ?? "");
    setFilingNotes(document?.filingNotes ?? "");
    setFolderIds(document?.folderIds ?? []);
    setPrimaryFolderId(document?.primaryFolderId ?? null);
    setTagNames(document?.tags ?? []);
  }, [document]);

  if (!document) {
    return (
      <section className="filing-panel">
        <h3>Manual filing</h3>
        <p className="empty-copy">Select a document to edit folders, tags, title, date, and notes.</p>
      </section>
    );
  }

  const manualFolders = folders.filter((folder) => folder.folderKind === "manual");

  async function save() {
    if (!document) {
      return;
    }
    setSaving(true);
    try {
      await onSave(document.id, {
        title,
        documentDate: documentDate || null,
        folderIds,
        primaryFolderId,
        tags: tagNames,
        filingNotes: filingNotes || null,
      });
    } finally {
      setSaving(false);
    }
  }

  function toggleFolder(folderId: string, enabled: boolean) {
    const next = enabled ? [...folderIds, folderId] : folderIds.filter((id) => id !== folderId);
    setFolderIds(next);
    if (enabled && !primaryFolderId) {
      setPrimaryFolderId(folderId);
    }
    if (!enabled && primaryFolderId === folderId) {
      setPrimaryFolderId(next[0] ?? null);
    }
  }

  return (
    <section className="filing-panel">
      <div className="section-title">
        <h3>Manual filing</h3>
        <button type="button" onClick={() => void save()} disabled={saving}>
          {saving ? "Saving..." : "Save filing"}
        </button>
      </div>
      <label>
        Title
        <input value={title} onChange={(event) => setTitle(event.target.value)} />
      </label>
      <label>
        Document date
        <input
          type="date"
          value={documentDate}
          onChange={(event) => setDocumentDate(event.target.value)}
        />
      </label>
      <label>
        Filing notes
        <textarea
          value={filingNotes}
          onChange={(event) => setFilingNotes(event.target.value)}
          rows={3}
          placeholder="Why this belongs here, deadlines, or filing context."
        />
      </label>
      <fieldset>
        <legend>Folders</legend>
        {manualFolders.map((folder) => {
          const selected = folderIds.includes(folder.id);
          return (
            <div key={folder.id} className="choice-row">
              <label className="choice-main">
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={(event) => toggleFolder(folder.id, event.target.checked)}
                />
                <span>{folder.path ?? `/${folder.name}`}</span>
              </label>
              <label className="primary-choice">
                <input
                  type="radio"
                  name={`primary-folder-${document.id}`}
                  aria-label={`Primary folder ${folder.name}`}
                  checked={primaryFolderId === folder.id}
                  disabled={!selected}
                  onChange={() => setPrimaryFolderId(folder.id)}
                />
                <small>Primary</small>
              </label>
            </div>
          );
        })}
        {!manualFolders.length ? <p className="empty-copy">Create a folder first.</p> : null}
      </fieldset>
      <fieldset>
        <legend>Tags</legend>
        <div className="tag-picker">
          {tags.map((tag) => (
            <label key={tag.id} className="tag-choice">
              <input
                type="checkbox"
                checked={tagNames.includes(tag.name)}
                onChange={(event) => {
                  setTagNames((current) =>
                    event.target.checked
                      ? [...current, tag.name]
                      : current.filter((name) => name !== tag.name),
                  );
                }}
              />
              <span>{tag.name}</span>
            </label>
          ))}
        </div>
      </fieldset>
    </section>
  );
}
