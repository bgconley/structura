import {useEffect, useState} from "react";

import {assetUrl} from "../api";
import {evidenceTargetFromRef, selectEvidenceRef} from "../evidence";
import {familyLabel, formatDate} from "../format";
import type {
  DocumentDetail,
  DocumentPage,
  EvidenceTarget,
  DocumentOrganizationWrite,
  DocumentSummary,
  ExtractionObservation,
  ExtractionSummary,
  Folder,
  ParseDebugView,
  QualityOutcome,
  SemanticAnnotationManifest,
  SemanticRegionExtraction,
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
  onOpenReview,
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
}: {
  document: DocumentDetail | null;
  summary?: DocumentSummary;
  evidenceTarget: EvidenceTarget | null;
  onBack: () => void;
  onOpenReview: () => void;
  folders: Folder[];
  tags: Tag[];
  onSaveOrganization: (documentId: string, payload: DocumentOrganizationWrite) => Promise<void>;
  documents: DocumentSummary[];
  onOpenDocument: (documentId: string, evidenceTarget?: EvidenceTarget) => void;
  onRelationshipsChanged: () => Promise<void>;
  parseDebug: ParseDebugView | null;
  parseDebugError: string | null;
  isParseDebugLoading: boolean;
  onLoadParseDebug: (documentId: string) => void;
  semanticAnnotation: SemanticAnnotationManifest | null;
  semanticAnnotationError: string | null;
  isSemanticAnnotationLoading: boolean;
  onLoadSemanticAnnotation: (documentId: string) => void;
}) {
  const active = document ?? summary;
  const original = document?.assets.find((asset) => asset.assetRole === "original");
  const pages = document?.pages ?? [];
  const evidencePageNumber = evidenceTarget?.pageNumber;
  const [selectedPageNumber, setSelectedPageNumber] = useState<number | null>(null);

  useEffect(() => {
    setSelectedPageNumber(evidencePageNumber ?? null);
  }, [evidencePageNumber, document?.id]);

  const activePageNumber = selectedPageNumber ?? evidencePageNumber ?? pages[0]?.pageNumber ?? 1;
  const activePage = pages.find((page) => page.pageNumber === activePageNumber) ?? pages[0];
  const preview = activePage?.imageUrl;
  const quality = document?.qualitySummary ?? summary?.qualitySummary ?? null;
  const extractionState = extractionChip(document);

  if (!active) {
    return null;
  }

  const showHighlight =
    Boolean(evidenceTarget?.bbox)
    && (evidenceTarget?.pageNumber ?? activePage?.pageNumber) === activePage?.pageNumber;

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
        {pages.length ? pages.map((page) => (
          <button
            className={page.pageNumber === activePage?.pageNumber ? "selected" : undefined}
            type="button"
            key={page.pageNumber}
            onClick={() => setSelectedPageNumber(page.pageNumber)}
          >
            <span className="rail-thumb" />
            <small>{page.pageNumber}</small>
          </button>
        )) : (
          <small>No parsed pages yet.</small>
        )}
      </aside>
      <section className="viewer-card">
        <div className="viewer-card-title">
          <h2>{active.title}</h2>
          <StatusChip tone="green" label="Immutable original" />
          {extractionState ? (
            <StatusChip tone={extractionState.tone} label={extractionState.label} />
          ) : null}
          {quality?.reviewRequired ? <StatusChip tone="amber" label="Difficult document" /> : null}
        </div>
        {evidenceTarget ? (
          <div className="evidence-focus" role="status">
            <strong>{evidenceTarget.fieldPath ?? "Evidence"}</strong>
            <span>
              Page {evidenceTarget.pageNumber ?? activePage?.pageNumber ?? 1}
              {evidenceTarget.sourceText ? ` · ${evidenceTarget.sourceText}` : ""}
              {evidenceTarget.bbox ? "" : " · no visual anchor; text/table locator only"}
            </span>
          </div>
        ) : null}
        <div className="rendered-page">
          {preview ? (
            <>
              <img src={assetUrl(preview)} alt={`Preview of ${active.title} page ${activePage?.pageNumber ?? 1}`} />
              {evidenceTarget && showHighlight ? (
                <EvidenceHighlight target={evidenceTarget} page={activePage} />
              ) : null}
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
            <strong>Document quality signals</strong>
            <span>{quality.summary ?? quality.reasons?.join(", ")}</span>
          </div>
        ) : null}
        <div className="viewer-actions">
          <button type="button" className="primary" onClick={onOpenReview}>Open review</button>
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
        {document?.fields.slice(0, 5).map((field) => (
          <FactRow
            key={field.id}
            label={field.fieldPath}
            value={formatFactValue(field.value, field.currency ?? undefined)}
            onJump={field.evidence?.length ? () => (
              onOpenDocument(
                document.id,
                evidenceTargetFromRef(document.id, selectEvidenceRef(field.evidence), field.fieldPath),
              )
            ) : undefined}
          />
        ))}
        {document ? <QualityDecisionPanel extractions={document.extractions} /> : null}
        {document ? (
          <RegionExtractionPanel regions={document.semanticRegionExtractions ?? []} />
        ) : null}
        {document ? (
          <ObservationPanel
            documentId={document.id}
            observations={document.observations ?? []}
            onJump={(target) => onOpenDocument(document.id, target)}
          />
        ) : null}
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
        />
      </aside>
    </section>
  );
}

