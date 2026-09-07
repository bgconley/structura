import {useLineItemHistory} from "../lineItems/useLineItemHistory";
import type {HistorySelector, HistoryValue} from "../lineItems/types";
import type {EvidenceTarget} from "../types";
import {LineItemValueDetails} from "./LineItemValueDetails";
import {LineItemEvidence} from "./LineItemEvidence";

function HistoryValues({value, label, onJump}: {value: HistoryValue; label: string; onJump: (target: EvidenceTarget) => void}) {
  return <section aria-label={label}><h4>{label}</h4><p>{value.canonical.description ?? "No description recorded"}</p>
    <p>{value.canonical.selected ? "Selected at this decision" : "Not selected at this decision"}</p>
    <LineItemValueDetails value={value.canonical} family={value.source?.extraction?.schemaName} />
    <p>{value.sourceCoverage === "recorded" ? "Source identity retained with this decision." : "Legacy source identity was not established by this history record."}</p>
    {value.source ? <p>Source proposal {value.source.candidate.ordinal} · {value.source.extraction?.extractionScope ?? "Extraction unavailable"} · {value.source.candidate.sourceEngine}</p> : null}
    <LineItemEvidence documentId={value.canonical.documentId} identity="historical line" historical evidence={value.canonical.evidence} onJump={onJump} />
  </section>;
}
export function LineItemHistory({documentId, selector, revision, onJump}: {documentId: string; selector: HistorySelector;
  revision: string; onJump: (target: EvidenceTarget) => void}) {
  const history = useLineItemHistory(documentId, selector, revision);
  return <section className="line-history" aria-label="Line decision history"><h3>Decision history</h3>
    {history.loading ? <p role="status">Loading line history…</p> : null}
    {history.error ? <p role="alert">{history.error} <button type="button" onClick={() => void history.reload()}>Retry history</button></p> : null}
    {!history.loading && !history.error && !history.items.length ? <p>No retained decisions were found for this exact line or proposal.</p> : null}
    {history.items.map((entry) => <details key={entry.id} className="line-history-event"><summary>
      {entry.operation.replaceAll("_", " ")} · {entry.actorLabel} · {entry.occurredAt}
    </summary><p>{entry.comment ?? "No comment recorded"}</p>
      {entry.coverage === "legacy_partial" ? <><p>Partial legacy history; full values and precision were not retained.</p>
        <p>{entry.legacySummary?.description ?? "Description not recorded"} · {entry.legacySummary?.status ?? "Status not recorded"}</p>
        <p>Legacy amount: {entry.legacySummary?.netAmount ?? "Not recorded"}</p></> : <>
        {entry.before ? <HistoryValues value={entry.before} label="Before this decision" onJump={onJump} /> : null}
        {entry.after ? <HistoryValues value={entry.after} label="After this decision" onJump={onJump} /> : null}
        {entry.source && !entry.after ? <><h4>Reviewed source proposal</h4><p>{entry.source.candidate.description}</p>
          <LineItemValueDetails value={entry.source.candidate} family={entry.source.extraction?.schemaName} />
          <LineItemEvidence documentId={documentId} identity="historical proposal" historical evidence={entry.source.evidence} onJump={onJump} /></> : null}
      </>}
    </details>)}
    {history.cursor ? <button type="button" disabled={history.loading} onClick={() => void history.more()}>Load earlier decisions</button> : null}
  </section>;
}
