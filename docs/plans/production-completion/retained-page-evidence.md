# Retained page evidence and exact-generation reads

Date: 2026-09-07

Status: **Root-approved bounded first slice implemented for integration review as
migration 102 and `lib/evidence`. Local focused checks pass; the root-owned migration
registration and API/error wiring are present in the shared integration checkpoint;
isolated PostgreSQL validation remains pending.
Nothing in this slice activates native publication or changes the ordinary Viewer.**

This is a bounded X-02/X-05/UI-06 slice. [ADR 0009](../../adr/0009-qwen-native-document-parsing.md)
requires original-page evidence independent of Docling, and
[ADR 0010](../../adr/0010-document-processing-authority.md) separates retained parse
history from execution authority and current publication. UI-06 and stories
2.1, 3.1/3.2 and 4.5 require stable page navigation, inspectable structure and
historical evidence. The root phase sequence and Phase 8.5 release gate remain.

## Why a separate catalog

Migration 098's `document_generation_render_assets` belongs to an index build and
contains only visually eligible pages. A digital-text page can need a Viewer image
without needing a visual vector; an index can be replaced without replacing its
source evidence. Do not change the existing 098 manifest or asset IDs, loosen its
immutable triggers, insert unselected native rows into legacy `document_pages` or
`document_assets`, or make current readers select the newest processing run.

Add a **parse-owned retained render set**. Every sealed parse page receives one
exact source image reference, regardless of classification, text content, visual
embedding eligibility or accepted facts. Content-addressed bytes can be shared
with 098; provenance and lifetime must remain independent of the index.

## Additive storage

`102_completion_retained_page_evidence.sql` is allocated exclusively to this slice.
Applied migrations 096/098/100 remain unchanged.

`document_parse_render_sets` has one immutable set per `parse_generation_id`:

- Stable UUID, document ID, parse generation, creator processing run and producer
  job; exact original asset ID/hash, inventory hash, structure hash and parser
  configuration hash. It records no current-publication pointer.
- Frozen expected-page manifest and digest: ordered page number, existing page ID,
  checkpoint content hash, full `SourceRender` digest, encoded image hash,
  dimensions, renderer/version and coordinate space. Do not duplicate native text
  in this manifest. Its digest binds the exact descriptor that includes that text.
- State `building` or `sealed`; immutable seal manifest/hash/time assigned once.
  The expected manifest is assigned on creation from a deeply checked sealed parse.
  Progress is the number of verified stored page rows, not an operator count.

`document_parse_page_render_assets` contains immutable content-addressed pages:

- Stable `uuid5(parse_generation_id, 'source-render-v1:' + page_id)`, set/document/
  parse/page IDs and page number; frozen source-descriptor/checkpoint hashes;
  original asset/hash inherited through the immutable render-set header; private
  object URI, PNG hash/byte size, pixel dimensions,
  renderer/version and `rendered_source_pixels` coordinate basis.
- Unique `(parse_generation_id, page_number)` and `(parse_generation_id, page_id)`.
  Composite foreign keys establish set/document/parse ownership. Add an additive
  checkpoint uniqueness key only if required to reference the exact
  `(parse_generation_id, page_number, page_id)` tuple; retain all existing keys.
- Insert-or-verify exact normalized payload; changing bytes, URI, source identity
  or metadata under the same ID fails. Do not use a content-replacing upsert or
  modify a set after sealing. Existing rows survive cancellation/supersession.

Set/source/run/job/checkpoint cross-branch references use reviewed `NO ACTION
DEFERRABLE INITIALLY DEFERRED` foreign keys where document cascades can encounter
temporary ordering conflicts, following migration 100. Set-to-page and
document-to-set ownership can cascade. Both new tables carry document IDs and
reject independent deletion while that document exists. A full physical document
deletion must succeed with populated 096/098/new rows; deleting the original,
producer job, parse, set or page independently must fail without losing history.
No actor/credential FK or existing retention policy is weakened.

## Writer, bounds and late rendering

The first producer is the existing claimed parse job after parse seal and before
ACK. It uses the current 097 request/run authority plus the exact job token.
There is no new worker, authority backfill, job retargeting or independent historical
rerender command in this slice. A superseded run may be read but cannot create its
missing page assets. A later repair/reindex request needs separately admitted
authority, not revival of the original creator.

Proposed initial resource settings are implementation safety bounds, **not
ratified performance or quality targets**:

- Keep the source layer's maximum 100 MiB original, 500 pages and 40 million pixels
  per rendered page. Preserve the frozen parse render scale and orientation.
- Retain the exact frozen RGB PNG source bytes, bounded at 128 MiB per page.
  The Viewer catalog must not inherit the embedding adapter's 10 MiB image limit.
  A page outside a limit remains explicitly unavailable/unsealed; never downscale
  a source image to satisfy an embedding limit or call an omitted page complete.
- Default one execution call to at most eight new pages and 256 MiB of newly
  registered encoded data, counting reused blobs too. Allow 1–32 pages and
  128–512 MiB per call, so every admissible page fits a fresh call. Process one
  raster at a time. The maximum document-wide
  catalog is bounded by page count and per-page bytes; storage quota/free-space
  admission and long-document timing remain operational activation gates.
