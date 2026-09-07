import {assetUrl} from "../api";
import {familyLabel, formatAmount, formatDate} from "../format";
import type {DocumentSummary} from "../types";
import {ReviewChip} from "./Status";
import "./DocumentTable.css";

export function DocumentTable({
  documents,
  selectedId,
  setSelectedId,
}: {
  documents: DocumentSummary[];
  selectedId: string | null;
  setSelectedId: (id: string) => void;
}) {
  return (
    <>
      {documents.length ? <p className="table-scroll-hint">Scroll across the table for all document details.</p> : null}
        <div className="document-table-scroll" role="region" aria-label="Document activity, scroll for more columns" tabIndex={0}>
        <table className="document-table" aria-label="Document activity" role="table">
          <thead role="rowgroup">
            <tr role="row">
              <th className="document-title-column">Document</th>
              <th className="document-review-column">Review Status</th>
              <th>Family</th>
              <th>Counterparty</th>
              <th>Date</th>
              <th>Key Amount</th>
              <th>Folder</th>
              <th>Tags</th>
              <th>Related</th>
              <th>Document State</th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {documents.map((document) => (
              <tr
                key={document.id}
                role="row"
                id={`document-row-${document.id}`}
                tabIndex={0}
                aria-selected={document.id === selectedId}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault(); setSelectedId(document.id);
                  }
                  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                    event.preventDefault();
                    const next = event.key === "ArrowDown" ? event.currentTarget.nextElementSibling : event.currentTarget.previousElementSibling;
                    if (next instanceof HTMLTableRowElement) next.focus();
                  }
                }}
                className={document.id === selectedId ? "selected" : undefined}
                onClick={() => setSelectedId(document.id)}
              >
                <td role="cell" className="document-title-cell">
                  <div className="doc-cell">
                    {document.thumbnailUrl ? (
                      <img src={assetUrl(document.thumbnailUrl)} alt="" />
                    ) : (
                      <span className="thumb-skeleton" aria-hidden="true" />
                    )}
                    <div>
                      <strong>{document.title}</strong>
                      <small>#{document.id.slice(0, 13).toUpperCase()}</small>
                    </div>
                  </div>
                </td>
                <td role="cell" data-label="Review Status"><ReviewChip status={document.reviewStatus} /></td>
                <td role="cell" data-label="Family">{familyLabel(document.family)}</td>
                <td role="cell" data-label="Counterparty">{document.counterpartyDisplay ?? "Pending"}</td>
                <td role="cell" data-label="Date">{formatDate(document.documentDate)}</td>
                <td role="cell" data-label="Key Amount">{formatAmount(document.amountTotal)}</td>
                <td role="cell" data-label="Folder">{document.folderPaths?.[0]?.replace("/", "") || "Unfiled"}</td>
                <td role="cell" data-label="Tags">
                  {document.tags?.length ? (
                    <span className="table-tags">{document.tags.slice(0, 2).join(", ")}</span>
                  ) : (
                    <span className="muted-cell">None</span>
                  )}
                </td>
                <td role="cell" data-label="Related">{document.relatedCount ?? 0}</td>
                <td role="cell" data-label="Document State"><span className="muted-cell">{document.lifecycleState.replaceAll("_", " ") || "Unknown"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
    </>
  );
}
