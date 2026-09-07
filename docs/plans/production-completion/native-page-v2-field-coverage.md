# Combined-page v2 field coverage and contract boundary

Status: pure contract implementation, ready for root review and integration. This
implements the contract slice of [combined page understanding](native-page-understanding.md),
using [app specification §6.2/§6.4](../../../pro-merged-master-v1.2/docs/01_App_Specification.md)
and the active [classification](../../../contracts/schemas/document_classification.v1.schema.json),
[receipt](../../../contracts/schemas/receipt.v1.schema.json),
[invoice](../../../contracts/schemas/invoice.v1.schema.json) and
[EOB](../../../contracts/schemas/medical_eob.v1.schema.json) schemas. It changes no
v1 DTO, parser/configuration/invocation, database, model runtime or public reader.

## Immutable products and authority

`PageUnderstanding` represents `structura.page_understanding.v2`. It contains the
same structural page fields as v1 plus required version, classification and
extraction members. Text, hierarchy, tables, empty/merged cells, headers, footers,
figures and printed continuation proposals stay in the structural product.
Sparse grids require partial structure and `content_omitted`; the contract does
not fill unknown cells with invented empty text.

The model supplies no document/claim UUID, source engine, accepted/review status,
invocation identity or trusted validation result. Scores are named
`uncalibrated_score`. Application diagnostics always require human review and
leave source-pixel support and arithmetic validation `not_evaluated`. The same
response quoting itself is internal consistency, never independent source proof.

Classification covers all 23 existing families in their existing order: receipt,
retail order, service record, invoice, medical EOB, medical bill, insurance document,
insurance denial, real-estate title, mortgage/escrow statement, financial dispute
form, legal contract, legal notice, tax document, bank statement, financial statement,
identity document, warranty, handwritten note, typed note, whitepaper, reference
document and generic. Known, mixed, ambiguous and unknown outcomes preserve
alternatives and page-local evidence. Mixed/ambiguous outcomes have no fabricated
primary family. The future document reducer must retain unresolved pages and
human overrides; there is no majority/average-based calibrated score here.

Only receipt, invoice and medical EOB have typed obligations in this version.
The other 20 families remain fully searchable and explicitly unsupported for this
typed branch, including historical retail-order/service-record extractors. Unsupported
does not mean unreadable or no target. Generic prose may truthfully have no typed target.

## Business-field coverage

The frozen registry declares **109 obligations**: 25 receipt, 39 invoice and 45 EOB.
Tests recursively compare every business-field path in the three active schemas,
including `partyCore`, and separately assert fields required by app §6.4 but absent
from the old schemas/claim registry.

| Family | Scalar obligations | Physical-line obligations |
| --- | --- | --- |
| Receipt | Merchant display name, address, identifiers, normalized-name proposal and party-type proposal; transaction date, time, register ID, receipt number, payment method/reference, subtotal, tax, tip, discount and total | Description, SKU/code, quantity, unit, unit price, amount, discount, tax-category and category hints |
| Invoice | Seller and buyer party fields; invoice/PO number, issue/due date, terms and service-period dates; remittance instructions, payee, address and reference; subtotal, tax, discount, shipping, total, paid and balance due | Description, service date, quantity, unit, unit price, net amount, tax, GL hint and retained legacy code/gross/category fields |
| Medical EOB | Payer, patient and provider party fields; claim/received/processed/group/member identifiers and dates; billed, allowed, plan-paid, patient-responsibility and visible deductible/copay/coinsurance totals | Description, service dates, procedure code, modifiers, diagnosis/revenue/place-of-service codes, units, billed, allowed, plan-paid, patient responsibility, deductible, copay, coinsurance, adjustment reason and remark codes |

`medical_eob.line_item.gross_amount` means billed amount, `plan_paid` means insurer
payment, and `amount` means patient responsibility. These keys never silently alias
each other. Procedure modifiers and remark codes preserve ordered string tokens,
including leading zeros. Receipt quantities and each amount retain exact decimal strings.

Address and arbitrary party-identifier objects are captured as source-bound verbatim
text proposals, potentially with multiple physical source occurrences for one field.
This retains the full printed wording without inventing normalized dictionary keys.
Registry `source_path` is requirements traceability, not an activated legacy-object
projection or canonical acceptance. Later conversion to `partyCore.address`/`identifiers`
requires an explicit versioned adapter. Likewise normalized names, party types, category and GL hints
remain model proposals, separately evidenced and review-only.

Application-owned ordinal, evidence, confidence/validation, metadata, document ID
and timestamps are deliberately absent from model business keys. Physical source
rows supply identity; the model cannot choose canonical ordinals or claim authority.

## Page-local accounting and physical identity

Known primary receipt/invoice/EOB classifications require the corresponding full
ledger, including a genuine boilerplate page whose fields are all
`not_on_this_page` and whose row inventory is `no_rows_on_this_page`. Mixed
classifications account for every typed component. Ambiguous alternatives also
retain each typed ledger, but their extraction remains `partial` with
`ambiguous_interpretation`; uncertainty cannot silently become complete or no-target
coverage. These page-local statements do not establish document-level absence.

Every declared scalar key and every key in an extracted physical row receives one
status: `present`, `not_on_this_page`, `not_applicable`, `unreadable`, `ambiguous` or
`omitted`. Required obligations cannot be waived as not applicable. A value on
another page remains `not_on_this_page`; it is not a missing-document-field verdict.
Every claim is referenced exactly once by its field/row coverage entry. Omitted
readable content requires a source locator; no arbitrary defaults replace it.

