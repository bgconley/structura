import {assetUrl} from "../api";
import {familyLabel, formatAmount, formatDate} from "../format";
import type {DocumentDetail, DocumentSummary} from "../types";
import {ReviewChip, StatusChip} from "./Status";

const filterLabels = [
  "All",
  "Needs Review",
  "Unfiled",
  "Awaiting Classification",
  "Duplicates",
  "Low Confidence",
  "Extracted",
  "Indexed",
];

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
}) {
  const needsReview = documents.filter((document) => document.reviewStatus === "needs_review").length;
  const unfiled = documents.filter((document) => !(document.folderPaths?.length)).length;

  return (
    <section className="home-grid">
      <div className="workspace">
        <div className="page-heading">
          <div>
            <h1>Document Operations</h1>
            <p>Overview of document review, filing, and trust state.</p>
          </div>
          <button type="button" onClick={openViewer} disabled={!selected}>
            Open Viewer
          </button>
        </div>
        <div className="metrics-row">
          <Metric label="Needs Review" value={needsReview} detail="Review required" tone="amber" />
          <Metric label="Unfiled Documents" value={unfiled} detail="Awaiting filing" tone="blue" />
          <Metric label="Awaiting Classification" value={total} detail="Phase 3 ready" tone="blue" />
          <Metric label="Missing Required Fields" value={0} detail="Needs attention" tone="amber" />
          <Metric label="Duplicate Suspects" value={0} detail="Exact hash flagged" tone="amber" />
          <Metric label="Recent Uploads" value={total} detail="Visible in inbox" tone="blue" />
        </div>
        <div className="filter-row" aria-label="Document filters">
          {filterLabels.map((filter) => (
            <button
              key={filter}
              className={filter === activeFilter ? "selected" : undefined}
              type="button"
              onClick={() => setActiveFilter(filter)}
            >
              <span />
              {filter}
            </button>
          ))}
        </div>
        {error ? <div className="inline-error">{error}</div> : null}
        <DocumentTable
          documents={documents}
          selectedId={selectedId}
          setSelectedId={setSelectedId}
          uploadFile={uploadFile}
        />
        <PipelineSummary
          total={total}
          previewed={documents.filter((document) => document.thumbnailUrl).length}
        />
      </div>
      <Inspector selected={selected} detail={detail} openViewer={openViewer} />
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: number;
  detail: string;
  tone: "blue" | "amber";
}) {
  return (
    <article className="metric-card">
      <p>{label}</p>
      <strong className={tone}>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function DocumentTable({
  documents,
  selectedId,
  setSelectedId,
  uploadFile,
}: {
  documents: DocumentSummary[];
  selectedId: string | null;
  setSelectedId: (id: string) => void;
  uploadFile: (file: File | undefined) => Promise<void>;
}) {
  return (
    <section className="document-panel">
      <div className="panel-title">
        <h2>Priority Document Activity</h2>
        <p>1-{Math.min(documents.length, 7)} of {documents.length} documents</p>
      </div>
      {documents.length === 0 ? (
        <div className="empty-state">
          <h3>No inbox documents yet</h3>
          <p>Upload a PDF or image to create the first document row and protected original asset.</p>
          <label className="primary-upload">
            Upload first document
            <input
              type="file"
              accept="application/pdf,image/png,image/jpeg,image/tiff,image/webp"
              onChange={(event) => void uploadFile(event.currentTarget.files?.[0])}
            />
          </label>
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th aria-label="select" />
              <th>Document</th>
              <th>Family</th>
              <th>Counterparty</th>
              <th>Date</th>
              <th>Key Amount</th>
              <th>Folder</th>
              <th>Review Status</th>
              <th>Pipeline</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr
                key={document.id}
                className={document.id === selectedId ? "selected" : undefined}
                onClick={() => setSelectedId(document.id)}
              >
                <td><span className="row-check" /></td>
                <td>
                  <div className="doc-cell">
                    {document.thumbnailUrl ? (
                      <img src={assetUrl(document.thumbnailUrl)} alt="" />
                    ) : (
                      <span className="thumb-skeleton" />
                    )}
                    <div>
                      <strong>{document.title}</strong>
                      <small>#{document.id.slice(0, 13).toUpperCase()}</small>
                    </div>
                  </div>
                </td>
                <td>{familyLabel(document.family)}</td>
                <td>{document.counterpartyDisplay ?? "Pending"}</td>
                <td>{formatDate(document.documentDate)}</td>
                <td>{formatAmount(document.amountTotal)}</td>
                <td>{document.folderPaths?.[0]?.replace("/", "") || "Unfiled"}</td>
                <td><ReviewChip status={document.reviewStatus} /></td>
                <td><span className="pipeline-state">Ingested</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Inspector({
  selected,
  detail,
  openViewer,
}: {
  selected: DocumentSummary | DocumentDetail | null;
  detail: DocumentDetail | null;
  openViewer: () => void;
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
          <p>Fields loaded.</p>
        ) : (
          <p className="pending-copy">
            Extraction fields are pending Phase 3. The original and preview are already protected.
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
        <button type="button">File document</button>
      </section>
      <section className="related-block">
        <h3>Related Documents</h3>
        <p>Relationship suggestions are prepared for Phase 7.</p>
      </section>
    </aside>
  );
}

function PipelineSummary({total, previewed}: {total: number; previewed: number}) {
  const stages = [
    ["Ingest", total, total, "green"],
    ["Preview", previewed, total, previewed === total ? "green" : "amber"],
    ["Docling parse", 0, total, "neutral"],
    ["Classification", 0, total, "neutral"],
    ["Extraction", 0, total, "neutral"],
    ["Indexing", 0, total, "neutral"],
  ];
  return (
    <section className="pipeline-panel">
      <div className="panel-title">
        <h2>Pipeline & Indexing Summary</h2>
        <button type="button">Pipeline details</button>
      </div>
      <div className="stage-row">
        {stages.map(([label, done, count, tone]) => (
          <article className={`stage-card ${tone}`} key={label}>
            <span />
            <strong>{label}</strong>
            <small>{done} / {count}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
