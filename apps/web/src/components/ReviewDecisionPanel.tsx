import {useRef, useState} from "react";

import type {FieldCandidate, ReviewTask} from "../types";

const DOCUMENT_FAMILIES = [
  "generic",
  "receipt",
  "retail_order",
  "service_record",
  "invoice",
  "medical_eob",
  "medical_bill",
  "insurance_document",
  "insurance_denial",
  "real_estate_title",
  "mortgage_escrow_statement",
  "financial_dispute_form",
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
  onCorrect: (value: string, comment: string, currency?: string) => Promise<boolean>;
  onReject: (comment: string) => Promise<void>;
  onReclassify: (family: string, subtype: string, comment: string) => Promise<void>;
  onMarkDone: () => Promise<void>;
  onRerunExtraction: () => Promise<void>;
}) {
  const fieldPath = activeTask.fieldPath ?? "classification.document_family";
  const valueType = referenceCandidate?.valueType ?? "string";
  const [correctionError, setCorrectionError] = useState<string | null>(null);
  const [savingCorrection, setSavingCorrection] = useState(false);
  const correctionPending = useRef(false);
  const candidateCurrency = referenceCandidate?.currency ?? (
    referenceCandidate?.value && typeof referenceCandidate.value === "object"
      && "currency" in referenceCandidate.value
      ? String(referenceCandidate.value.currency ?? "") : ""
  );
  const correctionReady = referenceCandidate?.documentId === activeTask.documentId
    && referenceCandidate?.fieldPath === activeTask.fieldPath;
  // Observation and line-item tasks are decided on their candidate cards
  // (accept/reject); relationship suggestions are decided through the
  // relationship actions. Field-shaped correct/reject forms only apply to
  // field-path review tasks.
  const candidateDecisionTask =
    activeTask.taskType === "observation_review" || activeTask.taskType === "line_item_review";
  const relationshipTask = activeTask.taskType === "relationship_suggestion";
  const showFieldForms = !candidateDecisionTask && !relationshipTask;

  return (
    <div className="review-decision-panel">
      {candidateDecisionTask ? (
        <p className="debug-copy">
          Accept or reject the candidate above; both decisions clear this task.
        </p>
      ) : null}
      {relationshipTask ? (
        <p className="debug-copy">
          Decide this suggestion from the Relationships workspace or the document&apos;s related panel.
        </p>
      ) : null}
      {showFieldForms ? (
      <form
        className="review-decision-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (correctionPending.current || !correctionReady) return;
          const form = event.currentTarget;
          const data = new FormData(form);
          correctionPending.current = true;
          setSavingCorrection(true);
          setCorrectionError(null);
          try {
            const saved = await onCorrect(
              String(data.get("correctedValue") ?? ""),
              String(data.get("comment") ?? ""),
              valueType === "money" ? String(data.get("currency") ?? "").trim() : undefined,
            );
            if (saved) form.reset();
            else setCorrectionError("Correction was not saved. Your entries have been kept; see the review status.");
          } catch (error) {
            setCorrectionError(error instanceof Error ? error.message : "Correction was not saved.");
          } finally {
            correctionPending.current = false;
            setSavingCorrection(false);
          }
        }}
      >
        <label>
          Corrected value
          <input
            name="correctedValue"
            aria-label="Corrected value"
            inputMode={valueType === "money" || valueType === "number" ? "decimal" : "text"}
            placeholder={formatValue(referenceCandidate?.value, referenceCandidate?.currency)}
            aria-invalid={correctionError ? true : undefined}
            aria-describedby={correctionError ? "correction-error" : undefined}
            disabled={savingCorrection || !correctionReady}
            required
          />
        </label>
        {valueType === "money" ? (
          <label>
            Currency
            <input name="currency" aria-label="Correction currency" defaultValue={candidateCurrency}
              pattern="[A-Z]{3}" maxLength={3} required disabled={savingCorrection} />
          </label>
        ) : null}
        {valueType === "money" || valueType === "number" ? (
          <small>Use a decimal amount such as 1234.56, without currency or grouping separators.</small>
        ) : null}
        <label>
          Correction note
          <input name="comment" aria-label="Correction note" disabled={savingCorrection} />
        </label>
        {correctionError ? <p id="correction-error" role="alert">{correctionError}</p> : null}
        <button type="submit" disabled={savingCorrection || !correctionReady}>
          {savingCorrection ? "Saving correction…" : "Correct field"}
        </button>
      </form>
      ) : null}

      {showFieldForms ? (
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
      ) : null}

      {showFieldForms ? (
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
      ) : null}

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
