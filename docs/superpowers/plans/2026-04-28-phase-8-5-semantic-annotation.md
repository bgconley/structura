# Phase 8.5 Semantic Annotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Docling-grounded Qwen semantic annotation layer that plans Granite targeted extraction without replacing Docling as the physical parser or treating Qwen output as canonical facts.

**Architecture:** Docling remains the canonical source-to-structure compiler. Qwen3-VL 2B/8B produces semantic manifests grounded to Docling page, element, and table IDs; Granite 4.0 3B Vision consumes those manifests for targeted structured extraction. Validators, provenance, review tasks, and canonical promotion remain the truth gate.

**Tech Stack:** FastAPI/Python, PostgreSQL/pgvector baseline migrations, existing pipeline job worker spine, existing `lib/model_runtime` OpenAI-compatible vision clients, Docling page/element/table artifacts, React/Vite UI.

---

## Scope And Non-Goals

This plan extends Phase 8.5. It does not start Phase 9 answer synthesis. It does not replace Docling with a VLM parser. It does not promote Qwen semantic annotation values as canonical facts. It does not require both Qwen2B and Qwen8B to run concurrently on one 24GB card before benchmark evidence exists.

## File Structure

- Create `database/075_phase8_5_semantic_annotations.sql`: semantic annotation tables, current-row constraints, indexes, and enum-safe check constraints.
- Modify `lib/db/migrations.py`: include migration 075 in the baseline runner.
- Create `lib/semantic_annotations/models.py`: dataclasses and value objects for manifests, pages, regions, quality mode, Granite task, grounding refs, and validation errors.
- Create `lib/semantic_annotations/policy.py`: semantic type/task allowlists, escalation policy, manifest validation, and high-quality trigger logic.
- Create `lib/semantic_annotations/docling_context.py`: load compact Docling context from parsed pages/elements/tables for model prompting.
- Create `lib/semantic_annotations/repository.py`: persistence and atomic supersede/load operations for manifests, pages, and regions.
- Create `lib/semantic_annotations/service.py`: orchestrates semantic annotation jobs, model calls, manifest validation, persistence, and targeted extraction job enqueueing.
- Create `lib/semantic_annotations/fixture_gateway.py`: deterministic semantic annotator for CI and fixture mode.
- Create `lib/semantic_annotations/qwen_gateway.py`: live Qwen semantic annotation gateway using existing model runtime clients.
- Create `workers/semantic_annotations/worker.py`: queue consumer for `semantic-annotation` jobs.
- Modify `workers/docling/worker.py` or Docling service completion path: enqueue semantic annotation after successful parse when smart parse is enabled.
- Modify `workers/extraction/worker.py` and `lib/extraction/service.py`: accept optional semantic region task context and preserve Granite targeted extraction provenance.
- Modify `lib/extraction/gateways/_vision.py`: include compact semantic task context in Granite prompt/request when provided.
- Modify `lib/model_runtime/profiles.py`: add `qwen3-vl-2b-semantic:v1` and `qwen3-vl-8b-semantic-hq:v1` profiles.
- Modify `compose.yaml`: add `worker-semantic-annotations` service and pass model profile/URL settings.
- Modify `apps/web/src/components/*` and `apps/web/src/api.ts`: expose Smart Parse status, High Quality Pass action, and semantic manifest diagnostics.
- Add tests under `tests/unit/semantic_annotations/`, `tests/integration/test_phase8_5_semantic_annotations.py`, and e2e/live specs after API/UI surfaces exist.

## Task 1: Database Foundation

**Files:**
- Create: `database/075_phase8_5_semantic_annotations.sql`
- Modify: `lib/db/migrations.py`
- Modify: `database/README.md`
- Test: `tests/unit/test_migrations.py`

- [ ] **Step 1: Write failing migration test**

Add a test that asserts `075_phase8_5_semantic_annotations.sql` is in `BASELINE_SQL_FILES`, and that the SQL creates `document_semantic_annotations`, `page_semantic_annotations`, and `semantic_region_annotations`.

Run: `python -m pytest -q tests/unit/test_migrations.py`
Expected: FAIL because migration 075 is not present.

- [ ] **Step 2: Add migration SQL**

