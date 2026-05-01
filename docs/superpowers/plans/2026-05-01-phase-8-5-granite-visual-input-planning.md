# Phase 8.5 Granite Visual Input Planning

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit Granite visual-input planner so region-scoped extraction sends the right visual evidence for each semantic task without regressing the current full-page workflow.

**Architecture:** Keep Docling as physical truth, Qwen/Docling as semantic target inventory, the extraction planner as coverage control, and Granite as the grounded structured extractor. Add a deterministic visual-input planning layer between `SemanticExtractionTask` and `VisionGenerateRequest`.

**External evidence used:** IBM's Granite 4.0 Vision model card describes document extraction, table extraction, and KVP extraction as first-class tasks, with table extraction evaluated in both cropped-table and full-page settings. vLLM's multimodal docs make multimodal media explicit per request and expose media-count/cache controls, so visual granularity is both a model-quality and runtime-stability decision.

## Implementation Status

Implementation pass 1 is complete for the gateway seam and conservative runtime policy:

- Added `lib/extraction/visual_input_planning.py` with visual-plan DTOs, bbox-basis handling, crop-quality checks, crop expansion, feature-flagged crop generation, output-usefulness fallback, and visual-attempt metadata.
- Extended extraction source DTOs/repository loading with page geometry, page metadata, element metadata, table `element_id`, table bbox, and table metadata.
- Integrated the planner into `lib/extraction/gateways/_vision.py`.
- Default runtime mode is `shadow_full_page`, so the model input remains the current full page while planner metadata is recorded.
- `planned` mode is opt-in through `STRUCTURA_GRANITE_VISUAL_INPUT_MODE=planned`.
- `full_page` remains a kill switch that restores current full-page behavior without rebuild.
- Crop-mode empty/noisy output retries once with `full_page_retry` when the Granite task budget allows a second attempt.
- Granite evidence now records visual scope, source page image hash, input hash, bbox, bbox basis, rotation policy, and crop-quality report when available.
- Local validation passed `ruff`, `mypy`, `pyright`, Compose config rendering, focused extraction/semantic unit slices, and full `pytest` (`330 passed`, `50 skipped`).

Remaining before enabling planned crop mode for corpus validation:

- Run GPU BMW replay in `shadow_full_page` and `planned`.
- Run the pre-crash ten-call replay in both modes.
- Run the private edge-case fixture checklist.
- Keep non-upright rotated pages on full-page fallback until a pixel-transform proof test is added for each rotation.
- Keep ambiguous `visual_bbox_hint` on full-page fallback unless Qwen/Docling emits explicit `bbox_basis`.

## Current Codebase Seams

The repo already exposes most of the needed seams:

- `lib/semantic_annotations/models.py`
  - `SemanticExtractionTask` carries `grounding`, `semantic_type`, `granite_task`, `target_schema`, `expected_fields`, and freeform `metadata`.
  - This is the correct input to a visual-input planner.
- `lib/semantic_annotations/extraction_plan.py`
  - The Granite extraction planner already buckets and annotates selected jobs.
  - Visual-input planning should not live here; this module chooses *what* to extract, not *which pixels* to send.
- `lib/extraction/source_repository.py`
  - `load_extraction_source()` loads pages, page image asset URIs, element bboxes, and table rows.
  - Missing seam: page dimensions are not loaded, and `ParsedTableText` does not expose `element_id` or table bbox via the linked table element.
- `lib/extraction/models.py`
  - `ParsedPageText`, `ParsedElementText`, `ParsedTableText`, `ExtractionSourceDocument`, and `GatewayExtraction` are good DTO boundaries.
  - Missing seam: no `VisualInputPlan` DTO, and no source-page/crop metadata attached to image inputs.
- `lib/extraction/gateways/_vision.py`
  - `_image_inputs()` is the right integration point today, but it is currently doing page selection and image loading directly.
  - Current behavior sends the selected full page image. It ignores `visual_bbox_hint` and element/table bboxes.
