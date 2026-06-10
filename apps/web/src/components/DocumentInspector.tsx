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
  const confidenceChip = extractionConfidenceChip(detail);

  return (
    <aside className="inspector">
      <h2>{selected.title}</h2>
      <p>{familyLabel(selected.family)}</p>
      <div className="inspector-chips">
        <ReviewChip status={selected.reviewStatus} />
        {confidenceChip ? <StatusChip tone="blue" label={confidenceChip} /> : null}
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
        </div>
        {detail?.fields.length ? (
          <div className="field-list">
            {detail.fields.slice(0, 4).map((field) => (
              <p key={field.id}>
                <strong>{field.fieldPath}</strong>
                <span>{formatFieldValue(field.value)}</span>
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
        {detail?.relationships.length ? (
          <div className="field-list">
            {detail.relationships.slice(0, 3).map((relationship) => (
              <p key={relationship.id}>
                <strong>{relationship.relationshipType.replaceAll("_", " ")}</strong>
                <span>{relationship.relatedTitle}</span>
              </p>
            ))}
          </div>
        ) : (
          <p>No confirmed or suggested links yet.</p>
        )}
      </section>
    </aside>
  );
}

function extractionConfidenceChip(detail: DocumentDetail | null): string | null {
  const extractions = detail?.extractions ?? [];
  const current = extractions.find((extraction) => extraction.extractionScope === "aggregate")
    ?? extractions.find((extraction) => extraction.extractionScope === "document")
    ?? extractions[0];
  if (!current || current.confidence === undefined || current.confidence === null) {
    return null;
  }
  return `${Math.round(current.confidence * 100)}% confidence`;
}

function formatFieldValue(value: unknown): string {
  if (value && typeof value === "object" && "amount" in value) {
    const money = value as {amount?: number; currency?: string};
    return `${money.currency ?? "USD"} ${money.amount ?? ""}`.trim();
  }
  return value === null || value === undefined ? "not set" : String(value);
}
