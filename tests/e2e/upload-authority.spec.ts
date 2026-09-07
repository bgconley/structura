import {expect, test} from "@playwright/test";
import {createHash} from "node:crypto";
import {parseUploadAttempt, parseUploadPolicy} from "../../apps/web/src/uploads/authority";
import {parseUploadReferences, registrationDigest, uploadRegistration, writeUploadReferences} from "../../apps/web/src/uploads/recovery";
import {applyUploadObservation, canDispatchUpload, clearUploadPrivateState, observedUploadPhase, type UploadEntry} from "../../apps/web/src/uploads/queue";
import {acceptedUpload, uploadActor, uploadAttempt, uploadId, uploadMetadata, uploadPolicy, uploadReference} from "./support/uploadAttemptFixture";

test("accepted and reused uploads preserve exact immutable receipts and distinct job semantics", () => {
  for (const state of ["accepted", "reused"] as const) {
    const value = parseUploadAttempt(acceptedUpload(state), uploadMetadata);
    expect(value.receipt?.outcome).toBe(state);
    expect(value.receipt?.documentId).toBe(uploadId(8));
    expect(value.receipt?.jobId).toBe(state === "accepted" ? uploadId(11) : null);
  }
});
for (const defect of ["operation", "batch", "resource", "receipt size", "receipt hash", "receipt outcome", "reused job", "false acceptance", "duplicate hidden by state"]) {
  test(`upload observation refuses ${defect} inconsistency`, () => {
    const value = acceptedUpload(), expected = {...uploadMetadata, uploadId: value.uploadId};
    if (defect === "operation") value.operationId = uploadId(90);
    if (defect === "batch") value.clientBatchId = uploadId(90);
    if (defect === "resource") value.uploadId = uploadId(90);
    if (defect === "receipt size") value.receipt!.byteSize++;
    if (defect === "receipt hash") value.receipt!.sha256 = "c".repeat(64);
    if (defect === "receipt outcome") value.receipt!.outcome = "reused";
    if (defect === "reused job") { value.state = "reused"; value.receipt!.outcome = "reused"; }
    if (defect === "false acceptance") value.receipt = null;
    if (defect === "duplicate hidden by state") value.duplicates = [{documentId: uploadId(80), title: "Unexpected match"}];
    expect(() => parseUploadAttempt(value, expected)).toThrow(/unavailable or inconsistent/);
  });
}
test("held duplicate and expired tombstone states do not invent acceptance", () => {
  const value = uploadAttempt();
  expect(parseUploadAttempt({...value, state: "expired"}, uploadMetadata).receipt).toBeNull();
  expect(() => parseUploadAttempt({...value, state: "awaiting_duplicate_decision"}, uploadMetadata)).toThrow();
  const held = {...acceptedUpload(), state: "awaiting_duplicate_decision", receipt: null, duplicates: [{documentId: uploadId(80), title: "Readable match"}]};
  expect(parseUploadAttempt(held, uploadMetadata).duplicates).toHaveLength(1);
});
test("policy must be explicit and bounded before any content dispatch", () => {
  expect(parseUploadPolicy(uploadPolicy()).inactiveSeconds).toBe(1800);
  for (const change of [{protocol: "legacy"}, {actorActiveLimit: 0}, {maxFileBytes: Infinity}, {queueReferenceLimit: 1001}, {mimeTypes: []}])
    expect(() => parseUploadPolicy({...uploadPolicy(), ...change})).toThrow();
});
test("registration recovery digest binds all immutable metadata and has deterministic property order", async () => {
  const file = {name: uploadMetadata.filename, size: uploadMetadata.declaredBytes, type: "application/pdf"};
  const registration = uploadRegistration(file, "web_upload", uploadMetadata.operationId, uploadMetadata.clientBatchId);
  expect(registration).toEqual(uploadMetadata);
  expect(await registrationDigest(registration)).toBe(createHash("sha256").update(JSON.stringify(registration)).digest("hex"));
  expect(await registrationDigest({...registration})).toBe(await registrationDigest({...registration, filename: file.name}));
  for (const change of [{filename: "Another.pdf"}, {declaredBytes: 257}, {source: "bulk_import" as const}, {title: "Changed"}])
    expect(await registrationDigest({...registration, ...change})).not.toBe(await registrationDigest(registration));
});
test("scope-bound storage whitelists opaque references and never persists private receipt or filename", () => {
  let stored = "";
  const reference = {...uploadReference(), filename: uploadMetadata.filename, receipt: acceptedUpload().receipt};
  writeUploadReferences(uploadActor, [reference], {setItem: (_key, value) => {stored = value;}, removeItem: () => {stored = "";}});
  expect(stored).not.toContain("Private medical"); expect(stored).not.toContain("receipt"); expect(stored).not.toContain(uploadId(8));
  expect(parseUploadReferences(stored, uploadActor, 100)).toEqual([uploadReference()]);
  expect(() => parseUploadReferences(stored, {...uploadActor, userId: uploadId(99)}, 100)).toThrow(/account/);
  expect(() => parseUploadReferences(stored, uploadActor, 0)).toThrow(/invalid/);
  const injected = JSON.parse(stored); injected.items[0].filename = "Sensitive";
  expect(() => parseUploadReferences(JSON.stringify(injected), uploadActor, 100)).toThrow();
});

function queueEntry(): UploadEntry {
  return {localId: uploadId(12), reference: uploadReference(), displayName: uploadMetadata.filename,
    metadata: uploadMetadata, file: new File([new Uint8Array(256)], uploadMetadata.filename, {type: "application/pdf"}),
    attempt: null, phase: "queued", sentBytes: 0, error: null, retryAt: null};
}
test("server observations preserve acceptance and require explicit generation replacement", () => {
  expect(observedUploadPhase({...uploadAttempt(), state: "receiving", currentTransferId: uploadId(77)}, true)).toBe("replacement_needed");
  expect(observedUploadPhase(uploadAttempt(), false)).toBe("needs_file");
  const accepted = applyUploadObservation(queueEntry(), acceptedUpload());
  expect(accepted.phase).toBe("accepted"); expect(accepted.file).toBeNull();
  expect(accepted.attempt?.receipt?.documentId).toBe(uploadId(8));
  const cleared = clearUploadPrivateState(accepted);
  expect(cleared.attempt).toBeNull(); expect(cleared.metadata).toBeNull(); expect(cleared.file).toBeNull();
  expect(cleared.displayName).not.toContain("Private");
});
test("local dispatch respects actor count and held storage reservations without trusting total batch success", () => {
  const first = queueEntry(), second = {...queueEntry(), localId: uploadId(22)}, third = {...queueEntry(), localId: uploadId(23)};
  const policy = uploadPolicy();
  expect(canDispatchUpload([first], first, policy)).toBe(true);
  expect(canDispatchUpload([{...second, phase: "sending"}, {...third, phase: "saving"}, first], first, policy)).toBe(false);
  const held = {...acceptedUpload(), state: "awaiting_duplicate_decision" as const, receipt: null};
  expect(canDispatchUpload([{...second, attempt: held, phase: "duplicate_choice"}, first], first, {...policy, actorReservedBytes: 256})).toBe(false);
  expect(canDispatchUpload([applyUploadObservation(second, acceptedUpload()), first], first, {...policy, actorReservedBytes: 256})).toBe(true);
});