- `lib/model_runtime/contracts.py`
  - `ModelImageInput` is the correct low-level model-client input.
  - Missing seam: image provenance metadata should stay outside model HTTP serialization, but be carried by the extraction gateway for raw output and evidence.
- `lib/extraction/evidence_context.py`
  - Evidence is now task-grounded by page, element, table, and semantic region.
  - Missing seam: evidence context does not yet include visual input scope, bbox, source page image hash, or crop hash.

## Correct Visual-Input Policy

Granite should not blindly receive the full document. It should receive the smallest visual input that preserves the evidence required for the specific task.

Use **full selected page** when:

- the task is page-level KVP or observation extraction;
- grounding is only `page`;
- metadata says `requires_full_page_image=true`;
- no trustworthy bbox can be derived;
- the bbox covers most of the page;
- the task needs surrounding legal, payment, or form context.

Use **crop-first** when:

- grounding is `table` and Docling provides or links to a table element bbox;
- grounding is `element` and the element has a bbox;
- task metadata has a high-confidence `visual_bbox_hint`;
- semantic type is a line-item/table/transaction type and the bounded region is credible;
- the task has `requires_full_page_image=false`.

Use **full-page fallback** when:

- crop generation fails;
- coordinate basis is unknown or inconsistent;
- crop would be too small after clamping;
- crop validation detects a blank/near-blank output;
- Granite returns a retryable model-service error and policy allows one fallback retry.

Do not send a naive crop just because a bbox exists. Real documents routinely contain rotation, skew, partial table headers, sparse labels outside the row area, low-resolution scans, repeated headers/footers, and multi-page continuations. The planner must treat crop selection as a guarded decision with validation and fallback, not as a direct bbox-to-image transform.

Allowed visual-input scopes:

- `full_page`: the current safe baseline. Use when context, geometry, or quality is uncertain.
- `element_crop`: crop from a Docling element bbox after coordinate normalization and quality checks.
- `table_crop`: crop from a Docling-linked table element bbox or a table-derived bbox.
- `bbox_crop`: crop from planner/Qwen metadata only when bbox basis is explicit and credible.
- `expanded_crop`: crop with deterministic padding/context expansion to preserve labels, headers, or columns.
- `full_page_retry`: fallback after crop output fails quality or extraction usefulness checks.

Do not send crop plus full page by default. That increases multimodal tokens and can reintroduce full-page distraction. Add `crop_plus_page_thumbnail` only after baseline crop/full-page behavior is measured and only behind a separate explicit mode.

## Edge-Case Hardening Matrix

These cases are common production document modes. The implementation is not complete until each has deterministic handling and tests.

