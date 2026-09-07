# Canonical line-item review: next bounded design

Root-approved implementation scope for migration 103. Implementation and canonical
validation are in progress; release acceptance remains open. See the concrete
[target contract](canonical-line-item-target-contract.md) for the active API rules.

## Confirmed baseline gaps addressed by this slice

- `lib/review/candidate_decision_repository.py:69` changes only a candidate's status,
  records a review event with description and float-converted net amount, and closes
  tasks by a type/ordinal path. It never creates a canonical line or fact history.
  Its comment that no canonical line-item type exists conflicts with the table in
  `database/025_baseline_identity_acl_candidate_rules.sql:234`.
- That table already retains typed amounts, source/evidence, selected candidate,
  accepting actor, timestamps and unique `(document_id,line_item_type,ordinal)`.
  `canonical_fact_history.canonical_line_item_id` already exists. There is no
  production INSERT/UPDATE writer for canonical line items in apps/lib/workers.
- Migration 088 added allowed and plan-paid only to candidates. The accepted
  canonical table lacks both; the public candidate DTO also omits both. EOB claim
  projection maps billed→gross, allowed→allowed, plan-paid→plan_paid and patient
  responsibility→net in `lib/extraction/claim_candidates.py:194`.
- Candidate ordinal is local to an extraction/group; region and aggregate rows
  can share type/ordinal. `candidate_group` is generic family text, not a stable
  cross-generation line identity. Do not silently equate every ordinal-one proposal.
- Current task closure uses `line_items.<type>.<ordinal>` and can close other
  candidates' tasks at the same ordinal. It needs an exact lineItemCandidateId seam.

## Proposed first slice

Accept/reject existing line-item proposals into truthful canonical rows, exact
money/evidence history, a coherent review envelope and the common transaction.
Preserve existing human/manual lines and physical ordinal identities. No automatic
line promotion, inferred cross-generation alignment, total recomputation from sums,
line-item correction editor, active index switch or manual metadata activation.

Split line decisions into focused repositories/service; retain observation behavior
in the existing candidate repository. The new endpoint uses the shared explicit
live request credential prefix and fresh post-wait/pre-commit checks. This extends
the new synchronous line decision boundary to session revocation and expiry; it
does not silently retrofit 101 callers or change durable 097 browser-job lifetime.

### Identity is an explicit admission condition

Preserve existing canonical slots `(document,type,ordinal)` and row UUIDs. A review
must carry exact candidate ID/version and exact intended canonical target. Existing
selected rows need their canonical timestamp and independent decision revision.
A candidate's extraction-local ordinal is provenance, not sufficient authority to
replace an occupied slot.

The server proposes an exact vacant slot for an unassigned eligible source, and
the client adopts it only through the explicit Add action. An existing line is
replaced only through an explicit target selection. Region/group collisions never
infer replacement, deduplication or region-to-aggregate equivalence. The client
does not calculate max+1; the frozen target contract below defines create/replace.

Rejecting a selected candidate withdraws that exact selected line only after current
canonical/decision preconditions. Rejecting another unselected proposal is a
candidate rejection, not permission to delete a different accepted line at the same
ordinal. It retains a full immutable decision snapshot/event and resolves only that
candidate's tasks. Canonical rejection retains the row plus a durable rejected slot
decision; no fake value is created for an unselected rejection. New proposals remain
reviewable, and no automatic line promotion is enabled by this slice.

### Additive schema needs (allocated migration 103)

1. Add nullable `allowed_amount` and `plan_paid_amount numeric(18,4)` to canonical
   lines; never fill absent amounts with zero or infer a currency.
2. Add document-owned canonical line decisions keyed by the existing exact slot,
   with revision UUID, confirmed/rejected/protected_legacy disposition, nullable
   actor, exact canonical/candidate/review-event references and explicit decision
   time. Copy the full selected typed/evidence snapshot into immutable event/history
   records. Source candidate/extraction/group/ordinal remain recorded even if FKs
   are later cleared; actor deletion must not remove human authority.
