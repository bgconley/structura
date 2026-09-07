# Native claim currency: bounded foundation

Status: root-approved X-05 implementation slice; migration 105 is reserved for this
foundation. This implements the [completion workstream](extraction-retrieval.md)
under [ADR 0009](../../adr/0009-qwen-native-document-parsing.md) and
[ADR 0010](../../adr/0010-document-processing-authority.md). Phase 8.5 still gates
Phase 9. Schema/model validity is not source support or release acceptance.

## Scope and authority

Persist native derived claims immutably in `extraction_claims`, and rebuild pure
diagnostic projections from a sealed persisted claim set. Original bytes, sealed
parse structure, page checkpoints and actual invocation records remain separate
retained evidence. No API route, model call, candidate/review-task publication,
canonical mutation, current parse/index selection, default activation or legacy
backfill belongs to this slice. Historical Docling/Granite rows and their existing
writer/read behavior remain intact. No synthetic extraction record is created to
make a native claim look like a legacy extraction.

All native values remain derived, require human review and report pixel support as
`not_evaluated`. Matching Qwen transcription proves only that a quote exists in
that derived transcription; it does not independently verify the original. The
current structural page-output contract contains no explicit fact-claim member.
An adapter must therefore distinguish deterministic normalization of recorded
structure from future explicit model-emitted claims; a caller cannot manufacture
Qwen extraction provenance by attaching an arbitrary value to a real page.

This version enables only `structure_normalization`: the library copies an exact
recorded element/cell span and applies approved deterministic typing. The frozen
normalizer, family registry and explicit anchored key mapping are application
interpretation provenance, separate from Qwen's transcription invocation.
`model_emission` remains reserved and fails closed until a separate version binds
typed members and support locators to the exact persisted combined raw response.

## Persistence branch and header

`native_claim_sets` owns one immutable interpretation of an exact sealed parse
generation under frozen normalizer/registry/review-policy configuration. Identity
includes document, household, processing run, parse generation, producer job,
configuration hash, original identity and the ordered checkpoint/input/invocation
manifest. The source manifest is constructed from locked persisted records, never
trusted caller metadata. Configuration changes require a distinct set identity.

The `extraction_claims` legacy branch retains a non-null `extraction_id` and no
native ownership. The native branch requires a set/page binding, versioned strict
payload and content hash, and has a null `extraction_id`. An explicit CHECK makes
the branches mutually exclusive. Native composite foreign keys enforce one
document/run/parse/page scope; unrelated legacy foreign-key debt is not declared
repaired. Native INSERT-or-verify never invokes the legacy conflict UPDATE path.

Each expected source page receives an immutable claim checkpoint, including pages
with no claims. Its disposition distinguishes completed claim inventory, partial
inventory, no extraction target and insufficient signal; it records omissions or
abstention reasons. Missing/deferred/failed checkpoints cannot seal successfully.
The header transitions once from building to sealed after every expected page is
accounted for. Completion preserves partial/abstention counts; sealing cannot turn
them into complete extraction or accepted facts. Empty output without an explicit
page disposition is unfinished work.

## Identity, values and evidence

`NativeClaim` and `NativeClaimAnchor` are separate strict version-2 models. They
do not grow the legacy `claims.py` module or relax its semantic-planner ban.
Evidence binds original/page raster hash, exact generation/page, structural
element or table/physical row and explicit rendered-source-pixel coordinates.
Reference validation checks actual retained structure, not current legacy pages.
Repeated rows require an actual distinct physical source identity; identical
values in two rows remain two rows. Model response ordering or a content-only
occurrence counter cannot substitute for a physical row identity.

The logical claim key is a deterministic digest of set/source-unit identity,
physical field/row locator and canonical key, independent of typed value. A row's
group identity survives scalar resolution and diagnostic line projection. Payload
hashes separately include exact value, quote, evidence, origin and normalization
metadata. Retrying the same key with changed content conflicts atomically; it
cannot silently overwrite a row or create a second logical claim.

