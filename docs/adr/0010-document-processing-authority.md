# ADR 0010: Document processing authority and immutable parse generations

Date: 2026-09-07

## Decision and implementation boundary

Accepted implementation design for X-02/JOB-02, following ADR 0009. Migration
096 and `lib/document_processing` introduce additive processing authority and
candidate checkpoint storage. They do not activate Qwen parsing, expose multiple
generations in the existing structural tables, or replace the current pipeline.
The selected parser remains Qwen3.8-27B on Oxcart; Blackbird embeddings serve
ingestion and query-time retrieval. No runtime change is implied by this ADR.

Four identities have different responsibilities: a job claim owns an execution
attempt; a processing run owns an authorized document request; a parse generation
owns one interpretation of exact original bytes under fixed configuration; a
publication selects the coherent parse/extraction snapshot shown to users.
Existing corpus `run_id` strings are reporting metadata, not execution authority.

## Additive authority and candidate storage

A document has a monotonic processing generation and desired-run pointer.
`document_processing_runs` records immutable request identity, original asset/hash,
creator, parser configuration, parse generation and root job. Retrying the same
request key returns that request without reviving a superseded run. A new request
increments the document counter and revokes the old run transactionally with its
audit record and root enqueue. Cancellation revokes authority permanently; retry
of a queue attempt cannot clear run revocation or retarget its source.

`document_parse_generations` binds the creator run, original bytes and full parser,
model, prompt, schema, normalizer, chunker and renderer configuration. Inventory
is assigned once. `document_parse_page_checkpoints` stores exact page/render,
raw output, normalized structure, invocation provenance and content hashes.
Successful checkpoints are insert-or-verify, never content-replacing upserts.
Stable UUIDs must not conceal changed model segmentation or transcription.

Deferred pages keep a generation unsealed. Continue resumes the same run and
generation from immutable checkpoints. Coverage and candidate work can be exposed
through future protected read models; the previous publication remains selected.
Seal once after every page has a terminal processing outcome and the assembled
artifact matches its inventory/checkpoints/chunks. Sealing is not activation or
proof of extraction usefulness. Partial/insufficient signal remain honest quality
outcomes; operational failures and deferred work cannot become a complete parse.
After sealing, any changed interpretation requires a new generation. No mutable
partial active artifact is introduced by this slice.

New job columns carry typed run/generation IDs and inherit their parent's exact
binding. Null bindings remain an explicit transitional allowance for the existing
pipeline. No historical or queued job is assigned a guessed current generation.
No base-table uniqueness constraint is dropped in 096. Candidate structures stay
in isolated checkpoint/final JSON storage until all consumers are migrated.

## Lock order and publication authority

External rendering, object staging and inference happen without open database
transactions. Migration 097 adds the same actor/resource lock prefix to request
admission, candidate persistence and bound child enqueue: household key-share,
user share, membership share, credential share where lifecycle applies, document
update, primary folder share and relevant existing ACL-row share, then run and
generation locks. User/credential share locks prevent non-key revocation updates;
key-share alone would not. New reads after waits check live authority.
Any job foreign-key references are prelocked before the existing job-root advisory
lock. Job roots are locked in UUID order, followed by job rows. Fresh checks after
the locks verify desired run, exact source/generation, ancestry and the live claim
using database `clock_timestamp()`. The checks and candidate publication commit
belong to the same transaction.

Claim, heartbeat, recovery and job-only cancellation do not acquire domain locks
after root/job locks. They may inspect run authority without locking domain rows;
this is an early rejection, not a substitute for the locked publication fence.
Run supersession does not need to mutate job rows to remove their authority.
Unfinished obsolete queue records can later be retired by the run-aware lifecycle
coordinator; they cannot be claimed or publish once their binding is revoked.
This separation also permits tests where the old job still has a live token.

Processing-run creation is an authorized request operation, not an implicit worker
child rebind. Workers inherit fixed bindings. Future fan-in must use explicit
assembly dependencies: an orchestration parent cannot wait for children that are
only runnable after that parent succeeds.

## Authenticated origin and durable-request lifetime

Migration 097 records an immutable explicit browser-session or API-token origin,
actor, household, `documents:write` capability and token scope ceiling. Admission
accepts an authenticated principal, validates its credential against locked live
rows, and captures the actual token scopes. Idempotency cannot move a request to
another credential. Unknown pre-097 origin stays `legacy_unestablished`: it cannot
execute, claim, renew, retry or publish, and its existing artifacts remain retained.
No implicit operator/system authority or credential backfill is introduced.

