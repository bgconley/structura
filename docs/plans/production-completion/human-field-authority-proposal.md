# Durable human decisions and fact projections

Status: root-approved design; migration 099 is reserved exclusively for this work.
The first bounded slice contains additive schema, immutable DTOs and transaction
protocols for review. Existing writers and public response activation are a later
integration slice; these foundations alone do not close the preservation gates.

The current revision-guard repair protects existing human-controlled canonical
fields during correction, confirmation and rejection. This follow-on closes the
remaining G1/X-02/X-05 gaps: rejection before any canonical value exists, manual
classification/date preservation, and stale derived rollups. It does not activate
native generations or introduce Phase 10 account-management features.

## Durable field decisions

Add a document-owned `canonical_field_decisions` table keyed by
`(document_id, field_path, ordinal)`. Store an independent revision UUID, disposition
(`confirmed`, `corrected`, `rejected`, or migration-only `protected_legacy`), decision timestamp, nullable deciding user,
and the exact review event/canonical field references where available. The human
decision survives deletion of its actor and candidate/extraction supersession.
Keep the existing immutable review events and canonical fact history.

Rejection with no canonical value creates a decision, not an accepted fact with a
fabricated value. Automatic promotion checks this state under the document lock;
any human disposition prevents silent replacement. New model candidates remain
reviewable. A later explicit human confirmation/correction may replace a rejection.

Expose decision identity/revision alongside the canonical-field review response,
including decisions without canonical rows. Add `expectedDecisionRevision` to
field mutation requests, with explicit null meaning no decision existed. Continue
checking `expectedUpdatedAt` for the displayed canonical row. Missing decision
revision may make a first decision only; it cannot bypass an existing tombstone.
Public activation requires additive shared-contract and client changes in the same
writer integration checkpoint. This foundation deliberately does not accept a new
public request field that the existing writers would silently ignore.

Write decision, canonical change, audit/history, scoped task closure and projection
revision in one transaction. Immutable decision history is the review event stream;
the decision table is its current selection, not a replacement for history.

Backfill only human authority established by existing row markers or exact review
history. Do not invent a reviewer or accepted value. Legacy path-wide rejections
need explicit migration handling because old requests did not carry an ordinal:
report and protect those ambiguous paths from automatic promotion until a precise
current decision is established; do not silently choose ordinal one as their history.
`canonical_field_path_guards` retains that distinct path-wide authority. A precise
human replacement acknowledges the active guard revision but does not clear the
guard for other ordinals. `protected_legacy` protects a current human-marked row
whose status does not establish acceptance; neither state is an accepted fact.

## Manual classification and document date

Add a cohesive `document_metadata_decisions` table keyed by document and property
(`classification`, `document_date`), with revision, nullable actor, decision time,
exact audit-event reference and a versioned, validated value. Classification keeps
family and subtype together. A manual date clear is an explicit null decision;
it must not fall through to a model-derived date.

Classifiers, semantic reconciliation and automatic filing respect the decision
after acquiring the document lock. They may retain conflicting proposals and
diagnostics but cannot replace selected manual metadata. An explicitly requested
human replacement uses its current revision; no implicit reset of human authority.

Record provenance for derived metadata separately from the manual override. Migrate
only demonstrated current bindings. An old reclassification event must not restore
its historical family over a different current value of uncertain origin. Preserve
unknown legacy values as `unestablished` provenance for resolution rather than
calling them human-accepted or silently deleting/relabeling them. The classification
browse predicate should consume this state once available.

## Derived rollups and transaction boundary

Create one repository-owned accepted-fact projection refresh used by all canonical
decision and automatic-promotion transactions. It deterministically derives
counterparty, date and total from accepted canonical rows, honoring manual metadata
decisions. Rejection of the last contributing accepted value clears the corresponding
*owned derived* projection; remove the current COALESCE fallback and conditional
total deletion that retain rejected values. Preserve unrelated/manual amount rows.

Update rollups, lexical projection and a monotonic accepted-fact/projection revision
in the same transaction as the source decision. Enqueue dependent work transactionally;
do not leave a successful review followed by a separate failed refresh/enqueue.
The native index builder must bind this revision plus the exact indexed metadata
snapshot before full-product activation. Its initial parse-only candidate remains
independent and explicitly excludes these facts/metadata.

Preserve the established lock prefix: request/actor authority, document, decision
and canonical rows, domain projections, then job lineage fence/enqueue. No model
request runs inside the transaction. Automatic legacy writers must acquire the
same document serialization before reading human decisions.

## Required isolated database regressions

- Reject before/after first promotion; retry and conflicting rerun retain rejection,
  candidates and history. Explicit current-revision human replacement succeeds.
- First rejection races automatic promotion in both commit orders; stale decision
  revision cannot confirm/correct over an unseen rejection without a canonical row.
- Manual classification/date/explicit date-clear survive classifier, semantic and
  extraction reruns, including inference paused before the human commit.
- Correct/reject the sole contributing merchant/date/amount; inspect rollups and
  search filters immediately and after an unrelated rerun. Unrelated manual values
  and other ordinals remain unchanged.
- Refresh/enqueue failure rolls back the whole review transaction; concurrent
  projection/index capture observes one coherent revision, never a mixed snapshot.
- Upgrade fixtures include deleted reviewers, exact known overrides, ambiguous
  path-wide rejection and contradictory historical classification. No guessed
  historical restoration or promotion of rejected canonical data is permitted.

## First bounded foundation and integration contract