| Document mode | Required planner behavior | Required tests |
| --- | --- | --- |
| Rotated pages and landscape scans | Use `document_pages.rotation_degrees`, page dimensions, and image dimensions to normalize orientation before crop planning. If rotation handling cannot be proven for the page, choose `full_page` with `fallbackReason=rotation_unresolved`. | Unit tests for 90/180/270-degree page metadata, landscape page dimensions, and fallback on unknown rotation basis. |
| Docling bboxes in PDF points versus image pixels | Require an explicit `bbox_basis` decision: `pdf_points`, `image_pixels`, `normalized_1000`, or `unknown`. Convert only when page points and image pixel dimensions are available. | Tests for point-to-pixel conversion, pixel passthrough, normalized mapping, and unknown-basis fallback. |
| Qwen `visual_bbox_hint` with unclear basis | Treat hint-only bboxes as advisory unless metadata includes basis/confidence/source. Unknown hint basis must never crop in `planned` mode. | Tests proving ambiguous hints produce full-page fallback and explicit-basis hints can crop. |
| Tables whose `document_tables` row has no linked element bbox | Try linked `document_tables.element_id` bbox first, then table metadata bbox if present, then union nearby table-like elements on the same page, then full-page fallback. | Tests for linked table bbox, metadata table bbox, inferred union bbox, and no-bbox fallback. |
| Multi-page or continuation tables | Do not crop only the first page if continuation metadata or same semantic group spans pages. Plan one bounded request per page/region or fall back to page-level extraction per continuation page. | Tests for continuation group metadata, per-page visual plans, and prevention of single-crop truncation. |
| Bboxes covering too much page | If padded crop exceeds area threshold, use full page. Initial threshold: 70% of page area. | Tests for crop area ratio just below and above threshold. |
| Bboxes covering too little page | If crop is below minimum width/height or text-area threshold, expand padding up to safe limits; if still too small, use full page. | Tests for tiny bbox expansion and too-small fallback. |
| Mostly blank margins | Compute simple blankness/content-density checks. If crop is mostly background, expand around bbox; if still blank, use full page. | Tests with synthetic blank-margin images and nonblank region images. |
| Skewed/scanned receipts where Docling text geometry does not align with visual rows | Prefer full page or expanded crop for low-confidence geometry, scanned/low-text pages, or quality signals indicating skew/degradation. Do not trust narrow Docling bboxes alone. | Tests where page quality metadata forces full page despite bbox. |
| Forms where surrounding labels outside bbox are required | Observation/KVP form tasks default to full page unless the crop policy explicitly expands to include left/top label bands. | Tests proving seller/escrow/form KVP uses full page by default and expanded crop only when configured. |
| Crops that lose headers/column names | For table/line-item crops, expand upward and leftward to include likely header row and first column labels. If header retention cannot be validated, use full page. | Tests proving table crop includes header-band padding and falls back when header band would exceed/clamp badly. |
| Low-resolution page images where cropping makes text unreadable | Enforce minimum crop pixel dimensions and effective DPI/page-scale heuristics. Low-res crops use full page or expanded crop; never downsample crop inputs. | Tests for low pixel dimensions and minimum readable crop size. |
| Repeated page headers/footers contaminating bbox-derived crops | Clamp crop expansion away from known header/footer bands unless region intersects them. Use page text/element ordinal and bbox position to avoid boilerplate bands. | Tests where top/bottom boilerplate bands are excluded from expanded crop. |
| Runtime fallback when cropped request succeeds technically but returns empty/noisy content | Treat empty rows, no observations, schema echo, or grid-only output as extraction-usefulness failure for crop mode. Retry once with full page when policy permits, and record both attempts. | Tests for crop success with empty/noisy payload triggering `full_page_retry` and final metadata preserving both attempts. |

## Implementation Plan

### Task 1: Add Visual Input Planning DTOs In Shadow Mode

- [ ] Add `lib/extraction/visual_input_planning.py`.
- [ ] Define:
  - `VisualInputScope = Literal["full_page", "element_crop", "table_crop", "bbox_crop", "expanded_crop", "full_page_retry"]`
  - `BBoxBasis = Literal["pdf_points", "image_pixels", "normalized_1000", "unknown"]`
  - `RotationPolicy = Literal["upright", "rotate_90", "rotate_180", "rotate_270", "unknown"]`
  - `VisualInputPlan`
  - `PlannedImageInput`
  - `VisualInputDecision`
  - `CropQualityReport`
  - `VisualInputAttempt`
- [ ] Planner inputs:
  - `ExtractionSourceDocument`
  - `SemanticExtractionTask | None`
  - `max_images`
  - `mode`, initially from `STRUCTURA_GRANITE_VISUAL_INPUT_MODE`
- [ ] Planner outputs:
  - selected page IDs/page numbers;
  - intended scope;
  - source page image sha256;
  - normalized bbox if available;
  - bbox basis;
  - rotation policy;
  - expansion policy;
  - crop quality report;
  - continuation group metadata when present;
  - fallback reason if full-page was selected.
- [ ] Integrate planner in `_vision.py` in **shadow mode only**:
  - Continue sending the exact current full-page image bytes.
  - Add `visualInputPlan` metadata to `raw_output_json`.
  - Do not alter model payloads yet.
