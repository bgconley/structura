# Phase 8.5 Semantic And Granite Routing RCA

Date: 2026-04-30

## Summary

Phase 8.5 drifted into a state where live model services were running, but the application still treated parts of the Phase 4 deterministic extraction path as authoritative and allowed Qwen semantic output to become the only Granite fanout source.

The visible failures were:

- BMW service invoice output had useful evidence in Docling/Qwen/Granite, but produced zero service line-item candidates.
- Phenix Title and UWM Escrow documents were vulnerable to receipt, invoice, or EOB masquerading.
- Docling tables were not independently allowed to drive Granite extraction if Qwen emitted too few regions.
- A broad classifier-driven Granite path could still send whole-document extraction prompts in live Phase 8.5.
- Granite could satisfy weak model-output schemas with flat or incomplete JSON that Structura could not materialize into canonical candidates.
- Observation persistence could fail on valid model runs because model confidence values were not bounded before inserting into `numeric(5,4)` columns.

The final corrected behavior is:

```text
Docling physical parse
-> Qwen3-VL-4B semantic inventory and document-family evidence
-> Docling structural target augmentation
-> Granite region/table/KVP extraction
-> model-output normalization
-> validators / review policy / candidate persistence
```

Qwen remains semantic and routing intelligence, not a canonical fact producer. Docling structural truth now participates directly in Granite fanout instead of being discarded when Qwen under-emits regions. Phase 4 classification remains useful as evidence, but it no longer overwrites Phase 8.5 semantic family reconciliation.

## Impact

Observed impact before the fixes:

- BMW completed model calls but had `lineItemCandidates: []`.
- Phenix Title could be classified as receipt by Phase 4 text heuristics.
- UWM Escrow could receive receipt/service-line style extraction targets just because tables existed.
- Granite document-observation regions could produce protocol failures or database overflows.
- The app was not consistently receiving the richer data that Docling, Qwen, and Granite had enough signal to provide.

Potential impact if left unresolved:

- Good structured evidence could be superseded or ignored by lower-detail later regions.
- Unsupported document families could masquerade as invoice, receipt, or EOB.
- Phase 8.5 validation could pass fixture/unit paths while live model runs remained brittle.
- Phase 9 would inherit ambiguous facts, weak provenance, and unreliable document-family state.

## How We Got Here

This was not one isolated bug. It was a stack of boundary mistakes that only became obvious after moving from fixture-backed extraction into real Docling, Qwen3-VL-4B, Granite, and visual-embedding runs.

### 1. Phase 4 Stayed Too Authoritative

Phase 4 deterministic classification was built before Phase 8.5 semantic reconciliation existed. Once Phase 8.5 started persisting Qwen/Docling-informed family decisions, Phase 4 still had code paths that could update the document read model afterward.

That meant a later heuristic classification could overwrite a better semantic family decision. This is how title, escrow, and service documents could drift back toward receipt, invoice, or EOB shapes.

### 2. Qwen Became A Granite Fanout Bottleneck

The intended design was complementary:

- Docling owns physical structure: pages, text, tables, elements, coordinates, page images.
- Qwen owns semantic inventory and routing.
- Granite owns region-scoped structured extraction.

The runtime path was narrower than that design. `_granite_job_specs()` created Granite jobs only from Qwen semantic regions. If Qwen emitted zero, too few, or slightly wrong regions, strong Docling tables and anchors did not independently create Granite work.

That made Docling look present in the pipeline while functionally disappearing from Granite extraction.

### 3. Schema Contracts Were Too Loose For Service Records

BMW-style service records are table-like, but they are not clean retail receipts or canonical invoices. Granite returned useful partial fields in earlier runs, but Structura lacked an explicit `service_record_line_item_table` model-output contract.

The first service-record schema still allowed top-level arrays like `quantity` and `unit_price` without requiring row objects. vLLM/Granite could therefore return schema-valid JSON that had no descriptions and could not become line-item candidates.

The final schema requires row-shaped `line_items[]` for service records.

### 4. Granite Was Getting Poor Table Context

Docling table JSON sometimes contains a dense grid with bounding boxes and cell metadata. Passing that raw JSON to Granite made the prompt noisy and did not emphasize the row text humans would use.

For BMW, Granite saw table evidence, but prompt context did not clearly present:

- service descriptions,
- parts,
- labor operations,
- amounts,
- row boundaries.

The prompt path now renders Docling table JSON as compact row text such as:

```text
DESCRIPTION OF SERVICE AND PARTS | AMOUNT
600 mile running-in check | $250.00
```

