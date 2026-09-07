# Native candidate index generations

Date: 2026-09-07

Status: **Root-approved hidden storage foundation and bounded embedding executor implemented; executor canonical DB/live-probe validation pending. Ordinary retrieval activation remains unimplemented.**

Scope: the hidden candidate-index portion of X-05/X-07, using sealed migration-096
parse artifacts and migration-097 request authority. Migration
`098_completion_native_index_candidates.sql` is assigned to the hidden storage
foundation; the integrator registers it with the matching code. This document does not activate a current index, alter
the selected models, or claim that X-05/X-07 or the Phase 8.5 gate is complete.

## Implementation checkpoint and retained gates

The bounded implementation in `lib/search/indexing/` supplies immutable accepted
configuration/input/render/observation types, pure parse-only projection, exact
producer/run/build binding, atomic preparation, insert-or-verify float32 vector
checkpoints, complete sealing and candidate cancellation. Its transaction service
never invokes models; the explicit execution adapter invokes one exact input per
request outside transactions. The reserved `CandidateIndexEvent` is a contract only; no worker/default
queue is wired. Local unit results and canonical database results must be recorded
separately; the migration is not a quality or release gate by itself.

Initial preparation registers **only visually eligible page PNGs**, with explicit
dispositions for every source page. Registering all page images for the Viewer and
ordinary evidence routes remains an activation prerequisite. The service verifies
bounded exact object bytes before preparation and again after committing references.
If cleanup removed a file before registration, the second check reports failure;
restore identical bytes and resume. Sealing independently snapshots registered
assets under authority, verifies their exact bytes outside the transaction and
then performs a fresh DB seal fence, so vector completion alone cannot hide a
missing render. Matching hashes do not independently establish
transcription fidelity or a live model invocation.

Preparation freezes at most 4096 inputs, 500 source pages and 6000 UTF-8 bytes per
text input. Overflow fails before inference; no truncation or input dropout is
allowed. These are implementation budgets, not ratified quality/latency targets.
The concrete visual policy includes image originals, fewer than 32 stripped native
PDF text characters, at least two tables or figures, and partial/insufficient parse
pages. Whitespace-only chunks are recorded as such rather than sent as empty input.
Visual-policy recall remains a measured acceptance gate.

Single-vector writes use the immutable selected input plus compact run/header
summaries; they do not reload the whole parse/manifest for each checkpoint. Deep
projection and row-parity checks run at preparation/replay inspection and sealing.
The default full-artifact processing loader retains its prior behavior. Profile
catalog entries used by retained v2 configurations must remain immutable; changes
need a new version and migration policy, never silent profile substitution.

The first producer is the still-claimed parse job after parse seal and before ACK.
The bounded executor preserves the complete model response, verifies exact image
bytes and input/model hashes, and checks lightweight current authority immediately
before every request. Each returned response is validated and independently fenced
before checkpoint commit. It resumes persisted missing inputs only; complete
sealing precedes ACK, and a pending result requires bounded continuation. The caller
owns lease renewal and job lifecycle. Initial execution uses one text or image input
per request, a default 128-new-input budget (1–4096 allowed) and a 90-second timeout
(1–120 allowed). These limits are implementation settings, not ratified performance
targets. Results record actual execution settings; the frozen model-space contract
does not claim to persist a transport timeout.

The source adapter stages only exact eligible PNGs from the frozen original/parser
configuration; replay uses registered bytes without rerendering. Interrupted
staging cleans newly created unreferenced objects after DB contexts close, preserving
reused and referenced hashes. Process-kill orphan cleanup remains a maintenance gate.
Canonical independent-connection tests and an owned live Blackbird document/query
probe must still establish response persistence, cancellation during calls, actual
transport counts versus checkpoint reuse, and retrieval behavior. Declared model
mode and artifact identity are not independent live-invocation attestation.
Historical index inspection, independent
reindex authority, all-page evidence assets, accepted-fact/metadata revisions,
generation-aware readers and coherent selection/rollback remain required follow-on
work within the approved completion scope. They do not require another model-choice
approval, and this storage checkpoint does not complete X-05/X-07.

## Source requirements and current seams

