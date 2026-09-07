import {evidenceTargetFromRef} from "../evidence";
import type {EvidenceRef, EvidenceTarget} from "../types";

export function LineItemEvidence({documentId, identity, evidence, historical = false, onJump}: {
  documentId: string; identity: string; evidence: EvidenceRef[]; historical?: boolean; onJump: (target: EvidenceTarget) => void;
}) {
  return <div className="recorded-evidence">
    {!evidence.length ? <p>No concrete source locator is recorded.</p> : null}
    {historical ? <p className="recorded-note">Historical source: open the recorded original page. An exact historical parse highlight is not attached to this view.</p> : null}
    {evidence.map((ref, index) => <div key={index}>
      <button type="button" aria-label={`Evidence for ${identity}, page ${ref.pageNumber}`}
        onClick={() => onJump(historical ? {documentId, pageNumber: ref.pageNumber}
          : evidenceTargetFromRef(documentId, ref, identity))}>{historical ? "Original page" : "Evidence"} · page {ref.pageNumber}</button>
      {!ref.bbox && !historical ? <span>Recorded text or table locator; no visual highlight.</span> : null}
      {ref.sourceText ? <blockquote>{ref.sourceText}</blockquote> : null}
    </div>)}
  </div>;
}
