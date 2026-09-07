# Line-item authority: concrete target and migration supplement

Root-approved target contract for migration 103, supplementing the
[line-item authority design](canonical-line-item-authority.md). Implementation and
canonical validation are in progress.

## Public endpoints and discriminated requests

Add `GET /api/v1/documents/{documentId}/canonical-line-items` with
`authorityVersion: line_item_authority.v1`, actual canonical `items`, slot `decisions`,
source-assignment summaries, and projection/basis revision. Retain the existing
line-item-candidates GET; extend its items with exact decimal strings for all amount
and quantity fields, `candidateVersion`, `sourceSnapshotSha256`, source extraction/
group/ordinal, `candidateDecisionRevision`, and explicit publication eligibility.
The two GETs use document read serialization so each envelope is coherent.

Add `POST /api/v1/documents/{documentId}/line-item-decisions`. A strict discriminated
union rejects unknown keys and keys belonging to another operation. UUIDs, hashes
and all expectation fields below are required; explicit null asserts absence.
No omitted-revision compatibility path is needed on this new endpoint.

```typescript
type Source = {
  candidateId: UUID;
  expectedCandidateVersion: UUID;
  expectedSourceSnapshotSha256: SHA256;
  expectedCandidateDecisionRevision: UUID | null;
};
type Slot = { lineItemType: LineItemType; ordinal: PositiveInt32 };
type Vacant = Slot & {
  canonicalLineItemId: null;
  expectedCanonicalUpdatedAt: null;
  expectedLineDecisionRevision: null;
};
type Existing = Slot & {
  canonicalLineItemId: UUID;
  expectedCanonicalUpdatedAt: RFC3339WithOffset;
  expectedLineDecisionRevision: UUID | null;
};
type LineDecision =
  | { operation: "create"; source: Source; target: Vacant; comment?: string }
  | { operation: "replace"; source: Source; target: Existing; comment?: string }
  | { operation: "reject_selected"; target: Existing; comment?: string }
  | { operation: "reject_candidate"; source: Source; comment?: string };
```

The route document UUID is authoritative; no second document UUID is accepted in
these bodies. `lineItemType` must equal both the source candidate type and target
row type where applicable. The request cannot change a canonical row's type/ordinal.
Server assigns the new canonical UUID for create; it never silently chooses a
position. The UI displays a suggested vacant position but submits it only as the
user's explicit create target. If a region/aggregate collision makes that suggestion
ambiguous, show target selection. Replace is labelled “Replace line N” with the
currently selected value visible; generic “Accept” cannot silently mean replacement.
No automatic append, ordinal renumbering, amount-based dedupe or group alignment.

- **Create:** no canonical row and no retained slot decision may exist at the target.
  An occupied/rejected/protected slot requires explicit replace with its loaded UUID
  and independent revisions. Different source and target ordinals are allowed only
  through this explicit target selection; preserve the source ordinal in provenance.
- **Replace:** exact canonical UUID/document/type/ordinal and timestamp must match.
  Compare slot decision and candidate decision revisions independently. Preserve the
  canonical UUID/position, record the prior complete value in history, then select
  the source snapshot. A human-corrected or protected legacy row is never exempt.
- **Reject selected:** no source argument, because its candidate/extraction may have
  been deleted or superseded. Exact target/revisions withdraw this selected fact;
  retain its value/evidence/history and a rejected slot decision. Current candidate
  eligibility is irrelevant to withdrawal. If a live selected candidate exists,
  update its decision/status in the same transaction after source locks are held.
- **Reject candidate:** candidate identity/version/snapshot and its decision revision
  must match, but current-extraction eligibility is unnecessary. If it is currently
  selected by any canonical row, return409 requiring `reject_selected`; never bypass
  canonical revision checks. Otherwise preserve a full candidate decision/event and
  leave all canonical rows/slot decisions unchanged. An old accepted-but-unselected
  candidate is not a selected fact merely because that historical decision remains.

Success returns `operation`, review event ID, current candidate decision if relevant,
canonical row or null, slot decision or null, and projection/basis revision. Conflicts
return safe409; missing/inaccessible resources404; malformed identity/value/evidence422.
Old `review-actions` accept_line_item/reject_line_item must not remain an unchecked
alternative: at activation they return a safe409 directing clients to reload the
versioned line-item workflow. New UI uses the dedicated endpoint. Observation actions
are unchanged. No field-only revision argument is silently accepted on line actions.

