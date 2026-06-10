import {useEffect, useMemo, useState} from "react";

import {
  listCanonicalFields,
  listFieldCandidates,
  listLineItemCandidates,
  listObservationCandidates,
  listReviewTasks,
  postReviewAction,
} from "../reviewApi";
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
  ReviewTask,
} from "../types";
import {ReviewDecisionPanel} from "./ReviewDecisionPanel";
import "./ReviewQueue.css";

export function ReviewQueue({
  onOpenDocument,
}: {
  onOpenDocument: (documentId: string, evidenceTarget?: EvidenceTarget) => void;
}) {
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<FieldCandidate[]>([]);
  const [observations, setObservations] = useState<ObservationCandidate[]>([]);
  const [lineItems, setLineItems] = useState<LineItemCandidate[]>([]);
  const [canonical, setCanonical] = useState<CanonicalField[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const activeTask = tasks.find((task) => task.id === activeTaskId) ?? tasks[0] ?? null;

  useEffect(() => {
    void refreshTasks();
  }, []);

  useEffect(() => {
    if (!activeTask) {
      setCandidates([]);
      setObservations([]);
      setLineItems([]);
      setCanonical([]);
      return;
    }
    void refreshReviewDetail(activeTask);
  }, [activeTask?.id]);

  async function refreshTasks() {
    const next = await listReviewTasks("open");
    setTasks(next);
    setActiveTaskId((current) => {
      if (current && next.some((task) => task.id === current)) {
        return current;
      }
      return next[0]?.id ?? null;
    });
  }

  async function refreshReviewDetail(task: ReviewTask) {
    const observationId = metadataId(task, "observationId");
    const lineItemCandidateId = metadataId(task, "lineItemCandidateId");
    const [nextCandidates, nextCanonical, nextObservations, nextLineItems] = await Promise.all([
      task.taskType === "observation_review" || task.taskType === "line_item_review"
        ? Promise.resolve([])
        : listFieldCandidates(task.documentId, task.fieldPath),
      listCanonicalFields(task.documentId),
      task.taskType === "observation_review"
        ? listObservationCandidates(task.documentId, observationId)
        : Promise.resolve([]),
      task.taskType === "line_item_review"
        ? listLineItemCandidates(task.documentId, lineItemCandidateId)
        : Promise.resolve([]),
    ]);
    setCandidates(nextCandidates);
    setCanonical(nextCanonical);
    setObservations(nextObservations);
    setLineItems(nextLineItems);
  }

  async function handleAccept(candidate: FieldCandidate) {
    await applyReviewAction(
      {
        schemaName: "review_action",
        schemaVersion: "v1",
        documentId: candidate.documentId,
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

  async function handleCorrect(valueText: string, comment: string) {
    if (!activeTask?.fieldPath) {
      setStatus("Select a field review task before correcting.");
      return;
    }
    const reference = referenceCandidate(activeTask, candidates);
    const coerced = coerceCorrectionValue(
      valueText,
      reference?.valueType ?? "string",
      reference?.currency,
    );
    await applyReviewAction(
      {
        schemaName: "review_action",
        schemaVersion: "v1",
        documentId: activeTask.documentId,
        reviewTaskId: activeTask.id,
        actionType: "correct_field",
        actorType: "human",
        fieldPath: activeTask.fieldPath,
        newValue: coerced.value,
        evidenceContext: reference?.evidence,
        metadata: coerced.metadata,
        comment: comment || "Corrected from review queue.",
        createdAt: new Date().toISOString(),
      },
      "Field corrected and review history updated.",
    );
  }

  async function handleReject(comment: string) {
    if (!activeTask?.fieldPath) {
      setStatus("Select a field review task before rejecting.");
      return;
    }
    await applyReviewAction(
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
      return;
    }
    await applyReviewAction(
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
      return;
    }
    await applyReviewAction(
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
      return;
    }
    await applyReviewAction(
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

  async function applyReviewAction(
    payload: Parameters<typeof postReviewAction>[0],
    successMessage: string,
  ) {
    try {
      await postReviewAction(payload);
      setStatus(successMessage);
      await refreshTasks();
      if (activeTask) {
        await refreshReviewDetail(activeTask);
      }
    } catch (exc) {
      setStatus(exc instanceof Error ? exc.message : "Review action failed.");
    }
  }

  const fieldGroups = useMemo(() => groupCandidates(candidates), [candidates]);
  const activeReferenceCandidate = activeTask ? referenceCandidate(activeTask, candidates) : undefined;

  return (
    <section className="review-workbench">
      <div className="review-heading">
        <div>
          <h1>Review Queue</h1>
          <p>Resolve uncertain extracted fields with candidates, validation, and source evidence.</p>
        </div>
        <button type="button" onClick={refreshTasks}>Refresh</button>
      </div>
      <div className="review-layout">
        <aside className="review-task-list" aria-label="Review tasks">
          {tasks.length ? tasks.map((task) => (
            <button
              key={task.id}
              className={task.id === activeTask?.id ? "selected" : undefined}
              type="button"
              onClick={() => setActiveTaskId(task.id)}
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
          {activeTask ? (
            <>
              <div className="candidate-panel-title">
                <h2>{activeTask.fieldPath ?? activeTask.taskType}</h2>
                <button type="button" onClick={() => onOpenDocument(activeTask.documentId)}>
                  Open document
                </button>
              </div>
              <CanonicalSummary canonical={canonical} fieldPath={activeTask.fieldPath} />
              {fieldGroups.map(([fieldPath, items]) => (
                <div className="candidate-group" key={fieldPath}>
                  <h3>{fieldPath}</h3>
                  {items.map((candidate) => (
                    <article key={candidate.id} className="candidate-card">
                      <div>
                        <strong>{formatValue(candidate.value, candidate.currency)}</strong>
                        <span>{candidate.sourceEngine} · {confidence(candidate.confidence)}</span>
                      </div>
                      <p>{candidate.status ?? "proposed"} · {evidenceLabel(candidate.evidence)}</p>
                      <small>{selectEvidenceRef(candidate.evidence)?.sourceText ?? "Evidence locator available."}</small>
                      <div className="candidate-actions">
                        <button type="button" onClick={() => handleAccept(candidate)}>
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
                    <strong>{formatValue(candidate.value)}</strong>
                    <span>
                      {candidate.observationFamily ?? "document_observation"}.{candidate.fieldName}
                      {" · "}
                      {candidate.sourceEngine} · {confidence(candidate.confidence ?? undefined)}
                    </span>
                  </div>
                  <p>{candidate.status ?? "needs_review"} · {evidenceLabel(candidate.evidence)}</p>
                  <small>{selectEvidenceRef(candidate.evidence)?.sourceText ?? "Evidence locator available."}</small>
                  <div className="candidate-actions">
                    <button type="button" onClick={() => handleObservationDecision(candidate, "accept")}>
                      Accept observation
                    </button>
                    <button type="button" onClick={() => handleObservationDecision(candidate, "reject")}>
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
                    <button type="button" onClick={() => handleLineItemDecision(candidate, "accept")}>
                      Accept line item
                    </button>
                    <button type="button" onClick={() => handleLineItemDecision(candidate, "reject")}>
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
          <span>{formatValue(field.value, field.currency)} · {field.reviewStatus}</span>
        </p>
      )) : <p>No accepted fact yet.</p>}
    </div>
  );
}

function metadataId(task: ReviewTask, key: string): string | undefined {
  const value = task.metadata?.[key];
  return typeof value === "string" && value ? value : undefined;
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

function formatValue(value: unknown, currency?: string): string {
  if (value && typeof value === "object" && "amount" in value) {
    const money = value as {amount?: number; currency?: string};
    return `${money.currency ?? currency ?? "USD"} ${money.amount ?? ""}`.trim();
  }
  return value === null || value === undefined ? "Not set" : String(value);
}
