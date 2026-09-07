import {useEffect, useState} from "react";
import {activeUploadPhases, terminalUploadPhases, type UploadEntry, type UploadPhase} from "../uploads/queue";
import type {UploadQueueController} from "../uploads/UploadQueueController";
import type {UploadPolicy} from "../uploads/types";
import {UploadDuplicateChoice} from "./UploadDuplicateChoice";

const labels: Record<UploadPhase, string> = {queued: "Queued", registering: "Registering upload", sending: "Sending bytes", saving: "Saving original",
  checking: "Checking upload outcome", cancelling: "Checking cancellation outcome", needs_file: "Select the original file", ready_to_send: "Ready to send",
  replacement_needed: "Unfinished transfer needs an explicit replacement", duplicate_choice: "Choose how to handle an exact copy", unknown: "Upload outcome needs checking",
  retry_wait: "Waiting for upload capacity", unavailable: "Upload unavailable", accepted: "Upload accepted", reused: "Existing document reused",
  rejected: "File rejected", cancelled: "Upload cancelled", expired: "Upload expired"};
export function UploadQueueRow({entry, controller, policy, onOpenDocument}: {entry: UploadEntry; controller: UploadQueueController;
  policy: UploadPolicy | null; onOpenDocument: (id: string) => void}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!entry.retryAt || entry.retryAt <= Date.now()) return;
    const timer = window.setInterval(() => { setNow(Date.now()); if (Date.now() >= entry.retryAt!) clearInterval(timer); }, 1000);
    return () => clearInterval(timer);
  }, [entry.retryAt]);
  const busy = activeUploadPhases.includes(entry.phase), terminal = terminalUploadPhases.includes(entry.phase);
  const receipt = entry.attempt?.receipt, cooldown = Math.max(0, Math.ceil(((entry.retryAt ?? 0) - now) / 1000));
  const reselection = !terminal && !busy && (entry.phase === "needs_file" || (!entry.file && entry.phase !== "duplicate_choice"));
  return <article className="upload-queue-row" aria-label={`Upload ${entry.displayName}`} data-state={entry.phase}>
    <div className="upload-row-heading"><h3>{entry.displayName}</h3><span>{labels[entry.phase]}</span></div>
    {entry.metadata || entry.attempt ? <p>{(entry.metadata?.declaredBytes ?? entry.attempt?.declaredBytes ?? 0).toLocaleString()} bytes</p> : null}
    {entry.phase === "sending" || entry.phase === "saving" ? <div className="upload-byte-progress">
      <progress aria-label={`Bytes sent for ${entry.displayName}`} max={entry.metadata?.declaredBytes ?? 1} value={entry.sentBytes} />
      <span>{entry.sentBytes.toLocaleString()} bytes sent{entry.phase === "saving" ? "; waiting for the server outcome." : ""}</span>
    </div> : null}
    {entry.error ? <p role="alert" className="upload-row-error">{entry.error}</p> : null}
    {cooldown ? <p role="status">Retry admission in {cooldown} seconds. No additional file bytes are being sent.</p> : null}
    {entry.phase === "replacement_needed" ? <p>The earlier transfer may still hold storage while it stops. Replacing it uses a new transfer under your current session.</p> : null}
    {entry.phase === "expired" ? <p>This operation cannot be revived. Select a file through Upload only if you intend to start a new operation.</p> : null}
    {receipt ? <><p>{receipt.outcome === "accepted" ? "The immutable original is recorded. Background processing can continue while you browse."
      : "This upload points to the existing original. No new processing job was created."}</p>
      <button type="button" onClick={() => onOpenDocument(receipt.documentId)}>Open document</button>
      <details><summary>Original receipt</summary><dl><dt>Document</dt><dd>{receipt.documentId}</dd><dt>Original asset</dt><dd>{receipt.assetId}</dd>
        <dt>SHA-256</dt><dd>{receipt.sha256}</dd><dt>Actual bytes</dt><dd>{receipt.byteSize.toLocaleString()}</dd>
        {receipt.jobId ? <><dt>Accepted processing job</dt><dd>{receipt.jobId}</dd></> : null}
        <dt>This operation recorded</dt><dd>{receipt.recordedAt}</dd></dl></details></> : null}
    {entry.phase === "duplicate_choice" && entry.attempt ? <UploadDuplicateChoice key={`${entry.attempt.uploadId}:${entry.attempt.revision}`}
      attempt={entry.attempt} disabled={busy} onChoose={(decision) => void controller.decide(entry.localId, decision)} onOpenDocument={onOpenDocument} /> : null}
    {reselection ? <label className="upload-reselect">Select original file<input type="file" accept={policy?.mimeTypes.join(",") ?? ""}
      onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (file) void controller.reselect(entry.localId, file); }} /></label> : null}
    <div className="upload-row-actions">
      {!terminal && !busy && entry.phase !== "queued" ? <button type="button" disabled={cooldown > 0} onClick={() => void controller.check(entry.localId)}>Check upload outcome</button> : null}
      {["ready_to_send", "replacement_needed"].includes(entry.phase) ? <button type="button" className="primary" onClick={() => void controller.send(entry.localId)}>
        {entry.phase === "replacement_needed" ? "Replace unfinished transfer" : "Send this file"}</button> : null}
      {!terminal ? <button type="button" disabled={entry.phase === "cancelling"} onClick={() => void controller.cancel(entry.localId)}>Cancel upload</button> : null}
      {terminal || entry.phase === "unavailable" ? <button type="button" onClick={() => controller.dismiss(entry.localId)}>Dismiss upload row</button> : null}
    </div>
  </article>;
}
