# Native model-emission claim import

Status: root-approved bounded X-05 implementation under migration 106. The
implementation is registered and awaiting canonical PostgreSQL validation;
local synthetic checks do not close model-quality or production-capacity gates. This follows [combined page understanding](native-page-understanding.md),
the [frozen v2 contract](native-page-v2-field-coverage.md), [105 claim currency](native-claim-currency.md)
and [ADR 0010](../../adr/0010-document-processing-authority.md). It activates no
public candidate, canonical fact, classification, parse or index selection.

## Result and existing constraints

Import every typed claim from an exact persisted v2 page response, together with
its classification and page-local obligation ledger. Retained diagnostic rebuilds
then consume immutable claim/page records rather than reparsing provider output.
The structural transcription, model-proposed typed interpretation, application
diagnostics and human decisions remain separate products.

The existing foundation is useful but cannot simply accept another derivation:

- [105](../../../database/105_completion_native_claim_currency.sql:66) permits only
  `native_structure`, fixes the method and payload version, and its content/retention
  triggers explicitly recognize only that origin. All must change together.
- [NativeClaim](../../../lib/extraction/native_claims/models.py:98) requires typed
  values to equal deterministic recorded-text normalization. Its scalar source
  identity omits cell column and occurrence span. Preserve that historical v2 model;
  do not widen its validator or silently change retained IDs.
- [089](../../../database/089_phase8_5_claim_currency.sql:35) lacks `time` and
  `identifiers`; [105 page records](../../../database/105_completion_native_claim_currency.sql:36)
  cap claims at 1,000, versus v2's explicit 3,000. Model-emission support must be
  branch-specific, without silently widening legacy/structure-normalization input.
- [Page persistence](../../../lib/extraction/native_claims/page_repository.py:19)
  accepts caller-supplied anchored key requests. The new service instead accepts
  only a bound set and page number; callers supply no values, JSON pointers,
  classification, coverage or reported model identity.
- [Retained reads](../../../lib/extraction/native_claims/read_repository.py:97)
  already separate current reader ACL from producer lifetime. Keep this behavior.

## Service and source contract

Add `NativeModelEmissionService` with `start(processing)`,
`checkpoint(binding, page_number)`, `seal(binding)` and
`rebuild(binding, *, credential: RequestCredential)`. The service chooses an
installed, frozen import/review policy, loading definition files before opening a
transaction; arbitrary caller definition hashes are not an override. The initial
writer requires a still-desired, sealed v2 parse and a
matching claimed producer job under 097. A completed producer is not implicitly
revived; a future orchestrator must admit the bound import child before finishing
its parent. This package adds no automatic enqueue or worker activation.

For admission and each page write:

1. Reuse the 097 actor/household/membership/credential/document/folder prefix, then
   run/generation and immutable original/checkpoint FK locks, followed by the
   claim-set/page locks. Source queries remain document/run/generation scoped.
2. Load `raw_output`, `page_json`, `invocation_json`, checkpoint digest and exact
   original/render/configuration from persisted 096 records. Recompute the existing
   `{page, invocation, raw}` checkpoint digest without changing its encoding.
3. Require explicit v2 configuration/invocation, frozen supported definitions and
   their request/source/context binding. Call the parser lane's `validate_checkpoint`
   and shared raw dispatcher; never relabel v1 as model-emitted typed output.
4. Decode persisted raw with the frozen v2 decoder. Derive each
   `/extraction/claims/N` and canonical member hash from that original parsed member,
   not from a normalized DTO dump. Derive classification and coverage-member hashes
   from the same validated raw. No pointer/value supplied by the caller is trusted.
5. Map element index to the exact normalized page element, table by element ID,
   cell by its starting row/column, and structural container through the retained
   parent hierarchy. Validate exact quote/span, row membership and normalized
   source-pixel box; include every primary and supporting locator. Copy source
   engine/profile/model/request ID and raster hash from actual persisted provenance.
