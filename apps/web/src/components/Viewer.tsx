import {assetUrl} from "../api";
import {familyLabel, formatDate} from "../format";
import type {DocumentDetail, DocumentSummary} from "../types";
import {FactRow, ReviewChip, StatusChip, TrustLine} from "./Status";

export function Viewer({
  document,
  summary,
  onBack,
}: {
  document: DocumentDetail | null;
  summary?: DocumentSummary;
  onBack: () => void;
}) {
  const active = document ?? summary;
  const original = document?.assets.find((asset) => asset.assetRole === "original");
  const preview = document?.pages[0]?.imageUrl;

  if (!active) {
    return null;
  }

  return (
    <section className="viewer-grid">
      <div className="viewer-heading">
        <div>
          <h1>Document Viewer</h1>
          <p>Read the original document in-app while preserving trust and provenance context.</p>
        </div>
        <button type="button" onClick={onBack}>Back to Inbox</button>
      </div>
      <aside className="page-rail">
        {[1, 2, 3, 4, 5].map((page) => (
          <button className={page === 1 ? "selected" : undefined} type="button" key={page}>
            <span className="rail-thumb" />
            <small>{page}</small>
          </button>
        ))}
      </aside>
      <section className="viewer-card">
        <div className="viewer-card-title">
          <h2>{active.title}</h2>
          <StatusChip tone="green" label="Immutable original" />
          <StatusChip tone="neutral" label="Extraction pending" />
        </div>
        <div className="rendered-page">
          {preview ? (
            <img src={assetUrl(preview)} alt={`Preview of ${active.title}`} />
          ) : original?.mimeType === "application/pdf" ? (
            <iframe src={assetUrl(original.assetUrl)} title={active.title} />
          ) : (
            <div className="preview-fallback">
              <span className="thumb-skeleton large" />
              <p>Preview generation is pending. The protected original is available.</p>
            </div>
          )}
        </div>
        <div className="viewer-actions">
          <button type="button" className="primary">Open review</button>
          {original ? <a href={assetUrl(original.assetUrl)} download>Download original</a> : null}
        </div>
      </section>
      <aside className="facts-panel">
        <h2>Document Facts</h2>
        <ReviewChip status={active.reviewStatus} />
        <p>
          {document?.description
            ?? `${familyLabel(active.family)} document preserved as an immutable original.`}
        </p>
        <h3>Trust state</h3>
        <TrustLine ok label="Original stored immutably" />
        <TrustLine ok label="SHA-256 fingerprint stored" />
        <TrustLine ok={Boolean(preview)} label={preview ? "Preview asset available" : "Preview pending"} />
        <TrustLine ok={active.reviewStatus !== "needs_review"} label="Fields pending review" />
        <h3>Key fields</h3>
        <FactRow label="Family" value={familyLabel(active.family)} />
        <FactRow label="Counterparty" value={active.counterpartyDisplay ?? "Pending extraction"} />
        <FactRow label="Date" value={formatDate(active.documentDate)} />
        <FactRow label="Folder" value={active.folderPaths?.[0] ?? "Unfiled"} />
        <button type="button" className="primary">Review extracted fields</button>
        <div className="two-actions">
          <button type="button">File document</button>
          <button type="button">Link document</button>
        </div>
      </aside>
    </section>
  );
}