const QUALITY_OUTCOME_LABELS: Record<QualityOutcome, {tone: "green" | "blue" | "neutral" | "amber"; label: string}> = {
  extracted_cleanly: {tone: "green", label: "Extracted cleanly"},
  needs_human_review: {tone: "amber", label: "Needs human review"},
  insufficient_signal: {tone: "amber", label: "Insufficient signal"},
  no_extraction_target: {tone: "neutral", label: "No extraction target"},
  pipeline_failed: {tone: "amber", label: "Pipeline failed"},
};

function extractionChip(
  document: DocumentDetail | null,
): {tone: "green" | "blue" | "neutral" | "amber"; label: string} | null {
  if (!document) {
    return null;
  }
  const extractions = document.extractions ?? [];
  const current = extractions.find((extraction) => extraction.extractionScope === "aggregate")
    ?? extractions.find((extraction) => extraction.extractionScope === "document")
    ?? extractions[0];
  if (!current) {
    return {tone: "neutral", label: "Extraction pending"};
  }
  if (current.qualityOutcome) {
    return QUALITY_OUTCOME_LABELS[current.qualityOutcome];
  }
  if (current.reviewStatus === "needs_review") {
    return {tone: "amber", label: "Extraction needs review"};
  }
  return {tone: "green", label: "Extracted"};
}

function QualityDecisionPanel({extractions}: {extractions: ExtractionSummary[]}) {
  const decided = extractions.filter(
    (extraction) => extraction.qualityOutcome || extraction.claimResolutionDecisions?.length,
  );
  if (!decided.length) {
    return null;
  }
  return (
    <section className="quality-decisions">
      <h3>Quality decisions</h3>
      {decided.map((extraction) => (
        <div key={extraction.id} className="field-list">
          <p>
            <strong>{extraction.schemaName}</strong>
            <span>
              {extraction.qualityOutcome
                ? QUALITY_OUTCOME_LABELS[extraction.qualityOutcome].label
                : extraction.reviewStatus ?? "recorded"}
            </span>
          </p>
          {extraction.claimResolutionDecisions?.slice(0, 6).map((decision) => (
            <p key={`${extraction.id}-${decision.canonicalKey}`}>
              <strong>{decision.canonicalKey}</strong>
              <span>{decision.decision} · {decision.reasonCode}</span>
            </p>
          ))}
        </div>
      ))}
    </section>
  );
}

function RegionExtractionPanel({regions}: {regions: SemanticRegionExtraction[]}) {
  if (!regions.length) {
    return null;
  }
  return (
    <section className="region-extractions">
      <h3>Region extractions</h3>
      <div className="field-list">
        {regions.map((region) => (
          <p key={region.id}>
            <strong>{region.semanticType ?? region.schemaName}</strong>
            <span>
              {region.graniteTask ?? "no granite task"}
              {" · "}
              {region.status}
              {region.reviewStatus ? ` · ${region.reviewStatus}` : ""}
              {region.qualityOutcome
                ? ` · ${QUALITY_OUTCOME_LABELS[region.qualityOutcome].label}`
                : ""}
            </span>
          </p>
        ))}
      </div>
    </section>
  );
}

function ObservationPanel({
  documentId,
  observations,
  onJump,
}: {
  documentId: string;
  observations: ExtractionObservation[];
  onJump: (target: EvidenceTarget) => void;
}) {
  if (!observations.length) {
    return null;
  }
  return (
    <section className="observation-rows">
      <h3>Observations</h3>
      <div className="field-list">
        {observations.slice(0, 12).map((observation) => {
          const evidence = selectEvidenceRef(observation.evidence);
          const fieldPath = `observations.${observation.observationFamily ?? "document_observation"}.${observation.fieldName}`;
          return (
            <FactRow
              key={observation.id}
              label={`${observation.observationFamily ?? "document_observation"}.${observation.fieldName}`}
              value={`${formatFactValue(observation.value)}${observation.status ? ` · ${observation.status}` : ""}`}
              onJump={evidence ? () => onJump(evidenceTargetFromRef(documentId, evidence, fieldPath)) : undefined}
            />
          );
        })}
      </div>
    </section>
  );
}

function SemanticAnnotationPanel({
  manifest,
  error,
  isLoading,
  onLoad,
}: {
  manifest: SemanticAnnotationManifest | null;
  error: string | null;
  isLoading: boolean;
  onLoad: () => void;
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
      </div>
      <p className="debug-copy">Smart Parse uses Qwen3-VL-8B FP8 for semantic planning.</p>
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

function EvidenceHighlight({target, page}: {target: EvidenceTarget; page?: DocumentPage}) {
  const box = normalizedBox(target.bbox, page);
  if (!box) {
    return null;
  }
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

function normalizedBox(bbox: [number, number, number, number] | undefined, page?: DocumentPage) {
  if (!bbox) {
    // No visual anchor: never fabricate a highlight.
    return null;
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
  const pageWidth = page?.width && page.width > 0 ? page.width : 612;
  const pageHeight = page?.height && page.height > 0 ? page.height : 792;
  return {
    left: clampPercent((left / pageWidth) * 100),
    top: clampPercent((top / pageHeight) * 100),
    width: clampPercent(((right - left) / pageWidth) * 100, 4),
    height: clampPercent(((bottom - top) / pageHeight) * 100, 4),
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