Browser session validity is an **admission requirement**. An admitted durable
ingestion request continues after logout, session expiry/deletion or password
reset. Its ongoing authority is the enabled actor's live household membership,
current document write grant and desired run. Explicit run revocation, disability,
membership loss/downgrade or loss of document access prevents further source/model
access and publication. This is deliberate background-request lifetime, not an
unimplemented session-revocation check.

API-token-origin work additionally requires the same existing, unrevoked,
unexpired token, matching actor/household, and write capability under both its
captured scope ceiling and current scopes. Token reset/revocation/expiry therefore
blocks remaining token-origin work. Browser origin IDs remain audit references;
credential retention does not prevent their deletion, and no browser session is
silently substituted for a missing API token.

The native parser's source/model admission checks and checkpoint/inventory/seal
transactions consume this boundary. Publication locks prevent a concurrent
privilege removal from committing between the fresh authority check and commit.
No locks span rendering or inference: revocation during a request cannot recall
an already transmitted page, but rejects its checkpoint and all subsequent calls.
Current ACLs are positive grants only; locking existing grants covers their removal
or reduction, and the folder lock covers folder-policy changes. A future explicit
deny/ACL management implementation must serialize policy changes on the folder
row; nonexistent deny rows cannot be protected by row locks on today's grants.

This is bounded candidate-run authority, not legacy-worker origin migration,
watched-folder/system-origin admission, revoked-run cleanup or current-generation
activation. These remain separate lifecycle and consumer-migration work.

## Staged consumer migration and activation

Before multiple structural generations become visible:

1. Retain the existing pages/elements/tables/chunks and their UUIDs, add generation
   ownership and composite reference constraints, and replace document-wide
   uniqueness with generation-scoped uniqueness in a later assigned migration.
   Backfill only established bindings; previously destroyed IDs or unknown legacy
   lineage cannot be reconstructed by assigning the newest parse.
2. Replace destructive parse persistence and preview page upserts. Source renders
   are immutable assets bound to original bytes and renderer identity. Equal object
   bytes may share storage, but must not overwrite provenance. Quality and search
   projections remain separately versioned interpretations of immutable structure.
3. Require exact parse/run source loaders for semantic planning, extraction,
   reconciliation, claims, quality and embeddings. Historical readers resolve exact
   IDs; ordinary reads select a publication explicitly. Never fall back to current
   pages for missing historical locators. Version evidence DTO/UI contracts with
   parse/page/render identity, coordinate basis and native/model origin.
4. Stage run-specific candidates/artifacts/review state; atomically select the
   coherent parse/extraction publication. Preserve accepted human corrections and
   their original evidence. Retire superseded generation-specific review tasks.
   Review rerun intent, authority update and enqueue become one transaction.
5. Bind indexing to exact parse plus actual projection/fact revision. Filter the
   selected generation before lexical/vector ranking and limits. Split embedding
   snapshot loading, inference and fenced persistence. Preserve the independent
   1536/2048 model/index contracts and measure both ingestion and query inference.
6. Drain legacy unbound processing jobs before cutover; run mixed-history and
   Docling-free gates before removing temporary converter dependencies. Rollback
   makes a new audited selection of retained output, never decrements authority or
   resurrects jobs, and preserves later human corrections/compatible indexes.

The initial library has no current-publication writer, rerun API integration or
legacy structural reader migration. Those are explicit follow-up work, not claims
that JOB-02/X-02 is complete. The root-owned neutral parser stays candidate-only.

## Acceptance

Meaningful isolated PostgreSQL tests independently supersede a run while its job
token stays live; reject old checkpoint/inventory/seal/child writes; serialize
concurrent request creation; preserve exact retries and reject conflicting page
content; verify seal-once, cancelled runs, wrong original/config/generation,
cross-document binding, and rollback of provisional writes after lost authority.
Existing unbound job behavior remains covered. No model service is required to
test database authority.

Full closure additionally requires every consumer/publication boundary's separate
run-supersession race, historical evidence after reparse, interrupted continuation,
correction during activation/rollback, pre-ranking current selection, clean and
representative-upgrade migrations, and selected live-model capacity/quality gates.