The [root phase map](../../../STRUCTURA_IMPLEMENTATION_PLAN.md) keeps Phase 9
behind real retrieval/extraction acceptance. The [completion workstream](extraction-retrieval.md)
requires full-content indexing, exact parse/projection/model identity, resumable
backfill, coherent activation/rollback, and ACL-safe evidence. [ADR 0010](../../adr/0010-document-processing-authority.md)
requires additive storage and exact source-generation loading before ordinary
readers may see another structural generation. The
[filter-aware search addendum](../../../pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md)
also requires filtered-recall tests; putting a WHERE clause around an ANN query is
not sufficient evidence of filter-aware recall.

Relevant verified implementation boundaries:

| Boundary | Present behavior and consequence |
| --- | --- |
| [096 storage](../../../database/096_completion_document_processing.sql) | Sealed structure and immutable page checkpoints retain parse/page/element/chunk IDs in JSON. They are suitable immutable inputs; no new relational parse rows are needed for a hidden build. |
| [097 request authority](../../../database/097_completion_processing_request_authority.sql) and [authority repository](../../../lib/document_processing/authority_repository.py) | Live actor/member/document authority, token lifecycle, desired processing run and claim ownership must gate every new index mutation. A historical sealed artifact is readable evidence, not permission to execute. |
| [EmbeddingService](../../../lib/search/embedding_service.py), lines 68–102 | Refreshes mutable projection, calls models and persists vectors inside one DB transaction. Do not call this orchestration from the new lane. Reuse validated adapters below it. |
| [Embedding sources](../../../lib/search/embedding_repository.py), lines 37–138 | Read document-wide current chunks/pages/current image assets. Native candidate inputs must instead load the exact sealed artifact and generation-owned renders. |
| [Legacy projection](../../../database/069_phase5_search.sql), function `refresh_document_chunk_projection` | Mixes accepted facts and mutable document/filing metadata into chunk projection. A parse hash alone cannot identify this content. |
| [Model input hashing](../../../lib/model_runtime/embedding_identity.py) and [gateway validation](../../../lib/search/embeddings/validation.py) | Already bind exact input, purpose, profile/protocol, requested dimensions and artifact declaration. Preserve these checks and carry the resulting identity into immutable storage. |
| [Existing job event](../../../contracts/events/embed_document_job.v1.schema.json) | Document ID, optional profile and `force_reembed` do not identify an immutable input set. Add a distinct versioned candidate event/typed binding; do not reinterpret an old queued job as native work. |
| [2048-vector index](../../../database/076_phase8_5_visual_embedding_2048.sql) | Uses an explicit `halfvec(2048)` HNSW expression. Preserve native 2048 output/storage; do not assume a direct `vector(2048)` HNSW index or silently reduce dimensions. |

The unscoped consumers/writers are `automation/repository`,
`documents/{parse_debug,parse_repository,quality,read_model}`,
`extraction/source_repository`, `search/{embedding_repository,repository,visual_repository}`,
`semantic_annotations/{extraction_plan_repository,repository}`, and `previews/service`.
Therefore **no unselected native rows enter legacy `document_pages`,
`document_elements`, `document_tables`, `document_chunks`, `embeddings`, or
current-asset/projection tables in this slice**. Preserve their IDs and behavior.

## Bounded first implementation

Build an explicitly requested text/visual candidate from one sealed native parse,
using its still-desired creator processing run and a matching claimed job. Persist
all input definitions before embedding; checkpoint validated vectors; seal a
complete candidate; allow a protected exact-ID inspection/probe. No ordinary
search path, default profile, active pointer or canonical fact changes.

The first projection is `native_parse_only_v1`: every nonempty neutral chunk is
searchable model-transcribed content, with exact page/element IDs and text origins.
Do not append current canonical facts, mutable titles/filing metadata, or a current
Docling projection. Record `fact_basis=not_collected` and
`metadata_basis=not_collected`, with null revision references. These are explicit
limitations, not a fabricated empty fact set/revision zero. Such a build cannot
qualify for full product activation.

The accepted profiles are fixed:

| Property | Text | Visual |
| --- | --- | --- |
| Profile | `qwen3-embedding-4b-1536-blackbird:v2` | `qwen3-vl-embedding-2b-2048-blackbird:v2` |
| Model / expected served name | `Qwen/Qwen3-Embedding-4B` | `Qwen/Qwen3-VL-Embedding-2B` |
| Declared artifact revision | `5cf2132abc99cad020ac570b19d031efec650f2b` | `9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda` |
| API | OpenAI `/v1/embeddings` | OpenAI `/v1/embeddings` |
| Dimension policy | Request 1536 | Native 2048; no dimensions override |
| Input format | `qwen_text`: raw document passage; instructed query | `qwen_vl_messages`: image document input and compatible query messages |
| Identity policy / metric | `reported_model` / cosine | `reported_model` / cosine |

