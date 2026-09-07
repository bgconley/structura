import {recordedValue} from "../recordedFactValues";
import {lineItemStatus, type RecordedLineItem} from "../recordedLineItems";
import type {EvidenceTarget} from "../types";
import {RecordedFactEvidence} from "./RecordedFactEvidence";
import {RecordedRows} from "./RecordedRows";

const columns = [
  ["code", "Code", "string"], ["codeSystem", "Code system", "string"], ["serviceDate", "Service date", "date"],
  ["quantity", "Quantity", "number"], ["unit", "Unit", "string"], ["unitPrice", "Unit price", "money"],
  ["grossAmount", "Gross amount", "money"], ["discountAmount", "Discount", "money"],
  ["taxAmount", "Tax", "money"], ["netAmount", "Net amount", "money"], ["categoryHint", "Category", "string"],
] as const;
const path = (item: RecordedLineItem) => `line_items.${item.lineItemType}.${item.ordinal ?? 1}`;

export function ViewerLineItems({documentId, family, items, evidenceTarget, onJump}: {
  documentId: string; family: string; items: RecordedLineItem[]; evidenceTarget: EvidenceTarget | null;
  onJump: (target: EvidenceTarget) => void;
}) {
  if (items.some((item) => item.documentId && item.documentId !== documentId)) return <p role="alert">Line items did not match this document. Reload the document before using them.</p>;
  return <section aria-label="Canonical line items" className="viewer-line-items">
    <h3>Canonical line items</h3>
    <p className="recorded-note">Line items show their recorded review status and are reviewed separately from individual fields. No totals are calculated here.</p>
    {family === "medical_eob" ? <p className="recorded-note">These recorded rows do not include an allowed, plan-paid or patient-responsibility breakdown. Missing amounts are not inferred.</p> : null}
    {!items.length ? <p className="recorded-note">No canonical line items are recorded. Accepting a line-item candidate records review only; it does not create a canonical row.</p> : null}
    <RecordedRows items={items} label="line items" rowKey={(item) => item.id}
      focusIndex={items.findIndex((item) => path(item) === evidenceTarget?.fieldPath)}
      render={(item) => <article className="recorded-card" data-status={lineItemStatus(item.reviewStatus).startsWith("Accepted") ? "accepted" : "review"}>
        <h4>{item.lineItemType.replaceAll("_", " ")} · position {item.ordinal ?? 1}</h4>
        <p className="recorded-description">{item.description ?? "No description recorded"}</p>
        <p className="recorded-state">{lineItemStatus(item.reviewStatus)}</p>
        <p className="recorded-note">Recorded source: {item.sourceKind ?? "Unspecified"} · {item.reviewStatus?.replaceAll("_", " ") ?? "Unspecified review status"}</p>
        <dl>{columns.map(([key, label, type]) => <div key={key} data-value-type={type}>
          <dt>{label}</dt><dd>{recordedValue(item[key], type, item.currency)}</dd>
        </div>)}</dl>
        <RecordedFactEvidence documentId={documentId} label={`line item ${item.ordinal ?? 1}`}
          fieldPath={path(item)} evidence={item.evidence} onJump={onJump} />
        {item.validation && Object.keys(item.validation).length ? <details><summary>Validation details</summary>
          <pre>{JSON.stringify(item.validation, null, 2)}</pre></details> : null}
      </article>} />
  </section>;
}