6. Insert-or-verify the complete page record and all claims atomically. Recheck
   current 097 authority and job ownership/lease using database time before commit.
   Acquire no new domain/FK locks after the job-root fence. Any conflict, expiry,
   supersession or revocation rolls back the whole page.

No model, network or filesystem IO occurs in these transactions. Initially follow
105's bounded per-page transaction pattern; explicit 2-second lock/5-second SQL
timeouts do not by themselves bound Python decoding time. The current model HTTP
transport caps the entire OpenAI envelope at **1 MiB**, below capture's 2,000,000-character
bound and the pure decoder's 16-MiB JSON bound. None is a measured dense-page token
budget. The page trigger parses retained raw once and validates its immutable
`source_members_json` cache; claim inserts check exact members in that cache. Measure
the 3,000-claim SQL/TOAST workload, Python validation and whole-source manifest loading
before claiming G2 scale. Those upper-bound workloads remain explicitly unqualified.
If preparation moves outside the transaction later, final persistence must derive
or independently verify all payloads against the locked exact raw source; a prepared
object carrying a valid raw hash is not sufficient provenance on its own.

Browser-origin admitted jobs continue after logout/reset as ADR 0010 specifies.
API-token-origin work retains captured scope ceiling, current scopes and token
lifetime. Disabled actor, lost membership/access or revoked/obsolete run denies
writes. Retained reads require current reader credentials and read ACL, even after
producer completion/reparse; they do not require the old producer credential.

Append/seal resolve the installed importer bytes before database locks and require
the stored full configuration fingerprint to match. They cannot resume a building
set under a different implementation. Retained reads have a separate explicit
`raw-member-import-v1`/schema/review/definition dispatch: they preserve the original
implementation hash as provenance but require no current installed factory, file
hash equality, model or network call. Future semantic changes must add historical
version support instead of rewriting these retained validators in place.

## Immutable models, identity and interpretation

Use separate `NativeModelEmissionConfiguration` (`native_model_emission_configuration.v1`),
`NativeModelClaim` (`native_model_claim.v1`), source/anchor and page-record DTOs in
new modules. Leave 105 `NativeClaim`, `NativePageRequest`, exact typing and their
hashes unchanged. New configuration records actual output/schema/taxonomy/registry/
typing/validation hashes plus importer, locator-mapping, diagnostic and review-policy
versions/hashes. New configuration, payload, physical-identity and completion hashes
use v2 `canonical_digest` (sorted compact UTF-8 JSON, `ensure_ascii=False`,
`allow_nan=False`). Existing 096 checkpoint and 105 source-manifest hashes keep their
original `content_digest` encoding. Do not swap the two for Unicode-containing data.

Reuse `native_claim_sets`, with distinct deterministic set UUID from parse generation
and the complete new configuration fingerprint. The source manifest remains the
locked original/configuration/ordered checkpoint/invocation inventory. Each new
claim stores the exact proposed value and raw quote, member index/pointer/hash,
raw-output/checkpoint/configuration hashes, actual invocation identity, primary and
support anchors, and uncalibrated model score separately from trusted confidence.
Retain the parsed original `raw_member_json` inside the immutable native payload as
well as the typed projection. Rebuild can verify its canonical member digest and
typed projection without decoding the provider envelope; reserializing a coerced
DTO is not a replacement for the originally hashed member.

Scalar `physical_source_id` hashes generation/page plus element, optional table/cell,
cell row/column and exact text start/end. A line instead uses generation/page plus
the real table-row or disjoint structural-container identity. Its `group_id` is that
row identity. `claim_id` hashes set, physical source and canonical key, independent
of typed value and response ordering. Set-local uniqueness prevents a changed value
from becoming a second logical claim. Derive the physical SQL row UUID deterministically
from set and claim ID, and preserve it on replay. Member index is source provenance,
never physical row identity. Reordering raw within one immutable checkpoint conflicts;
a genuinely different response requires a new generation.

