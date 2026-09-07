import {useEffect, useMemo} from "react";

import {useReviewQueueState} from "../useReviewQueueState";
import {
  coerceCorrectionValue,
  evidenceTargetFromCandidate,
  referenceCandidate,
} from "../reviewActions";
import {evidenceTargetFromRef, selectEvidenceRef} from "../evidence";
import {fieldDecisionPreconditions} from "../reviewAuthority";
import {recordedValue} from "../recordedFactValues";
import type {
  EvidenceRef,
  EvidenceTarget,
  FieldCandidate,
  ObservationCandidate,
} from "../types";
import {ReviewDecisionPanel} from "./ReviewDecisionPanel";
import {LineItemReviewPanel} from "./LineItemReviewPanel";
import {ReviewFieldHistory} from "./ReviewFieldHistory";
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
  const {tasks, activeTask, selectTask, candidates, observations, authority, authorityError,
    status, setStatus, pending, detailReady, detailFailed, fieldDecisionReady, fieldConflict,
    selectionError, taskLoading, tasksLoaded, refresh, applyReviewAction}
    = useReviewQueueState(selectedTaskId, documentId, onSelectTask);
  const decisionDisabled = pending || !detailReady || activeTask?.status !== "open";
  useEffect(() => {
    if (selectionError || detailReady || detailFailed || (tasksLoaded && !taskLoading && !activeTask)) onReady();
  });

  async function handleAccept(candidate: FieldCandidate) {
    const reference = activeTask ? referenceCandidate(activeTask, candidates) : undefined;
    if (activeTask?.fieldPath && (!reference || candidate.fieldPath !== reference.fieldPath
      || (candidate.ordinal ?? 1) !== (reference.ordinal ?? 1))) {
      setStatus("Reload the selected field's candidate before accepting.");
      return false;
    }
    const preconditions = fieldDecisionPreconditions(authority, candidate);
    if (!preconditions || !fieldDecisionReady) {
      setStatus("Reload this field to obtain its current revision before accepting.");
      return false;
    }
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
        ...preconditions,
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

  async function handleCorrect(valueText: string, comment: string, currency?: string) {
    if (!activeTask?.fieldPath) {
      setStatus("Select a field review task before correcting.");
      return false;
    }
    const reference = referenceCandidate(activeTask, candidates);
    if (!reference) throw new Error("Wait for the selected field's candidate before correcting.");
    const preconditions = fieldDecisionPreconditions(authority, reference);
    if (!preconditions || !fieldDecisionReady) {
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
        ...preconditions,
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
    const reference = referenceCandidate(activeTask, candidates);
    if (!reference) {
      setStatus("Reload the selected field's candidate before rejecting.");
      return false;
    }
    const ordinal = reference.ordinal ?? 1;
    const preconditions = fieldDecisionPreconditions(authority, {
      documentId: activeTask.documentId, fieldPath: activeTask.fieldPath, ordinal,
    });
    if (!preconditions || !fieldDecisionReady) {
      setStatus("Reload this field to obtain its current revision before rejecting.");
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
        ...preconditions,
        metadata: {ordinal},
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
  const correctionRevisionReady = fieldDecisionReady && !!activeReferenceCandidate
    && !!fieldDecisionPreconditions(authority, activeReferenceCandidate);

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
              {activeTask.status !== "open" ? <p role="status">This task is {activeTask.status}. {activeTask.taskType === "line_item_review" ? "Its exact line decisions and history remain available below." : "Its review history is preserved; decisions are disabled."}</p> : null}
              {!detailReady ? <p role="status">{detailFailed ? "Review details could not be refreshed. Your entries are preserved; refresh to retry." : "Loading review details…"}</p> : null}
              {authorityError ? <p role="alert">{authorityError}</p> : null}
              {fieldConflict ? <p role="alert">This field has a newer decision. Refresh to review it before saving again. Your entries are preserved.</p> : null}
              <ReviewFieldHistory authority={authority} fieldPath={activeTask.fieldPath} formatValue={formatValue} />
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
                        <button type="button" disabled={decisionDisabled || !fieldDecisionReady
                          || (!!activeTask.fieldPath && (!activeReferenceCandidate
                            || candidate.fieldPath !== activeReferenceCandidate.fieldPath
                            || (candidate.ordinal ?? 1) !== (activeReferenceCandidate.ordinal ?? 1)))
                          || !fieldDecisionPreconditions(authority, candidate)} onClick={() => handleAccept(candidate)}>
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
              {activeTask.taskType === "line_item_review" ? <LineItemReviewPanel key={activeTask.id}
                documentId={activeTask.documentId} contextId={activeTask.id}
                candidateId={typeof activeTask.metadata?.lineItemCandidateId === "string" ? activeTask.metadata.lineItemCandidateId : undefined}
                onJump={(target) => onOpenDocument(activeTask.documentId, target)} onSaved={refresh} /> : null}
              {activeTask.taskType === "observation_review" && !observations.length ? (
                <p className="empty-state">No observation candidate found for this task.</p>
              ) : null}
              <ReviewDecisionPanel
                key={`${activeTask.id}:${activeReferenceCandidate?.id ?? "loading"}`}
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

function formatValue(value: unknown, currency?: string, valueType?: string): string {
  return recordedValue(value, valueType, currency);
}