- [ ] Tests:
  - element-grounded task produces `element_crop` decision in metadata but still sends full page in shadow mode;
  - page-grounded task produces `full_page`;
  - missing/invalid bbox produces `full_page` with fallback reason.
  - line-item/table tasks produce crop-intent only when geometry basis is explicit.
  - ambiguous `visual_bbox_hint` produces full-page intent.
- [ ] Regression check:
  - Existing `tests/unit/extraction/test_model_gateways.py` must pass unchanged except for expected metadata additions where asserted.

### Task 2: Load Geometry Needed For Safe Cropping

- [ ] Extend `ParsedPageText` with optional `width_points`, `height_points`, and `rotation_degrees`.
- [ ] Extend `ParsedTableText` with optional `element_id`, `bbox`, and `metadata`.
- [ ] Extend `ParsedElementText` with optional `metadata` if needed for geometry source/basis.
- [ ] Update `load_extraction_source()` to load:
  - `document_pages.width_points`
  - `document_pages.height_points`
  - `document_pages.rotation_degrees`
  - `document_pages.metadata_json`
  - `document_tables.element_id`
  - linked table element `bbox_json`
  - `document_tables.metadata_json`
  - `document_elements.metadata_json`
- [ ] Add tests proving old fixtures without dimensions/bboxes still load.
- [ ] Add tests proving table grounding can resolve through `document_tables.element_id` to a bbox.
- [ ] Add tests proving missing table element bbox can fall back to table metadata bbox when basis is explicit.
- [ ] Do not add a migration in this task. The schema already has the required columns.

### Task 3: Implement Coordinate Normalization Without Behavior Change

- [ ] Add coordinate helpers in `visual_input_planning.py`:
  - normalize Docling element bbox formats already accepted by `lib/extraction/evidence.py`;
  - detect metadata `visual_bbox_hint` basis;
  - convert page-point bboxes to image-pixel bboxes when page points and image pixels are both known;
  - handle normalized 0-1000 hints conservatively;
  - apply page rotation transforms when rotation is explicit;
  - detect landscape page/image mismatch;
  - clamp and pad bboxes.
- [ ] Add `bboxConfidence` / `bboxBasis` / `bboxFallbackReason` / `rotationPolicy` to planner metadata.
- [ ] Conservative rules:
  - if coordinate basis is ambiguous, plan `full_page`;
  - if rotation is nonzero and transform cannot be proven, plan `full_page`;
  - if page points/image pixels are unavailable for PDF-point conversion, plan `full_page`;
  - if crop after transform is inverted, out of bounds, or degenerate, plan `full_page`.
- [ ] Tests:
  - PDF-point bbox maps to image pixels;
  - normalized 0-1000 bbox maps to image pixels;
  - image-pixel bbox passes through with clamping;
  - explicit 90/180/270-degree rotation maps correctly or falls back when unhandled;
  - landscape image/page dimensions do not produce inverted crops;
  - inverted/out-of-range bbox falls back full page;
  - crop area above configured page-ratio threshold falls back full page.

### Task 4: Add Crop Quality Analysis Without Behavior Change

- [ ] Implement `CropQualityReport` in `visual_input_planning.py`.
- [ ] Quality checks must include:
  - crop width/height in pixels;
  - crop area ratio versus page image;
  - blankness/content-density estimate;
  - minimum effective text size heuristic;
  - border/margin dominance;
  - whether header/label expansion was applied;
  - whether crop touches page edge after padding;
  - whether page quality metadata suggests skew/degraded/low-text scan.
- [ ] Add configurable conservative thresholds:
  - maximum crop area ratio, initial 0.70;
  - minimum crop width/height, initial 384px short edge unless full page is smaller;
  - minimum content density, initial implementation based on luminance variance or nonwhite pixel ratio;
  - header/footer exclusion bands, initial 8% top/bottom unless region intersects them.