Rows identify an actual table element and zero-based row, or a real structural
row container with validated ancestry. Primary value locators identify exact
element/cell text occurrences. A cell spanning multiple rows cannot establish one
independent monetary line, and a model list index or arbitrary row label is not
physical evidence. Complete inventories account for every recorded table row as
extracted or explicitly excluded. Exclusions retain header/summary/non-line versus
unreadable/omitted reasons. Empty row inventory must be explicit.
Represented structural rows must be disjoint: an enclosing section and its nested
rows cannot both be counted as independent lines.

Scalar identity includes the field key plus element, cell row/column and exact
text-span start/end. Repeated values at different occurrences in one paragraph or
cell remain distinct. Line identity instead remains one key per real physical row;
a second span in that row cannot silently duplicate its monetary field.

`row_key()` is page-local only. Future persistence must bind it to the exact
generation/page/checkpoint. Equal rows on different pages and printed continuation
keys remain separate until a versioned reconciliation rule establishes their relation.

`complete` is a model-reported page inventory, not measured recall or validated
document completeness. Partial/abstention/unsupported outcomes and application
interpretation diagnostics remain separate. Original-source evaluation is required
to detect falsely claimed absence, incorrectly excluded rows or omitted structures.

## Exact proposals and raw-member binding

Money, numbers and quantities accept finite plain decimal strings with at most
38 digits and 12 fractional places. Scale, signed zero and identifier characters
are preserved. Dates require valid ISO dates; local time has no inferred timezone.
Currency must be null or an explicit three-letter code. A proposed ISO date derived
from ambiguous printed notation and a proposed currency inferred from `$` remain
visible proposals with application-generated interpretation diagnostics. The model's
chosen value is retained separately from its exact raw quote; it is never labeled a
verified literal just because its type is valid.

`decode_page_understanding(raw)` rejects duplicate JSON members, non-finite JSON,
unknown versions and invalid bindings. It returns immutable `DecodedUnderstanding`
with the validated page, exact UTF-8 raw-output SHA256 and per-claim
`RawClaimMember(index, pointer, canonical_member_sha256)`. Pointers are derived
as `/extraction/claims/N`, never accepted from the model/caller. A member digest
identifies canonical JSON content; formatting changes still change the full raw hash.
This decoder proves no live invocation or checkpoint provenance. The later importer
must load exact persisted raw under its actual checkpoint/invocation/source binding.

## Frozen definitions and encoding

`definitions.frozen_definitions()` verifies actual installed schema, taxonomy,
registry, typing source and validation source against fixed checkpoint hashes.
`model_output_schema()` equals `PageUnderstanding.model_json_schema()` and the
published [v2 artifact](../../../contracts/model_outputs/structura_page_understanding.v2.schema.json).
The typing/validation hashes include actual source bytes; a version label alone
cannot conceal changes. Later behavior changes need explicit version dispatch,
preserving historical v1 and this frozen v2 interpretation.

Canonical JSON is UTF-8, sorted keys, compact separators, `ensure_ascii=False` and
`allow_nan=False`. Existing processing `content_digest` uses different Unicode
escaping; do not substitute it for these member/definition hashes. Raw-output hashes
cover the original UTF-8 string bytes without JSON reserialization.

| Definition | SHA256 |
| --- | --- |
| Schema | `8a1630253a3026a288ce18e1a68c7f913391f37da05c3b48e96013810ef18a45` |
| 23-family taxonomy | `81b4248651ec70ebbf8d2cb31f16d37f414027ad0838a5cf335cd6ffbe94790d` |
| 109-field registry | `1fa55014eaa4b15130acf4d1fd00d59783e4c249041a4ac2ffb7059fe550f2e3` |
| Typing | `e1fb29f85b6a34725fb6963fe53695c9e5ac7a4d53657714080b8627c2f1949c` |
| Validation implementation | `1c6421f8575cc50bf504e29a8ac4a99d32ba77377cc1ad6e79bc45467a05cb16` |

## Bounds and remaining gates

The provisional shape bounds are 400 elements, 3,000 cells per table, 50,000 grid
positions per table, 3,000 claims, three typed families, 500 represented and 500
excluded rows per family, and a **16 MiB raw UTF-8 response ceiling**. Each family
reports every scalar obligation and each extracted row reports its line obligations;
at the row bounds this is substantial overhead. All overflow is rejected, never
silently truncated into a complete result. Explicit partial output preserves what
was captured and identifies omissions.

The compact schema measures **23,705 bytes**; the independent synthetic two-line
invoice response measures **9,076 bytes**. These are byte counts, not model tokens,
dense-page capacity or latency evidence. The current 8,192-token output budget is
still unqualified. Capture's separate transport bound, actual provider schema/input
budget, dense/long/mixed-page output limits and loss rates must be measured together.
If continuation is needed, it requires explicit immutable subpage identity rather
than a hidden second semantic pass.

The local synthetic contract/static gates do not establish original-pixel support,
classification accuracy, field recall, document reduction, model-call counts,
publication safety or production performance. Versioned adapter/configuration,
historical dispatch, raw-bound persistence, candidates/review and coherent activation
remain separately owned implementation slices. Migration 105's exact
`structure_normalization` branch remains unchanged.
