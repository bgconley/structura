import {useEffect, useRef, useState} from "react";

import {listCanonicalFields, listFieldCandidates, listLineItemCandidates,
  listObservationCandidates, listReviewTasks, getReviewTask, postReviewAction} from "./reviewApi";
import {ApiError} from "./api";
import {useKeyedRequest} from "./useKeyedRequest";
import type {CanonicalField, FieldCandidate, LineItemCandidate, ObservationCandidate,
  ReviewActionPayload, ReviewTask} from "./types";

type ReviewDetail = {
  identity: string;
  candidates: FieldCandidate[];
  canonical: CanonicalField[];
  observations: ObservationCandidate[];
  lineItems: LineItemCandidate[];
};

const EMPTY_DETAIL = {candidates: [], canonical: [], observations: [], lineItems: []};

function taskIdentity(task: ReviewTask | null): string {
  return task ? [task.id, task.documentId, task.taskType, task.fieldPath,
    task.metadata?.observationId, task.metadata?.lineItemCandidateId].join(":") : "";
}

export function useReviewQueueState(selectedTaskId: string | undefined, documentId: string | undefined,
  onSelectTask: (id: string | undefined) => void) {
  const [tasksLoaded, setTasksLoaded] = useState(false);
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [loadedContext, setLoadedContext] = useState<string | undefined>(undefined);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const pendingRef = useRef(false);
  const taskSequence = useRef(0);
  const detailSequence = useRef(0);
  const context = useRef({documentId, selectedTaskId, onSelectTask});
  context.current = {documentId, selectedTaskId, onSelectTask};
  const exact = useKeyedRequest(selectedTaskId ? `${selectedTaskId}:${documentId ?? ""}` : null, async (signal) => {
    const task = await getReviewTask(selectedTaskId!, signal);
    if (task.id !== selectedTaskId || (documentId && task.documentId !== documentId)) {
      throw new Error("This review task does not match the requested document.");
    }
    return task;
  });
  const visibleTasks = loadedContext === documentId ? tasks : [];
  const activeTask = selectedTaskId ? exact.data : visibleTasks[0] ?? null;
  const identity = taskIdentity(activeTask);
  const detailReady = !!identity && detail?.identity === identity;
  const current = useRef<{task: ReviewTask | null; identity: string; detailReady: boolean}>(
    {task: activeTask, identity, detailReady},
  );
  current.current = {task: activeTask, identity, detailReady};

  useEffect(() => {
    void refreshTasks();
    return () => {
      taskSequence.current += 1;
      detailSequence.current += 1;
      current.current = {task: null, identity: "", detailReady: false};
    };
  }, [documentId]);

  useEffect(() => {
    if (activeTask) void refreshReviewDetail(activeTask);
    else setDetail(null);
  }, [identity]);

  async function refreshTasks(): Promise<boolean> {
    const sequence = ++taskSequence.current;
    const requestedContext = documentId;
    try {
      const next = await listReviewTasks("open", requestedContext);
      if (sequence !== taskSequence.current || context.current.documentId !== requestedContext) return false;
      setTasksLoaded(true);
      setLoadedContext(requestedContext);
      setTasks(next);
      if (!context.current.selectedTaskId && next[0]) context.current.onSelectTask(next[0].id);
      return true;
    } catch (error) {
      if (sequence === taskSequence.current) {
        setStatus(error instanceof Error ? error.message : "Review tasks could not be loaded.");
      }
      return false;
    }
  }

  async function refreshReviewDetail(task: ReviewTask): Promise<boolean> {
    const sequence = ++detailSequence.current;
    const requestedIdentity = taskIdentity(task);
    setDetail(null);
    try {
      const [candidates, canonical, observations, lineItems] = await Promise.all([
        task.taskType === "observation_review" || task.taskType === "line_item_review"
          ? Promise.resolve([]) : listFieldCandidates(task.documentId, task.fieldPath),
        listCanonicalFields(task.documentId),
        task.taskType === "observation_review"
          ? listObservationCandidates(task.documentId, metadataId(task, "observationId"))
          : Promise.resolve([]),
        task.taskType === "line_item_review"
          ? listLineItemCandidates(task.documentId, metadataId(task, "lineItemCandidateId"))
          : Promise.resolve([]),
      ]);
      if (sequence !== detailSequence.current || current.current.identity !== requestedIdentity) return false;
      if ([...candidates, ...canonical, ...observations, ...lineItems]
        .some((item) => item.documentId !== task.documentId)
        || candidates.some((item) => task.fieldPath && item.fieldPath !== task.fieldPath)
        || observations.some((item) => metadataId(task, "observationId")
          && item.id !== metadataId(task, "observationId"))
        || lineItems.some((item) => metadataId(task, "lineItemCandidateId")
          && item.id !== metadataId(task, "lineItemCandidateId"))) {
        throw new Error("Review details did not match the selected document. Refresh before making a decision.");
      }
      setDetail({identity: requestedIdentity, candidates, canonical, observations, lineItems});
      return true;
    } catch (error) {
      if (sequence === detailSequence.current && current.current.identity === requestedIdentity) {
        setStatus(error instanceof Error ? error.message : "Review details could not be loaded.");
      }
      return false;
    }
  }

  async function refresh() {
    if (pendingRef.current) return;
    await Promise.all([refreshTasks(), exact.reload()]);
    const selected = current.current.task;
    if (selected) await refreshReviewDetail(selected);
  }

  async function applyReviewAction(payload: ReviewActionPayload, successMessage: string): Promise<boolean> {
    if (pendingRef.current) return false;
    if (current.current.task?.status !== "open" || !current.current.detailReady || payload.documentId !== current.current.task?.documentId
      || (payload.reviewTaskId && payload.reviewTaskId !== current.current.task?.id)) {
      setStatus("Wait for the selected task's details before making a decision.");
      return false;
    }
    const actionIdentity = current.current.identity;
    pendingRef.current = true;
    setPending(true);
    try {
      const result = await postReviewAction(payload);
      if (!result.ok) throw new Error("Review action was not applied.");
      if (current.current.identity !== actionIdentity) return true;
      setStatus(successMessage);
      const refreshed = await refreshTasks();
      await exact.reload();
      const selected = current.current.task;
      const detailsRefreshed = selected ? await refreshReviewDetail(selected) : true;
      if (!refreshed || !detailsRefreshed) {
        setStatus(`${successMessage} Refresh the queue to see the updated state.`);
      }
      return true;
    } catch (error) {
      if (current.current.identity === actionIdentity) {
        setStatus(error instanceof Error ? error.message : "Review action failed.");
      }
      return false;
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  }

  const selectionError = exact.error instanceof ApiError && [403, 404].includes(exact.error.status)
    ? "This review task is unavailable or you no longer have access." : exact.error?.message;
  return {tasks: exact.data && !visibleTasks.some((task) => task.id === exact.data!.id)
      ? [exact.data, ...visibleTasks] : visibleTasks, activeTask, selectTask: onSelectTask, status, setStatus, pending,
    selectionError, taskLoading: exact.loading, tasksLoaded: tasksLoaded && loadedContext === documentId,
    detailReady, ...(detailReady && detail ? detail : EMPTY_DETAIL), refresh, applyReviewAction};
}

function metadataId(task: ReviewTask, key: string): string | undefined {
  const value = task.metadata?.[key];
  return typeof value === "string" && value ? value : undefined;
}
