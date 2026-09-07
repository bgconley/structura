# ADR 0009: Qwen-native document parsing

Date: 2026-09-07

## Status and scope

Accepted target architecture for the completion plan, following the user's request to incorporate the Qwen-native parser direction. Implementation, migration and release gates remain open. [ADR 0008](0008-qwen38-27b-ingestion.md) continues to select the existing Oxcart Qwen3.8-27B BF16 model. This decision replaces mandatory Docling conversion and selection-only text extraction with a Qwen-native structural parse and extraction pipeline. It preserves immutable originals, concrete evidence, truthful provenance, deterministic validation, accepted-fact policy and human corrections.

Docling is a temporary migration/comparison option. Its successful execution or agreement with Qwen is not an acceptance prerequisite. Existing Docling artifacts remain genuine historical records; they must not be fabricated or relabeled to make the new implementation look compatible.

## Explicit specification amendment

The artifact pack's app spec §5.3, §6.3, §§8–11 and §16 name Docling in the structural representation, service/data flow, routing, storage/output and debug acceptance requirements. The completion plan intentionally replaces those provider-specific requirements with thin source handling, Qwen-native parsing and a versioned provider-neutral structural artifact. Stories 3.1/3.2 retain durable parsing and inspectable diagnostics; Story 4.5 retains original-source evidence. The root phase sequence and Phase 8.5 stop point remain unchanged. Original artifact-pack wording and prior evidence are retained as historical source material with this amendment taking precedence for implementation.

This ADR supersedes ADR 0006's mandatory Docling source/selection contract and the parts of ADR 0008 that made native parsing only an experimental future option. A model-generated parse may be the application's current canonical structural representation. It is still a derived interpretation, not the immutable original or an automatically accepted set of facts. No broader relaxation of model-backed promotion or sensitivity policy is implied.

## Target pipeline

```text
Immutable original bytes
  -> lightweight PDF/image handling and authoritative page inventory
  -> original page images + optional native PDF text
  -> Qwen3.8-27B BF16 structured parsing and extraction on Oxcart
  -> versioned structural artifact, searchable text, typed candidates and source locators
  -> evidence/validation/reconciliation and acceptance/review policy
  -> current accepted facts, Viewer/evidence and search projections

Blackbird PRO 4000 embedding services:
  document chunks + selected original page images -> ingestion/reindex vectors
  search queries -> compatible query vectors
```

The lightweight source layer enumerates real pages, hashes originals/rendered images, records dimensions/rotation, renders bounded images/crops and extracts native text when useful. It does not depend on learned layout/table recognition or Docling being present. Native text is supporting source data, not a veto when the visible source contradicts it. Keep original-resolution assets for viewing and evidence; request resizing/cropping records reversible coordinate transforms.

## Required structural contract

Qwen must produce a complete useful representation of the document, including pages, text blocks, hierarchy/reading order, tables/cells, row/column relationships, and appropriate headers/footers or other material content. Preserve original wording in searchable transcription separately from summaries, normalized fields or inferred explanations. Unsupported typed families must still have searchable document content.

Persist application-assigned IDs, parse/run generation, page ownership, locators, source/image hashes, converter/model revision, task/prompt/schema identity, actual request outcomes and explicit omissions/ambiguities. IDs are stable within an immutable parse version; reruns map or retain historical references rather than pretending new model segmentation has identical IDs. Record every real page as processed, deferred, unsupported or failed. Bounded page batches and continuation state prevent silent long-document truncation.

Move the useful pages/elements/tables/chunks interface in `lib/documents/parse_models.py` behind an explicit converter-neutral contract. Rename or replace the `docling_json`-specific field and hard-coded `source_engine='docling'` persistence through forward-compatible migrations/adapters. Do not write Qwen output into a nominal Docling artifact or claim independent source verification merely because a later step copies model-generated text.

## Evidence and authority

- Original bytes and rendered source pages remain the inspectable source. Parse text, boxes and table structure record their actual native/model origins.
- Check document/page ownership, coordinate bounds, rotation/crop transforms and locator resolution in deterministic code. These checks prove where a locator points; they do not by themselves prove the quoted content is correct.
- A quote matched only against the same Qwen-generated transcription is circular corroboration. Preserve model origin through parse, chunks, candidates, claims and accepted-fact policy. Independent native-text matches may provide additional support when the text layer is reliable.
- Assess transcription, field/row accuracy and visual locator support against original pages and human-reviewed expectations. Weak, ambiguous or unsupported evidence remains explicit review/partial/abstention state. Semantic planning metadata and summaries do not become extracted facts.
- Keep schema/type validation, amount/date consistency, reconciliation, review policy and human corrections. A valid schema, confidence score, model self-check or agreement with Docling is not sufficient evidence on its own.

## Migration and release sequence

1. **Contracts and provenance:** X-01 defines converter/task profiles, artifact/schema versions, native/model source types, DTO/UI/debug/export semantics and historical compatibility. Make the model-origin policy explicit across all consumers before publishing the new parse.
2. **Source handling and Qwen parse adapter:** X-02/X-03 implement the thin page layer and bounded whole-content parsing, with independent claim/run fencing, checkpoints, cancellation, continuation and full source inventory. Reuse existing renderer primitives where appropriate; do not move Docling/Torch dependencies into API or shared workers.
3. **Extraction and evidence:** X-04/X-05 connect full parse and bounded extraction results to one authoritative claim/projection path. Combined requests may return structure and candidates, but separate their schemas/origins and enforce the same evidence and review rules. Retain exact native-source copying where useful without forcing a Docling selector round trip.
4. **Versioned activation and indexing:** X-05/X-07 switch a document's current parse/projections atomically after validation, preserve old evidence and accepted corrections, and rebuild chunks/text/visual indexes with generation-aware progress and profile compatibility. UI-06/UI-07 keep source jumps, complete tables, parse diagnostics and historical decisions usable during and after migration.
5. **Docling-free gate:** X-06/X-08 and G3 run representative and held-out ingestion end to end with Docling conversion unavailable. Test ordinary text coverage, exact identifiers, amounts/dates, merged/continued tables, rotated/mixed/handwritten pages, long documents, invented/omitted content, incorrect coordinates, retries and stale publication. Validate real ingestion/query embeddings, search usefulness, Viewer/evidence navigation and shared Oxcart capacity. Optional Docling comparisons may diagnose differences; the reference is the annotated original.
6. **Retirement and recovery:** retire Docling queue dependencies, worker/image startup requirements and legacy converter routing after cutover and rollback/recovery gates. Keep genuine historical artifacts readable. Rollback restores prior current-version pointers/compatible indexes in a scoped manner and cannot erase later human corrections. OPS-02 must recover and use a Qwen-native archive without needing to reinstall Docling to read it.

Gate failures remain named completion issues; they do not silently restore a mandatory Docling pipeline, switch the selected model or mark incomplete text as successfully indexed. The architecture choice is settled, while production activation depends on evidence. Owners and decisive checks are in the [completion plan](../../STRUCTURA_PRODUCTION_COMPLETION_PLAN.md) and its [closure register](../plans/production-completion/closure-register.md).

## Consequences

Ingestion can use one document-understanding model and a small source-handling layer instead of requiring the former converter ensemble. The migration must replace structural functionality and provenance assumptions, not only extraction prompts. Blackbird serves both document/page ingestion embeddings and compatible query embeddings. This ADR updates the implementation plan; it does not remove code, reparse the user's archive, change review policy or modify running services.