Freeze the full profiles/protocols from [profiles.py](../../../lib/model_runtime/profiles.py)
and [embedding_protocol.py](../../../lib/model_runtime/embedding_protocol.py), not
just these display strings. Include the query instruction, visual system
instruction, input-identity algorithm version, tokenizer/preprocessing versions,
dimensions, distance semantics and effective input limits. Profile changes require
a new build identity. Endpoint credentials are not persisted in the manifest.
Artifact revision in current adapter output is a frozen deployment declaration;
the model name is checked from the response. Neither proves a weight-file hash.

## Proposed additive persistence contract

The approved first migration uses the names below. The migration owner must review their constraints and
lock ordering before assignment. Payloads use versioned schemas and canonical
digests; SQL triggers enforce immutable ownership/content and permitted state
transitions. Every composite ownership reference includes the document and parse
generation; no foreign UUID is accepted merely because it exists elsewhere.

### 1. Index header: `document_index_generations`

Immutable identity: UUID, document/household, processing run, consumed parse
generation and sealed structure/inventory/config digests, controlled build slot,
monotonic slot generation, request key, requesting/producing job reference, full
profile bundle/config JSON and digest, requested modalities, projection and visual
eligibility policy versions, fact/metadata basis and optional revision/digests.
The request key is idempotent within the same run/slot; changing any input while
reusing it is a conflict. Source/profile authority never comes from job payload
strings alone.

State progresses `preparing → embedding → sealed`. Input-manifest content/digest
and expected counts become assigned once at the preparation seal. Completion
content/digest and timestamp are assigned once at the final seal. A separate
permanent `revoked_at` preserves the history of a sealed build when cancelled or
superseded. Do not overwrite vectors or turn a sealed build back into preparation.
Operational retries remain job lifecycle state; failures do not manufacture
successful index completion.

Serialize new builds on the document under the 097 prefix. Increment slot
generation, revoke previous authority in that slot, and atomically enqueue the
new work. Never choose the latest *unrevoked* number in a way that revives an older
build after a newer cancellation. Retain all slot numbers and revocations. The
fixed first slot covers this native candidate/profile bundle; future dual-profile
qualification must use explicitly distinct slots, not caller-invented bypasses.

### 2. Frozen input set: `document_index_inputs`

