import {useEffect, useRef, useState} from "react";
import {ApiError} from "../api";
import {getCanonicalLines, getLineCandidates, getLineHistory, postLineDecision} from "./api";
import {requestStillMatches} from "./decisionIntent";
import {useLineDrafts, type LineDraft} from "./LineItemDraftProvider";
import type {CanonicalLines, LineCandidate, LineRequest} from "./types";

type Loaded = {key: string; authority: CanonicalLines; candidates: LineCandidate[]};
export function useLineItemReview(documentId: string, candidateId: string | undefined, contextId: string,
  onSaved?: () => void | Promise<void>) {
  const store = useLineDrafts();
  const key = JSON.stringify([store.actor, documentId, contextId, candidateId ?? null]);
  const empty: LineDraft = {actor: store.actor, documentId, sourceId: candidateId ?? null, comment: "", request: null, phase: "editing", message: null};
  const draft = store.entries.get(key) ?? empty;
  const current = useRef({key, draft, store, onSaved});
  current.current = {key, draft, store, onSaved};
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const sequence = useRef(0), saving = useRef(false);
  const alive = useRef(true);
  const data = loaded?.key === key ? loaded : null;
  const candidate = data?.candidates.find((item) => item.id === candidateId) ?? null;

  useEffect(() => {
    alive.current = true;
    void reload();
    return () => { alive.current = false; sequence.current++; };
  }, [key]);

  async function reload(): Promise<boolean> {
    const attempt = ++sequence.current, requestedKey = key;
    setLoading(true); setError(null); setLoaded(null);
    try {
      const [authority, candidates] = await Promise.all([getCanonicalLines(documentId), candidateId
        ? getLineCandidates(documentId, candidateId) : Promise.resolve({items: []})]);
      // An uncertain save is reconciled with exact immutable history before another intent may be reviewed.
      const previous = current.current.draft;
      if (previous.phase === "unknown" && previous.request) {
        const request = previous.request;
        const selector = "source" in request ? {sourceCandidateId: request.source.candidateId}
          : {canonicalLineItemId: request.target.canonicalLineItemId};
        await getLineHistory(documentId, selector);
      }
      if (!alive.current || sequence.current !== attempt || current.current.key !== requestedKey) return false;
      setLoaded({key: requestedKey, authority, candidates: candidates.items}); setLoading(false);
      const d = current.current.draft;
      if (d.phase === "reviewing" && d.request && !requestStillMatches(d.request, candidates.items.find((item) => item.id === candidateId) ?? null, authority)) {
        store.update(key, {...d, phase: "conflict", message: "The proposal or recorded line changed. Review the latest values and choose the action again."});
      } else if (d.phase === "unknown") {
        store.update(key, {...d, phase: "conflict", message: "Latest values and retained history have been reloaded. Inspect them and choose any further action explicitly; the previous save is not repeated."});
      }
      return true;
    } catch (failure) {
      if (!alive.current || sequence.current !== attempt || current.current.key !== requestedKey) return false;
      setLoading(false); setError(failure instanceof Error ? failure.message : "Line items could not be loaded.");
      if (failure instanceof ApiError && [401, 403, 404].includes(failure.status)) store.removeDocument(documentId);
      return false;
    }
  }
  function update(change: Partial<LineDraft>) { store.update(key, {...current.current.draft, ...change}); }
  function choose(request: LineRequest) {
    if (!store.authorized || !data || loading || draft.phase === "saving" || !requestStillMatches(request, candidate, data.authority)) return;
    update({request, phase: "reviewing", message: null});
  }
  async function save() {
    const d = current.current.draft, request = d.request;
    if (saving.current || d.phase !== "reviewing" || !request || !store.authorized || !data || loading
      || !requestStillMatches(request, candidate, data.authority)) return;
    saving.current = true;
    const submittedKey = key, submitted = {...d, phase: "saving" as const, message: "Saving this line decision…"};
    store.update(key, submitted);
    try {
      await postLineDecision(documentId, {...request, comment: d.comment.trim() || undefined});
      store.update(submittedKey, {...d, request: null, phase: "saved", message: "Line decision saved. Reloading the latest values…"});
      if (alive.current && current.current.key === submittedKey) {
        const refreshed = await reload();
        store.update(submittedKey, {...d, request: null, phase: "saved", message: refreshed
          ? "Line decision saved. The latest recorded values are shown." : "Saved; latest details could not be loaded. Reload before another decision."});
        if (refreshed) {
          try { await current.current.onSaved?.(); }
          catch { store.update(submittedKey, {...d, request: null, phase: "saved", message: "Line decision saved. Refresh the review queue to see its latest status."}); }
        }
      }
    } catch (failure) {
      if (failure instanceof ApiError && [401, 403, 404].includes(failure.status)) {
        store.removeDocument(documentId);
        if (alive.current && current.current.key === submittedKey) { setLoaded(null); setError("This document is unavailable or you no longer have access."); }
      } else {
        const conflict = failure instanceof ApiError && [409, 422].includes(failure.status);
        store.update(submittedKey, {...d, phase: conflict ? "conflict" : "unknown", message: conflict
          ? "This proposal or recorded line changed or cannot be published. Reload the latest values before choosing an action again. Your comment is preserved."
          : "The save could not be confirmed. Reload the latest line and history before trying again. Your comment is preserved."});
        if (alive.current && current.current.key === submittedKey) setLoaded(null);
      }
    } finally { saving.current = false; }
  }
  return {draft, candidate, authority: data?.authority ?? null, candidates: data?.candidates ?? [], loading, error,
    authorized: store.authorized, pending: draft.phase === "saving", reload, choose, save,
    setComment: (comment: string) => update({comment}), cancel: () => update({request: null, phase: "editing", message: null})};
}
