import {useId, useState} from "react";
import {listCanonicalFields} from "../reviewApi";
import {useKeyedRequest} from "../useKeyedRequest";
import {getCanonicalLines} from "../lineItems/api";
import type {RecordedLineItem} from "../recordedLineItems";
import type {EvidenceTarget} from "../types";
import {ViewerFieldRecords} from "./ViewerFieldRecords";
import {ViewerLineItems} from "./ViewerLineItems";
import "./ViewerRecordedFacts.css";

export function ViewerRecordedFacts({documentId, family, evidenceTarget, onJump}: {
  documentId: string; family: string; lineItems: RecordedLineItem[]; evidenceTarget: EvidenceTarget | null;
  onJump: (target: EvidenceTarget) => void;
}) {
  const authority = useKeyedRequest(documentId, () => listCanonicalFields(documentId));
  const lines = useKeyedRequest(documentId, (signal) => getCanonicalLines(documentId, signal));
  const [view, setView] = useState(evidenceTarget?.fieldPath?.startsWith("line_items.") ? "lines" : "fields");
  const id = useId();
  return <section className="viewer-recorded-facts" aria-label="Recorded facts and line items">
    <div className="recorded-tabs" role="tablist" aria-label="Recorded fact sections">
      {[["fields", "Fields"], ["lines", `Line items${lines.data ? ` (${lines.data.items.length})` : ""}`]].map(([value, label]) => <button key={value}
        type="button" role="tab" id={`${id}-${value}`} aria-controls={`${id}-panel`} aria-selected={view === value}
        tabIndex={view === value ? 0 : -1} onClick={() => setView(value)} onKeyDown={(event) => {
          if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
            event.preventDefault();
            const next = event.key === "Home" ? "fields" : event.key === "End" ? "lines" : value === "fields" ? "lines" : "fields";
            setView(next); document.getElementById(`${id}-${next}`)?.focus();
          }
        }}>{label}</button>)}
    </div>
    <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-${view}`}>
      {view === "fields" ? <>
        <button type="button" className="recorded-refresh" disabled={authority.loading} onClick={() => void authority.reload()}>Refresh fields</button>
        {authority.loading ? <p role="status">Loading field decisions…</p>
          : authority.error ? <p role="alert">{authority.error.message}</p>
          : authority.data ? <ViewerFieldRecords authority={authority.data} evidenceTarget={evidenceTarget} onJump={onJump} /> : null}
      </> : <ViewerLineItems documentId={documentId} family={family} authority={lines.data} loading={lines.loading}
        error={lines.error?.message ?? null} onReload={lines.reload} evidenceTarget={evidenceTarget} onJump={onJump} />}
    </div>
  </section>;
}