- Read registered rows and byte sizes before resuming. A per-call budget stop is
  `pending` with exact completed/remaining page IDs, not success or a failed parse.
  If the next page does not fit the remaining byte allowance, retain no partial
  page; a later invocation can resume it. Budgets do not change source identity.

Execution steps:

1. Under authority, freeze/verify the set and load exact source/configuration plus
   expected page descriptors. Resume existing exact rows; no current fallback.
2. When missing pages remain, outside a DB transaction open only the registered
   content-addressed original and verify asset ID/hash/MIME/byte size and complete
   inventory. Existing page descriptors resume without rerendering or rereading all
   previously stored bytes for each page. Full byte parity runs at seal/explicit
   sealed replay; it needs no renderer. Individual media reads verify their own page.
3. For each missing page, check authority, require the installed renderer identity
   to match the frozen configuration, render, compare the entire resulting
   `SourceRender` with the sealed checkpoint and recheck authority. Original-byte
   verification is mandatory even if a matching 098 render is reused; the 098 row
   alone cannot establish this new registration's original binding.
4. Store, snapshot-verify and stage exact bytes outside the transaction. In a
   fresh short transaction prelock the required source FK rows and content hash.
   Under that hash lock atomically commit the verified staged object (or verify
   the bounded existing object's hash/size), then register insert-or-verify and
   apply the fresh processing/job fence before commit. This small blob-commit
   exception prevents cleanup from deleting unreferenced bytes between initial
   verification and registration. If cleanup won, the exact staged bytes restore
   the destination before a retained pointer can commit. Reverify after commit.
5. On an exception, clean tracked newly created unreferenced objects only after
   rollback/closed transactions. Track the blob callback's actual `StoredObject.created`
   flag: it may recreate a destination the ingestion caller originally reused.
   Preserve existing objects and every retained hash. Process-kill orphan discovery
   remains a separate maintenance task.
6. Seal only when every expected source page has exactly one matching page row.
   Snapshot all registered descriptors under authority, verify their bounded bytes
   outside the transaction, then apply a fresh fenced seal transaction with full
   expected/actual parity and final manifest hash. Sealing repeats idempotently;
   any missing/corrupt page refuses a successful result and producer ACK.

Lock order remains 097 household/user/membership/credential/document authority,
run/generation and required source FK rows, sorted content-hash locks, render-set/page
rows, then job roots/claim. Original source reads, rendering, PNG decoding, verified
spooling/staging and HTTP remain outside those transactions. The explicit exception
is bounded verification of an existing destination or atomic commit of an already
verified staged blob while holding its content lock, before inserting the reference.
Cleanup takes the content lock and plain reference SELECTs only; it must not acquire
document/run/set locks in reverse order.

## Coexistence, cleanup and historical reads

Extend `cleanup_unreferenced_stored_object` with both URI and hash references from
the new catalog under its existing hash lock. Keep its pre-migration table-existence
guard and commit the cleanup query with the registered migration. Old 098 rows
continue protecting their bytes. New all-page rows protect the same bytes even if
no visual index exists, the run is superseded, or all index work is cancelled.
Do not rewrite old 098 manifests/observations to adopt new asset IDs. A later
index adapter may consume the retained PNG bytes while preserving its own current
versioned input contract. Original and historical legacy assets remain untouched.

Read authority is deliberately different from writer authority. Use the existing
live document/token read policy, current persisted membership role and token
scopes, with exact document+parse+page ownership in the same statement snapshot.
Allow sealed historical/superseded/cancelled generations; never require a current
run, live creator, job claim or installed historical renderer merely to read bytes.
Do not reuse `lock_current_run` for a Viewer read or depend on `lib/evaluation`.
Shared pure structural validators may be extracted deliberately, but runtime
reader code must not depend on scoring/declaration/holdout concepts.

## Exact-generation API and DTO proposal

Add cohesive `lib/evidence` domain/DTO, repository, service and artifact adapter
modules, with a thin `routes_generation_evidence.py`. Coordinate shared exports,
OpenAPI and frontend types with their owners before editing them.

- `GET /api/v1/documents/{documentId}/parse-generations/{parseGenerationId}` returns
  exact run/parse/original identity, seal hashes, source page count and deterministic
  paginated page metadata (`offset`, `limit`, `total`). Every original page is
  represented, including pages whose source render is not yet retained. It returns
  `viewScope: retained_parse_generation`; no inferred `isCurrent` property.
- `GET .../pages/{pageNumber}` returns its stable page ID, parse outcome, full
  elements/reading order/tables/cells and exact chunk references, plus separate
  native text/model-transcription origins and registered source-render metadata.
  No raw model response, source URI, hidden storage path or accepted-fact claim is
  part of this ordinary read DTO. Protected diagnostics remain separately scoped.
- `GET .../pages/{pageNumber}/render` serves only the registered original-page PNG
  for that exact parse/page. The DTO provides this protected URL and image ID/hash,
  dimensions and coordinate basis. Missing/wrong-generation/unauthorized references
  never fall back to current pages. Return the same unavailable result for unknown
  and unauthorized references; an authorized reader may see explicit registration
  progress in the metadata endpoint.

Read metadata distinguishes `registered` from `not_retained`; a catalog row alone
does not attest present byte availability. Media retrieval verifies actual bytes.
Open the bounded content-addressed file once and copy into a private bounded
snapshot while computing its hash. Use a temporary spool with at most 8 MiB in
memory, private on-disk spill and the 128 MiB total cap; validate size/hash/PNG
identity on that snapshot, then recheck live read access after expensive I/O and
stream from the **same verified private snapshot**. This also survives an in-place
change to the source file after verification, not only a renamed path. Do not
verify a path and hand it to `FileResponse` for a later reopen. Close the source
and spool on denial, error, disconnect or completion.
Use `private, no-store`, `nosniff`, fixed `image/png` and a static safe filename;
do not serve HTML/SVG or pass object URIs to the browser. No DB lock spans the
media read/response. As with the existing authorized read contract, later revocation
cannot recall already returned bytes; subsequent requests reauthorize.

The exact source raster defines a top-left origin with x right/y down. Existing
boxes already use that raster's pixels, including intrinsic source orientation.
Display zoom/rotation is a separate reversible UI transform; never rotate the
source again from `SourcePage.rotation_degrees`. Validate element/table/cell/page
ownership and box bounds. A native-text span without independently established
geometry yields an excerpt/page jump, not a fabricated highlight. Copying model
text does not make it independently verified. Retained images remain readable when
the parser/renderer is unavailable; historical structure versions need explicit
supported readers, not re-normalization with an arbitrarily newer implementation.

Repository page reads load compact sealed header identity plus the requested
checkpoint and registered asset, with digest/ownership parity for those rows.
They do not fetch/re-normalize the full structure or every raw model response on
each page request. Full cross-page parity belongs to set creation/seal and explicit
diagnostic verification. Preserve versioned read schemas even after a parser or
renderer implementation changes.

The existing `DocumentDetail`, `EvidenceRef` and frontend `EvidenceTarget` stay
unchanged in the first slice. Later integration adds a versioned exact-generation
locator and shared resolver without interpreting old unscoped references as newest
native IDs. Ordinary Viewer selection, accepted fields, thumbnails, find-in-document,
deep-link routing and coherent parse/fact/index publication remain explicit follow-on
work. The initial API must not mix today's accepted fields with an unselected parse.

## Executable first slice and decisive checks

The implementation contains the two tables, frozen types and pure manifest
validation; transactional creation/checkpoint/seal repositories; bounded rendering
and media adapters; cleanup integration; compact historical metadata/page reads;
and separate protected API contracts. Add an explicit optional before-ACK consumer
to the isolated probe after integration, with all-page registration/replay and
historical read after a later processing run. No ordinary pipeline or UI activation.

Root-owned API, error and migration registration are present for the integration
checkpoint. Local tests include real digital PDF rendering (including rotation),
bounded TIFF continuation, source mutation, private spool mode and transport failure,
DTO/OpenAPI parity, historical mapping and fresh post-IO access denial. Authored
PostgreSQL cases cover immutable catalog rows, populated 096/098/102 document
cascades, byte cleanup serialization, claim revocation/expiry after SQL lock waits
and separate-connection token/member revocation during media IO. These are not yet
reported as passing PostgreSQL or live service evidence.

Required checks include:

- A digital PDF page excluded from visual embeddings still has a retained source
  image; image/TIFF pages, blank pages and partial/insufficient parses remain in
  the exact denominator. Missing/bad final-page bytes prevent sealing.
- Resume after each page; conflicting bytes/IDs/config/URI and changed originals
  fail; registered replay survives a missing renderer and makes no inference call.
- Separate-connection cancellation, membership/token/ACL loss and run supersession
  during render or while waiting to register refuse stale writes and ACK. Historical
  sealed reads still work after supersession under a currently authorized reader.
- Cross-document/page/parse/household IDs, token-scope changes, deleted documents
  and protected-route enumeration fail; no original/model text or storage path leaks
  through denial. Replace or modify the source file between verification and response
  to prove the same verified snapshot is streamed; corruption/missing bytes before
  the snapshot is verified fail closed.
- Independent deletion fails and full document deletion succeeds with populated
  096/098/new rows. Cleanup preserves URI/hash references across both catalogs and
  releases only unreferenced objects after complete deletion.
- A rotated PDF and oriented image preserve exact page identity and boxes. Test
  cropped/rotated UI mapping before using a highlight in the shared Viewer.
- Source metadata/page reads remain bounded; no whole 500-page structure/raw-output
  transfer for one page request. Unit, real PostgreSQL, contract and authenticated
  API tests validate the new lane. UI-06's first-page <1-second and long-document
  navigation gates remain measured product work, not inferred from this foundation.

This slice can establish durable all-page source evidence and an ACL-safe exact
reader. It does not close UI-06, ordinary generation activation, semantic support
of extracted claims, representative document quality or release acceptance.