Money/number/quantity use finite exact decimal strings; dates use validated ISO
dates; identifiers preserve their string digits. No float round-trip is allowed.
The first exact normalizer permits at most 38 digits and 12 fractional places,
plain decimal syntax, ISO dates and optional explicit three-letter currency codes.
It rejects ambiguous locale/exponent/currency inference instead of repairing it.
The existing family registry controls known keys and value types. Unknown families
or unsupported keys cannot enter this first typed currency branch; callers record
partial/abstention coverage instead. A future observation adapter remains separate.
Neither schema validity nor a resolver's agreement
changes the required human-review disposition.

## Locks and retention

Admission and writes reuse 097: household/actor/membership/credential and
document/folder/ACL prefix, run, immutable source FK rows, claim set/checkpoint/claim
rows, then job-root ownership fence. Source and authority are re-read after waits.
No model/filesystem work or new domain/FK acquisition follows the job fence.
Checkpoints and seal commit only under the matching bound producer job. Revocation
during inference blocks its result; browser logout alone does not cancel an already
admitted durable browser request. Token-origin work retains token lifetime and
captured-scope checks.

Native rows and their source bindings are immutable and retained while the document
exists. Individual extraction/run/parse/set cleanup cannot erase native history.
Cross-reference checks are deferred where independent whole-document cascades
require it; a populated document deletion must complete without weakening retained
history. No parse rerun retargets accepted human evidence or revives obsolete work.

## Rebuild and later consumer boundary

The native reader verifies the sealed header, all expected checkpoints and exact
claim hashes, then produces deterministic diagnostic field/physical-row groups.
Raw response JSON and compatibility region envelopes are not reconstruction inputs.
There is no fallback to mutable current extraction records or newer pages.
Retained source hashes are checked without parsing raw provider JSON. Reads require
an explicit current `RequestCredential` with current document read access; they do
not require the producer to remain running, the original request credential to
remain live, or the old run to remain desired. Job completion and later reparse
preserve reconstruction. Reader logout, expiry, disabled membership or lost document
access still deny the read. Reads acquire the credential/document/folder prefix,
retained run/source and set locks, then recheck read authority before returning.
Write admission/checkpoint/seal retain their separate live 097 and job fences.

This diagnostic grouping does not run arithmetic reconciliation or select accepted
facts; source-pixel support, arithmetic validation and required-key evaluation
remain `not_evaluated`. Historical diagnostics never consult a newer family registry
to reinterpret their completeness. `recorded-text-exact-v1` typing semantics are
immutable; later typing changes require explicit version dispatch for retained rows.
Full-set reads currently load retained source manifests and claims with bounded
statement/lock timeouts. Pagination and long-document cost remain G2 performance
work rather than an established scalable read contract.

Later public candidate work must retain these row/claim identities through the
existing content-dedupe and ordinal pipeline, introduce exact native source
eligibility/evidence DTOs, and preserve 101 field decisions/path guards and 103
line selection/history/source assignment. It must not call the legacy Qwen
rejection path or mislabel native claims as Docling/Granite. Accepted selection
continues through the shared fact-projection coordinator after explicit decisions.
The 098 native index still reports `fact_basis=not_collected`; this foundation does
not change its parse-text-only contract.

## Decisive checks

- Identical replay retains IDs/hashes/counts; changed value/origin/locator under
  the same logical key fails. Two equal-value physical rows survive persistence
  and diagnostic reconstruction separately.
- Partial restart and explicit zero-target pages seal only with complete page
  accounting. Missing or tampered source/config/invocation bindings fail closed.
- Database reconstruction is independent of raw/envelope parsing, preserves exact
  decimal/identifier values and never reports derived claims as accepted facts.
- Sealed currency rebuilds identically after producer completion and a later run;
  a current read-only credential works, while revoked or inaccessible readers fail.
- Independent connections exercise supersession/cancellation, actor/token authority
  changes and source-lock waits; failure rolls back every provisional claim/seal.
- Native immutability, illegal individual deletion and populated whole-document
  cascades coexist with unchanged legacy claims and retained human histories.

Local checks and root-owned committed-source PostgreSQL validation are recorded at
handoff. No model quality, current publication or production readiness is implied.