## Source lifetime and eligibility

The source fingerprint is `line_item_source.v1`: document/candidate/extraction IDs,
source engine, extraction schema/model/prompt/scope, semantic annotation/region IDs,
source group/ordinal, complete typed values with exact decimals/currency, evidence,
validation and stable original-asset/page binding. Exclude mutable workflow status,
last-used timestamps and candidate decision revisions from this content hash.
`candidateVersion` changes on every material candidate update, including status;
content changes after a persisted source assignment are prohibited (create a new
candidate instead). Candidate identity/document/extraction binding cannot be retargeted.

Publication requires, after locks: enabled/current request authority; undeleted
document; candidate exists in that document with matching version and source hash;
non-null same-document extraction that is `completed` and `is_current`; complete
concrete evidence resolving to that document's original/page; finite typed values
within storage precision; and no unresolved legacy assignment conflict. For semantic
region/aggregate sources, the referenced annotation must also be same-document,
`succeeded` and current, and region membership must match where applicable. A merely
current region extraction from a superseded annotation is insufficient.

`proposed`, `needs_review`, and legacy `accepted` candidates may be explicitly
published after these checks. A rejected candidate additionally requires its current
rejection revision, so the action explicitly reverses that decision. A previously
published candidate may only be selected again in its original canonical slot;
its current source must still be eligible. Historical/orphaned/failed/superseded
sources remain readable with an ineligible reason and can be rejected as proposals;
they cannot be newly published through this endpoint. Existing selected canonical
values remain readable and rejectable regardless of source lifetime.

An admitted newer parse that has not superseded the published extraction does not
by itself revoke a human review of the still-published source. Once supersession
commits, stale source publication fails. No accepted-line deletion or value reversal
occurs merely because a model extraction becomes historical. Source snapshots and
original/page bindings survive candidate/extraction FK cleanup; exact historical
parse-asset resolution remains coordinated with the retained-evidence work, not
claimed by a copied transient element UUID alone.

## Exact additive SQL plan

1. Add `allowed_amount` and `plan_paid_amount numeric(18,4)` to canonical lines,
   nullable with no inference/backfill of financial values. Add `decision_version
   uuid NOT NULL DEFAULT gen_random_uuid()` to line-item candidates. A BEFORE UPDATE
   trigger owns version refresh on material changes (excluding updated_at/version),
   prohibits identity retargeting, and prohibits bound source-content mutation while
   still allowing workflow status changes. This avoids timestamp ABA/clock ordering.

2. Add unique referenced identities `(id,document_id)` on candidates and
   `(id,document_id,line_item_type,ordinal)` on canonical lines. Add a same-document
   candidate/extraction FK, with nullable extraction preserving legitimate orphan
   history. Any legacy cross-document source binding is reported and publication-
   ineligible; do not invent provenance while validating the upgrade.

3. `line_item_candidate_decisions`: UUID primary key, unique
   `(document_id,source_candidate_id)`, immutable non-null historical source UUID,
   nullable live candidate FK, independent unique revision UUID, disposition
   accepted/rejected/protected_legacy, origin, exact source snapshot/hash, nullable
   actor/review-event FKs, decided_at, recorded_at. Live candidate FK is composite
   `(candidate_id,document_id)` with SET NULL(candidate_id), deferred; CHECK live
   candidate ID is null or equals historical source UUID. The historical UUID and
   document never change. Live decisions require a time; update advances revision
   and recorded_at. Cleanup only clears refs, retaining decision and snapshot.

4. `canonical_line_item_decisions`: UUID primary key, unique
   `(document_id,line_item_type,ordinal)`, unique revision UUID, disposition
   confirmed/corrected/rejected/protected_legacy, origin, non-null exact canonical
   UUID and nullable actor/event FKs, decided_at and recorded_at. Composite canonical reference
   includes document/type/ordinal and is deferred. Review creates confirmed/rejected;
   corrected can preserve a demonstrated legacy human-corrected row. Row identity
   is immutable; retained decision revision changes on an explicit decision, not
   actor/candidate FK cleanup. Deletion while its document exists is prohibited.

