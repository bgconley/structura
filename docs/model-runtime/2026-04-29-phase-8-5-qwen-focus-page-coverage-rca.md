# Phase 8.5 Qwen3-VL-4B Focus-Page Coverage RCA

Date: 2026-04-29

## Summary

During Phase 8.5 live Smart Parse validation, the MRI Anthem denial PDF failed during semantic annotation even though the Qwen3-VL-4B service returned HTTP 200 responses. The application rejected the model output because semantic annotation page coverage did not exactly match Docling pages.

The failure was not caused by Docling image resizing or cropped page images. The observed MRI page images were full-page renderings, and the problematic page was a Docling-proven blank/no-signal page. The deeper problem was that Structura had allowed fallback behavior to become the recovery mechanism for primary Smart Parse contract failures. That masked whether Qwen3-VL-4B could satisfy the intended 4-image semantic fan-in contract.

The corrected behavior is: Smart Parse runs the primary Qwen3-VL-4B 4-image window path, keeps whole-document Docling context, constrains output to the current focus/input pages, and requires every focus page to be represented in `pages[]`, including blank or no-target pages. Coverage/context/truncation failures no longer trigger one-page fallback.

## Impact

Observed impact:

- The full private corpus run could not proceed past the first MRI document.
- The semantic annotation worker persisted a generic semantic job failure, while the direct gateway reproduction showed the true validation error: page coverage mismatch.
- The old fallback path risked turning primary contract defects into one-page window behavior, making later classification/routing issues harder to diagnose.

Potential impact if left unresolved:

- Short PDFs could silently change behavior depending on fallback outcome.
- Longer PDFs could lose semantic continuity if one-page fallback became the normal recovery path.
- Document-family voting and Granite routing could be influenced by page-window artifacts instead of the primary semantic contract.

## Root Cause

The root cause was an incomplete focus-page contract between Docling context, Qwen3-VL-4B image windows, and semantic manifest validation.

For documents longer than the configured image fan-in, Structura sends Qwen a chunk of page images while also providing whole-document Docling context. Before the fix, the prompt/context did not make the boundary strict enough:

- `document.pageOutline` was useful as context but could leak into output `pages[]`.
- Qwen could output page annotations for non-focus pages or omit a focus page.
- Blank/no-target pages were not explicitly required to appear in `pages[]`.
- The gateway had automatic one-page fallback for page coverage, context length, and truncation failures.

That combination made fallback look like a reliability feature, but it was actually hiding the primary-path contract problem.

## Contributing Factors

- Qwen3-VL-2B previously ran most short PDFs in a 4-image request, so the one-page behavior introduced during the Qwen3-VL-4B swap changed the semantic input shape.
- Whole-document Docling context is necessary for classification and semantic boundaries, but it must be marked as context-only when the model is producing output for a focus window.
- The live failure surfaced on a blank/no-signal page. A model may reasonably omit an empty page unless the contract explicitly requires structural page coverage.
- The corpus runner initially reported only a worker-level semantic failure. Direct gateway reproduction was required to expose the page coverage validation error.

## Corrective Actions

### 1. Remove Behavioral One-Page Fallback

Commit: `7b5fba4` (`Tighten Qwen focus-page semantic contract`)

`QwenSemanticAnnotationGateway` no longer falls back to one-page windows for:

- page coverage mismatch,
- context length rejection,
- truncated model response.

Those failures now remain primary-path failures that must be investigated directly.

### 2. Add A Strict Focus-Page Contract

Commit: `7b5fba4`

`lib/semantic_annotations/docling_context.py` now includes `document.focusPageContract`:

- `allowedPageIds`
- `allowedPageNumbers`
- `pagesArrayMustMatchFocusPages`
- `pageOutlineIsContextOnly`

`lib/semantic_annotations/prompting.py` now instructs Qwen that when `focusPages` is present:

- `document.pageOutline` is context-only,
- `pages[]` must contain exactly the focus/input pages,
- regions must ground only to focus/input pages.

### 3. Require Blank/No-Target Page Coverage

Commit: `344b826` (`Fill blank Qwen focus pages structurally`)

The prompt now says blank or no-target focus pages must still emit one `pages[]` object with:

- `extraction_usefulness: "none"`
- `has_structured_targets: false`
- no regions.

The normalizer also has a narrow structural safety net: if Docling proves a missing focus page is blank/no-signal, and there are no elements, tables, text, or model regions for that page, it can fill a `no_extraction_target` page annotation and record normalization telemetry. Nonblank missing pages still fail coverage validation.

This is not behavioral fallback. It does not retry or change image fan-in. It only preserves structural manifest coverage for Docling-proven blank pages.

## Validation Evidence

### Direct MRI Semantic Probe

Document:

- `MRI Anthem Denial 01-26.pdf`
- document ID: `60a95828-096d-47dd-8662-7dea27a420d2`
- Docling source: 12 pages, 169 elements, 1 table

Result after `344b826`:

- Qwen3-VL-4B Smart Parse completed through three 4-page windows.
- Manifest contained all 12 pages.
- Manifest contained 7 semantic regions.
- Document type resolved to `medical_eob`.
- No `fallback_reason` was present in manifest confidence.

### Per-Window Probe

The MRI document was probed in 4-page windows:

- pages 1-4 returned pages 1, 2, 3, 4 with 3 regions.
- pages 5-8 returned pages 5, 6, 7, 8 with 4 regions.
- pages 9-12 returned pages 9, 10, 11, 12 with 0 regions.

The important observation is that pages 5-8 returned page 8 directly from Qwen after the blank/no-target prompt change. The structural blank-page normalization did not fire in that live probe because there was no `confidence.normalization` marker.

## Implications

### Short Documents

Short documents up to the configured image fan-in should run as one primary semantic request. If they fail page coverage, that is a real contract or model-output defect. The system should not hide it by switching to one-page behavior.

### Longer Documents

Longer documents still run in bounded 4-page Qwen windows, but every window receives whole-document Docling context. The contract now separates:

- context pages: useful for classification and semantic continuity,
- focus pages: the only pages allowed in `pages[]` and region grounding.

This preserves document-level awareness without allowing non-focus pages to leak into output.

### Complex Documents

Complex documents may still expose semantic routing or classification gaps. Those should be investigated as Qwen planner-contract problems, Docling context/projection problems, or Granite routing problems. They should not be routed around with fallback.

Future probes should track whether failures come from:

- missing focus-page coverage,
- out-of-window output leakage,
- insufficient Docling context,
- bad document-family voting,
- Granite target-schema mismatch,
- runtime/model service errors.

## Follow-Up Rules

- Do not reintroduce one-page fallback as a normal Smart Parse recovery path.
- Treat Qwen coverage failures as primary-path defects unless the missing page is Docling-proven blank/no-signal and the structural normalizer records that bounded repair.
- Keep Qwen3-VL-4B at the intended 4-image semantic fan-in while runtime capacity supports it.
- Keep whole-document Docling context, but enforce focus-page output boundaries.
- When corpus validation fails, reproduce the direct semantic gateway call before changing fallback or routing behavior.

