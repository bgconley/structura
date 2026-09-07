import {useEffect, useRef} from "react";
import type {UploadQueueController} from "../uploads/UploadQueueController";
import {activeUploadPhases, terminalUploadPhases, type UploadQueueSnapshot} from "../uploads/queue";
import {UploadDropArea} from "./UploadIntake";
import {UploadQueueRow} from "./UploadQueueRow";
import "./UploadQueue.css";

export function uploadAttentionCount(state: UploadQueueSnapshot): number {
  return state.entries.filter((entry) => !["accepted", "reused", "cancelled", "queued"].includes(entry.phase) && !activeUploadPhases.includes(entry.phase)).length;
}
export function uploadQueueLabel(state: UploadQueueSnapshot): string {
  if (!state.policy && state.policyError) return "Uploads unavailable";
  if (state.admissionRetryAt) return "Uploads (waiting for capacity)";
  const active = state.entries.filter((entry) => entry.phase === "queued" || activeUploadPhases.includes(entry.phase)).length;
  const attention = uploadAttentionCount(state);
  return active ? `Uploads (${active} active${attention ? `, ${attention} need attention` : ""})`
    : attention ? `Uploads (${attention} need attention)` : `Uploads (${state.entries.length})`;
}
export function UploadQueue({state, controller, onOpenDocument}: {state: UploadQueueSnapshot; controller: UploadQueueController;
  onOpenDocument: (id: string) => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (state.open && !dialog.current?.open) dialog.current?.showModal();
    else if (!state.open && dialog.current?.open) dialog.current?.close();
  }, [state.open]);
  const count = (phase: string) => state.entries.filter((entry) => entry.phase === phase).length;
  const working = state.entries.filter((entry) => ["registering", "sending", "saving"].includes(entry.phase)).length;
  const counts = [[count("queued"), "queued"], [working, "transferring or saving"], [count("duplicate_choice"), count("duplicate_choice") === 1 ? "duplicate choice" : "duplicate choices"],
    [count("accepted"), "accepted"], [count("reused"), "reused"], [count("rejected"), "rejected"], [count("cancelled"), "cancelled"], [count("expired"), "expired"]]
    .filter(([amount]) => !!amount).map(([amount, label]) => `${amount} ${label}`).join(" · ");
  const uncertain = state.entries.some((entry) => ["unknown", "retry_wait", "unavailable"].includes(entry.phase));
  const unfinished = state.entries.some((entry) => !terminalUploadPhases.includes(entry.phase));
  const finished = state.entries.some((entry) => terminalUploadPhases.includes(entry.phase));
  function openDocument(id: string) { controller.setOpen(false); onOpenDocument(id); }
  return <dialog ref={dialog} className="upload-queue" aria-labelledby="upload-queue-title"
    onCancel={(event) => { event.preventDefault(); controller.setOpen(false); }} onClose={() => controller.setOpen(false)}>
    <div className="upload-queue-heading"><div><h2 id="upload-queue-title">Upload files</h2><p>Closing this queue leaves active uploads running.</p></div>
      <button type="button" onClick={() => controller.setOpen(false)}>Close uploads</button></div>
    <p className="upload-queue-counts" role="status">{counts || (state.entries.length ? "Check individual upload outcomes below." : "No uploads in this queue yet.")}</p>
    {!state.online ? <p role="alert">You appear to be offline. New transfers are paused; existing outcomes may need checking when the connection returns.</p> : null}
    {state.admissionRetryAt ? <p role="status">The queue is waiting for server capacity. Untouched files will start after the admission pause. Attempted uploads still require an explicit outcome check.</p> : null}
    {state.policyError ? <p role="alert">{state.policyError} <button type="button" onClick={() => void controller.loadPolicy()}>Retry upload policy</button></p> : null}
    {state.storageError ? <p role="alert">{state.storageError}</p> : null}
    <UploadDropArea policy={state.policy} onFiles={(files, source) => controller.add(files, source)} />
    {state.policy ? <p className="upload-retention-note">Up to {state.policy.queueReferenceLimit} files in this queue; {state.policy.actorActiveLimit} transfers at a time.</p> : <p role="status">Loading upload policy…</p>}
    <details className="upload-recovery-help"><summary>Previous uploads and recovery</summary>
      <p className="upload-retention-note">After refresh or sign-out, check previous uploads before continuing. Unfinished uploads may require selecting the original file again.</p>
      <p className="upload-retention-note">Inactive uploads and held copies can expire. Use Check upload outcome to fetch the recorded state before continuing.</p></details>
    <div className="upload-batch-actions"><button type="button" disabled={!uncertain || !!state.admissionRetryAt} onClick={() => void controller.checkUncertain()}>Check uncertain uploads</button>
      <button type="button" disabled={!unfinished} onClick={() => void controller.cancelUnaccepted()}>Cancel unaccepted uploads</button>
      <button type="button" disabled={!finished} onClick={() => controller.clearFinished()}>Clear finished rows</button></div>
    <div className="upload-queue-rows">{state.entries.map((entry) => <UploadQueueRow key={entry.localId} entry={entry}
      controller={controller} policy={state.policy} onOpenDocument={openDocument} />)}</div>
    {!state.entries.length ? <p>No files are in this queue. Choose files or drop them above.</p> : null}
  </dialog>;
}