3. Enforce document/type/ordinal composite bindings, monotonic revision timestamps
   and retained decisions. Use deferred document-owned FK checks so whole-document
   cascade succeeds while illegal individual rebinding/deletion fails. Rejection
   and protected_legacy cannot become selected accepted lines because of a stale
   legacy `review_status` alone.
4. Backfill only demonstrated current canonical human binding. Existing `accepted`
   candidate status is not permission to synthesize canonical facts: old events
   preserve only a subset of values and may not establish current full-row evidence.
   Preserve/reveal those earlier decisions as legacy review history requiring an
   explicit current publication decision. Ambiguous old type/ordinal rejections
   cannot be guessed into a different region/group slot or erase a current line.
5. Version the expanded fact basis explicitly. 101 hashes `accepted_fields.v1`.
   An added projection basis discriminator permits `accepted_fields_and_lines.v1`
   only after both selectors and writers are coordinated. Reconciliation changes
   the digest/revision once, not an unlabelled reinterpretation of the old hash.
   Native indexes remain `fact_basis=not_collected` pending their complete capture.

### Public contract and transaction

Use a dedicated line-item DTO module, disjoint from field and upload schemas.
Expose exact decimal strings for quantity/prices/all amounts, candidate and canonical
versions, scope/group/source identity, every concrete evidence ref, and the selected
line decision. Keep nulls and currency explicit; EOB labels must identify gross as
billed and net as patient responsibility. The review surface must display the exact
values it asks the user to accept, including allowed and plan-paid.

Provide a versioned canonical-line envelope: actual rows, decisions and projection
basis/revision. A missing envelope does not prove an empty decision set. Requests
carry independent candidate version UUID, canonical timestamp, decision revisions and
an explicit target; omit/null/current semantics are documented and enforced.
Return safe409 on stale or contradictory identity and retain the client draft.
Do not silently accept field-only revision arguments on line-item actions.

One repository transaction performs request authority → document → exact candidate/
canonical/decision locks and rechecks → selected line mutation → full precision
history/event → exact candidate task closure → selected-line lexical projection +
versioned field/line digest → job fence/enqueue. Failed projection/enqueue rolls back
all changes. Source model/evidence provenance remains truthful; accepting a model
candidate establishes human selection without relabeling its text as native source.

Do not sum accepted lines into invoice/EOB totals or overwrite manual totals in this
slice. Existing 101 scalar/total ownership remains separate. The line refresh only
extends the accepted fact basis and lexical input, preserving original rows/history.

## Required isolated tests

- Accept a visible typed line: exact canonical row, complete money/evidence and
  actor history, matching response revision, lexical inclusion, one queued job.
- Zero/negative/max four-place amounts, full bigint identities, unknown currency,
  absent allowed/paid values and EOB billed/allowed/paid/patient labels survive
  round-trip. No float rounding or default USD.
- Reject selected line: preserve its data/history, durable rejected selection,
  immediate lexical exclusion and one atomic projection transition. Reject an
  unrelated same-ordinal proposal: selected line and other candidates/tasks remain.
- Explicit replace requires loaded target revision. Two-connection accept/accept,
  accept/reject and human-corrected-existing-line/rerun conflicts yield one winner,
  fresh authority checks and no hidden overwrite. Test deleted accepting actor.
- Region/aggregate same-ordinal and duplicate description/amount fixtures cannot
  silently collide; explicit different vacant targets preserve both source refs.
- Revocation during blocked review denies with no effects; projection/enqueue
  failures roll back canonical/decision/history/task/projection/job writes.
- Candidate/extraction deletion retains canonical value, source snapshot and human
  decision; whole-document cascade and illegal individual rebinding are checked.
- Upgrade preserves real existing canonical rows, human corrections and ambiguous
  historical candidate decisions without publishing guessed accepted facts.
- Browser tests show complete precise values, exact create/replace intent, source
  evidence, stale409 recovery and selected/rejected/historical status after reload.
