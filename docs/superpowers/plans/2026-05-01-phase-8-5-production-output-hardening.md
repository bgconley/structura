# Phase 8.5 Production Output Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden Phase 8.5 production outputs after the 20260501T062604Z corpus run without regressing the now-working resident production pipeline.

**Architecture:** Keep Docling, Qwen3-VL-8B FP8 Smart Parse, Granite 4.0 3B Vision, validators, and resident worker orchestration unchanged in this pass. Fix deterministic application seams where successful model outputs become noisy persisted candidates: candidate normalization, observation normalization, and semantic family reconciliation over weak Phase 4 classifications.

**Tech Stack:** Python 3.12, pytest, dataclass DTOs in `lib/extraction/models.py`, extraction normalization in `lib/extraction/normalization.py`, semantic-family reconciliation in `lib/semantic_annotations/semantic_family.py`.

---

## Baseline Evidence

The production-style 11-document run `20260501T062604Z` completed with zero target-queue failures and confirmed the model/runtime path is viable. Remaining defects are output-quality hardening issues, not container-orchestration issues:

- BH Photo and BMW emitted useful lines, but duplicate or sparse duplicate line-item candidates survived normalization.
- MRI and UWM emitted repeated observations, including null-valued fields that are not useful review candidates.
- Generic/table-grid documents emitted noisy observations such as `dimensions` and `cells`.
- Scan Oct 8 persisted as `invoice` despite weak evidence; Phase 4 classification must not remain authoritative when Phase 8.5 semantic reconciliation says the document is generic or unsupported and Docling lacks anchors for the specific Phase 4 family.

## Non-Goals

- Do not alter Qwen or Granite model prompts.
- Do not change model placement, KV cache, image budgets, or worker orchestration.
- Do not delete raw extraction artifacts or provenance.
- Do not add document-specific fixes for any private corpus file.
- Do not make Qwen output canonical facts.

## Files

- Modify: `lib/extraction/normalization.py`
  - Add deterministic line-item candidate dedupe.
  - Add observation suppression/dedupe for empty, repeated, and grid-only observations.
- Modify: `lib/semantic_annotations/semantic_family.py`
  - Let Phase 8.5 semantic reconciliation downgrade weak Phase 4 specific families to `generic` when Qwen reports generic/unsupported/no-target and Docling lacks anchors for the Phase 4 family.
- Modify: `tests/unit/extraction/test_model_output_normalization.py`
  - Add regression tests for sparse duplicate line items, exact duplicate observations, null observations, and grid-only observations.
- Modify: `tests/unit/semantic_annotations/test_semantic_family.py`
  - Add regression tests for weak Phase 4 `invoice` downgrade and supported Phase 4 family retention.

## Task 1: Line-Item Candidate Dedupe

- [x] Add a failing test in `tests/unit/extraction/test_model_output_normalization.py` proving `line_item_candidates_from_extraction()` removes exact duplicate lines and drops sparse duplicates when a richer line with the same description exists.
- [x] Run:

```bash
python -m pytest -q tests/unit/extraction/test_model_output_normalization.py::test_line_item_candidates_drop_exact_and_sparse_duplicates
```

Expected: FAIL before implementation because duplicates are currently returned.

- [x] Implement `_dedupe_line_item_candidates()` in `lib/extraction/normalization.py`.
  - Drop exact duplicates by normalized description, code, quantity, amounts, currency, date, and line type.
  - Drop sparse duplicates when the same normalized description/code has a richer candidate with amounts or quantity.
  - Preserve distinct same-description candidates with different real amounts.
  - Reassign ordinals after dedupe.
- [x] Re-run the focused test. Expected: PASS.

## Task 2: Observation Candidate Suppression And Dedupe

- [x] Add failing tests in `tests/unit/extraction/test_model_output_normalization.py` proving:
  - null/empty observation values are not persisted as review candidates;
  - repeated observations with the same family, field name, value type, and value collapse to one;
  - grid-only observations such as `dimensions` and numeric-only `cells` are suppressed.
- [x] Run each focused test. Expected: FAIL before implementation.
- [x] Implement `_dedupe_observation_candidates()` and helpers in `lib/extraction/normalization.py`.
  - Skip values that are `None`, empty strings, empty lists, or empty dicts.
  - Skip table-shape observations whose field is `dimensions` or `cells` when the value contains no textual content.
  - Dedupe exact normalized observation keys.
  - Preserve evidence and status on the first useful candidate.
- [x] Re-run focused observation tests. Expected: PASS.

## Task 3: Semantic Family Downgrade For Weak Phase 4 Families

- [x] Add a failing test in `tests/unit/semantic_annotations/test_semantic_family.py` proving a Phase 4 `invoice` classification downgrades to `generic` when the semantic document type is `generic_form`, `unsupported_document`, or `no_extraction_target` and Docling lacks invoice anchors.
- [x] Add a companion test proving a supported Phase 4 `invoice` remains `invoice` when Docling contains invoice anchors, even if the semantic document type is generic.
- [x] Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_semantic_family.py
```

Expected: the new downgrade test FAILS before implementation.

- [x] Implement a narrow downgrade branch in `semantic_document_family_decision()`.
  - Only apply to specific Phase 4 families that can over-classify generic documents.
  - Only apply when semantic document type maps to generic/unsupported/no extraction target.
  - Only apply when Docling lacks support anchors for the existing source family.
  - Record reason `semantic_generic_downgrades_unsupported_phase4_family`.
- [x] Re-run semantic-family tests. Expected: PASS.

## Task 4: Regression Sweep

- [x] Run focused unit tests:

```bash
python -m pytest -q tests/unit/extraction/test_model_output_normalization.py tests/unit/semantic_annotations/test_semantic_family.py
```

- [x] Run nearby policy tests:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_target_schema_policy.py tests/unit/extraction/test_reconciliation.py tests/unit/extraction/test_extraction_persistence_policy.py
```

- [x] Inspect `git diff` for accidental prompt/runtime/orchestration changes. Expected: no changes outside the planned files and this plan doc.

## Completion Criteria

- Duplicate and sparse duplicate line items are removed before persistence without losing distinct same-description, different-amount lines.
- Empty/null and grid-only observations do not create review noise.
- Exact duplicate observations collapse deterministically.
- Weak Phase 4 specific families can no longer remain authoritative when Phase 8.5 says generic/unsupported and Docling lacks supporting anchors.
- Tests prove the behavior with synthetic fixtures, not private PDFs.