The original page/crop image remains available to Granite. The compact table text is supplemental grounding, not a replacement for visual evidence.

### 5. Broad Classifier Granite Jobs Were Still Possible

The Phase 4 classifier used to enqueue broad document-level extraction jobs for known schemas. In live Phase 8.5, that was unsafe because Granite should receive grounded semantic/structural targets, not broad whole-document prompts based on a heuristic family label.

That path caused shape-mismatch risk and bypassed the region-scoped extraction discipline Phase 8.5 is supposed to enforce.

### 6. Observation Persistence Was Not Defensive Enough

Granite can return arbitrary numeric values in field-level confidence slots. The database expects confidence values in `[0, 1]` and stores them as `numeric(5,4)`.

One UWM observation run produced a value outside the allowed persistence range. That was a persistence bug, not a document-quality failure. The normalizer now drops out-of-range confidence values before inserting observation candidates.

### 7. Structured Output Was Helpful But Not Sufficient

vLLM structured output and JSON schemas improved shape control, but they did not eliminate the need for prompt discipline and post-model validation. The live failures showed exactly why:

- A schema can be too permissive.
- A model can return confidence-only JSON.
- A model can satisfy scalar fields while omitting the rows the app actually needs.
- A valid JSON object can still be semantically useless.

The fix was to treat model-output schemas as adapter contracts, then normalize and validate into app-owned canonical/reviewable shapes.

## Corrective Actions

Commit: `6746eb0` (`Harden Phase 8.5 semantic Granite routing`)

### 1. Add Service-Record Model-Output Routing

`lib/extraction/model_output_schemas.py` now routes `service_record_line_item_table` to:

- `contracts/model_outputs/granite_service_record_line_items.v1.schema.json`

That schema is service-record specific and requires `line_items[]` rows.

### 2. Normalize Service-Record Outputs Into Line-Item Candidates

`lib/extraction/model_output_normalization.py` now maps service-record outputs into canonical receipt-style line items with service-record metadata.

It handles:

- row-shaped `line_items[]`,
- flat service descriptions,
- labor operation fields,
- part numbers,
- quantities,
- unit prices,
- line totals.

### 3. Prevent Phase 4 From Overwriting Phase 8.5 Family Decisions

`lib/semantic_annotations/semantic_family.py` now calculates a Phase 8.5 semantic family decision from Qwen document type plus Docling anchor evidence.

`lib/extraction/extraction_repository.py` now treats existing `metadata_json.phase8_5.semantic_classification` as authoritative for document-family read-model fields during later Phase 4 classification persistence.

Phase 4 classification still persists as an extraction artifact. It no longer gets to overwrite the reconciled Phase 8.5 family.

### 4. Stop Live Classifier Jobs From Launching Broad Granite Extraction

`lib/extraction/service.py` now allows classifier-driven broad document extraction only in fixture mode.

In live/required model mode, Granite jobs must come from semantic or Docling structural regions.

### 5. Add Docling Structural Granite Targets

`lib/semantic_annotations/docling_targets.py` now augments Qwen manifests with bounded Docling structural targets when Docling has strong evidence Qwen missed.

This adds targets from:

- Docling tables,
- page-level title/seller/escrow/dispute anchors,
- family hints from Docling text/table audit.

It also prevents table presence alone from creating receipt/service-line targets for observation-dominant families like title and escrow documents.

### 6. Dedupe Repeated Semantic Regions Before Granite Fanout

`lib/semantic_annotations/service.py` now dedupes Granite job specs by grounded document/page/element/table, semantic type, Granite task, and page-level intent.

This prevents repeated Qwen regions from creating redundant Granite work while preserving legitimate separate page-level regions.

### 7. Improve Granite Prompt Grounding

`lib/extraction/granite_prompting.py` now:

- puts `<tables_json>` first for table tasks,
- tells Granite to populate row-shaped `line_items[]`,
- renders Docling table JSON as compact rows instead of raw bbox-heavy JSON,
- keeps page text/table context region-scoped.

### 8. Harden Model-Client And Persistence Edge Cases

`lib/model_runtime/clients/_openai_vision.py` now treats confidence-only JSON as an empty extraction payload instead of throwing `ModelProtocolError`.

`lib/extraction/normalization.py` now rejects out-of-range observation confidence values before persistence.

## Validation Evidence

### Local Verification

After the final patch:

```text
ruff check .
pytest tests/unit -q
npm --prefix apps/web run lint
python3.11 scripts/validate_contracts.py
```

Results:

- `ruff`: passed
- `pytest`: `301 passed`
- web typecheck: passed
- contract validation: `47 OpenAPI paths, 14 schemas, 6 event schemas`

### GPU Verification

GPU checkout:

- host: `bgconley@10.25.0.50`
- repo: `/tank/repos/structura`
- commit: `6746eb0`

Remote verification:

- `ruff`: passed
- `pytest tests/unit -q`: `301 passed`
- contract validation: passed
- web typecheck in Node container: passed
- affected services rebuilt and restarted
- all normal services healthy after the run

### Live Five-Document Pressure Run

Run log:

```text
/srv/structura/objects/exports/phase85-rerun_after_second_fix_20260430T030347Z.jsonl
```

Final report:

```text
has_extraction_failures: false
text_embedder: skipped_by_request
```

Document outcomes:

| Document | Family After Fix | Result |
| --- | --- | --- |
| BMW CE-04 service invoice | `service_record` | 4 Granite line-item candidates, no failed jobs |
| BH Photo order | `retail_order` | 3 Granite line-item candidates, no failed jobs |
| Phenix Title Seller Info | `real_estate_title` | observation extraction only, no receipt masquerade |
| UWM Final Escrow Statement | `mortgage_escrow_statement` | observation extraction only, no service/receipt table misroute |
| MRI Anthem Denial | `medical_eob` | Granite medical/observation extraction completed |

Additional database evidence from the final run:

```text
document_semantic_annotations:
  source_engine = qwen3_vl_4b
  model_name = Qwen/Qwen3-VL-4B-Instruct
  quality_mode = smart
  count = 5
```

No Qwen3-VL 8B, High Quality, or rescue path ran.

BMW line-item candidate sample:

```text
PERFORM 600 MILE RUNNING-IN CHECK ACCORDING TO BMWCHECKLIST.        250.0000
MOUNT AND BALANCE FRONT AND REAR TIRES.DISPOSE OF OLD TIRES...      127.5000
removed rear wheel mounted and balanced rear tire...                465.6600
check headlight adjustment...                                         0.0000
```

All final-run jobs for the five pressure documents were either `succeeded` or intentionally `cancelled` text-embedding jobs. There were no failed extraction jobs.

## Before And After

Before:

- Qwen under-emission could starve Granite.
- Docling tables were present but not independently actionable.
- Phase 4 family could supersede Phase 8.5 semantic reconciliation.
- Broad classifier extraction could still hit Granite in live mode.
- Service-record model output had no dedicated contract.
- Granite could return shape-valid but app-useless arrays.
- Observation confidence could crash persistence.
- BMW service lines were absent from candidates.

After:

- Qwen and Docling both inform Granite fanout.
- Docling structural targets backstop Qwen under-emission.
- Phase 8.5 semantic family decisions are protected.
- Live Granite extraction is region-scoped.
- Service records have an explicit adapter schema.
- Granite table prompts are row-oriented and task-specific.
- Model JSON is normalized defensively.
- BMW service lines persist as reviewable line-item candidates.
- Title and escrow documents no longer masquerade as receipt/EOB paths in the pressure slice.

## Follow-Up Guardrails

- Do not reintroduce classifier-driven broad Granite jobs in live Phase 8.5.
- Do not let Phase 4 heuristic classification overwrite Phase 8.5 semantic family metadata.
- Do not make Qwen canonical fact authority. Qwen routes and explains; Granite extracts; validators/review decide.
- Do not make Docling structural targets blindly extract every table as receipt/service lines.
- Keep model-output schemas adapter-specific and stricter than generic app schemas.
- Keep service-line/table contracts row-shaped.
- Preserve raw model output and normalization telemetry for every repair or rejection.
- Treat out-of-range model confidence as invalid model metadata, not a persistence failure.
- Validate future changes with both unit tests and GPU corpus pressure runs.

## Remaining Risks

The pressure run proves the critical routing and persistence failures are closed for the representative five-document slice. It does not mean extraction quality is complete for every document family.

Known areas to keep improving:

- Granite row extraction quality can still improve, especially for noisy Docling tables.
- Observation fields are preserved, but richer canonical schemas for title, escrow, and dispute documents may be needed later.
- Qwen3-VL-4B planner recall should continue to be measured with semantic-only canaries.
- Larger and more diverse private corpus gates should be added before Phase 9 consumes these outputs.

The important architecture correction is complete: Structura no longer discards Docling structural evidence behind Qwen fanout, no longer allows Phase 4 to overwrite semantic reconciliation, and no longer treats broad classifier Granite extraction as a live Phase 8.5 path.