Retain exact decimal strings, local times, identifier lists and leading zeros from
the frozen proposed-value DTO. Do not apply `type_recorded_text` to model-emitted
values or coerce them through float. Ambiguous dates/currency retain both the proposed
value and quote plus application-generated interpretation diagnostics. A missing
currency stays missing; a code inferred from `$` is review-required, never verified.
Addresses/party identifiers retain source-text proposals, not guessed normalized
objects. All rows require review; pixel support, arithmetic validation and document
required-key evaluation remain `not_evaluated`. Model inventory completeness is not
accuracy, coverage against originals, or canonical acceptance.

## Migration 106

The additive [migration 106](../../../database/106_completion_native_model_emission.sql)
implements these coordinated changes:

1. Add immutable `native_claim_sets.interpretation_kind`, defaulting existing rows
   to their already-established `structure_normalization` branch. Permit only that
   and `model_emission`; validate exact configuration version/derivation per branch.
   No legacy extraction or v1 page is backfilled into model-emission provenance.
2. Extend `extraction_claim_origin_branch` with `native_model_emission`, null legacy
   extraction/semantic-region IDs, method `model_emission:v1`, actual Qwen source
   engine and null trusted confidence. Require the new payload version, review-only
   markers and equality of every indexed identity/value/anchor to its payload.
3. Add nullable `native_member_index` and `native_member_sha256`. They must be null
   in existing branches and non-null/range-valid in the new branch. Require payload
   pointer exactly `/extraction/claims/` plus the index, and matching member digest.
   Add partial unique `(native_claim_set_id,native_page_number,native_member_index)`
   for model emission, alongside existing set/claim-ID uniqueness.
4. Keep page classification, complete coverage, unsupported fields, original member
   hashes, bound evidence and index→claim-ID mapping in versioned `request_json` as
   `native_model_claim_page.v1`. Require matching header branch. Add page-level
   `source_checkpoint_sha256` for model emission, null for the old branch, with a
   deferred composite FK to the exact 096 generation/page/content digest (add its
   referenced unique constraint). Payload also includes exact raw-output digest.
   The immutable `source_members_json` page cache is NULL for old pages and equals
   the exact raw extraction claims for new pages. Page admission checks cached
   members, classification and coverage against one parsed persisted envelope; each
   inserted claim must equal its cached raw member at the recorded index.
5. Replace the page-count CHECK with explicit upper bound 3,000 plus trigger-enforced
   old-branch bound 1,000. Seal requires every expected page, exact actual row/member
   counts, one mapping per emitted member, no missing/extra claims, and matching page
   content hashes. Zero-claim unsupported/partial/blank pages are still checkpoints.
6. Extend the value-type CHECK so `time`/`identifiers` are allowed only for the new
   origin; all existing branch types remain unchanged. Extend native insert/update,
   sealed-content and retention triggers for both native origins, including origin
   conversion rejection. Header identity cannot switch branches after creation.
7. Retain the existing composite document/set/page constraints. Cross-reference
   checks needed during whole-document deletion remain deferred; individual
   checkpoint/set/claim/run deletion remains prohibited while its document exists.

Use named constraints and tests against an actual 105 baseline, not assumptions
about autogenerated CHECK names. No new current pointer, accepted selector, public
DTO or mutation of `field_candidates`, `line_item_candidates`, canonical tables,
human authority/history, document metadata or index tables belongs to this migration.

## Accounting, audit and reconstruction

Persist classification and the complete page ledger even for zero-claim pages.
Retain exact raw classification/coverage member hashes and separately bound source
locators; translate claim indices to stored claim IDs without dropping the original
index mapping. Every valid emitted member must have one immutable row. Low confidence,
unsupported optional fields or ambiguous interpretations do not filter rows. An
invalid supposedly v2 response is a contract failure, not an empty successful import.

