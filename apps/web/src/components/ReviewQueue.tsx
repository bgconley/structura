import {useEffect, useMemo, useState} from "react";

import {
  listCanonicalFields,
  listFieldCandidates,
  listReviewTasks,
  postReviewAction,
} from "../reviewApi";
import {
  coerceCorrectionValue,
  evidenceTargetFromCandidate,
  referenceCandidate,
  schemaFromReviewTask,
} from "../reviewActions";
import type {CanonicalField, EvidenceTarget, FieldCandidate, ReviewTask} from "../types";
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
  const [canonical, setCanonical] = useState<CanonicalField[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const activeTask = tasks.find((task) => task.id === activeTaskId) ?? tasks[0] ?? null;

  useEffect(() => {
    void refreshTasks();
  }, []);

  useEffect(() => {
    if (!activeTask) {
      setCandidates([]);
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
    const [nextCandidates, nextCanonical] = await Promise.all([
      listFieldCandidates(task.documentId, task.fieldPath),
      listCanonicalFields(task.documentId),
    ]);
    setCandidates(nextCandidates);
    setCanonical(nextCanonical);
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
        metadata: {targetSchemaName: schemaFromReviewTask(activeTask)},
        comment: "Manual re-run requested from review queue.",
        createdAt: new Date().toISOString(),
      },
      "Extraction re-run queued.",
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
                      <p>{candidate.status ?? "proposed"} · evidence page {candidate.evidence[0]?.pageNumber ?? "?"}</p>
                      <small>{candidate.evidence[0]?.sourceText ?? "Evidence locator available."}</small>
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

function formatValue(value: unknown, currency?: string): string {
  if (value && typeof value === "object" && "amount" in value) {
    const money = value as {amount?: number; currency?: string};
    return `${money.currency ?? currency ?? "USD"} ${money.amount ?? ""}`.trim();
  }
  return value === null || value === undefined ? "Not set" : String(value);
}