- [ ] The report must be generated in shadow mode for observability.
- [ ] Tests:
  - mostly blank crop fails quality;
  - tiny crop expands or falls back;
  - oversized crop falls back;
  - low-resolution crop falls back;
  - header/footer bands are not accidentally included by expansion;
  - degraded/skew quality metadata forces full page or expanded crop.

### Task 5: Add Context-Preserving Crop Expansion

- [ ] Implement crop expansion policies:
  - `table_header_band`: expand up to include column headers.
  - `left_label_band`: expand left for form/KVP labels.
  - `top_label_band`: expand up for form/KVP section labels.
  - `row_context_band`: expand above/below line-item rows.
  - `safe_margin_pad`: baseline padding for all crops.
- [ ] Expansion must be task-aware:
  - table/line-item crops preserve headers and first-column labels;
  - form/KVP crops preserve nearby labels or fall back full page;
  - receipt/service rows preserve row context but avoid top/bottom boilerplate bands;
  - low-confidence or scanned/skewed geometry defaults to full page.
- [ ] Expansion must be reversible/auditable in metadata:
  - original bbox;
  - expanded bbox;
  - expansion policy;
  - excluded bands;
  - fallback reason.
- [ ] Tests:
  - line-item crop includes header band;
  - form crop includes left/top label band or falls back;
  - expansion avoids repeated page header/footer unless region overlaps it;
  - expansion clamps safely at page edges;
  - expansion that would exceed area threshold falls back full page.

### Task 6: Add Crop Generation Behind A Feature Flag

- [ ] Add crop generation to `visual_input_planning.py`, gated by:
  - `STRUCTURA_GRANITE_VISUAL_INPUT_MODE=planned`
  - default remains `full_page` or `shadow_full_page`.
- [ ] Use Pillow as the minimal image dependency only if accepted:
  - add to `apps/api/requirements.txt` / lock because `worker-extraction` uses the API image;
  - do not add Docling, Torch, OpenCV, or GPU image dependencies to the API image.
- [ ] If adding Pillow is rejected, stop and choose a separate lightweight image-crop worker/image path instead. Do not write a partial PNG/JPEG parser by hand.
- [ ] Crop behavior:
  - decode selected page image;
  - apply proven rotation transform or fall back full page;
  - crop padded bbox;
  - validate crop quality before sending;
  - encode to PNG or preserve JPEG only if safe;
  - compute sha256;
  - return `ModelImageInput` with crop bytes.
- [ ] Do not persist crop assets initially. Record crop sha and bbox in raw extraction metadata. This avoids enum/migration churn.
- [ ] Tests:
  - crop image hash differs from full page;
  - crop dimensions match expected padded/clamped bbox;
  - model input hash still validates;
  - full-page fallback remains byte-identical to current behavior.
  - crop generation refuses ambiguous coordinate basis.

### Task 7: Route Visual Input Policy By Semantic Task

- [ ] Add deterministic policy table:
  - line-item/table semantic types default to crop-first when bbox/table geometry is available;
  - observation/KVP summary types default to full-page unless `requires_full_page_image=false` and bbox is credible;
  - `document_observation` page regions default to full-page;
  - `unmatched_region` defaults to full-page.
- [ ] Add document-quality-aware overrides:
  - degraded/low-text/skewed scanned pages prefer full-page or expanded crop;
  - low-resolution page images prefer full-page;
  - landscape/rotated pages crop only after proven normalization.
- [ ] Add continuation-aware overrides:
  - semantic regions with continuation metadata plan per-page inputs;
  - do not collapse multiple continuation pages into a single crop;
  - if the current extraction worker cannot process multiple planned images safely, enqueue per-region/per-page Granite jobs instead of sending multi-image input.
- [ ] Use existing metadata:
  - `requires_full_page_image`
  - `visual_bbox_hint`
  - `visual_bbox_basis`
  - `extraction_scope`
  - `region_source`
  - `docling_table_id`
  - `coverage_role`
  - `continuation_group`
  - `continuation_of`
  - page quality metadata from Phase 8 where available
