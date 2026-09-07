import {evidenceTargetFromRef, selectEvidenceRef} from "../evidence";
import type {EvidenceRef, EvidenceTarget} from "../types";

export function RecordedFactEvidence({documentId, label, fieldPath, evidence, onJump}: {
  documentId: string; label: string; fieldPath: string; evidence?: EvidenceRef[];
  onJump: (target: EvidenceTarget) => void;
}) {
  const refs = (evidence ?? []).filter((ref) => Number.isInteger(ref.pageNumber) && ref.pageNumber > 0
    && (ref.elementId || ref.tableId || ref.textSpan || (Array.isArray(ref.bbox) && ref.bbox.length === 4)));
  const selected = selectEvidenceRef(refs);
  if (!selected) return <p className="recorded-note">No concrete evidence locator is available.</p>;
  const jump = (ref: EvidenceRef) => onJump(evidenceTargetFromRef(documentId, ref, fieldPath));
  return <div className="recorded-evidence">
    <button type="button" aria-label={`Evidence for ${label}, page ${selected.pageNumber}`}
      onClick={() => jump(selected)}>Evidence · page {selected.pageNumber}</button>
    {!selected.bbox ? <span>Text or table locator; no visual highlight.</span> : null}
    {selected.sourceText ? <blockquote>{selected.sourceText}</blockquote> : null}
    {refs.length > 1 ? <details><summary>All {refs.length} source locators</summary>
      <ul>{refs.map((ref, index) => <li key={index}>
        <button type="button" onClick={() => jump(ref)}>
          Page {ref.pageNumber}{ref.rowIndex != null ? ` · table row ${ref.rowIndex + 1}` : ref.tableId ? " · table" : ref.elementId ? " · element" : " · text"}
        </button>
      </li>)}</ul>
    </details> : null}
  </div>;
}