5. `canonical_line_item_source_bindings` enforces one source candidate → one slot
   **for the lifetime of that document**, including after replacement/rejection.
   Primary key `(document_id,source_candidate_id)` uses the immutable historical UUID.
   Store nullable live candidate FK, binding_state assigned/legacy_conflict, exact
   canonical UUID/type/ordinal for assigned rows, full immutable source snapshot/hash
   (or explicitly tagged legacy snapshot), and recorded_at. Assigned state requires
   a non-null target; legacy_conflict has no chosen target and records all conflicting
   legacy target UUIDs. Composite target FK is deferred/document-owned. Bindings are
   immutable except FK cleanup; deletion is permitted only on document cascade.

   Add UNIQUE(document_id,source_candidate_id,canonical_line_item_id) on bindings,
   then a deferred FK from canonical `(document_id,selected_candidate_id,id)` to
   that triple. Add it NOT VALID to avoid rewriting unresolved historical links;
   it still enforces every new/changed selected-candidate key. The service's source
   binding INSERT and canonical selection occur atomically with the deferred check.
   A candidate raced into two different slots has only one binding winner. A replay
   cannot silently move its binding or create a second row. NULL selected_candidate
   after source deletion skips the live FK while the historical binding remains.

6. Backfill slot decisions from current canonical human markers using 099's policy:
   source_kind human, user_confirmed/user_corrected, or retained accepting actor.
   Rejected status wins; other nonaccepted statuses become protected_legacy;
   accepted statuses become corrected/confirmed as established by those markers.
   Build assigned source bindings only for one existing target per source UUID;
   duplicate legacy target links produce one legacy_conflict binding, not a guessed
   winner. Orphan/history snapshots are labelled legacy, never certified original
   evidence. Old candidate acceptance events do not synthesize canonical rows or
   claim that omitted allowed/paid values were reviewed.

7. Add `selected_canonical_line_items`: accepted row status AND (exact confirmed/
   corrected slot decision referencing that row OR no slot decision). This preserves
   previously selected system/validator legacy rows under their existing policy;
   it does not call them human accepted. Human-marker nonaccepted rows have protected
   decisions and stay excluded. Rejected/protected decisions override stale accepted
   status. A protected legacy row enters selection only through explicit replacement
   with exact canonical and decision revisions; it is never lifted by status alone.

8. Add explicit `accepted_fact_basis_schema_version` to projection state, initially
   `accepted_fields.v1` without altering old hashes. The common refresh becomes
   field+selected-line aware and records `accepted_fields_and_lines.v1` on its next
   transaction, advancing the fact revision when the versioned digest changes. Every
   field/line/automatic refresh must preserve this expanded basis thereafter; no
   writer may downgrade it. Lexical uses both selected views. Do not derive document
   totals by summing lines. Native indexes remain `fact_basis=not_collected` until
   their separately approved complete capture/activation.

All new document-owned reference checks are deferred to support full document
cascade. Retention triggers distinguish whole-document deletion from individual
line/decision/source-binding destruction; direct reassignment and reference cleanup
need separate tests. The NOT VALID legacy FK and conflict bindings are explicit
migration debt, not claims that every historical source assignment was verified.

## Publication lock order and real races

Use live credential prefix → document FOR UPDATE → semantic annotation (if any) →
extraction → candidate → target canonical/decision/source-binding rows → projection
→ job root/fence/enqueue. Missing target/binding rows are protected by the document
lock and unique constraints. Fresh eligibility/version queries run after all source
locks, not predicates that PostgreSQL evaluated before waiting.

Prerequisite: move the document lock to the start of
`persist_semantic_manifest_with_cursor` (its current `_validate_document_refs` only
reads). It currently supersedes annotations/extractions before family application
locks the document. That inverse order must be corrected for both standalone and
service callers before enabling document→annotation review locking. Existing
`_persist_extraction_rows` already locks document before extraction supersession.
No model call is inside these transactions; legacy reconciliation advisory locks
are not acquired by review. New publication keeps all source locks through commit.

Required two-connection proofs: supersession wins→accept409/no effects; review wins→
supersession waits and accepted line survives; semantic supersession/document review
has no inversion; same candidate/different vacant slots→one assignment; different
candidates/same vacant slot→one canonical winner; stale replace/reject→409; unselected
same-ordinal rejection leaves selected line/tasks intact; deleted source and actor
preserve authority; rollback after enqueue removes every staged effect. Upgrade tests
cover duplicate legacy links, protected human rows, cross-document/orphan candidates,
whole-document cascade, and failure of illegal live rebinding/deletion.

## Session lifetime follow-on (not a 101 expansion)

