import {assetUrl} from "../api";
import {familyLabel} from "../format";
import type {DocumentDetail, DocumentOrganizationWrite, DocumentSummary, Folder, Tag} from "../types";
import {FilingPanel} from "./FilingPanel";
import {ReviewChip, StatusChip} from "./Status";

export function DocumentInspector({
  selected,
  detail,
  openViewer,
  folders,
  tags,
  onSaveOrganization,
}: {
  selected: DocumentSummary | DocumentDetail | null;
  detail: DocumentDetail | null;
  openViewer: () => void;
  folders: Folder[];
  tags: Tag[];
  onSaveOrganization: (documentId: string, payload: DocumentOrganizationWrite) => Promise<void>;
}) {
  if (!selected) {
    return (
      <aside className="inspector">
        <h2>No document selected</h2>
        <p>Upload or select a row to inspect evidence and document state.</p>
      </aside>
    );
  }
  const original = detail?.assets.find((asset) => asset.assetRole === "original");
  const sha = original?.sha256 ? `${original.sha256.slice(0, 12)}...` : "Stored after upload";

  return (
    <aside className="inspector">
      <h2>{selected.title}</h2>
      <p>{familyLabel(selected.family)}</p>
      <div className="inspector-chips">
        <ReviewChip status={selected.reviewStatus} />
        <StatusChip tone="blue" label="86% confidence" />
      </div>
      <p className="fingerprint">Immutable original · SHA-256 {sha}</p>
      <div className="evidence-preview">
        {selected.thumbnailUrl ? (
          <img src={assetUrl(selected.thumbnailUrl)} alt="" />
        ) : (
          <span className="thumb-skeleton large" />
        )}
        <small>Evidence cue anchors the selected field</small>
      </div>
      <section className="fields-block">
        <div className="section-title">
          <h3>Extracted Fields</h3>
          <button type="button">Jump to evidence</button>
        </div>
        {detail?.fields.length ? (
          <div className="field-list">
            {detail.fields.slice(0, 4).map((field, index) => (
              <p key={index}>
                <strong>{String((field as {fieldPath?: string}).fieldPath ?? "field")}</strong>
                <span>{String((field as {value?: unknown}).value ?? "not set")}</span>
              </p>
            ))}
          </div>
        ) : (
          <p className="pending-copy">
            Extraction fields are pending. The original and preview are already protected.
          </p>
        )}
      </section>
      <section className="actions-block">
        <h3>Document actions</h3>
        <button type="button" className="primary" onClick={openViewer}>Open viewer</button>
        {original ? (
          <a href={assetUrl(original.assetUrl)} download>
            Download original
          </a>
        ) : null}
      </section>
      <FilingPanel
        document={detail}
        folders={folders}
        tags={tags}
        onSave={onSaveOrganization}
      />
      <section className="related-block">
        <h3>Related Documents</h3>
        <p>Relationship suggestions are prepared for Phase 7.</p>
      </section>
    </aside>
  );
}
