import {useEffect, useMemo, useState} from "react";

import {
  listCanonicalFields,
  listFieldCandidates,
  listReviewTasks,
  postReviewAction,
} from "../reviewApi";
import type {CanonicalField, FieldCandidate, ReviewTask} from "../types";
import "./ReviewQueue.css";

export function ReviewQueue({
  onOpenDocument,
}: {
  onOpenDocument: (documentId: string) => void;
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
    await postReviewAction({
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
    });
    setStatus("Candidate accepted and promoted.");
    await refreshTasks();
  }

  async function handleMarkDone() {
    if (!activeTask) {
      return;
    }
    await postReviewAction({
      schemaName: "review_action",
      schemaVersion: "v1",
      documentId: activeTask.documentId,
      reviewTaskId: activeTask.id,
      actionType: "mark_done",
      actorType: "human",
      comment: "Marked reviewed from queue.",
      createdAt: new Date().toISOString(),
    });
    setStatus("Review task closed.");
    await refreshTasks();
  }

  async function handleRerunExtraction() {
    if (!activeTask) {
      return;
    }
    await postReviewAction({
      schemaName: "review_action",
      schemaVersion: "v1",
      documentId: activeTask.documentId,
      actionType: "rerun_extraction",
      actorType: "human",
      metadata: {targetSchemaName: _schemaFromTask(activeTask)},
      comment: "Manual re-run requested from review queue.",
      createdAt: new Date().toISOString(),
    });
    setStatus("Extraction re-run queued.");
  }

  const fieldGroups = useMemo(() => groupCandidates(candidates), [candidates]);

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
                      <button type="button" onClick={() => handleAccept(candidate)}>
                        Accept candidate
                      </button>
                    </article>
                  ))}
                </div>
              ))}
              <div className="review-actions">
                <button type="button" className="primary" onClick={handleMarkDone}>Mark reviewed</button>
                <button type="button" onClick={handleRerunExtraction}>Re-run extraction</button>
              </div>
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

function _schemaFromTask(task: ReviewTask): string {
  if (task.fieldPath?.startsWith("invoice.")) {
    return "invoice";
  }
  if (task.fieldPath?.startsWith("medical_eob.")) {
    return "medical_eob";
  }
  return "receipt";
}
