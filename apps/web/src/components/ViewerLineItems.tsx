import {useState} from "react";
import type {CanonicalLines} from "../lineItems/types";
import type {EvidenceTarget} from "../types";
import {LineItemValueDetails} from "./LineItemValueDetails";
import {LineItemEvidence} from "./LineItemEvidence";
import {LineItemReviewPanel} from "./LineItemReviewPanel";
import {RecordedRows} from "./RecordedRows";

export function ViewerLineItems({documentId, family, authority, loading, error, onReload, evidenceTarget, onJump}: {
  documentId: string; family: string; authority: CanonicalLines | null; loading: boolean; error: string | null;
  onReload: () => Promise<unknown>; evidenceTarget: EvidenceTarget | null; onJump: (target: EvidenceTarget) => void;
}) {
  const [reviewId, setReviewId] = useState<string | null>(null);
  return <section aria-label="Canonical line items" className="viewer-line-items">
    <h3>Canonical line items</h3>
    <button type="button" disabled={loading} onClick={() => void onReload()}>Refresh line items</button>
    {loading ? <p role="status">Loading line decisions…</p> : error ? <p role="alert">{error}</p> : !authority ? <p role="alert">Line decision authority is unavailable.</p> : <>
      <p className="recorded-note">Every recorded row is shown with its current selection decision. Missing amounts are not inferred and document totals are not recalculated.</p>
      <p className="recorded-note">{authority.projection.state === "unestablished" ? "The accepted fact projection has not been established."
        : authority.projection.acceptedFactBasisSchemaVersion === "accepted_fields_and_lines.v1" ? "The accepted fact projection includes selected fields and line items."
          : "The current fact projection covers fields only; line-item coverage has not been established."}</p>
      {!authority.items.length ? <p className="recorded-note">No canonical line items are recorded. Eligible proposals can be added through explicit line review.</p> : null}
      <RecordedRows items={authority.items} label="line items" rowKey={(item) => item.id}
        focusIndex={authority.items.findIndex((item) => reviewId ? item.id === reviewId
          : `line_items.${item.lineItemType}.${item.ordinal}` === evidenceTarget?.fieldPath)}
        render={(item) => {
          const decision = authority.decisions.find((entry) => entry.canonicalLineItemId === item.id);
          const status = item.selected ? decision ? "Selected by human decision" : "Selected by earlier extraction policy"
            : decision?.disposition === "protected_legacy" ? "Historical value awaiting an explicit decision"
              : decision?.disposition === "rejected" || item.reviewStatus === "rejected" ? "Removed from accepted lines" : "Not selected as an accepted fact";
          return <article className="recorded-card" data-status={item.selected ? "accepted" : "review"}>
            <h4>{item.lineItemType.replaceAll("_", " ")} · position {item.ordinal}</h4>
            <p className="recorded-description">{item.description ?? "No description recorded"}</p>
            <p className="recorded-state">{status}</p><p className="recorded-note">Recorded source: {item.sourceKind} · {item.reviewStatus.replaceAll("_", " ")}</p>
            <LineItemValueDetails value={item} family={family} />
            <LineItemEvidence documentId={documentId} identity={`line_items.${item.lineItemType}.${item.ordinal}`} evidence={item.evidence} onJump={onJump} />
            <button type="button" onClick={() => setReviewId(item.id)}>Review line {item.ordinal} and history</button>
          </article>;
        }} />
      {reviewId ? <><button type="button" onClick={() => setReviewId(null)}>Close line review</button>
        <LineItemReviewPanel key={`${documentId}:${reviewId}`} documentId={documentId} canonicalId={reviewId}
          contextId={`canonical:${reviewId}`} family={family} onJump={onJump} onSaved={async () => { await onReload(); }} /></> : null}
    </>}
  </section>;
}
