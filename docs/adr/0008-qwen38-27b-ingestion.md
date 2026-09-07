# ADR 0008: Qwen3.8-27B as the ingestion model

Date: 2026-09-07

## Status and authority

Accepted model decision, following the user's instruction: “Let's use 27B. Update the plan accordingly.” Integration and release validation remain planned. This ADR supersedes ADR 0006's choice of Qwen3-VL-8B-Instruct-FP8 and the initial ADR 0007 proposal to place generative ingestion on Blackbird's PRO 4000. It preserves the source, claim, validation and review rules from ADRs 0005/0006. It does not assert that Structura is already connected to the selected service.

Subsequent architecture decision: [ADR 0009](0009-qwen-native-document-parsing.md) makes Qwen-native full-document parsing the target and supersedes this ADR's initial mandatory-Docling and experimental-only simplification posture. Original preservation, truthful provenance, validation and review remain required; Docling is temporary migration/comparison support.

## Decision

Use the existing **Qwen3.8-27B BF16 service on Oxcart** as Structura's primary parser and sole generative ingestion backend. Full searchable structural parsing, classification, semantic understanding, extraction and difficult-page vision use the same selected engine through distinct bounded task contracts under ADR 0009. There is no new 8B/Granite dependency, separate automatic rescue model, or required quantized 27B deployment on Blackbird.

Model selection is complete. Evaluate the selected model against annotated source truth and the product gates. Comparisons with old-model outputs may help diagnosis but are not required to reconfirm the user's choice. A failing release gate produces an explicit integration/quality/capacity issue; it cannot silently switch providers or fall back to a fixture.

The 2026-09-07 read-only inventory and user confirmation identified:

| Item | Observed configuration |
| --- | --- |
| Host | Oxcart, `10.25.0.50` |
| Running container | `qwen38-27b-bf16-mtp-vl-oxcart-server` |
| Served model name | `qwen38-27b-bf16-oxcart` |
| Host port | `18012` |
| Weight dtype | `bfloat16` |

The unauthenticated metadata request returned an HTTP error. Resolve existing service authentication privately and perform actual authenticated text/image/structured-output calls during integration. Record the actual checkpoint revision, image digest and runtime settings; names and running state alone are not functional acceptance. Do not commit credentials or recreate/reconfigure the resident service as a routine setup step.

## Responsibilities preserved

- Storage preserves original bytes, hashes and immutable history.
- A thin source layer supplies real page inventory, rendered originals, coordinate transforms and available native text. Qwen supplies versioned derived structure and transcription with truthful model provenance. Keep reliable native values available for exact copying. Historical Docling artifacts remain readable; agreement with Docling is not a release requirement.
- Deterministic typing, schemas, reconciliation and evidence checks turn supported candidates into claims; human review controls model-backed acceptance. Semantic annotations remain planning metadata.
- Job claims/run generations control publication, retries and cancellation independently of model choice.
- Text and visual embedding models encode document chunks and selected page images during ingestion/reindexing, then encode search queries in the corresponding compatible 1536/2048-dimensional spaces. Blackbird's proposed embedding role includes both workloads. Qwen generation is not a replacement for their retrieval contracts.
- Analysis remains a later, optional Phase 9 worker and task/profile contract. Reusing the 27B endpoint for analysis requires its own citation and simultaneous-workload gates.

## Planned implementation and simplification

1. **Register a truthful ingestion profile.** Proposed logical identifier: `qwen3.8-27b-bf16-ingestion:v1`; this is not an existing runtime constant. Separate the model engine identity from task/prompt/schema profiles and the served endpoint alias. Replace 8B-specific identity branches with explicit supported capabilities where appropriate. Coordinate configuration, client routing, structured outputs, budgets, thinking/final-answer handling, source-engine enums, provenance, UI labels and evaluation reports. Never label a 27B invocation as 8B or Granite. Historical records retain their actual original lineage.
2. **Prove the authenticated adapter before whole-pipeline tuning.** Exercise semantic manifests, classification, table/KVP selection and difficult-page vision with actual inputs, bounded output/time/image limits and current response parsing. Cover invalid schema, timeout/unavailable, no-target and review-required outcomes. The current semantic gateway's profile equality controls whether it supplies a response schema; changing only a URL/model string is insufficient.
3. **Implement the Qwen-native parse contract and thin source layer.** Preserve full page coverage, ordinary searchable text, reading order, tables and source locators. Replace provider-specific parse fields and hardcoded source origins with a versioned provider-neutral representation. Preserve historical origins and distinguish native text from generated transcription before downstream extraction can consume either.
4. **Use bounded parse and extraction tasks on the same 27B.** Consume original page images plus available native context and return distinct structural, planning and candidate contracts. Measure completeness, field/row correctness, exact amounts/dates, locator support, review burden, latency and repeatability. Preserve page inventory, continuation, document-level reconciliation and visible abstention. A model value matching its own transcription is not independent verification.
5. **Activate the target using annotated quality and migration evidence.** ADR 0009 records the architectural departure from mandatory Docling and selection-only extraction. Require a Docling-free ingest/index/Viewer path, versioned cutover and rollback that preserve original assets, historical claims and later human corrections. Retire redundant stages after recovery and compatibility gates pass. Docling comparison is optional and cannot veto the selected architecture.

## Deployment and acceptance

Keep Oxcart's archive/control plane and resident 27B service. Evaluate Blackbird's available PRO 4000 for text/visual retrieval embedding services under [ADR 0007](0007-blackbird-production-validation-topology.md), preserving its unrelated Gemma service. No new generation-model fit experiment on the 24 GB card is required.

Integration must have bounded admission, queueing, retries and cancellation, with measured latency and impact on existing Oxcart clients. Reuse does not imply exclusive GPU ownership or unlimited capacity. Validate concurrent ingest/search against real embedding endpoints, then add analysis load at Phase 9. Separate safe document uncertainty from system failures.

G3 requires current-profile authenticated adapter evidence, scored representative and held-out extraction/classification/retrieval results, truthful lineage, invariant/race/outage tests, useful source navigation and measured shared-service capacity. Prior 8B UAT, favorable benchmarks or a well-formatted response do not close these gates. Owners and package acceptance are in the [completion plan](../../STRUCTURA_PRODUCTION_COMPLETION_PLAN.md) and [extraction/retrieval workstream](../plans/production-completion/extraction-retrieval.md).

## Consequences

The project can consolidate ingestion around a stronger already-resident model and reserve the additional GPU for retrieval. Integration now includes a shared inference-service boundary and a new model/profile identity. The completion plan prioritizes that migration and measured simplification over further work specific to the previous model arrangement. This ADR changes the plan; it launches no services and changes no application configuration.
