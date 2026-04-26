import type {FieldCandidate, ReviewTask} from "../types";

const DOCUMENT_FAMILIES = [
  "generic",
  "receipt",
  "invoice",
  "medical_eob",
  "medical_bill",
  "insurance_document",
  "legal_contract",
  "legal_notice",
  "tax_document",
  "warranty",
  "identity_document",
  "bank_statement",
  "financial_statement",
  "handwritten_note",
  "typed_note",
  "whitepaper",
  "reference_document",
];

export function ReviewDecisionPanel({
  activeTask,
  referenceCandidate,
  onCorrect,
  onReject,
  onReclassify,
  onMarkDone,
  onRerunExtraction,
}: {
  activeTask: ReviewTask;
  referenceCandidate?: FieldCandidate;
  onCorrect: (value: string, comment: string) => Promise<void>;
  onReject: (comment: string) => Promise<void>;
  onReclassify: (family: string, subtype: string, comment: string) => Promise<void>;
  onMarkDone: () => Promise<void>;
  onRerunExtraction: () => Promise<void>;
}) {
  const fieldPath = activeTask.fieldPath ?? "classification.document_family";
  const valueType = referenceCandidate?.valueType ?? "string";

  return (
    <div className="review-decision-panel">
      <form
        className="review-decision-form"
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          void onCorrect(
            String(data.get("correctedValue") ?? ""),
            String(data.get("comment") ?? ""),
          );
          event.currentTarget.reset();
        }}
      >
        <label>
          Corrected value
          <input
            name="correctedValue"
            aria-label="Corrected value"
            inputMode={valueType === "money" || valueType === "number" ? "decimal" : "text"}
            placeholder={formatValue(referenceCandidate?.value, referenceCandidate?.currency)}
            required
          />
        </label>
        <label>
          Correction note
          <input name="comment" aria-label="Correction note" />
        </label>
        <button type="submit">Correct field</button>
      </form>

      <form
        className="review-decision-form compact"
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          void onReject(String(data.get("comment") ?? ""));
          event.currentTarget.reset();
        }}
      >
        <label>
          Reject note
          <input
            name="comment"
            aria-label="Reject note"
            defaultValue={`Rejected ${fieldPath}`}
            required
          />
        </label>
        <button type="submit">Reject field</button>
      </form>

      <form
        className="review-decision-form"
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          void onReclassify(
            String(data.get("family") ?? "generic"),
            String(data.get("subtype") ?? ""),
            String(data.get("comment") ?? ""),
          );
          event.currentTarget.reset();
        }}
      >
        <label>
          Family
          <select name="family" aria-label="Document family" defaultValue={schemaFromTask(activeTask)}>
            {DOCUMENT_FAMILIES.map((family) => (
              <option key={family} value={family}>{family}</option>
            ))}
          </select>
        </label>
        <label>
          Subtype
          <input name="subtype" aria-label="Document subtype" />
        </label>
        <label>
          Reclassification note
          <input name="comment" aria-label="Reclassification note" />
        </label>
        <button type="submit">Reclassify</button>
      </form>

      <div className="review-actions">
        <button type="button" className="primary" onClick={() => void onMarkDone()}>
          Mark reviewed
        </button>
        <button type="button" onClick={() => void onRerunExtraction()}>
          Re-run extraction
        </button>
      </div>
    </div>
  );
}

function schemaFromTask(task: ReviewTask): string {
  if (task.fieldPath?.startsWith("invoice.")) {
    return "invoice";
  }
  if (task.fieldPath?.startsWith("medical_eob.")) {
    return "medical_eob";
  }
  if (task.fieldPath?.startsWith("receipt.")) {
    return "receipt";
  }
  return "generic";
}

function formatValue(value: unknown, currency?: string): string {
  if (value && typeof value === "object" && "amount" in value) {
    const money = value as {amount?: number; currency?: string};
    return `${money.amount ?? ""} ${money.currency ?? currency ?? "USD"}`.trim();
  }
  return value === null || value === undefined ? "" : String(value);
}
