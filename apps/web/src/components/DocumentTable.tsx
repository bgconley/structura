import {assetUrl} from "../api";
import {familyLabel, formatAmount, formatDate} from "../format";
import type {DocumentSummary} from "../types";
import {ReviewChip} from "./Status";

export function DocumentTable({
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
              <th>Tags</th>
              <th>Related</th>
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
                <td>
                  {document.tags?.length ? (
                    <span className="table-tags">{document.tags.slice(0, 2).join(", ")}</span>
                  ) : (
                    <span className="muted-cell">None</span>
                  )}
                </td>
                <td>{document.relatedCount ?? 0}</td>
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