Seal builds a versioned completion digest over ordered page records and stored claim
hashes. It reports known/mixed/ambiguous/unknown classifications, page dispositions,
per-field reported states, unsupported content and explicit omissions without a
document-level winner or inferred absence. It does not average scores. The durable
set/page/claim records, producer/run/origin and configuration are the import audit;
create no fake human-review event. Rebuild verifies these hashes and uses only
persisted typed rows and retained page records for interpretation. It may validate
immutable source manifests/hashes, but must not decode raw to recreate claims.
Retained validation independently rebinds every primary/support locator and
classification/coverage source reference. It builds only a validation view of the
sealed normalized structure and runs the frozen full cross-member obligation,
physical-row, classification and claim-index accounting rules. Recomputed payload
hashes cannot hide an omitted obligation or an equal-text locator moved to another cell.

## Ownership and acceptance

New package: `lib/extraction/native_claims/model_emission/` with `models.py`,
`configuration.py`, `source_repository.py`, `anchors.py`, `import_page.py`,
`page_repository.py`, `projection.py` and `service.py`. Each owns its named layer;
the pure importer derives typed payloads, while the repository owns SQL. Keep
services thin. Prefer a small shared version dispatcher
and header/page lifecycle coordinator at existing 105 boundaries over duplicating
authority/retention logic or growing its DTO module. Existing normalization and
legacy writer paths remain behavior-preserving, independently tested branches.
Narrow shared edits: `native_claims/{authority_repository,set_repository,service}.py`
plus new `record_types.py` and `transactions.py`. The old service retains its
`_transaction` compatibility import; source/read/retained authority stays reused
without edits. Retain old
`models.py`, `normalization.py`, `values.py` and `page_repository.py` semantics.
The assigned SQL file and focused test directories are the remaining write scope.

The parser lane owns `raw_output.py`, invocation/configuration types and binding,
checkpoint validation, structural normalization and the current 105 source-reader
adaptation. Wait for its committed checkpoint, then coordinate only narrow shared
source/header/read dispatch edits. Its confirmed mapping stays element index →
normalized element, table by element, cell by row/column. Frozen v2's 22 files stay
untouched. Root allocated 106 and owns its registry and integration; no API/main/
OpenAPI or runtime change is needed for this package.

Add focused pure tests and a new `tests/integration/native_model_emission/` suite:

- Exact v2 member imports, scalar repeated spans/cells, equal physical lines,
  continuation identity, every value type, four distinct EOB money roles, ambiguous
  currency/date diagnostics and injected prose retained as data.
- Wrong original/page/config/invocation/raw/member/quote/support locator fails;
  caller overrides are impossible through service input. Same-key changed content,
  duplicate/missing member mappings and frozen-definition mismatch roll back.
- Explicit zero-target, unsupported, partial and mixed/ambiguous page ledgers seal
  truthfully; missing pages/claims cannot seal. All 109 obligations remain accounted.
- Two connections prove supersession, cancellation, token expiry/revocation,
  actor/membership loss and refile while waiting reject the whole page/seal; admitted
  browser logout continues. Replay concurrency produces one set/page/physical row ID.
- After producer success and later reparse, rebuild is identical with the raw decoder
  made unavailable. Current revoked/foreign reader fails. Claimed job retry cannot
  revive an obsolete set; wrong producer/root ownership fails without partial rows.
- Representative 105 upgrade preserves old payload hashes/IDs and unchanged old
  value limits. Test all native origin conversions, individual deletion rejection,
  cross-document FK failures and populated whole-document cascade with retained
  101/103 human histories. Assert zero candidate/canonical/current/index writes.

Canonical PostgreSQL validation runs only from root's committed source. Synthetic
cases establish contracts and concurrency, not live transcription quality. Typed
candidate/review publication and accepted-fact integration remain the next distinct
package after this immutable currency is verified.