Each immutable row contains `(index_generation_id, input_id, ordinal, modality)`,
exact owner kind/UUID, parse page and element/chunk IDs, source-content digest,
complete exact text or render reference, source origin, profile-space digest,
`EmbeddingInput.sha256`, and `EmbeddingInputIdentity` including scheme and purpose.
Use generation-owned stable IDs derived from the index ID plus source occurrence
and any deterministic split range. Repeated identical text on different pages or
rows remains separate input occurrences; a text hash is not an owner identity.
Chunk/element IDs currently live inside sealed JSON and cannot acquire a normal
relational FK merely by naming that UUID. Exact loaders and the preparation seal
must verify their membership, text, origins and ranges against the hashed sealed
artifact. Page references can use the checkpoint's `(parse_generation_id,
page_number)` key with a checked page UUID; add a matching candidate-table unique
key if a composite page-ID FK is needed. Do not invent legacy relational rows to
obtain a convenient FK.

Store an ordered manifest containing the complete expected source/input IDs and
digests. Preparation may checkpoint rows in bounded transactions, but no inference
starts until the complete input set is sealed. Duplicate same-content inserts are
idempotent; conflicting content under an existing ID is rejected. Database
constraints prevent adding/removing/retargeting inputs after the manifest seal.
The seal independently recomputes the manifest from persisted rows and the sealed
parse/declared projection policy, rather than trusting caller-supplied counts.

Every source page has an immutable modality disposition in the manifest:
`eligible`, `ineligible` with explicit policy reason, or `not_requested`.
Preparation errors/resource limits are incomplete work, not `ineligible`.
This inventory includes pages with no chunks and partial/insufficient-signal
parses; lack of a typed extractor never removes general content from indexing.

### 3. Original render assets: `document_generation_render_assets`

Use a separate generation-owned asset registry: asset UUID; document, original
asset/hash, parse generation/page UUID/number; exact `SourceRender` identity;
renderer/config digest; encoded SHA-256, MIME, byte size, dimensions and protected
content-addressed object URI. A composite relation ties each visual input to its
same-document/same-generation render. Do not attach it through a legacy current
page asset or use a preview placeholder.

Load the exact registered original, verify its bytes/MIME/size/page inventory,
render at the frozen parse settings, and require equality with the checkpoint's
entire source identity before staging the PNG. Persist actual immutable PNG bytes
for subsequent index retries; reload and hash-check those bytes before inference.
This also avoids silently rerendering old sources with another compression or
renderer version. If the exact historical renderer cannot reproduce a missing
asset, fail explicitly; never swap in a current preview, relabel a hash or create
an unrecorded image transform.

Preparation lock order is the existing 097 actor/credential/document/run/source
prefix, then sorted content-hash advisory locks, then the index header and job
root/claim. Content locks cannot precede the document: duplicate ingestion already
holds a document FK before its content lock. Cleanup takes only the content lock
and plain reference reads. Its reference query includes retained candidate-render
URI/hash references and safely handles an installation not yet migrated through
098. Source reads remain outside transactions; postcommit verification distinguishes
registered metadata from presently available bytes.

Object writes happen outside DB transactions to private content-addressed storage,
then metadata/reference publication is fenced in a short transaction. A rejected
DB publication may leave an unreferenced staged object; bounded orphan cleanup
must distinguish these from referenced originals/history. No cleanup deletes a
shared blob still referenced by another retained asset. Public download/evidence
routes remain out of scope until they understand this registry and live ACLs.

### 4. Vector checkpoints: `document_index_vector_checkpoints`

Exactly one immutable checkpoint per `(index_generation_id, input_id)`, with a
composite FK to the frozen input and its modality/profile. Store vector dimensions,
full-precision vector, canonical vector-content digest, expected model input
identity, response-reported model/version, declared artifact/protocol identity,
invocation/attempt reference, measured latency and creation time. Record whether
the result was freshly invoked or explicitly reused, with its source checkpoint
reference; never count a cache replay as a new live call.

Validate count/index order, exact model/input identities, dimension, numeric type,
finite values and nonzero magnitude through the existing adapters before storage.
Define the persisted digest over canonical float32 values (the pgvector storage
representation), with an explicit byte order/version and range checks; avoid a
float64 JSON hash that does not describe what PostgreSQL retained. Preserve the
actual full vector even if a later visual ANN index casts it to halfvec.

Same-identity/same-vector inserts replay; a conflicting vector under a completed
input cannot overwrite history. Retry reads completed rows before calling a model.
Initially reuse only this build's checkpoints. Cross-build cache reuse is a later
explicit copy operation requiring full input-space/source equality, live access,
and retained invocation origin; it may not collapse different source occurrences.

No HNSW or BM25 activation is necessary for this hidden persistence slice. A
protected exact-generation diagnostic may use exhaustive distance over this small
candidate. Later native retrieval indexes live on these isolated generation-owned
tables with reviewed text1536/visual2048 expressions, rather than borrowing legacy
index names that happen to contain the right dimensions.

### 5. Typed job/build relation

Add an immutable typed relation between an index producer job and its index header,
including the existing run/parse/document binding. A candidate event carries only
the corresponding IDs and safe execution controls. Every load/write checks this
relation as well as claim token and run authority. Queued profile hints cannot
override the frozen header, and unbound legacy jobs cannot acquire a current build
by looking up the document.

For the first in-process probe, the already-claimed parse job may produce its
bound candidate index after sealing the parse and before ACK. For a separate
worker, enqueue an index child while the parser/orchestrator still owns its claim,
then finish the parent so the child can run. Never keep the parent running while
waiting for a child that requires parent success. Use one bounded index worker
with resumable batches initially; fan-out/fan-in needs an explicit dependency
contract and is not implied by queue-terminal counts.

## Projection and input policy

Text projection must preserve all nonempty neutral chunks and their source IDs.
If a passage exceeds the accepted tokenizer/input budget, split deterministically
with exact source character ranges and a frozen tokenizer/artifact revision; do
not truncate or silently drop it. Until that splitter is implemented, reject an
oversized candidate as incomplete instead of recording zero eligible inputs.
Do not assume the current 3000-character chunk limit universally proves an
8192-token limit. Empty/whitespace chunk decisions are recorded separately.

Visual inputs use the exact page PNG and an initially empty descriptor. This
avoids importing mutable title/family/filename text into the image identity.
Future image-plus-text descriptors require a separate frozen projection policy.
Build `native_visual_eligibility_v1` as a pure, versioned projection over source
inventory and sealed parse outcomes. It may reuse the current quality rule
thresholds, but must distinguish native text availability from Qwen transcription,
leave unavailable OCR/handwriting signals unknown, and record every decision.
Image sources, missing/low native text, relevant layout/figure complexity and
partial/insufficient-signal pages must be represented in its tests. Current
mutable `document_pages.metadata_json.phase8` is not an input. This policy requires
source-quality review before production activation; the first hidden test is not
evidence that all useful visual pages have been selected.

A genuinely empty eligible set can seal only after the full source inventory and
per-page policy decisions prove it. Report zero denominators explicitly and make
zero model calls. `visual disabled/not requested`, `eligible but asset missing`,
`failed rendering`, `all deferred`, and `model unavailable` are not successful
zero-eligibility cases. Sealed partial parse content can yield a complete index of
that parse, while source text omissions/review state remain visible; index
completeness must not be reported as parser completeness or quality acceptance.

## Fact and metadata revision strategy before activation

Add real immutable `document_search_projection_revisions` in a later reviewed
publisher slice, with independent monotonic fact and metadata revisions maintained
under the document lock. Snapshot selected canonical field/line-item IDs and
history/evidence references, accepted status and typed values; snapshot the
metadata actually used for lexical text/filter/facet projection. Store versioned
serialization and content hashes. Timestamps, a parse ID, a maximum candidate ID,
or arbitrary `run_id` text cannot substitute for these revisions.
Derive accepted-value filters from those exact selected canonical values, including
explicit clearing when the last accepted value is rejected. Do not copy existing
document date/counterparty/amount rollups as authoritative: current correction and
rollup paths have independent refresh/clearing gaps. Reconciliation and tests must
prove the snapshot matches canonical state before its revision can be selected.

All canonical acceptance/correction/rejection/promotion and document metadata,
filing/rule, quality, relationship/deadline updates that affect search must bump
their applicable revision in the same mutation transaction. Inventory these
writers before enabling a revision-dependent publisher. Source transcript chunks
and accepted-fact passages should remain separate source types, so a correction
does not require retranscribing or re-embedding every unchanged parse chunk.
Human corrections retain their old evidence/history; new parsing never relabels
them as confirmed by the new parse.

ACLs are always checked live. An immutable projection is never a cached grant.
For other filters, choose and expose one coherent selected metadata/fact snapshot;
do not combine an old ranked accepted-value passage with a newer unlabelled facet
value. A correction committed during index inference prevents selection of the
stale fact projection. Compatible immutable transcript vectors may later be reused
into a newly complete projection with explicit lineage. A canonical rejection or
correction must invalidate stale accepted-fact passages/filters in its own commit;
waiting for background embedding must not leave the rejected value labelled as
accepted in search. The later publisher needs an explicit freshness policy: retain
compatible parse-only retrieval, expose current canonical/filter state, exclude
stale fact-vector units before ranking, and report pending fact-index coverage
until replacement vectors are ready. This partial-coverage behavior and its UI
contract must be implemented and tested before activation. The previous coherent
parse publication can remain while a reparse builds, but its fact revision never
overrides a newer human action.

A superseded parse's creator run cannot authorize an independent later reindex.
The first implementation deliberately supports only its still-desired 096 run.
Historical backfill/reindex/rollback preparation needs a separately admitted
durable index request carrying 097-equivalent origin/actor/resource authority and
an exact immutable source reference. Do not revive/decrement processing authority,
forge a new parse creator, or guess origin for legacy work to bridge that gap.

## Transaction and retry sequence

1. **Admit/snapshot:** acquire 097 household→actor→membership→credential→document→
   folder/ACL locks, then exact run/parse and candidate header. Validate current
   desired run, sealed structure/config hashes, source ownership and build slot.
   Prelock every FK/domain reference before job-root/job ownership locks. Freeze
   the snapshot/header or resume the exact existing request. Close the transaction.
2. **Prepare outside the transaction:** verify bounded source bytes, derive the
   full input manifest, tokenize/split as supported, reproduce/stage exact page
   renders. Recheck admission between bounded source/model operations. Persist
   input/render checkpoints through short transactions with the same lock prefix,
   fresh post-lock authority and claim checks. Seal preparation after independent
   completeness/hash validation. No model request happens against a partial set.
3. **Infer outside the transaction:** load a bounded set of missing inputs from
   the frozen manifest; verify private asset bytes and actual selected adapter
   identity. Immediately before every HTTP call check run/build authority. Text
   batches have a configured count/token/byte budget; visual calls contain one
   image each. Renew the job lease independently. Finite admission waits, timeouts
   and retries remain observable; query traffic has protected capacity.
4. **Checkpoint:** validate returned input order, identity and values; in a short
   transaction reacquire the complete prefix, verify this still-desired build and
   any captured projection revisions, insert-or-verify vectors, then fence the
   exact claimed job before commit. Revocation during HTTP can finish that call,
   but cannot publish it or admit another. Do not hold a lock across inference.
5. **Seal/ACK:** compare persisted inputs and vector rows by exact IDs/digests,
   require one valid vector for every eligible input and none for other rows,
   verify assets and full modality dispositions, and assign completion once under
   the same authority fence. ACK only after commit. A crash after checkpoint/seal
   resumes without additional completed-input calls. A lost ACK never causes a
   content-replacing force-reembed.

Job-only claim/heartbeat/cancellation/recovery retain their existing root/job lock
order and acquire no new domain locks afterward. Index cancellation/supersession
uses the domain prefix and irreversible header revocation; old valid job tokens
do not restore publication rights. Domain writes that already hold locks must
enter this agreed prefix before index/job locks, not acquire it in reverse. Test
FK acquisition as well as explicit SQL locks, including repeated child enqueue.

## Acceptance and follow-on activation

The bounded implementation is ready for integration only with these checks:

- Real PostgreSQL separate-connection races supersede the processing run and index
  slot independently while the old token remains live; no stale input/render/vector
  row or seal survives. Repeat with job reclaim/cancellation, actor disability,
  membership/ACL loss and token revocation/expiry. Browser logout follows 097's
  admitted durable-request lifetime, not a newly invented cancellation rule.
- Kill after source staging, after a vector batch, after seal and before ACK;
  replay resumes only missing work. Missing/corrupt assets and conflicting
  checkpoint payloads fail; original/historical evidence remains intact.
- Forged cross-document/parse/build/input IDs, changed profile/protocol/artifact,
  query-purpose vector persistence, fixture relabelled live, wrong response index,
  NaN/zero/dimension mismatch and float32-range failures are rejected.
- Repeated identical text/page occurrences retain separate IDs. Full source-page
  and chunk inventories reconcile; zero eligibility makes zero calls; missing
  eligibility/assets/over-budget inputs cannot disappear from denominators.
- Change title/facts/filing while building: the initial parse-only candidate does
  not claim to have indexed them; a later revision-enabled publisher rejects a
  stale snapshot. Human correction and rollback races are mandatory before that
  publisher is accepted.
- Persisted vectors and frozen inputs rehash/replay under real PostgreSQL. Native
  hidden rows do not change ordinary search results, current assets, canonical
  data, legacy vector activation, review tasks or any of the unscoped readers.
- An owned live probe runs text1536 and visual2048 document inputs on Blackbird,
  compatible real query embeddings, and exact-generation retrieval/scoring with
  declared source labels. Report actual calls, per-modality counts, queue/service
  time and fixture/live provenance. No threshold or quality pass is inferred from
  vectors merely being nonzero or from endpoint health.

The initial executor uses one text input or one image per call;
exact batch/token/concurrency/p95/soak limits require a recorded development
baseline and ratification before release measurement. Existing stated semantic
median <500 ms and hybrid median <1 second targets remain contextual operational
targets. No new quality or performance threshold is ratified by this design.

Follow-on work remains separate: complete fact/metadata revisions and independent
index-request authority; generation-aware ordinary readers and evidence DTOs;
native BM25/vector indexes; atomic parse/claims/index publication; per-document
and corpus profile migration; progress/degraded status; stable pagination,
grouping/facets/query-history and ACL-before-ranking/limit/filter-recall tests;
judged lexical/semantic/visual/hybrid comparisons and combined Oxcart-ingest plus
Blackbird-index/query contention; audited rollback preserving newer corrections.
Activation selects a coherent retained publication, never mutates historical
objects or revives jobs. Those gates, not this candidate storage, close X-05/X-07.

Suggested implementation ownership: `lib/search/indexing/` for immutable index
domain/DTO, pure input projection, repository, source-asset adapter and bounded
service; existing `lib/model_runtime/` and `lib/search/embeddings/` for wire
adapters/identity validation; shared jobs/processing owners for typed binding and
authority; integrator for migration assignment and later publisher/reader cutover.
Keep workers thin and tests organized along these boundaries.
