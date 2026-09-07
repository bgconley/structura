import {recordedFieldStatus} from "../reviewAuthority";
import {recordedValue} from "../recordedFactValues";
import type {CanonicalFieldResponse, EvidenceRef, EvidenceTarget} from "../types";
import {RecordedFactEvidence} from "./RecordedFactEvidence";
import {RecordedRows} from "./RecordedRows";

const locatorKey = (ref: EvidenceRef | EvidenceTarget) => JSON.stringify([ref.pageNumber, ref.tableId, ref.rowIndex,
  ref.elementId, ref.bbox, ref.textSpan?.start, ref.textSpan?.end]);

export function ViewerFieldRecords({authority, evidenceTarget, onJump}: {
  authority: CanonicalFieldResponse; evidenceTarget: EvidenceTarget | null; onJump: (target: EvidenceTarget) => void;
}) {
  const documentId = authority.projection.documentId;
  const records = authority.items.map((field) => ({key: field.id, fieldPath: field.fieldPath, ordinal: field.ordinal ?? 1,
    field, status: recordedFieldStatus(authority, field)}));
  const accepted = records.filter((record) => record.status === "Accepted value").length;
  const unbound = authority.decisions.filter((decision) => !authority.items.some((field) => field.fieldPath === decision.fieldPath
    && (field.ordinal ?? 1) === decision.ordinal));
  return <section aria-label="Recorded fields" className="viewer-recorded-fields">
    <h3>Recorded fields</h3>
    <p className="recorded-note">{accepted} accepted of {records.length} recorded values. Acceptance follows the current field decisions.</p>
    {authority.projection.state === "unestablished" ? <p role="status" className="recorded-warning">Accepted facts have not been verified for this document yet.</p> : null}
    {!records.length ? <p className="recorded-note">No canonical field values are recorded.</p> : null}
    <RecordedRows items={records} label="recorded fields" rowKey={(record) => record.key}
      focusIndex={records.findIndex((record) => record.fieldPath === evidenceTarget?.fieldPath
        && record.field.evidence?.some((ref) => evidenceTarget && locatorKey(ref) === locatorKey(evidenceTarget)))}
      render={({field, ordinal, status}) => <article className="recorded-card" data-status={status === "Accepted value" ? "accepted" : "review"}>
        <h4>{field.fieldPath} <span>· position {ordinal}</span></h4>
        <pre className="recorded-value">{recordedValue(field.value, field.valueType, field.currency)}</pre>
        <p className="recorded-state">{status}</p>
        <p className="recorded-note">Recorded source: {field.sourceKind} · {field.reviewStatus.replaceAll("_", " ")}</p>
        <RecordedFactEvidence documentId={documentId} label={`${field.fieldPath}, position ${ordinal}`}
          fieldPath={field.fieldPath} evidence={field.evidence} onJump={onJump} />
        {field.validation && Object.keys(field.validation).length ? <details><summary>Validation details</summary>
          <pre>{JSON.stringify(field.validation, null, 2)}</pre></details> : null}
      </article>} />
    {unbound.length ? <section aria-label="Human decisions without values"><h4>Human decisions without a current value</h4>
      <RecordedRows items={unbound} label="decisions without values" rowKey={(decision) => decision.id} render={(decision) => <article className="recorded-card">
        <h4>{decision.fieldPath} · position {decision.ordinal}</h4>
        <p>Human {decision.disposition.replaceAll("_", " ")}. No accepted value is present for this position.</p>
      </article>} /></section> : null}
    {authority.pathGuards.filter((guard) => guard.status === "active").map((guard) => <p className="recorded-warning" key={guard.id}>
      {guard.fieldPath}: an earlier rejection protects positions without an explicit newer decision.
    </p>)}
  </section>;
}
