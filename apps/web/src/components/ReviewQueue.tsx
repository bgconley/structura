import {useEffect, useMemo} from "react";

import {useReviewQueueState} from "../useReviewQueueState";
import {
  coerceCorrectionValue,
  evidenceTargetFromCandidate,
  referenceCandidate,
} from "../reviewActions";
import {evidenceTargetFromRef, selectEvidenceRef} from "../evidence";
import type {
  CanonicalField,
  EvidenceRef,
  EvidenceTarget,
  FieldCandidate,
  LineItemCandidate,
  ObservationCandidate,
} from "../types";
import {ReviewDecisionPanel} from "./ReviewDecisionPanel";
import "./ReviewQueue.css";

export function ReviewQueue({
  onOpenDocument, selectedTaskId, documentId, onSelectTask, onReady,
}: {
  onReady: () => void;
  selectedTaskId?: string;
  documentId?: string;
  onSelectTask: (taskId: string | undefined) => void;
  onOpenDocument: (documentId: string, evidenceTarget?: EvidenceTarget) => void;
}) {
  const {tasks, activeTask, selectTask, candidates, observations, lineItems, canonical,
    status, setStatus, pending, detailReady, selectionError, taskLoading, tasksLoaded, refresh, applyReviewAction}
    = useReviewQueueState(selectedTaskId, documentId, onSelectTask);
  const decisionDisabled = pending || !detailReady || activeTask?.status !== "open";
  useEffect(() => {
    if (selectionError || detailReady || (tasksLoaded && !taskLoading && !activeTask)) onReady();
  });

  async function handleAccept(candidate: FieldCandidate) {
    await applyReviewAction(
      {
        schemaName: "review_action",
        schemaVersion: "v1",
        documentId: candidate.documentId,
        reviewTaskId: activeTask?.id,
        actionType: "confirm_field",
        actorType: "human",
        fieldPath: candidate.fieldPath,
        newValue: candidate.id,
        metadata: {candidateId: candidate.id},
        comment: "Accepted from review queue.",
        createdAt: new Date().toISOString(),
      },
      "Candidate accepted and promoted.",
    );
  }

  async function handleObservationDecision(
    candidate: ObservationCandidate,
    decision: "accept" | "reject",
  ) {
    await applyReviewAction(
      {
        schemaName: "review_action",
        schemaVersion: "v1",
        documentId: candidate.documentId,
        reviewTaskId: activeTask?.id,
        actionType: decision === "accept" ? "accept_observation" : "reject_observation",
        actorType: "human",
        metadata: {observationId: candidate.id},
        comment: `Observation ${decision}ed from review queue.`,
        createdAt: new Date().toISOString(),
      },
      decision === "accept" ? "Observation accepted." : "Observation rejected.",
    );
  }

  async function handleLineItemDecision(
    candidate: LineItemCandidate,
    decision: "accept" | "reject",
  ) {
    await applyReviewAction(
      {
        schemaName: "review_action",
        schemaVersion: "v1",
        documentId: candidate.documentId,
        reviewTaskId: activeTask?.id,
        actionType: decision === "accept" ? "accept_line_item" : "reject_line_item",
        actorType: "human",
        metadata: {lineItemCandidateId: candidate.id},
        comment: `Line item ${decision}ed from review queue.`,
        createdAt: new Date().toISOString(),
      },
      decision === "accept" ? "Line item accepted." : "Line item rejected.",
    );
  }

  async function handleCorrect(valueText: string, comment: string, currency?: string) {
    if (!activeTask?.fieldPath) {
      setStatus("Select a field review task before correcting.");
      return false;
    }
    const reference = referenceCandidate(activeTask, candidates);
    if (!reference) throw new Error("Wait for the selected field's candidate before correcting.");
    const currentField = canonical.find((field) => field.fieldPath === activeTask.fieldPath
      && (field.ordinal ?? 1) === (reference.ordinal ?? 1));
    if (currentField && !currentField.updatedAt) {
      throw new Error("Reload this field to obtain its current revision before correcting.");
    }
    const coerced = coerceCorrectionValue(
      valueText,
      reference.valueType,
      currency,
    );
    return applyReviewAction(
      {
        schemaName: "review_action",
        schemaVersion: "v1",
        documentId: activeTask.documentId,
        reviewTaskId: activeTask.id,
        actionType: "correct_field",
        actorType: "human",
        fieldPath: activeTask.fieldPath,
        newValue: coerced.value,
        expectedUpdatedAt: currentField?.updatedAt ?? null,
        evidenceContext: reference?.evidence,
        metadata: {...coerced.metadata, ordinal: reference.ordinal ?? 1, candidateId: reference.id},
        comment: comment || "Corrected from review queue.",
        createdAt: new Date().toISOString(),
      },
      "Field corrected and review history updated.",
    );
  }

  async function handleReject(comment: string) {
    if (!activeTask?.fieldPath) {
      setStatus("Select a field review task before rejecting.");
      return false;
    }
    return applyReviewAction(
      {
        schemaName: "review_action",
        schemaVersion: "v1",
        documentId: activeTask.documentId,
        reviewTaskId: activeTask.id,
        actionType: "reject_field",
        actorType: "human",
        fieldPath: activeTask.fieldPath,
        comment: comment || "Rejected from review queue.",
        createdAt: new Date().toISOString(),
      },
      "Field rejected and candidates closed.",
    );
  }

  async function handleReclassify(family: string, subtype: string, comment: string) {
    if (!activeTask) {
      return false;
    }
    return applyReviewAction(
      {
        schemaName: "review_action",
        schemaVersion: "v1",
        documentId: activeTask.documentId,
        reviewTaskId: activeTask.id,
        actionType: "reclassify_document",
        actorType: "human",
        fieldPath: "classification.document_family",
        newValue: {family, subtype: subtype.trim() || null},
        comment: comment || "Reclassified from review queue.",
        createdAt: new Date().toISOString(),
      },
      "Document classification updated.",
    );
  }

  async function handleMarkDone() {
    if (!activeTask) {
      return false;
    }
    return applyReviewAction(
      {
        schemaName: "review_action",
        schemaVersion: "v1",
        documentId: activeTask.documentId,
        reviewTaskId: activeTask.id,
        actionType: "mark_done",
        actorType: "human",
        comment: "Marked reviewed from queue.",
        createdAt: new Date().toISOString(),
      },
      "Review task closed.",
    );
  }

  async function handleRerunExtraction() {
    if (!activeTask) {
      return false;
    }
    return applyReviewAction(
      {
        schemaName: "review_action",
        schemaVersion: "v1",
        documentId: activeTask.documentId,
        actionType: "rerun_extraction",
        actorType: "human",
        comment: "Manual re-run requested from review queue.",
        createdAt: new Date().toISOString(),
      },
      "Smart Parse re-run queued.",
    );
  }

  const fieldGroups = useMemo(() => groupCandidates(candidates), [candidates]);
  const activeReferenceCandidate = activeTask ? referenceCandidate(activeTask, candidates) : undefined;
  const activeCanonical = canonical.find((field) => field.fieldPath === activeTask?.fieldPath
    && (field.ordinal ?? 1) === (activeReferenceCandidate?.ordinal ?? 1));
  const correctionRevisionReady = !activeCanonical || !!activeCanonical.updatedAt;

  return (
    <section className="review-workbench">
      <div className="review-heading">
        <div>
          <h1>Review Queue</h1>
          <p>Resolve uncertain extracted fields with candidates, validation, and source evidence.</p>
        </div>
        <button type="button" onClick={() => void refresh()} disabled={pending}>Refresh</button>
      </div>
      <div className="review-layout">
        <aside className="review-task-list" aria-label="Review tasks">
          {tasks.length ? tasks.map((task) => (
            <button
              key={task.id}
              id={`review-task-${task.id}`}
              className={task.id === activeTask?.id ? "selected" : undefined}
              type="button"
              onClick={() => selectTask(task.id)}
              disabled={pending}
            >
              <strong>{task.fieldPath ?? task.taskType}</strong>
              <span>{task.rationale ?? "Review required"}</span>
              <small>Priority {task.priority}</small>
            </button>
          )) : (
            <p className="empty-state">No open review tasks.</p>
          )}
        </aside>
        <section className="candidate-panel">
          {taskLoading ? <p role="status">Loading selected review task…</p> : null}
          {selectionError ? <p role="alert">{selectionError}</p> : null}
          {activeTask ? (
            <>
              <div className="candidate-panel-title">
                <h2>{activeTask.fieldPath ?? activeTask.taskType}</h2>
                <button id="review-open-document" type="button" onClick={() => onOpenDocument(activeTask.documentId)}>
                  Open document
                </button>
              </div>
              {activeTask.status !== "open" ? <p role="status">This task is {activeTask.status}. Its review history is preserved; decisions are disabled.</p> : null}
              {!detailReady ? <p role="status">Loading review details…</p> : null}
              <CanonicalSummary canonical={canonical} fieldPath={activeTask.fieldPath} />
              {fieldGroups.map(([fieldPath, items]) => (
                <div className="candidate-group" key={fieldPath}>
                  <h3>{fieldPath}</h3>
                  {items.map((candidate) => (
                    <article key={candidate.id} className="candidate-card">
                      <div>
                        <strong>{formatValue(candidate.value, candidate.currency, candidate.valueType)}</strong>
                        <span>{candidate.sourceEngine} · {confidence(candidate.confidence)}</span>
                      </div>
                      <p>{candidate.status ?? "proposed"} · {evidenceLabel(candidate.evidence)}</p>
                      <small>{selectEvidenceRef(candidate.evidence)?.sourceText ?? "Evidence locator available."}</small>
                      <div className="candidate-actions">
                        <button type="button" disabled={decisionDisabled} onClick={() => handleAccept(candidate)}>
                          Accept candidate
                        </button>
                        <button
                          type="button"
                          onClick={() => (
                            onOpenDocument(candidate.documentId, evidenceTargetFromCandidate(candidate))
                          )}
                        >
                          Jump to evidence
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ))}
              {observations.map((candidate) => (
                <article key={candidate.id} className="candidate-card">
                  <div>
                    <strong>{formatValue(candidate.value, undefined, candidate.valueType)}</strong>
                    <span>
                      {candidate.observationFamily ?? "document_observation"}.{candidate.fieldName}
                      {" · "}
                      {candidate.sourceEngine} · {confidence(candidate.confidence ?? undefined)}
                    </span>
                  </div>
                  <p>{candidate.status ?? "needs_review"} · {evidenceLabel(candidate.evidence)}</p>
                  <small>{selectEvidenceRef(candidate.evidence)?.sourceText ?? "Evidence locator available."}</small>
                  <div className="candidate-actions">
                    <button type="button" disabled={decisionDisabled} onClick={() => handleObservationDecision(candidate, "accept")}>
                      Accept observation
                    </button>
                    <button type="button" disabled={decisionDisabled} onClick={() => handleObservationDecision(candidate, "reject")}>
                      Reject observation
                    </button>
                    <button
                      type="button"
                      onClick={() => (
                        onOpenDocument(
                          candidate.documentId,
                          evidenceTargetFromRef(
                            candidate.documentId,
                            selectEvidenceRef(candidate.evidence),
                            `observations.${candidate.observationFamily ?? "document_observation"}.${candidate.fieldName}`,
                          ),
                        )
                      )}
                    >
                      Jump to evidence
                    </button>
                  </div>
                </article>
              ))}
              {lineItems.map((candidate) => (
                <article key={candidate.id} className="candidate-card">
                  <div>
                    <strong>{candidate.description ?? `${candidate.lineItemType} ${candidate.ordinal}`}</strong>
                    <span>
                      {formatAmount(candidate.netAmount, candidate.currency)}
                      {" · "}
                      {candidate.sourceEngine} · {confidence(candidate.confidence ?? undefined)}
                    </span>
                  </div>
                  <p>{candidate.status ?? "proposed"} · {evidenceLabel(candidate.evidence)}</p>
                  <small>{selectEvidenceRef(candidate.evidence)?.sourceText ?? "Evidence locator available."}</small>
                  <div className="candidate-actions">
                    <button type="button" disabled={decisionDisabled} onClick={() => handleLineItemDecision(candidate, "accept")}>
                      Accept line item
                    </button>
                    <button type="button" disabled={decisionDisabled} onClick={() => handleLineItemDecision(candidate, "reject")}>
                      Reject line item
                    </button>
                    <button
                      type="button"
                      onClick={() => (
                        onOpenDocument(
                          candidate.documentId,
                          evidenceTargetFromRef(
                            candidate.documentId,
                            selectEvidenceRef(candidate.evidence),
                            `line_items.${candidate.lineItemType}.${candidate.ordinal}`,
                          ),
                        )
                      )}
                    >
                      Jump to evidence
                    </button>
                  </div>
                </article>
              ))}
              {activeTask.taskType === "observation_review" && !observations.length ? (
                <p className="empty-state">No observation candidate found for this task.</p>
              ) : null}
              {activeTask.taskType === "line_item_review" && !lineItems.length ? (
                <p className="empty-state">No line-item candidate found for this task.</p>
              ) : null}
              <ReviewDecisionPanel
                key={`${activeTask.id}:${activeReferenceCandidate?.id ?? "loading"}:${activeCanonical?.updatedAt ?? "absent"}`}
                disabled={decisionDisabled}
                correctionRevisionReady={correctionRevisionReady}
                activeTask={activeTask}
                referenceCandidate={activeReferenceCandidate}
                onCorrect={handleCorrect}
                onReject={handleReject}
                onReclassify={handleReclassify}
                onMarkDone={handleMarkDone}
                onRerunExtraction={handleRerunExtraction}
              />
            </>
          ) : (
            <p className="empty-state">Select a review task to inspect candidates.</p>
          )}
          {status ? <p className="review-status">{status}</p> : null}
        </section>
      </div>
    </section>
  );
}

function CanonicalSummary({
  canonical,
  fieldPath,
}: {
  canonical: CanonicalField[];
  fieldPath?: string;
}) {
  const fields = fieldPath ? canonical.filter((field) => field.fieldPath === fieldPath) : canonical;
  return (
    <div className="canonical-summary">
      <h3>Canonical facts</h3>
      {fields.length ? fields.map((field) => (
        <p key={field.id}>
          <strong>{field.fieldPath}</strong>
          <span>{formatValue(field.value, field.currency, field.valueType)} · {field.reviewStatus}</span>
        </p>
      )) : <p>No accepted fact yet.</p>}
    </div>
  );
}

function evidenceLabel(evidence: EvidenceRef[]): string {
  const selected = selectEvidenceRef(evidence);
  return selected ? `evidence page ${selected.pageNumber}` : "no evidence locator";
}

function groupCandidates(candidates: FieldCandidate[]): Array<[string, FieldCandidate[]]> {
  const groups = new Map<string, FieldCandidate[]>();
  for (const candidate of candidates) {
    const current = groups.get(candidate.fieldPath) ?? [];
    current.push(candidate);
    groups.set(candidate.fieldPath, current);
  }
  return [...groups.entries()];
}

function confidence(value?: number): string {
  return value === undefined || value === null ? "confidence pending" : `${Math.round(value * 100)}%`;
}

function formatAmount(amount?: number | null, currency?: string | null): string {
  if (amount === undefined || amount === null) {
    return "Amount pending";
  }
  return `${currency ?? "USD"} ${amount}`;
}

function formatValue(value: unknown, currency?: string, valueType?: string): string {
  if (valueType === "json") return JSON.stringify(value) ?? "Not set";
  if (value && typeof value === "object" && "amount" in value) {
    const money = value as {amount?: number; currency?: string};
    return `${money.currency ?? currency ?? "USD"} ${money.amount ?? ""}`.trim();
  }
  return value === null || value === undefined ? "Not set" : String(value);
}