Create the three tables with:
- document-level manifest rows;
- page annotation rows linked to one manifest and one `document_pages` row;
- region annotation rows linked to one manifest, optional page annotation, optional `document_elements`, optional `document_tables`;
- one-current partial unique index per document/profile/quality mode;
- JSONB manifest/confidence/model metadata;
- status values `pending`, `succeeded`, `failed`, `superseded`;
- quality modes `smart`, `high_quality`, `rescue`;
- review-required and unmatched-region fields.

- [ ] **Step 3: Wire baseline migration**

Add `075_phase8_5_semantic_annotations.sql` to `BASELINE_SQL_FILES` after `074_phase7_deadline_status_waived.sql`.

- [ ] **Step 4: Verify**

Run: `python -m pytest -q tests/unit/test_migrations.py`
Expected: PASS.

## Task 2: Semantic Annotation Contracts

**Files:**
- Create: `lib/semantic_annotations/__init__.py`
- Create: `lib/semantic_annotations/models.py`
- Create: `lib/semantic_annotations/policy.py`
- Test: `tests/unit/semantic_annotations/test_policy.py`

- [ ] **Step 1: Write failing policy tests**

Cover:
- valid manifests can reference Docling page/element/table IDs;
- unknown Granite tasks are rejected;
- unknown semantic types are rejected;
- ungrounded regions are allowed only as `unmatched_region` with `review_required=True`;
- Qwen-proposed values are tagged as routing/planning metadata, not canonical facts;
- high-quality triggers fire for validation failure, low confidence, poor OCR, ambiguous type, and important medical/legal/financial/tax documents.

Run: `python -m pytest -q tests/unit/semantic_annotations/test_policy.py`
Expected: FAIL because package does not exist.

- [ ] **Step 2: Implement models**

Define focused dataclasses for `SemanticGroundingRef`, `SemanticRegionAnnotation`, `PageSemanticAnnotation`, `DocumentSemanticManifest`, `SemanticAnnotationRequest`, and `SemanticAnnotationResult`.

- [ ] **Step 3: Implement policy validation**

Add explicit allowlists for semantic types and Granite tasks. Validation must be deterministic and return actionable errors without importing web, DB, or model-runtime modules.

- [ ] **Step 4: Verify**

Run: `python -m pytest -q tests/unit/semantic_annotations/test_policy.py`
Expected: PASS.

## Task 3: Docling Context Builder

**Files:**
- Create: `lib/semantic_annotations/docling_context.py`
- Test: `tests/unit/semantic_annotations/test_docling_context.py`

- [ ] **Step 1: Write failing tests**

Cover compact context construction from `ExtractionSourceDocument`: page IDs, page numbers, image hashes, element IDs/bboxes/types where available, table IDs/indexes, snippets, and quality metadata. Assert raw full-document text is not dumped into model context.

Run: `python -m pytest -q tests/unit/semantic_annotations/test_docling_context.py`
Expected: FAIL because builder does not exist.

- [ ] **Step 2: Implement context builder**

Build bounded per-page context using existing parsed page/element/table dataclasses. Enforce max snippet lengths and omit raw object URIs.

- [ ] **Step 3: Verify**

Run: `python -m pytest -q tests/unit/semantic_annotations/test_docling_context.py`
Expected: PASS.

## Task 4: Repository And Atomic Persistence

**Files:**
- Create: `lib/semantic_annotations/repository.py`
- Test: `tests/integration/test_phase8_5_semantic_annotations.py`

- [ ] **Step 1: Write failing integration tests**

Using the integration DB runner, create a parsed document with pages/elements/tables, persist a manifest, assert:
- previous current manifest is superseded atomically;
- page and region annotations persist with Docling refs;
- invalid cross-document refs fail;
- load-current returns only the active manifest for document/profile/quality mode.

Run: `STRUCTURA_TEST_DATABASE_URL=... python -m pytest -q tests/integration/test_phase8_5_semantic_annotations.py`
Expected: FAIL because repository does not exist.

- [ ] **Step 2: Implement repository**

Use transaction-scoped cursor functions where possible. Do not open hidden independent transactions for operations that must commit together.

- [ ] **Step 3: Verify**

Run integration test through `scripts/run_integration_tests.py`.
Expected: PASS for the semantic annotation test.

## Task 5: Semantic Annotation Gateways

**Files:**
- Create: `lib/semantic_annotations/fixture_gateway.py`
- Create: `lib/semantic_annotations/qwen_gateway.py`
- Modify: `lib/model_runtime/profiles.py`
- Test: `tests/unit/semantic_annotations/test_gateways.py`
- Test: `tests/unit/model_runtime/test_profiles.py`

