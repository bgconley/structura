# Combined Qwen page understanding

Status: approved implementation direction for X-03–X-05; implementation and quality
acceptance remain open. This follows the [completion phase map](../../../STRUCTURA_PRODUCTION_COMPLETION_PLAN.md),
[native parser decision](../../adr/0009-qwen-native-document-parsing.md),
[processing authority](../../adr/0010-document-processing-authority.md) and
[native claim foundation](native-claim-currency.md). It does not advance a gate.

## Result and model calls

Use the existing Oxcart Qwen3.8-27B BF16 service for one combined response per new
page: complete searchable structure, page classification and explicit typed
extraction. Classification and extraction remain separately typed products of that
response. There is no mandatory Docling, Granite, second classifier, semantic rescue
or summary-model pass. Blackbird's RTX PRO 4000 continues to serve text and visual
embeddings for document ingestion/reindexing and queries.

Original inventory, page rendering, reference validation, exact normalization,
arithmetic checks, human decisions and publication remain application responsibilities.
Model transcription and a matching model quote are not independent original-pixel
verification. Generative output cannot assign trusted provenance or acceptance.

## Contract and completeness

Introduce `structura.page_understanding.v2` with the full v1 structural fields plus
required classification and extraction members. Retain wording, reading order,
hierarchy, tables, empty/merged cells, headers, footers, figures and incomplete-page
diagnostics. A document outside the three typed extraction families still receives
its complete searchable structure and a useful classification.

Classification uses the full existing 23-family taxonomy, alternatives, subtype,
bounded rationale, source locators and explicitly uncalibrated model scores.
Document reduction preserves mixed/unknown pages and conflicting alternatives;
neither a majority vote nor an average establishes a calibrated probability.
Human classification overrides remain separate and durable.

Family obligations must cover every field specified in app §6.4: receipt merchant
address, date/time, payment, totals and quantities; invoice seller/buyer, identifiers,
dates, purchase order, remittance, totals and lines; EOB parties, claim/processed date,
procedure/modifiers, billed/allowed/paid/patient responsibility and visible benefit
components. The existing claim registry is incomplete and is not the final acceptance
definition. Preserve explicit unsupported fields/families, omissions and ambiguity.
Missing readable fields produce partial coverage, never fabricated defaults.

Claims retain exact decimal strings and identifiers, the model-proposed typed value,
verbatim raw value and same-response element/cell/span locators. Physical row identity
comes from the actual page/table row or validated structural grouping. Equal-value
rows remain distinct; response order is not physical evidence. Continued rows retain
their physical locations until a versioned reconciliation rule links them.

## Persistence and versioning

096 already retains the exact `{page, invocation, raw}` checkpoint. Preserve its
historical bytes and hashes. Add explicit versioned configuration/invocation types
and a shared raw-output dispatcher; do not add serialization-changing defaults to
the existing v1 DTOs. Freeze actual prompt/schema/taxonomy/registry/typing definitions,
context recipe, request settings and output budget. Unknown versions fail closed.

Convert parser resume, checkpoint validation, evidence, indexing, evaluation capture
and native claim source readers together. Historical v1 parses and 102 page evidence
must remain readable without inference. Bounded whole-document context comes from
frozen original metadata/native text or explicitly selected immutable checkpoints;
resume cannot silently take newer mutable document fields as input.

105 remains an exact recorded-text normalization branch. Model-emitted claims require
a separate explicit persistence branch and a root-assigned later migration. Its
importer accepts exact checkpoint identity and policy, loads persisted v2 raw output,
and derives JSON pointers/member digests and invocation/source binding itself. A
caller-supplied value or pointer cannot establish model-emission provenance.
After import, consumers rebuild from immutable claim rows rather than reparsing the
model envelope as another source of application facts.

## Delivery and decisive evidence

1. Implement versioned output/configuration contracts and dispatch with exact v1
   hash-preservation tests and independently authored synthetic sources.
2. Wire the combined adapter into existing bounded 096/097 orchestration, retaining
   an immutable checkpoint after each page. Preserve pre-call and post-wait authority
   checks; never hold a database transaction over inference.
3. Implement raw-member-bound claim import, full family obligations and deterministic
   classification/claim diagnostics as retained generation outputs.
4. Connect candidates, review evidence and coherent parse/claim/index publication
   separately, preserving accepted human history and tested rollback.
5. Prove N new pages use N generative calls, complete resume uses zero additional
   calls, and post-checkpoint claim reconstruction uses zero calls. Test source/member
   mismatches, exact numeric values, repeated rows, continuation, mixed/blank/unsupported
   pages, injected instructions, cancellation/revocation and historical evidence.

8192 output tokens is an unqualified current limit, not a demonstrated dense-page
capacity. Measure omissions and output volume before fixing the combined budget.
Any necessary continuation/crops require explicit subpage identities and transforms;
truncation cannot masquerade as completed coverage. Source-authored precision/recall,
classification, structure and pixel-support evaluation remain separate from schema
validity. Synthetic smokes, all-review output and model self-checks do not close G3.