Migration `099_completion_human_fact_authority.sql` adds the four authority/projection
tables and conservative backfills. Independent decision UUIDs are server-generated;
an update changes the revision and advances `recorded_at`. Actor/canonical/event FK
cleanup only clears the reference, preserving authority and its revision. Composite
canonical/event references are deferred to support all document-owned cascades;
schema tests force those checks before rollback. Deleting a live document's authority
record directly is rejected. Document deletion may cascade through the full set.

`lib/fact_authority/models.py` contains frozen snapshots and revision expectations.
`preconditions.py` checks each independent revision and excludes rejected/unknown
authority from accepted selection even when an old canonical status says accepted.
`transaction.py` declares the repository transaction boundary for the next slice;
it has no DB adapter or production caller. Its policy checks do not authenticate a
request or acquire a lock. Current legacy writers remain unchanged in this checkpoint.

The writer checkpoint must activate these DTO changes together:

| Surface | Contract |
| --- | --- |
| Canonical-field list | Retain `items` as actual canonical rows; add `authorityVersion: "human_authority.v1"`, `decisions`, `pathGuards` and projection state. A rejection before promotion returns an empty `items` array with a populated decision. |
| Confirm/correct/reject requests | Retain `expectedUpdatedAt`; add `expectedDecisionRevision` and `expectedPathGuardRevision`. Each field independently distinguishes omission, explicit null and a current timestamp/UUID. Missing/explicit-null authority revisions cannot replace an existing decision or active path guard. |
| Successful field mutation | Return the new decision revision and canonical row/timestamp if one exists. Do not fabricate a canonical row for rejection. Existing correction POST still returns a real canonical row; its additive authority field carries the revision. |
| Manual classification/date | Return the selected metadata decision, including `manual_metadata.v1`, its property/value and revision; accept `expectedMetadataRevision` for the targeted property. First explicit null asserts no manual override, while a later change must acknowledge the current revision. |
| Revision conflict | Return safe HTTP 409; reload exact canonical/decision/path state before retry. A matching canonical timestamp cannot substitute for a decision UUID, or vice versa. |

Old clients retain first-decision behavior only when no durable decision or active
path guard exists. New clients must detect `authorityVersion` before using the new
contract; the old API's missing envelope means unavailable authority information,
not an empty set of tombstones. The existing request model's `model_fields_set`
must preserve omission versus explicit null. These changes belong in canonical/
review sections of Python/OpenAPI/JSON Schema/TypeScript, disjoint from upload DTOs.

Projection revision zero remains `unestablished`; its verified fact revision and
hashes are unavailable, rather than a claim that an empty fact set was verified.
First reconciliation establishes a deterministic accepted-fact digest and revision
one. Subsequent accepted-fact digest changes require exactly one fact-revision
increment. Metadata-only changes retain that fact revision and advance projection
revision. The digest binds selected canonical identity/path/ordinal, typed value,
currency, evidence, selected candidate, acceptance status and exact decision revision;
rejected/unknown decisions and unreviewed proposals are excluded. Indexed metadata
has its own versioned digest. Clock values are generated after locking and must be
strictly later than the previous recorded value, even if clock resolution is coarse.

Rollup ownership is explicit in the versioned projection snapshot. A manual date,
including null, wins. Only an established derived counterparty/date/amount may be
cleared when its last accepted contributor disappears. Unknown legacy document
metadata stays preserved and labelled unestablished until explicitly resolved;
matching a new model value does not establish prior ownership. Existing amount rows
whose metadata explicitly identifies Phase 4 canonical ownership may be reconciled;
other amount rows remain separate. No arbitrary `MAX(currency)` may pair one fact's
amount with another fact's currency.

## Next writer slice and repository boundaries

Before adding authority persistence to the 507-line `action_repository.py`, extract
canonical value/selection/history persistence into a focused canonical review
repository, and document workflow actions into a separate workflow repository.
Keep the existing facade names during the behavior-preserving extraction. The new
authority repository owns current decisions and lock-protected precondition reads;
the projection repository owns selected fact snapshots, rollups, lexical refresh
and transactional job enqueue. Services orchestrate a single transaction instead
of calling another committing service after a successful review.

| Existing writer | Required integration |
| --- | --- |
| `lib/review/action_repository.py` confirm/correct/reject | Fresh decision/canonical checks after document lock; one decision/history/task/projection transaction. Reject without a canonical row creates only the decision. |
| `lib/extraction/canonical_repository.py` promotion and rollups | Consult exact decision plus path guard; preserve existing human markers; delegate rollups to the common projection repository. |
| `lib/extraction/extraction_repository.py` classification/reconciliation persistence | Preserve manual classification and date, use current accepted selection, refresh projections inside the existing publication transaction. |
| `lib/semantic_annotations/semantic_family.py` classification application | Retain model proposals without replacing manual classification; apply the same serialization. |
| `lib/organization/document_organization.py` / `repository.py` | Record explicit date edits and null clears even when equal to the current derived value; persist audit, authority and projection/enqueue together. |
| `lib/automation/action_application.py` document type | Respect established manual metadata. A rule action remains automation and does not acquire human override authority merely because a user accepted a filing suggestion. |
| `lib/search/projection.py` / `embedding_repository.py` | Replace independent committing refresh paths with the shared transaction-aware projection refresh; lexical facts use the same rejection/authority filter as rollups. |
| `lib/review/audit_repository.py` | Keep document review status as workflow state; never infer classification authority from that status. Retain scoped ordinal closure and immutable fact history. |

All candidate/native publishers must later call this same accepted-selection seam.
The initial 098 hidden parse-only index does not bind or claim these facts. No current
index activation, human line-item promotion, phase advancement or full closure is
implied by the additive schema, domain policy tests or transaction port declarations.