- [ ] **Step 1: Write failing gateway/profile tests**

Assert:
- profile registry includes `qwen3-vl-2b-semantic:v1` and `qwen3-vl-8b-semantic-hq:v1`;
- fixture gateway emits explicit fixture provenance;
- live Qwen gateway emits truthful Qwen2B/Qwen8B provenance;
- malformed model output fails validation instead of persisting.

Run: `python -m pytest -q tests/unit/semantic_annotations/test_gateways.py tests/unit/model_runtime/test_profiles.py`
Expected: FAIL because profiles/gateways are absent.

- [ ] **Step 2: Implement gateways**

The fixture gateway must be deterministic and explicitly named as fixture. The live gateway must use `VisionGenerateRequest`, include bounded Docling context, include page images, and validate response JSON before returning.

- [ ] **Step 3: Verify**

Run: `python -m pytest -q tests/unit/semantic_annotations/test_gateways.py tests/unit/model_runtime/test_profiles.py`
Expected: PASS.

## Task 6: Semantic Annotation Service And Worker

**Files:**
- Create: `lib/semantic_annotations/service.py`
- Create: `workers/semantic_annotations/__init__.py`
- Create: `workers/semantic_annotations/worker.py`
- Modify: `compose.yaml`
- Test: `tests/unit/semantic_annotations/test_service.py`
- Test: `tests/unit/test_compose_model_profiles.py`

- [ ] **Step 1: Write failing service tests**

Assert:
- fixture mode uses fixture gateway;
- live/required mode uses Qwen gateway;
- successful annotation persists manifest and enqueues Granite targeted extraction jobs;
- failed annotation records failed status and does not enqueue extraction;
- high-quality request uses Qwen8B profile.

Run: `python -m pytest -q tests/unit/semantic_annotations/test_service.py tests/unit/test_compose_model_profiles.py`
Expected: FAIL because service/worker/compose service are absent.

- [ ] **Step 2: Implement service and worker**

Claim `semantic-annotation` queue jobs, load source document, call gateway, validate manifest, persist atomically, enqueue targeted `extract` jobs with semantic region IDs in payload.

- [ ] **Step 3: Wire Compose**

Add `worker-semantic-annotations` behind extraction/search model profiles with a health port and model URL/profile settings.

- [ ] **Step 4: Verify**

Run service tests and `docker compose --profile extraction --profile search --profile visual --profile models-placeholder config -q`.
Expected: PASS.

## Task 7: Enqueue Semantic Annotation After Docling Parse

**Files:**
- Modify: `workers/docling/service.py`
- Modify: `workers/docling/worker.py`
- Test: `tests/integration/test_phase8_5_semantic_annotations.py`

- [ ] **Step 1: Write failing integration test**

Assert successful Docling parse completion enqueues exactly one `semantic_annotate` job when smart parse is enabled, and does not enqueue when disabled.

Run integration test.
Expected: FAIL because no enqueue path exists.

- [ ] **Step 2: Implement enqueue seam**

After successful parse persistence and preview refresh, enqueue semantic annotation as a separate queue job. Preserve Docling as independently successful even if enqueue fails only when job service is down; record failure in job health/error path.

- [ ] **Step 3: Verify**

Run integration test.
Expected: PASS.

## Task 8: Granite Targeted Extraction From Semantic Regions

**Files:**
- Modify: `lib/extraction/models.py`
- Modify: `lib/extraction/service.py`
- Modify: `lib/extraction/gateways/_vision.py`
- Modify: `workers/extraction/worker.py`
- Test: `tests/unit/extraction/test_model_gateways.py`
- Test: `tests/integration/test_phase8_5_semantic_annotations.py`

- [ ] **Step 1: Write failing tests**

Assert `extract` jobs with `semantic_region_id` load region context, include semantic task instructions in Granite prompts, persist provenance linking candidate facts to semantic region metadata, and remain review-required when validation fails.

Run targeted tests.
Expected: FAIL because extraction ignores semantic region payload.

- [ ] **Step 2: Implement semantic extraction context**

Add optional semantic task context to extraction source/gateway request. Keep routes thin and service orchestration explicit.

- [ ] **Step 3: Verify**

