import type {CanonicalFieldResponse} from "../types";
import {recordedFieldStatus} from "../reviewAuthority";

export function ReviewFieldHistory({authority, fieldPath, formatValue}: {
  authority: CanonicalFieldResponse | null;
  fieldPath?: string;
  formatValue: (value: unknown, currency?: string, valueType?: string) => string;
}) {
  if (!authority) return null;
  const fields = authority.items.filter((field) => !fieldPath || field.fieldPath === fieldPath);
  const decisions = authority.decisions.filter((decision) => !fieldPath || decision.fieldPath === fieldPath);
  const guards = authority.pathGuards.filter((guard) => guard.status === "active" && (!fieldPath || guard.fieldPath === fieldPath));
  return <div className="canonical-summary">
    <h3>Recorded fields and human decisions</h3>
    {authority.projection.state === "unestablished" ? <p role="status">Accepted facts have not been verified for this document yet. You can review the recorded values and make a human decision.</p> : null}
    {fields.map((field) => <p key={field.id}>
      <strong>{field.fieldPath} · position {field.ordinal ?? 1}</strong>
      <span>{formatValue(field.value, field.currency, field.valueType)} · {recordedFieldStatus(authority, field)}</span>
    </p>)}
    {!fields.length ? <p>No recorded canonical value.</p> : null}
    {decisions.map((decision) => <p key={decision.id}>
      <strong>{decision.fieldPath} · position {decision.ordinal}</strong>
      <span>{decision.disposition === "protected_legacy" ? "Protected historical decision" : `Human ${decision.disposition}`}
        {decision.disposition === "rejected" ? " · This position has no accepted fact." : ""}
      </span>
    </p>)}
    {guards.map((guard) => <p key={guard.id}>
      <strong>{guard.fieldPath}</strong>
      <span>An earlier rejection protects every position in this field. Your next decision changes only the selected position; other positions remain protected.</span>
    </p>)}
  </div>;
}