- [ ] Add planner report into Granite job raw output:
  - `visualInputPlan.mode`
  - `visualInputPlan.scope`
  - `visualInputPlan.pageId`
  - `visualInputPlan.pageNumber`
  - `visualInputPlan.sourcePageImageSha256`
  - `visualInputPlan.inputSha256`
  - `visualInputPlan.bbox`
  - `visualInputPlan.originalBbox`
  - `visualInputPlan.expandedBbox`
  - `visualInputPlan.bboxBasis`
  - `visualInputPlan.rotationPolicy`
  - `visualInputPlan.cropQuality`
  - `visualInputPlan.expansionPolicy`
  - `visualInputPlan.fallbackReason`

### Task 8: Runtime Output-Quality Fallback

- [ ] Add a post-Granite output-usefulness check for crop-mode attempts.
- [ ] Treat these as crop failure, not document failure:
  - empty line items for line-item/table task when model returned valid JSON;
  - empty observations for observation task with expected fields;
  - schema/instruction echo;
  - grid-only output;
  - all-null candidate payload;
  - validation report says no concrete evidence;
  - normalized output has fewer useful facts than the same task's Docling text context strongly predicts.
- [ ] Retry once with `full_page_retry` when:
  - first attempt used crop/expanded crop;
  - model service itself did not hard-fail;
  - retry budget allows;
  - task is not explicitly crop-only.
- [ ] Persist/record both attempts in raw output:
  - `visualInputAttempts[0]` crop attempt metadata and usefulness result;
  - `visualInputAttempts[1]` full-page retry metadata when used;
  - selected attempt reason.
- [ ] Do not allow infinite fallback loops.
- [ ] Tests:
  - valid empty crop output retries full page;
  - schema echo crop output retries full page;
  - noisy grid-only crop output retries full page;
  - successful useful crop does not retry;
  - full-page retry failure remains `needs_review`/job failure according to existing model failure policy.

### Task 9: Evidence Integration

- [ ] Extend `EvidenceContext` with:
  - `visual_input_scope`
  - `visual_input_sha256`
  - `source_page_image_sha256`
  - `bbox`
  - `bbox_basis`
  - `original_bbox`
  - `expanded_bbox`
  - `rotation_policy`
  - `crop_quality`
  - `visual_input_attempt`
- [ ] Pass the selected visual plan into `evidence_context_for_task()` or a new `evidence_context_for_visual_plan()`.
- [ ] Include bbox and visual input hashes in Granite-normalized evidence.
- [ ] Preserve current evidence acceptance semantics:
  - existing page/semantic-region evidence remains concrete;
  - crop evidence with page_id + semantic_region_id + bbox is concrete;
  - source_text-only Granite evidence remains non-concrete.
- [ ] Tests:
  - Granite crop evidence is concrete because it has page/region/bbox;
  - Granite source_text-only evidence is still not concrete.
  - full-page fallback evidence remains page/region grounded but does not invent bbox.
  - retry metadata does not make rejected crop evidence canonical.

### Task 10: Edge-Case Corpus And Fixture Gate

- [ ] Build synthetic/unit fixtures for every row in the edge-case hardening matrix.
- [ ] Add a private/manual GPU fixture checklist covering:
  - rotated page;
  - landscape scan;
  - low-resolution receipt;
  - multi-page table/continuation;
  - form with labels outside row bbox;
  - repeated header/footer;
  - skewed scan;
  - table with missing linked element bbox.
- [ ] The implementation cannot proceed to full corpus validation until the synthetic fixtures pass in both `shadow_full_page` and `planned` mode.

### Task 11: Controlled Runtime Gate

- [ ] Run all unit tests touched by visual input planning.
- [ ] Run current extraction/semantic unit tests with default mode.
- [ ] Run a one-request BMW replay in `shadow_full_page` mode and compare:
  - same image hash sent as current full-page behavior;
  - planner metadata says crop would be selected.
- [ ] Run the same BMW replay in `planned` mode:
  - verify Granite succeeds;
  - verify output has expected service-line candidates;
  - verify crop metadata is recorded.
