import {assetUrl} from "../api";
import {familyLabel, formatDate} from "../format";
import type {
  DocumentDetail,
  EvidenceTarget,
  DocumentOrganizationWrite,
  DocumentSummary,
  Folder,
  ParseDebugView,
  SemanticAnnotationManifest,
  Tag,
} from "../types";
import {FilingPanel} from "./FilingPanel";
import {ParseDebugPanel} from "./ParseDebugPanel";
import {RelationshipPanel} from "./RelationshipPanel";
import {FactRow, ReviewChip, StatusChip, TrustLine} from "./Status";

export function Viewer({
  document,
  summary,
  evidenceTarget,
  onBack,
  folders,
  tags,
  onSaveOrganization,
  documents,
  onOpenDocument,
  onRelationshipsChanged,
  parseDebug,
  parseDebugError,
  isParseDebugLoading,
  onLoadParseDebug,
  semanticAnnotation,
  semanticAnnotationError,
  isSemanticAnnotationLoading,
  onLoadSemanticAnnotation,
  onQueueHighQualityPass,
}: {
  document: DocumentDetail | null;
  summary?: DocumentSummary;
  evidenceTarget: EvidenceTarget | null;
  onBack: () => void;
  folders: Folder[];
  tags: Tag[];
  onSaveOrganization: (documentId: string, payload: DocumentOrganizationWrite) => Promise<void>;
  documents: DocumentSummary[];
  onOpenDocument: (documentId: string) => void;
  onRelationshipsChanged: () => Promise<void>;
  parseDebug: ParseDebugView | null;
  parseDebugError: string | null;
  isParseDebugLoading: boolean;
  onLoadParseDebug: (documentId: string) => void;
  semanticAnnotation: SemanticAnnotationManifest | null;
  semanticAnnotationError: string | null;
  isSemanticAnnotationLoading: boolean;
  onLoadSemanticAnnotation: (documentId: string) => void;
  onQueueHighQualityPass: (documentId: string) => Promise<void>;
}) {
  const active = document ?? summary;
  const original = document?.assets.find((asset) => asset.assetRole === "original");
  const preview = document?.pages[0]?.imageUrl;
  const quality = document?.qualitySummary ?? summary?.qualitySummary ?? null;

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
          {quality?.reviewRequired ? <StatusChip tone="amber" label="Difficult document" /> : null}
        </div>
        {evidenceTarget ? (
          <div className="evidence-focus" role="status">
            <strong>{evidenceTarget.fieldPath ?? "Evidence"}</strong>
            <span>
              Page {evidenceTarget.pageNumber ?? document?.pages[0]?.pageNumber ?? 1}
              {evidenceTarget.sourceText ? ` · ${evidenceTarget.sourceText}` : ""}
            </span>
          </div>
        ) : null}
        <div className="rendered-page">
          {preview ? (
            <>
              <img src={assetUrl(preview)} alt={`Preview of ${active.title}`} />
              {evidenceTarget ? <EvidenceHighlight target={evidenceTarget} /> : null}
            </>
          ) : original?.mimeType === "application/pdf" ? (
            <iframe src={assetUrl(original.assetUrl)} title={active.title} />
          ) : (
            <div className="preview-fallback">
              <span className="thumb-skeleton large" />
              <p>Preview generation is pending. The protected original is available.</p>
            </div>
          )}
        </div>
        {quality ? (
          <div className="quality-banner" role="note">
            <strong>Phase 8 quality signals</strong>
            <span>{quality.summary ?? quality.reasons?.join(", ")}</span>
          </div>
        ) : null}
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
        {quality ? (
          <>
            <TrustLine ok={!quality.reviewRequired} label={quality.reviewRequired ? "Difficult-document review required" : "No difficult-document review needed"} />
            <TrustLine ok={!quality.visualEmbeddingEligible} label={quality.visualEmbeddingEligible ? "Visual retrieval eligible" : "Text retrieval sufficient"} />
          </>
        ) : null}
        <h3>Key fields</h3>
        <FactRow label="Family" value={familyLabel(active.family)} />
        <FactRow label="Counterparty" value={active.counterpartyDisplay ?? "Pending extraction"} />
        <FactRow label="Date" value={formatDate(active.documentDate)} />
        <FactRow label="Folder" value={active.folderPaths?.[0] ?? "Unfiled"} />
        {document?.fields.slice(0, 5).map((field, index) => (
          <FactRow
            key={index}
            label={String((field as {fieldPath?: string}).fieldPath ?? "Field")}
            value={formatFactValue((field as {value?: unknown; currency?: string}).value, (field as {currency?: string}).currency)}
          />
        ))}
        <button type="button" className="primary">Review extracted fields</button>
        <div className="two-actions">
          <button type="button">File document</button>
          <button type="button">Link document</button>
        </div>
        <FilingPanel
          document={document}
          folders={folders}
          tags={tags}
          onSave={onSaveOrganization}
        />
        <RelationshipPanel
          document={document}
          documents={documents}
          onOpenDocument={onOpenDocument}
          onChanged={onRelationshipsChanged}
        />
        <ParseDebugPanel
          debug={parseDebug}
          error={parseDebugError}
          isLoading={isParseDebugLoading}
          onLoad={() => onLoadParseDebug(String(active.id))}
        />
        <SemanticAnnotationPanel
          manifest={semanticAnnotation}
          error={semanticAnnotationError}
          isLoading={isSemanticAnnotationLoading}
          onLoad={() => onLoadSemanticAnnotation(String(active.id))}
          onHighQuality={() => onQueueHighQualityPass(String(active.id))}
        />
      </aside>
    </section>
  );
}

