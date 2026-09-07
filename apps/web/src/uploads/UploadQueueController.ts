import {ApiError} from "../api";
import {randomUuid} from "../browserUuid";
import {cancelUpload, decideUpload, getUpload, getUploadPolicy, registerUpload, UploadHttpError} from "./api";
import {uploadDigest, uploadUuid} from "./authority";
import {activeUploadPhases, applyUploadObservation, canDispatchUpload, clearUploadPrivateState, observedUploadPhase,
  terminalUploadPhases, uploadFileByteLimit, type UploadEntry, type UploadPhase, type UploadQueueSnapshot} from "./queue";
import {readUploadReferences, registrationDigest, uploadRegistration, writeUploadReferences} from "./recovery";
import {sendUploadContent} from "./transport";
import type {UploadActor, UploadAttempt, UploadDecision, UploadReceipt, UploadSource} from "./types";

// Owns one authenticated shell's upload work. React only subscribes and renders.
export class UploadQueueController {
  private state: UploadQueueSnapshot = {entries: [], policy: null, policyError: null, storageError: null, open: false, online: navigator.onLine, admissionRetryAt: null};
  private listeners = new Set<() => void>();
  private requests = new Map<string, AbortController>();
  private receipts = new Set<string>();
  private epoch = 0;
  private live = false;
  private adding = 0;
  private recovered = false;
  private paused = false;
  private admissionTimer: ReturnType<typeof setTimeout> | null = null;
  constructor(private actor: UploadActor, private onAccepted: (receipt: UploadReceipt) => void | Promise<void>) {}
  snapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private change(change: Partial<UploadQueueSnapshot>) { this.state = {...this.state, ...change}; this.listeners.forEach((listener) => listener()); }
  private entry(localId: string) { return this.state.entries.find((entry) => entry.localId === localId); }
  private update(localId: string, change: Partial<UploadEntry>) {
    if (this.live) this.change({entries: this.state.entries.map((entry) => entry.localId === localId ? {...entry, ...change} : entry)});
  }
  private persist() {
    try { writeUploadReferences(this.actor, this.state.entries
      .filter((entry) => entry.attempt || entry.reference.uploadId || !terminalUploadPhases.includes(entry.phase))
      .map((entry) => entry.reference).filter((ref) => uploadDigest(ref.registrationSha256))); }
    catch { this.change({storageError: "Uploads can continue in this page, but recovery after refresh is unavailable in this browser."}); }
  }
  start() {
    this.live = true; this.epoch++;
    if (!uploadUuid(this.actor.userId) || !uploadUuid(this.actor.householdId)) {
      this.change({policyError: "A current actor and household identity are required for uploads."}); return;
    }
    void this.loadPolicy();
  }
  dispose() {
    this.live = false; this.epoch++;
    if (this.admissionTimer) clearTimeout(this.admissionTimer);
    this.admissionTimer = null;
    this.requests.forEach((request) => request.abort()); this.requests.clear();
    this.state = {...this.state, entries: this.state.entries.map(clearUploadPrivateState), open: false, admissionRetryAt: null};
  }
  setOpen(open: boolean) { this.change({open}); }
  setOnline(online: boolean) { this.change({online}); if (online) this.pump(); }
  async loadPolicy() {
    if (!uploadUuid(this.actor.userId) || !uploadUuid(this.actor.householdId)) return;
    const epoch = this.epoch;
    try {
      const policy = await getUploadPolicy();
      if (!this.live || epoch !== this.epoch) return;
      this.change({policy, policyError: policy.available ? null : "New uploads are currently unavailable."});
      if (!this.recovered) {
        this.recovered = true;
        try {
          const references = readUploadReferences(this.actor, policy.queueReferenceLimit);
          this.change({entries: references.map((reference) => ({localId: reference.localId, reference, displayName: "Previous upload",
            metadata: null, file: null, attempt: null, phase: "unknown", sentBytes: 0, error: null, retryAt: null}))});
        } catch { this.change({storageError: "Previous upload references could not be read safely. No earlier operation has been restarted."}); }
      }
      this.pump();
    } catch (failure) {
      if (this.live && epoch === this.epoch) this.change({policyError: failure instanceof Error ? failure.message : "Upload policy could not be loaded."});
    }
  }
  async add(files: File[], source: UploadSource = "web_upload") {
    const policy = this.state.policy, epoch = this.epoch;
    if (!policy?.available || !this.live) return;
    this.setOpen(true);
    const room = Math.max(0, policy.queueReferenceLimit - this.state.entries.length - this.adding);
    const selected = files.slice(0, room); this.adding += selected.length;
    if (selected.length < files.length) this.change({policyError: `${files.length - selected.length} files were not added because the upload queue is full. Clear finished rows before selecting them again.`});
    const clientBatchId = randomUuid();
    for (const file of selected) {
      try {
        const localId = randomUuid(), operationId = randomUuid();
        const metadata = uploadRegistration(file, source, operationId, clientBatchId);
        let digest = "";
        try { digest = await registrationDigest(metadata); }
        catch { this.change({storageError: "Uploads can continue here, but refresh recovery could not be prepared."}); }
        if (!this.live || epoch !== this.epoch) return;
        const limit = uploadFileByteLimit(policy);
        const error = file.size === 0 ? "This file is empty." : file.size > limit ? "This file exceeds the configured upload or reserved-storage limit."
          : Array.from(file.name).length > 255 ? "This filename is longer than the server supports." : null;
        const entry: UploadEntry = {localId, reference: {...this.actor, localId, operationId, clientBatchId, registrationSha256: digest, source},
          displayName: file.name, metadata, file: error ? null : file, attempt: null, phase: error ? "rejected" : "queued", sentBytes: 0, error, retryAt: null};
        this.change({entries: [...this.state.entries, entry]}); this.persist(); this.pump();
      } finally { this.adding--; }
    }
  }
  private pump() {
    if (!this.live || this.paused || !this.state.online || !this.state.policy || this.admissionPaused()) return;
    for (const entry of this.state.entries) if (canDispatchUpload(this.state.entries, entry, this.state.policy)) {
      void this.run(entry.localId, "registering", async (current, signal) => {
        const attempt = await registerUpload(current.metadata!, signal);
        this.update(current.localId, {attempt, reference: {...current.reference, uploadId: attempt.uploadId}}); this.persist();
        if (attempt.state !== "awaiting_content" || attempt.currentTransferId) return attempt;
        return this.transfer({...current, attempt}, signal);
      });
    }
  }
  private admissionPaused() { return !!this.state.admissionRetryAt && Date.now() < this.state.admissionRetryAt; }
  private pauseAdmission(retryAt: number) {
    const until = Math.max(this.state.admissionRetryAt ?? 0, retryAt);
    this.change({admissionRetryAt: until});
    if (this.admissionTimer) clearTimeout(this.admissionTimer);
    this.admissionTimer = setTimeout(() => {
      this.admissionTimer = null;
      if (!this.live) return;
      this.change({admissionRetryAt: null}); this.pump();
    }, Math.max(1, until - Date.now()));
  }
  private transfer(entry: UploadEntry, signal: AbortSignal) {
    const attempt = entry.attempt!;
    this.update(entry.localId, {phase: "sending", sentBytes: 0});
    return sendUploadContent(entry.file!, {...entry.reference, uploadId: attempt.uploadId, revision: attempt.revision,
      filename: entry.metadata!.filename, declaredBytes: entry.metadata!.declaredBytes,
      ...(attempt.currentTransferId ? {replaceTransferId: attempt.currentTransferId} : {})}, {
      signal, timeoutMs: (this.state.policy!.absoluteSeconds + this.state.policy!.idleSeconds) * 1000,
      onProgress: (sentBytes, totalBytes) => this.update(entry.localId, {sentBytes, phase: sentBytes === totalBytes ? "saving" : "sending"}),
    });
  }
  private async run(localId: string, phase: UploadPhase, action: (entry: UploadEntry, signal: AbortSignal) => Promise<UploadAttempt>, replacePending = false) {
    const entry = this.entry(localId), epoch = this.epoch;
    if (!this.live || !entry || (!replacePending && this.requests.has(localId))) return;
    if (phase !== "cancelling" && entry.retryAt && Date.now() < entry.retryAt) return;
    this.requests.get(localId)?.abort();
    const request = new AbortController(); this.requests.set(localId, request);
    this.update(localId, {phase, error: null});
    try {
      const attempt = await action(entry, request.signal);
      if (!this.live || epoch !== this.epoch || this.requests.get(localId) !== request) return;
      const current = this.entry(localId); if (!current) return;
      this.update(localId, applyUploadObservation(current, attempt)); this.persist();
      if (attempt.receipt) {
        const key = `${localId}:${attempt.receipt.recordedAt}`;
        if (!this.receipts.has(key)) {
          this.receipts.add(key);
          try { await this.onAccepted(attempt.receipt); }
          catch { this.update(localId, {error: "The original is accepted, but the document list could not be refreshed. Open its exact document or refresh the list."}); }
        }
      }
    } catch (failure) {
      if (!this.live || epoch !== this.epoch || this.requests.get(localId) !== request) return;
      if (failure instanceof ApiError && [401, 403, 404].includes(failure.status)) {
        const current = this.entry(localId); if (current) this.update(localId, {...clearUploadPrivateState(current), phase: "unavailable", error: "This upload is unavailable or you no longer have access."});
      } else {
        const limited = failure instanceof UploadHttpError && failure.status === 429;
        const retryAt = limited ? Date.now() + (failure.retryAfterMs ?? 2000) : null;
        if (retryAt) this.pauseAdmission(retryAt);
        this.update(localId, {phase: limited ? "retry_wait" : "unknown", retryAt,
          error: failure instanceof Error ? failure.message : "The upload outcome could not be confirmed. Check it before sending again."});
      }
    } finally {
      if (this.requests.get(localId) === request) { this.requests.delete(localId); this.pump(); }
    }
  }
  async check(localId: string) {
    const entry = this.entry(localId); if (!entry) return;
    if (!entry.reference.uploadId && !entry.metadata) { this.update(localId, {phase: "needs_file", error: "Select the original file to check its unchanged registration."}); return; }
    await this.run(localId, "checking", (current, signal) => current.reference.uploadId
      ? getUpload({...current.reference, uploadId: current.reference.uploadId}, signal) : registerUpload(current.metadata!, signal));
  }
  async reselect(localId: string, file: File) {
    const entry = this.entry(localId), epoch = this.epoch;
    if (!entry || activeUploadPhases.includes(entry.phase) || terminalUploadPhases.includes(entry.phase)) return;
    const metadata = uploadRegistration(file, entry.reference.source, entry.reference.operationId, entry.reference.clientBatchId);
    try {
      if (await registrationDigest(metadata) !== entry.reference.registrationSha256) throw new Error("This file's registration metadata does not match the previous upload. Select the original file; this operation has not been changed.");
      if (this.live && epoch === this.epoch && this.entry(localId) === entry) this.update(localId, {metadata, file, displayName: file.name,
        phase: entry.attempt ? observedUploadPhase(entry.attempt, true) : "unknown", error: null});
    } catch (failure) { if (this.live && epoch === this.epoch) this.update(localId, {error: failure instanceof Error ? failure.message : "File metadata could not be checked."}); }
  }
  async send(localId: string) {
    const entry = this.entry(localId);
    if (!entry?.file || !entry.metadata || !entry.attempt || !["ready_to_send", "replacement_needed"].includes(entry.phase)) return;
    if (!this.state.online || this.admissionPaused() || !this.state.policy || !canDispatchUpload(this.state.entries, {...entry, phase: "queued"}, this.state.policy)) {
      this.update(localId, {error: "Wait for other transfers or held duplicate choices to finish, then send this file explicitly."}); return;
    }
    await this.run(localId, "sending", (current, signal) => this.transfer(current, signal));
  }
  async decide(localId: string, decision: UploadDecision) {
    const entry = this.entry(localId), attempt = entry?.attempt;
    if (!entry || !attempt || entry.phase !== "duplicate_choice" || decision.revision !== attempt.revision
      || (decision.decision === "use_existing" && !attempt.duplicates.some((match) => match.documentId === decision.documentId))) return;
    await this.run(localId, "saving", (current, signal) => decideUpload({...current.reference, uploadId: attempt.uploadId}, decision, signal));
  }
  async cancel(localId: string) {
    const entry = this.entry(localId); if (!entry || terminalUploadPhases.includes(entry.phase)) return;
    if (entry.phase === "queued" && !entry.reference.uploadId) { this.update(localId, {phase: "cancelled", file: null, metadata: null}); this.persist(); return; }
    if (!entry.reference.uploadId && !entry.metadata) { this.update(localId, {error: "Reselect the original file to locate and cancel this unconfirmed registration."}); return; }
    await this.run(localId, "cancelling", async (current, signal) => {
      const uploadId = current.reference.uploadId ?? (await registerUpload(current.metadata!, signal)).uploadId;
      return cancelUpload({...current.reference, uploadId}, signal);
    }, true);
  }
  dismiss(localId: string) {
    const entry = this.entry(localId); if (!entry || activeUploadPhases.includes(entry.phase)) return;
    this.change({entries: this.state.entries.filter((item) => item.localId !== localId)}); this.persist(); this.pump();
  }
  async checkUncertain() {
    const ids = this.state.entries.filter((entry) => ["unknown", "retry_wait", "unavailable"].includes(entry.phase)).map((entry) => entry.localId);
    for (const id of ids) { if (!this.live) return; await this.check(id); }
  }
  async cancelUnaccepted() {
    this.paused = true;
    const ids = this.state.entries.filter((entry) => !terminalUploadPhases.includes(entry.phase)).map((entry) => entry.localId);
    try { for (const id of ids) { if (!this.live) return; await this.cancel(id); } }
    finally { this.paused = false; this.pump(); }
  }
  clearFinished() {
    this.change({entries: this.state.entries.filter((entry) => !terminalUploadPhases.includes(entry.phase))}); this.persist(); this.pump();
  }
}