- [ ] Run a bounded replay of the pre-crash ten-call sequence:
  - full-page mode;
  - planned crop mode.
- [ ] Run the edge-case fixture set in planned mode.
- [ ] Compare full-page versus planned-crop outputs:
  - job failures;
  - empty outputs;
  - candidate counts;
  - line-item counts;
  - observation noise;
  - validation needs-review rate;
  - Granite latency and runtime health.
- [ ] Only after bounded replay passes, rerun the 11-document corpus.

### Task 12: Rollout And Zero-Regression Controls

- [ ] Keep default mode at `shadow_full_page` until corpus proof exists.
- [ ] Add a Compose env default that does not change behavior:
  - `STRUCTURA_GRANITE_VISUAL_INPUT_MODE=shadow_full_page`
- [ ] Enable `planned` only for explicit GPU validation.
- [ ] Add runtime kill switch:
  - `STRUCTURA_GRANITE_VISUAL_INPUT_MODE=full_page`
  - must restore current behavior without rebuild.
- [ ] Add optional per-task override:
  - `STRUCTURA_GRANITE_CROP_SEMANTIC_TYPES=...`
  - default empty until planned mode is validated.
- [ ] Do not change Qwen prompt contracts.
- [ ] Do not change Granite model prompts except if planner metadata requires one sentence clarifying crop/full-page scope.
- [ ] Do not alter extraction planner quotas in this plan.
- [ ] Do not alter canonical promotion, reconciliation, or review policy in this plan.
- [ ] Do not change model placement, Qwen service, Docling worker, or visual embedding services.

## Acceptance Gates

- Default mode is byte-identical for model image inputs compared with current full-page behavior.
- Planner metadata appears in raw Granite output for every Granite extraction.
- Crop mode is opt-in until GPU replay and corpus validation pass.
- Region-level tasks can produce crop inputs from element/table/bbox grounding.
- Page-level tasks still receive full-page inputs.
- Any uncertain coordinate case falls back to full page.
- Rotated and landscape pages are normalized or fall back; no unproven rotation crop is sent.
- Bbox basis is explicit for every crop; unknown basis never crops.
- Missing table bboxes have deterministic fallback order and never produce guessed unsafe crops.
- Continuation tables are handled per page/region and are not silently truncated.
- Tiny, oversized, mostly blank, low-resolution, and boilerplate-contaminated crops are rejected or expanded deterministically.
- Form/KVP crops preserve labels or use full page.
- Table/line-item crops preserve headers/column labels or use full page.
- Crop-mode empty/noisy/schema-echo outputs retry once with full page and record both attempts.
- Granite evidence records page, semantic region, visual input scope, input hash, and bbox when cropped.
- Existing tests for extraction, semantic annotation, model gateway routing, and evidence validation pass.
- GPU validation includes:
  - exact BMW failing request replay;
  - original pre-crash ten-call replay;
  - edge-case fixture set;
  - full 11-document corpus only after bounded replay passes.

## Non-Goals

- Do not optimize Qwen visual token budgets.
- Do not change Docling conversion behavior.
- Do not add OCR or Docling/Torch dependencies to API/extraction images.
- Do not persist crop assets in `document_assets` during the first implementation pass.
- Do not switch all Granite calls to crops blindly.
- Do not use full document images for Granite region extraction.

## Open Questions To Resolve Before Task 6

- Is adding Pillow to the shared API/extraction image acceptable, given the cropper runs in `worker-extraction` but the image is shared with API?
- Should crop bytes be persisted as derived storage objects without `document_assets`, or should a later migration add a first-class `granite_visual_input` asset role?
- Should `visual_bbox_hint` be treated as normalized 0-1000 by contract, or should Qwen/Docling explicitly emit `bbox_basis` before crop mode is enabled?
- What maximum crop/page area ratio should force full-page fallback? Initial recommendation: fallback to full page when padded crop exceeds 70% of page area.