function SemanticAnnotationPanel({
  manifest,
  error,
  isLoading,
  onLoad,
  onHighQuality,
}: {
  manifest: SemanticAnnotationManifest | null;
  error: string | null;
  isLoading: boolean;
  onLoad: () => void;
  onHighQuality: () => Promise<void>;
}) {
  return (
    <section className="semantic-annotation-panel">
      <h3>Smart Parse</h3>
      <p className="debug-copy">
        Qwen semantic annotations stay grounded to Docling pages and route targeted Granite extraction.
      </p>
      <div className="two-actions">
        <button type="button" onClick={onLoad} disabled={isLoading}>
          {isLoading ? "Loading..." : "Load Smart Parse"}
        </button>
        <button type="button" onClick={() => void onHighQuality()}>
          High Quality Pass
        </button>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      {manifest ? (
        <div className="semantic-annotation-summary">
          <span>{manifest.qualityMode} · {manifest.sourceEngine}</span>
          <strong>{manifest.modelName}</strong>
          <p>{manifest.regions.length} semantic region targets · {manifest.pages.length} pages</p>
          <ul>
            {manifest.regions.slice(0, 4).map((region, index) => (
              <li key={`${region.semanticType}-${index}`}>
                <b>{region.semanticType}</b>
                <span>{region.graniteTask ?? "no extraction"} · {region.grounding.kind}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="empty-state">No semantic manifest loaded.</p>
      )}
    </section>
  );
}

function EvidenceHighlight({target}: {target: EvidenceTarget}) {
  const box = normalizedBox(target.bbox);
  return (
    <div
      className="evidence-highlight"
      aria-label="Evidence highlight"
      style={{
        left: `${box.left}%`,
        top: `${box.top}%`,
        width: `${box.width}%`,
        height: `${box.height}%`,
      }}
    />
  );
}

function normalizedBox(bbox?: [number, number, number, number]) {
  if (!bbox) {
    return {left: 12, top: 16, width: 76, height: 12};
  }
  const [left, top, right, bottom] = bbox;
  const maxX = Math.max(left, right, 1);
  const maxY = Math.max(top, bottom, 1);
  if (maxX <= 1 && maxY <= 1) {
    return {
      left: clampPercent(left * 100),
      top: clampPercent(top * 100),
      width: clampPercent((right - left) * 100, 4),
      height: clampPercent((bottom - top) * 100, 4),
    };
  }
  return {
    left: clampPercent((left / 612) * 100),
    top: clampPercent((top / 792) * 100),
    width: clampPercent(((right - left) / 612) * 100, 4),
    height: clampPercent(((bottom - top) / 792) * 100, 4),
  };
}

function clampPercent(value: number, minimum = 0): number {
  return Math.min(100, Math.max(minimum, value));
}

function formatFactValue(value: unknown, currency?: string): string {
  if (value && typeof value === "object" && "amount" in value) {
    const money = value as {amount?: number; currency?: string};
    return `${money.currency ?? currency ?? "USD"} ${money.amount ?? ""}`.trim();
  }
  return value === null || value === undefined ? "Pending" : String(value);
}
