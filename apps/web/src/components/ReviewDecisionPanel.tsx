import {useRef, useState} from "react";

import type {FieldCandidate, ReviewTask} from "../types";
import {CorrectionValueInput} from "./CorrectionValueInput";

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
  disabled = false,
  correctionRevisionReady = true,
}: {
  activeTask: ReviewTask;
  referenceCandidate?: FieldCandidate;
  onCorrect: (value: string, comment: string, currency?: string) => Promise<boolean>;
  onReject: (comment: string) => Promise<boolean>;
  onReclassify: (family: string, subtype: string, comment: string) => Promise<boolean>;
  onMarkDone: () => Promise<boolean>;
  onRerunExtraction: () => Promise<boolean>;
  disabled?: boolean;
  correctionRevisionReady?: boolean;
}) {
  const fieldPath = activeTask.fieldPath;
  const valueType = referenceCandidate?.valueType ?? "string";
  const [correctionError, setCorrectionError] = useState<string | null>(null);
  const [savingCorrection, setSavingCorrection] = useState(false);
  const correctionPending = useRef(false);
  const candidateCurrency = referenceCandidate?.currency ?? (
    referenceCandidate?.value && typeof referenceCandidate.value === "object"
      && "currency" in referenceCandidate.value
      ? String(referenceCandidate.value.currency ?? "") : ""
  );
  const correctionReady = !disabled && correctionRevisionReady
    && referenceCandidate?.documentId === activeTask.documentId
    && referenceCandidate?.fieldPath === activeTask.fieldPath;
  // Observation and line-item tasks are decided on their candidate cards
  // (accept/reject); relationship suggestions are decided through the
  // relationship actions. Field-shaped correct/reject forms only apply to
  // field-path review tasks.
  const candidateDecisionTask =
    activeTask.taskType === "observation_review" || activeTask.taskType === "line_item_review";
  const relationshipTask = activeTask.taskType === "relationship_suggestion";
  const showClassificationForm = !candidateDecisionTask && !relationshipTask;
  const showFieldForms = showClassificationForm && Boolean(fieldPath?.trim());

  return (
    <div className="review-decision-panel">
      {candidateDecisionTask ? (
        <p className="debug-copy">
          Use the candidate decisions above to record your review.
        </p>
      ) : null}
      {relationshipTask ? (
        <p className="debug-copy">
          Decide this suggestion from the Relationships workspace or the document&apos;s related panel.
        </p>
      ) : null}
      {showFieldForms && !correctionRevisionReady ? <p role="status" className="review-decision-notice">
        Reload this field to obtain its current revision before correcting.
      </p> : null}
      {showFieldForms ? (
      <form
        className="review-decision-form"
        aria-label="Correct canonical field"
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
        <CorrectionValueInput candidate={referenceCandidate}
          disabled={savingCorrection || !correctionReady} error={correctionError} />
        {valueType === "money" ? (
          <label>
            Currency
            <input name="currency" aria-label="Correction currency" defaultValue={candidateCurrency}
              pattern="[A-Z]{3}" maxLength={3} required disabled={savingCorrection || !correctionReady} />
          </label>
        ) : null}
        <label>
          Correction note
          <input name="comment" aria-label="Correction note" disabled={savingCorrection || !correctionReady} />
        </label>
        {correctionError ? <p id="correction-error" role="alert" className="review-decision-notice">{correctionError}</p> : null}
        <button type="submit" disabled={savingCorrection || !correctionReady}>
          {savingCorrection ? "Saving correction…" : "Correct field"}
        </button>
      </form>
      ) : null}

      {showFieldForms ? (
      <form
        className="review-decision-form compact"
        aria-label="Reject canonical field"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!correctionReady) return;
          const form = event.currentTarget;
          const data = new FormData(form);
          if (await onReject(String(data.get("comment") ?? ""))) form.reset();
        }}
      >
        <label>
          Reject note
          <input
            name="comment"
            aria-label="Reject note"
            defaultValue={`Rejected ${fieldPath}`}
            required
            disabled={disabled}
          />
        </label>
        <button type="submit" disabled={!correctionReady}>Reject field</button>
      </form>
      ) : null}

      {showClassificationForm ? (
      <form
        className="review-decision-form"
        aria-label="Classify document"
        onSubmit={async (event) => {
          event.preventDefault();
          if (disabled) return;
          const form = event.currentTarget;
          const data = new FormData(form);
          const saved = await onReclassify(
            String(data.get("family") ?? "generic"),
            String(data.get("subtype") ?? ""),
            String(data.get("comment") ?? ""),
          );
          if (saved) form.reset();
        }}
      >
        <label>
          Family
          <select name="family" aria-label="Document family" defaultValue={schemaFromTask(activeTask)} disabled={disabled}>
            {DOCUMENT_FAMILIES.map((family) => (
              <option key={family} value={family}>{family}</option>
            ))}
          </select>
        </label>
        <label>
          Subtype
          <input name="subtype" aria-label="Document subtype" disabled={disabled} />
        </label>
        <label>
          Reclassification note
          <input name="comment" aria-label="Reclassification note" disabled={disabled} />
        </label>
        <button type="submit" disabled={disabled}>Reclassify</button>
      </form>
      ) : null}

      <div className="review-actions">
        <button type="button" className="primary" disabled={disabled} onClick={() => void onMarkDone()}>
          Mark reviewed
        </button>
        <button type="button" disabled={disabled} onClick={() => void onRerunExtraction()}>
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
