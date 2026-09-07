import {useState} from "react";
import type {UploadAttempt, UploadDecision} from "../uploads/types";

export function UploadDuplicateChoice({attempt, disabled, onChoose, onOpenDocument}: {attempt: UploadAttempt; disabled: boolean;
  onChoose: (decision: UploadDecision) => void; onOpenDocument: (documentId: string) => void}) {
  const [selected, setSelected] = useState<string | null>(null);
  return <fieldset className="upload-duplicates" disabled={disabled}><legend>An exact copy is already recorded</legend>
    <p>Use a listed document without changing its filing or facts, or keep this upload as a separate document.</p>
    {!attempt.duplicates.length ? <p>The earlier matching documents are no longer available in this observation. No replacement is selected automatically.</p> : null}
    {attempt.duplicates.map((match) => <div key={match.documentId}>
      <label><input type="radio" name={`duplicate-${attempt.uploadId}`} value={match.documentId}
        checked={selected === match.documentId} onChange={() => setSelected(match.documentId)} />{match.title}</label>
      <button type="button" onClick={() => onOpenDocument(match.documentId)}>Inspect {match.title}</button>
    </div>)}
    <div className="upload-row-actions"><button type="button" disabled={!selected}
      onClick={() => { if (selected) onChoose({revision: attempt.revision, decision: "use_existing", documentId: selected}); }}>Use selected existing document</button>
    <button type="button" onClick={() => onChoose({revision: attempt.revision, decision: "keep_separate"})}>Keep as a separate document</button></div>
  </fieldset>;
}