Run targeted unit/integration tests.
Expected: PASS.

## Task 9: Rescue And High Quality Orchestration

**Files:**
- Modify: `lib/semantic_annotations/policy.py`
- Modify: `lib/semantic_annotations/service.py`
- Modify: `lib/extraction/service.py`
- Test: `tests/unit/semantic_annotations/test_policy.py`
- Test: `tests/integration/test_phase8_5_semantic_annotations.py`

- [ ] **Step 1: Write failing tests**

Assert rescue is requested when Granite output fails schema validation, totals conflict, required fields are missing, confidence is low, OCR/page quality is poor, or the document is important medical/legal/financial/tax material.

Run targeted tests.
Expected: FAIL for missing rescue orchestration.

- [ ] **Step 2: Implement rescue policy**

Schedule `semantic_annotate` with `quality_mode=rescue` and Qwen8B profile when policy triggers. Do not loop indefinitely; cap rescue attempts per document/profile.

- [ ] **Step 3: Verify**

Run targeted tests.
Expected: PASS.

## Task 10: API And UI Surfaces

**Files:**
- Create: `apps/api/structura_api/routes_semantic_annotations.py`
- Modify: `apps/api/structura_api/main.py`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/components/DocumentViewer.tsx` or focused viewer child component
- Test: `tests/integration/test_phase8_5_semantic_annotations.py`
- Test: `tests/e2e/phase8.spec.ts`

- [ ] **Step 1: Write failing API/UI tests**

Assert users can fetch current semantic manifest for readable documents, cannot fetch unreadable documents, can request High Quality Pass through CSRF-protected mutation, and see semantic diagnostics/evidence jumps in viewer.

Run targeted tests.
Expected: FAIL because route/UI is absent.

- [ ] **Step 2: Implement thin API route**

Routes perform auth/readability/CSRF/dependency wiring only. Services own enqueue/load behavior.

- [ ] **Step 3: Implement UI affordance**

Add Smart Parse status, High Quality Pass button, semantic region summary, and evidence jump wiring without embedding business logic in components.

- [ ] **Step 4: Verify**

Run targeted integration and e2e tests.
Expected: PASS.

## Task 11: Runtime Docs, Gates, And GPU Validation

**Files:**
- Modify: `STRUCTURA_PHASE_8_5_IMPLEMENTATION_PLAN.md`
- Modify: `STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md`
- Modify: `docs/adr/0004-phase-8-5-local-model-runtime.md`
- Modify: `docs/model-runtime/phase8_5_gpu_validation.md`
- Modify: `scripts/gpu/phase8_5_model_smoke.sh`
- Modify: `README.md`
- Test: canonical GPU gates

- [ ] **Step 1: Update docs**

Document semantic annotation as a Phase 8.5 prerequisite for Phase 9 analysis, including model placement, Docling/Qwen/Granite responsibilities, provenance rules, and high-quality/rescue policies.

- [ ] **Step 2: Extend GPU smoke**

Smoke must prove Qwen semantic annotation, Granite targeted extraction, and model-backed corpus evidence when live models are available.

- [ ] **Step 3: Run local gates**

Run:
`python -m ruff check .`
`python -m ruff format --check .`
`python scripts/validate_contracts.py`
`python -m pytest -q tests/unit`
`python scripts/run_golden_corpus.py`
`python scripts/run_model_corpus.py --manifest tests/fixtures/model_corpus/phase8_5_model_manifest.example.json`
`make sast`
`python -m pyright --pythonpath "$(which python)" apps lib workers scripts`
`python -m mypy apps/api lib workers scripts`

- [ ] **Step 4: Run GPU gates**

Commit, push, pull on GPU node, then run canonical GPU lint/type/test/security/build/compose/live Playwright gates according to `AGENTS.md`.

## Self-Review Checklist

- Docling remains physical parse truth.
- Qwen semantic annotations are planning metadata only.
- Granite is the structured extractor for Docling-grounded targets.
- Validators/review/canonical fact promotion remain the truth gate.
- Phase 9 analysis is blocked from citing semantic manifests as source evidence.
- No raw document text, prompts, model responses, object URIs, or image paths are logged.
- Routes remain thin.
- DB writes that must be atomic use one transaction.
- Tests cover invalid grounding, unknown tasks/types, fixture provenance, live provenance, high-quality/rescue, ACL, and targeted extraction.