Observed: `AuthPrincipal` carries session_id, but `DocumentAccessContext` does not.
101 rechecks actor/membership/token/document under locks, while cookie-session
revocation/expiry is checked during initial HTTP authentication, before the review
transaction. A logout/replacement after that check can therefore precede a waiting
101 mutation's commit. Existing docs promise expiry on reads/writes but do not define
this in-flight boundary; ADR0010's logout-surviving policy applies to already-admitted
background ingestion, not an HTTP mutation still awaiting admission. Do not describe
101 as fencing browser session revocation at publication.

Recommend an explicit request-admission policy: credential must still be live at the
last authorization check inside the short publishing transaction. Logout/replacement
that wins the session lock causes denial; a mutation that wins holds session SHARE
through commit and logout waits. Absolute expiry is freshly checked after all waits/
fences immediately before commit. Already-admitted browser jobs retain ADR0010's
lifetime and never acquire a continued-session requirement.

Extract a shared immutable request credential identity from real AuthPrincipal
(session UUID or token UUID + captured scopes; no raw secret). Shared auth repository
functions acquire household→user→membership→session/token before domain locks and
perform a fresh credential/disabled/member/scope check after waits; session must match
actor/household and be unrevoked/unexpired/CSRF-bound. Current and captured token scopes
both apply; no credential omission or fallback to a system actor. Routes still own
Origin/CSRF validation. This is suitable for the new line endpoint and mandatory for
upload-attempt acceptance after byte IO. Stage bytes outside DB locks, then recheck
that same originating credential before document/attempt/run commit; revoke/replace/
expire during IO leaves no admitted attempt. Extend existing synchronous mutation
callers as a separate explicit SEC01 follow-on, with logout/reset/replacement races;
do not silently change 101 or durable background lifetime in this migration.

## Reviewed consumer and history refinements

Each candidate read provides a server-computed `suggestedVacantTarget`, adopted only
by the explicit Add action, and a `sourceAssignment` with its lifetime original slot
and current selection state. The client never calculates max+1 or infers replacement.
A retained slot decision always references a real, retained canonical UUID (NOT NULL).
Unselected rejection creates a candidate decision and history only. Rejected/protected
canonical slots restore through explicit replace with the actual row revisions.

`GET /api/v1/documents/{documentId}/line-item-history` takes exactly one of
`canonicalLineItemId` or `sourceCandidateId`, plus an opaque cursor and bounded limit.
It returns immutable complete before/after value, evidence and source snapshots for
new decisions, and explicitly labels partial legacy history. A deleted actor has a
truthful fallback label. It never fabricates full history from current summaries.

## Implemented review boundary and remaining acceptance

Migration 103 and the scoped writer/read modules implement this contract; canonical
SQL and browser acceptance are still pending the root's committed-source gate.
The schema retains a `decision_event_id` independently from generic review-event
cleanup, so deleting a source candidate or generic review event does not erase the
exact last selected source. It never guesses from several old bindings to one slot.
Source provenance reads/locks are document-scoped even for tolerated legacy bad FKs.
The candidate/extraction FK, canonical/candidate FK and reverse source-binding FK
remain NOT VALID for preserved historical conflicts. Their presence is not a claim
that legacy records have been repaired or fully validated.

Line-domain evidence admission now checks locator existence against recorded
page/element text and actual table dimensions. Known spans must be nonempty and
within their identified text. A sole sourceText locator must uniquely occur in the
identified recorded page. Chunk/raw/unspecified spans without an independent valid
box, element, table row or unique text match are incomplete; the DTO has no immutable
chunk/raw artifact identity. Boxes use the existing normalized page-relative
[x0,y0,x1,y1] contract and must be ordered and nonempty. Missing dimensions, ambiguous
text and inconsistent locator combinations stay visible with `evidence_incomplete`
and cannot publish. This is recorded-locator completeness, not independent native
text validation or proof of source pixels; source engines retain their actual names.
Historical rows and their known evidence remain readable, with partial legacy source
history explicitly marked. The shared EvidenceRef contract is unchanged.

Current candidate collection reads remain unpaginated and perform per-source and
per-evidence queries under a document SHARE lock. They preserve complete DTOs but
have no long-document scalability acceptance. Read entrypoints cap each statement
at 5 seconds, each lock wait at 2 seconds, and stop issuing queries after a 20-second
application budget (an already running final statement can consume its remaining
5-second statement limit). G2 must measure and replace these reads with batched
queries/server pagination before claiming capacity or long-document performance.
The native index `fact_basis` remains `not_collected`; no native activation occurs.
