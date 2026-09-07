# Upload attempt contract and admission design

Implementation supplement to [batch intake](batch-intake.md), UI-04 and SEC-01.
Root owns migration **104** and this backend lane. Migration 103 remains the
line-item authority lane. The existing intake decomposition landed in `927b215`;
the resource below is implemented as a candidate backend pending the isolated
PostgreSQL/API/proxy gate and root registration. No browser retry or native pipeline
activation is included in this checkpoint.

## Transport decision

The new content endpoint accepts the file's raw bytes, with metadata registered
separately. This intentionally replaces the draft multipart PUT in batch-intake.
Local inspection of the installed FastAPI route handler showed `request.form()`
consumes multipart input before dependency resolution. A `Request`-stream endpoint
without a declared form/body field lets authentication and a database admission
lease run before body consumption. It also removes multipart overhead from this
new endpoint's file-size limit. Existing `POST /documents` remains compatible.

The web proxy and API enforce actual streamed
byte limits at both proxy and API boundaries; do not rely on browser metadata or
one network hop. Legacy multipart gets a separately bounded envelope allowance.
Small JSON control bodies have their own limit. Oversize and interrupted streams
must release their file handles and leave no accepted receipt.

The legacy API repair authenticates and checks write/CSRF authority before any
multipart receive call. Its adapter enforces the configured file limit independently
of a 64 KiB total envelope allowance, one file and three named control fields,
16 KiB per field and aggregate part headers, 4 KiB per part header,
matching actual/declared length when
provided, a 30-second idle timeout and a ten-minute transfer deadline. Missing
Content-Length remains supported. Ambiguous duplicate fields, unfinished multipart
boundaries and malformed headers are rejected; completed and unfinished temporary
files close on success, failure, disconnect and cancellation. These stricter bounds
preserve the documented `file`, `source`, `suppliedTitle`, `hintsJson` wire format
and acceptance receipt. Intake disk/database work runs outside the API event loop.
This repair does not add durable admission/replay or a post-transfer credential
fence to the legacy endpoint; those remain distinct from the stronger resource below.

## Resource and operation identity

- `POST /api/v1/uploads`: an actor/household-scoped operation UUID, client batch UUID,
  filename, declared byte count, optional declared MIME, source and optional title.
  Immutable metadata defines replay equality. Same key and metadata returns the
  same resource; changed metadata returns409. No original/document/job exists yet.
- `PUT /api/v1/uploads/{id}/content`: raw bytes, authenticated and CSRF-protected.
  Reserve a transfer generation before consuming bytes. Check actual size, signature
  and hash; persist exactly one immutable received-content identity. Then accept or
  hold that content for a readable exact-duplicate decision.
- `GET /api/v1/uploads/{id}`: reconcile exact outcome under current actor membership
  and document ACL. Resource existence does not grant access to its accepted document.
- `POST /api/v1/uploads/{id}/decision`: exact resource revision plus `keep_separate`
  or `use_existing` with a concrete authorized matching document UUID. Revalidate
  the exact original/hash and current reader permission before reusing it.
- `DELETE /api/v1/uploads/{id}`: cancel only an unaccepted operation. If acceptance
  won, return the actual receipt. Transport abort alone cannot establish cancellation.
- `GET /api/v1/upload-policy`: bounded queue, active transfer and byte limits,
  supported signatures, and availability of this protocol. UI consumes these values.

The resource keeps actor, household and operation identity after cancellation or
expiry. Eligible inactive awaiting_content registrations/retry slots become expired
tombstones after their configured deadline; active/held transfers and unconfirmed
running IO are not released by this rule. Capacity admission also expires old slots
for the current actor, so losing unstarted browser references cannot permanently
exhaust the queue. Neither cleanup nor retry may erase an old key and turn it into permission
to create a second document. A transfer lease has its own UUID/revision and captured
credential identity; it is distinct from the longer-lived upload operation.

New acceptance returns exact document, original asset, batch, ingest job, actual
size/hash and acceptance timestamp. Reuse returns the chosen document and original
identity, with an explicit reused outcome and no invented new processing job.
Accepted-content replay must verify equality; GET is the preferred way to recover a
lost response without resending bytes. Different bytes under the same operation
cannot replace an original or return a misleading successful replay.

## Concurrency, credentials and storage accounting

