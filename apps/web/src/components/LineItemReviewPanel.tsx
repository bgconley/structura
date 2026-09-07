import {useState} from "react";
import {existingTarget, lineLabel, sourceExpectation} from "../lineItems/decisionIntent";
import {useLineItemReview} from "../lineItems/useLineItemReview";
import type {EvidenceTarget} from "../types";
import {LineItemValueDetails} from "./LineItemValueDetails";
import {LineItemTargetPicker} from "./LineItemTargetPicker";
import {LineItemEvidence} from "./LineItemEvidence";
import {LineItemHistory} from "./LineItemHistory";
import "./LineItemReview.css";

const reasons: Record<string, string> = {
  source_missing: "The source extraction is no longer available.", source_superseded: "This proposal belongs to a historical extraction.",
  source_failed: "The source extraction did not complete.", source_binding_invalid: "The source identity could not be established for this document.",
  evidence_incomplete: "Complete source evidence is required before this proposal can be selected.",
  legacy_assignment_conflict: "Earlier records assign this proposal to conflicting lines. Its destination must be resolved before publication.",
  unsupported_candidate_state: "This proposal is not in a supported review state.",
};
export function LineItemReviewPanel({documentId, candidateId, canonicalId, contextId, family, onJump, onSaved}: {
  documentId: string; candidateId?: string; canonicalId?: string; contextId: string; family?: string;
  onJump: (target: EvidenceTarget) => void; onSaved?: () => void | Promise<void>;
}) {
  const review = useLineItemReview(documentId, candidateId, contextId, onSaved);
  const {candidate, authority, draft} = review;
  const [picker, setPicker] = useState(false), [history, setHistory] = useState(false);
  const withdrawn = authority?.items.find((item) => item.id === canonicalId);
  const targetId = draft.request && "target" in draft.request ? draft.request.target.canonicalLineItemId : null;
  const target = authority?.items.find((item) => item.id === targetId);
  const chosen = draft.request;
  const candidateFamily = candidate?.extraction?.schemaName ?? family;
  const ready = review.authorized && !!authority && !review.loading && !review.pending;
  const sourceSelected = candidate?.sourceAssignment?.currentlySelected;
  const selectedLine = sourceSelected ? authority?.items.find((item) => item.id === candidate?.sourceAssignment?.canonicalLineItemId) : null;
  const canPublish = ready && candidate?.publicationEligibility.eligible && !sourceSelected;
  const historySelector = canonicalId ? {canonicalLineItemId: canonicalId} : candidateId ? {sourceCandidateId: candidateId} : null;
  const summary = chosen?.operation === "create" ? `Add this proposal as a separate ${chosen.target.lineItemType.replaceAll("_", " ")} · recorded line ${chosen.target.ordinal}`
    : chosen?.operation === "replace" ? `Replace ${target ? lineLabel(target) : "the previously chosen recorded line"}`
      : chosen?.operation === "reject_selected" ? `Remove ${target ? lineLabel(target) : "the previously chosen line"} from accepted lines`
        : chosen?.operation === "reject_candidate" ? "Reject this proposal; recorded lines stay unchanged" : null;
  return <section className="line-review" aria-label="Line-item review">
    <div className="line-review-heading"><h3>{canonicalId ? "Review recorded line" : "Review line proposal"}</h3>
      <button type="button" disabled={review.pending || review.loading} onClick={() => void review.reload()}>Reload line details</button></div>
    {!review.authorized ? <p role="alert">A current actor and household identity are required before saving a line decision.</p> : null}
    {review.loading ? <p role="status">Loading line authority and source details…</p> : null}
    {review.error ? <p role="alert">{review.error}</p> : null}
    {draft.message ? <p role={draft.phase === "conflict" || draft.phase === "unknown" ? "alert" : "status"}>{draft.message}</p> : null}
    {candidate ? <article className="line-proposal" aria-label="Source proposal">
      <h4>{candidate.description ?? "No description recorded"}</h4>
      <p>Source proposal {candidate.ordinal} · {candidate.extraction?.extractionScope.replaceAll("_", " ") ?? "Extraction unavailable"}
        {candidate.candidateGroup ? ` · ${candidate.candidateGroup}` : ""}</p>
      <p>{candidate.sourceEngine}{candidate.extraction?.modelName ? ` · ${candidate.extraction.modelName}` : ""}</p>
      <p>{sourceSelected ? `Selected as recorded line ${candidate.sourceAssignment?.target?.ordinal}`
        : candidate.status === "rejected" ? "Proposal rejected previously; a new explicit selection reverses that decision."
          : candidate.status === "accepted" ? "Previously accepted as a proposal; currently not a selected line." : "Proposal awaiting review"}</p>
      {!candidate.publicationEligibility.eligible ? <p className="line-warning">{reasons[candidate.publicationEligibility.reason] ?? "Publication eligibility is unreported."}</p> : null}
      {candidate.sourceAssignment?.state === "assigned" && !sourceSelected ? <p>This proposal can only replace its original recorded line {candidate.sourceAssignment.target?.ordinal}. It cannot be added to another position.</p> : null}
      <LineItemValueDetails value={candidate} family={candidateFamily} />
      <LineItemEvidence documentId={documentId} identity={`line_item_candidates.${candidate.id}`} evidence={candidate.evidence}
        historical={["source_superseded", "source_missing", "source_failed"].includes(candidate.publicationEligibility.reason)} onJump={onJump} />
      <details><summary>Source and validation details</summary>
        <dl><dt>Proposal identity</dt><dd>{candidate.id}</dd><dt>Extraction identity</dt><dd>{candidate.extractionId ?? "Not recorded"}</dd>
          <dt>Schema</dt><dd>{candidate.extraction ? `${candidate.extraction.schemaName} · ${candidate.extraction.schemaVersion}` : "Not recorded"}</dd>
          <dt>Model revision</dt><dd>{candidate.extraction?.modelVersion ?? "Not recorded"}</dd>
          <dt>Prompt version</dt><dd>{candidate.extraction?.promptVersion ?? "Not recorded"}</dd></dl>
        <p>{candidate.validation.needsReview === true ? "Validation indicates review is needed." : candidate.validation.needsReview === false ? "Validation did not flag review." : "Validation review requirement is unreported."}</p>
        <ul>{candidate.validation.checks.map((check, index) => <li key={index}>{check.code}: {check.status.replaceAll("_", " ")}</li>)}</ul>
        {candidate.validation.unrepresentedCheckCount ? <p>{candidate.validation.unrepresentedCheckCount} additional checks are retained but not represented in this view.</p> : null}
      </details>
      <div className="line-actions">
        {sourceSelected ? <button type="button" disabled={!ready || !selectedLine} onClick={() => {
          if (selectedLine) onJump({documentId, pageNumber: selectedLine.evidence[0]?.pageNumber,
            fieldPath: `line_items.${selectedLine.lineItemType}.${selectedLine.ordinal}`});
        }}>Open selected recorded line</button> : null}
        {candidate.suggestedVacantTarget && !sourceSelected ? <button type="button" disabled={!canPublish} onClick={() => {
          setPicker(false); review.choose({operation: "create", source: sourceExpectation(candidate), target: candidate.suggestedVacantTarget!});
        }}>Add as a separate line</button> : null}
        {!sourceSelected ? <button type="button" disabled={!canPublish} onClick={() => setPicker(!picker)}>Replace a recorded line…</button> : null}
        {!sourceSelected ? <button type="button" disabled={!ready} onClick={() => { setPicker(false); review.choose({operation: "reject_candidate", source: sourceExpectation(candidate)}); }}>Reject this proposal</button> : null}
      </div>
    </article> : !review.loading && !review.error && candidateId ? <p>No current proposal was found for this exact task. Its retained history remains available.</p> : null}
    {!candidateId && !canonicalId ? <p>This task does not identify an exact line proposal. No destination or proposal is selected automatically.</p> : null}
    {picker && candidate && authority && ready ? <LineItemTargetPicker candidate={candidate} items={authority.items} onChoose={(item) => {
      review.choose({operation: "replace", source: sourceExpectation(candidate), target: existingTarget(item, authority)}); setPicker(false);
    }} /> : null}
    {withdrawn && authority ? <article className="line-proposal" aria-label="Recorded line to review"><h4>{lineLabel(withdrawn)}</h4>
      <LineItemValueDetails value={withdrawn} family={family} />
      <LineItemEvidence documentId={documentId} identity={`line_items.${withdrawn.lineItemType}.${withdrawn.ordinal}`} evidence={withdrawn.evidence} onJump={onJump} />
      <p>{withdrawn.selected ? "This line is currently selected." : "This line is not selected; its values and history are retained."}</p>
      {withdrawn.selected ? <button type="button" disabled={!ready} onClick={() => review.choose({operation: "reject_selected", target: existingTarget(withdrawn, authority)})}>Remove from accepted lines…</button> : null}
    </article> : null}
    {summary ? <section className="line-confirmation" aria-label="Review line decision"><h4>{summary}</h4>
      {target && chosen?.operation === "replace" ? <div className="line-comparison"><section aria-label="Current recorded value"><h4>Current recorded value</h4><p>{target.description}</p>
        <LineItemValueDetails value={target} family={family ?? candidateFamily} /></section>
      {candidate ? <section aria-label="Proposed replacement value"><h4>Proposed replacement value</h4><p>{candidate.description}</p><LineItemValueDetails value={candidate} family={candidateFamily} /></section> : null}</div> : null}
      {chosen?.operation === "reject_selected" ? <p>The row, values and history are retained. This line will be excluded from accepted facts; document totals are not recalculated.</p> : null}
      {chosen?.operation === "create" ? <p>The destination shown above is advisory until saved. A conflicting selection requires a new explicit decision.</p> : null}
      {draft.phase !== "reviewing" && draft.phase !== "saving" ? <p>Previous intent retained for reference. Review the latest values and choose the action again to enable saving.</p> : null}
    </section> : null}
    <label className="line-comment">Decision comment<textarea maxLength={2000} value={draft.comment} disabled={review.pending}
      onChange={(event) => review.setComment(event.target.value)} /></label>
    {chosen ? <div className="line-actions"><button type="button" className="primary" disabled={!ready || draft.phase !== "reviewing"} onClick={() => void review.save()}>
      {review.pending ? "Saving decision…" : chosen.operation === "create" ? "Add this line" : chosen.operation === "replace" ? "Save replacement"
        : chosen.operation === "reject_selected" ? "Confirm removal from accepted lines" : "Confirm proposal rejection"}
    </button><button type="button" disabled={review.pending} onClick={review.cancel}>Cancel this decision</button></div> : null}
    {historySelector ? <><button type="button" className="line-history-toggle" aria-expanded={history} onClick={() => setHistory(!history)}>Decision history</button>
      {history ? <LineItemHistory documentId={documentId} selector={historySelector} revision={String(authority?.projection.projectionRevision ?? "unloaded")} onJump={onJump} /> : null}</> : null}
  </section>;
}
