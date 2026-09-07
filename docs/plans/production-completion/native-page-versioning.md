# Native page parser versioning

Status: bounded v2 adapter and reader implementation, awaiting canonical integration
and database validation. This supports the approved [combined page contract](native-page-understanding.md).
It does not activate candidate parsing, publish facts, select a current generation,
change model services, or close source-quality and production-capacity gates.

## Versions and retained history

`parser_configuration(...)` and `execute_parse_candidate(...)` retain v1 as their
default. V2 requires an explicit `ParseConfigurationV2` produced by
`understanding_configuration(deployment, opened_source, request=..., render_scale=2)`.
The caller opens `DocumentSource` with the exact registered original asset ID,
hash, MIME and byte bound before preparing this configuration, then admits a run
through `DocumentProcessingService.start_parse` under the existing request policy.
Configuration preparation makes no model calls. Execution uses the existing
caller-owned renewing job lease and 096/097 authority checks.

V1 configuration and invocation fields, defaults, order, serialized instances,
checkpoint digests and original `PageParseOutput` schema remain unchanged. Explicit
codecs discriminate on `output_schema_version`; missing, invented and future
versions fail closed. The expanded document-structure and capture JSON-schema
artifacts have different bytes and hashes because they now describe nested v2
alternatives. That does not rewrite historical v1 instances or their digests.
The outer document structure/capture versions remain v1. JSON schemas also constrain
the legacy union branch to v1, matching runtime version discrimination.

`ParseInvocation` remains available from its original `structure` module as a
compatibility re-export. `normalize_raw_page` is the shared version dispatcher for
new normalization, replay, checkpoint validation and evaluation. V2 keeps every
classification/extraction member in the exact raw checkpoint and projects only
the existing structural fields through the unchanged deterministic ID/coordinate
normalizer. It does not create canonical fields or line items from the envelope.

## Frozen source and request

V2 freezes the accepted Qwen3.8-27B Oxcart profile, declared deployment revision,
actual output/taxonomy/registry/typing/validation definitions, renderer, normalizer,
chunker, request implementation and source-context recipe. Installed definition
source-file hashing occurs only during configuration preparation and executor
validation outside a database transaction. Historical reads verify retained
identities without contacting a model or requiring a currently selected run.
Versioned definitions must remain available for historical reconstruction; changing
their implementation requires a new explicit version instead of silently changing
the meaning of a retained version.

The document context binds the complete original inventory and original asset
identity. PDF context selects at most eight evenly spaced source pages, including
the endpoints, and records at most 384 Python characters from each native-text
page. It records selected and omitted page numbers, exact original-page UUIDs,
source-page hashes and full native-text character counts. Context is capped at
24 KiB UTF-8. Raster documents carry metadata-only context and explicitly omit all
native excerpts. The current page independently includes at most 12,000 native
characters, with selected/omitted counts. Native text is labeled untrusted
`pdf_native`; copying it into model transcription does not establish independent
support for a claim. Mutable titles, classifications, summaries and other runs'
model outputs do not become request context.

Execution reproduces the context from its same verified original snapshot before
new calls. Each v2 invocation binds the configuration, complete inventory, context,
actual prompt, schema, request settings and exact PNG bytes. Prompt/request
reconstruction is pure and usable by checkpoint, capture, retained evidence and
claim readers. The optional source-artifact verifier also reproduces the native
context from original bytes, separately from its authorized database snapshot.
These checks establish consistency, not proof of a live invocation or pixel-faithful
transcription. A reported server model version may be absent and remains explicitly
null; the caller-declared deployment revision is retained separately.

Request settings require an explicit output-token budget, temperature, timeout
and nullable seed. Null seed means omit it from HTTP; zero means send zero.
The budget must leave room within the profile's declared context limit, but that
simple bound is not tokenizer accounting or evidence that a dense page fits.
An explicit execution timeout cannot override a frozen v2 timeout.

## Calls, bounds and uncertainty

One new page uses one combined adapter call. There is no second classifier,
extractor, summary pass or hidden rescue. The existing HTTP adapter has no implicit
retry loop; job retries resume immutable checkpoints. A completed replay makes no
new calls. The actual transport must be observed independently for live call-count
evidence; fixture/client metadata cannot attest live execution.

Prompt input is capped at 160 KiB UTF-8, and image input retains the accepted
profile's 10 MiB cap. The current HTTP client bounds the decoded response envelope
to 1 MiB. The protected capture contract separately caps raw output at 2,000,000
characters, while the standalone strict v2 decoder has a 16 MiB byte guard.
These are distinct validation limits, not production-throughput or recall claims.
The adapter does not truncate a response to fit. A non-stop finish, malformed or
duplicate-member JSON, repaired dictionary differing from exact raw output, invalid
coverage/claim shape or unsupported version cannot produce a successful checkpoint.
Valid partial/insufficient-signal output remains explicit and review-only.

The protected capture wrapper requires v2 budget/temperature declarations to match
the stored request, and labels their provenance `frozen_configuration`. V1 retains
`externally_declared` behavior. Commit metadata remains externally declared for
both; invocation authenticity and source-pixel support are not inferred.

## Consumer and follow-on boundaries

096 checkpoints, 102 retained evidence, 098 candidate index preparation and the
evaluation capture readers accept explicit v1/v2 configurations and invocations.
Compact evidence reads still load one page; metadata requests do not fetch every
raw response. Historical generations remain subject to current reader ACL/token
policy, with no current-generation fallback. Original assets, page locators and
existing evidence IDs are preserved.

105 remains the `structure_normalization` / `recorded-text-exact-v1` path. It can
derive an explicitly requested claim from v2's retained transcription and verifies
the invocation binding, but it does not parse the raw envelope to build application
facts or relabel the result `model_emission`. Retained claim rebuilding reads its
immutable typed rows. A separate raw-member-bound model-emission importer, document
classification reduction, coherent publication, human-review integration and
real source-annotated quality/capacity gates remain required subsequent work.

Validation includes exact historical v1 golden serialization/hashes, unknown-version
JSON-schema rejection, explicit request settings, real adapter transport with mock
HTTP, N-page/resume behavior, raw/request/source tampering and pre/post-call authority
loss. New PostgreSQL cases exercise v2 historical capture, evidence and media,
index preparation, 105 retained claims and independent run supersession during an
in-flight model call. Only root's canonical database run establishes those SQL gates.