Reuse the shared `RequestCredential`, `lock_request_authority` and
`assert_request_authority` helpers from the 103 lane. A receiving generation captures
the originating real session/token identity; no raw secret is persisted. Recheck
that exact credential after byte IO and all lock waits before publication. A new
credential may explicitly reserve a replacement transfer generation for the same
actor's unfinished operation. Already-admitted processing keeps ADR0010's lifetime.

Reserve concurrency and declared bytes transactionally across tabs/processes.
Initial validation policy: two active transfers per actor and four globally, a
100-reference browser queue, and the existing 100 MiB maximum file. Staged duplicate
decisions also consume bounded storage capacity. Validation defaults now configure 200 MiB actor/400 MiB global reserved bytes,
30-minute held content and inactive-operation expiry, 10-minute absolute transfer
and 30-second idle deadlines; these require the isolated gate before activation; disk capacity is not inferred from a
small active-request count.

An upload operation and its transfer reservations require separate records:
cancelling an operation does not instantly release a still-writing transfer's byte
reservation. Retain that reservation until IO stops and staged cleanup is confirmed.
Expired/crashed generations need a cleanup claim and recorded cleanup outcome;
releasing a database lease while abandoned bytes remain is not storage reclamation.
Every stream enforces a bounded deadline and idle timeout outside DB transactions.

Use a dedicated admission advisory-lock namespace before the request credential
prefix when reserving global capacity. Use a separate household/content admission
namespace to serialize same-hash duplicate lookup and acceptance. All participating
upload writers use the same order; these locks are not the existing content cleanup
lock. Preserve document-before-content-hash ordering when publishing an original.
Do not hold database locks while consuming request bytes or doing full-file hashing.

Duplicate lookup returns readable documents only. No readable match means ordinary
acceptance, without a hidden-match flag, title, count or alternate status. A matching
document revoked while a choice is open yields safe unavailability. Keep separate
creates one independent document with its own filing; use existing never refiles,
merges, reruns or changes facts. Content-addressed bytes may be shared.

Receipt, original/document records and job creation commit in one transaction using
the shared intake repositories and queue factory. A rollback invokes reference-aware
cleanup only for objects this attempt created. Retained duplicate staging must be
protected from cleanup until its decision/expiry is terminal. Preserve originals
and every accepted receipt across cancellation, worker outage and process restart.

## Acceptance before UI activation

Use a fresh isolated database plus the actual API/proxy for body-stream tests.
Required cases include same-key lost-response recovery, different-byte conflict,
same-hash concurrent acceptance, exact readable duplicate choice, hidden matches,
credential revocation/replacement/expiry during IO, admission limits across clients,
cancel-versus-accept, late bytes after cancellation, expired generation fencing,
post-blob and post-job rollback, disconnect and crash cleanup, absent/misdeclared
Content-Length, exact-limit and over-limit bodies, and actual signature mismatch.

Resource schemas, safe errors and lease accounting must pass those tests before
browser automatic retries are enabled. Model/worker availability does not gate
original acceptance. Native parse/index publication and the separate processing
status read model are not activated by this resource.


## Candidate backend checkpoint

Migration104 and `lib/uploads/` implement the admitted raw-stream resource, immutable
transfer generation/content equality, exact duplicate decisions, synchronous captured
credential fences, staged IO reservations and strict crash cleanup. The public PUT
requires `If-Match` revision; explicit replacement additionally names the current
`X-Replace-Transfer-ID`. The separate filesystem publication adapter hashes an open
FD outside SQL and checks exact no-symlink inode/size/time identity under the content
lock. Same-filesystem publication links avoid an unaccounted second file copy.
Directory fsync ordering precedes persisted verified content and original acceptance;
the real process-kill regression is not a measured power-loss recovery rehearsal.

`lib/uploads/README.md` records lock order, limits, failure and retention behavior.
The bounded `clean_expired_uploads` entry point is supplemented by the supervised
`worker-upload-cleanup` service. Its existing-namespace guard, fair bounded sweeps,
health, shutdown and separate-process recovery tests are implemented. Root integrated
the router/errors, batch browser queue and scoped Compose service. The
[upload/claim checkpoint](../../release-evidence/production-completion-g0/upload-claims-checkpoint.md)
records 474 passing PostgreSQL tests and isolated startup health. Real browser/API
upload acceptance and production runtime qualification remain separate gates.
