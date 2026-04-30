# Phase 8.5 Qwen Semantic Understanding Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-center the Phase 8.5 Qwen3-VL-4B layer on broad, inventory-first semantic document understanding, remove narrow repair drift, and preserve Qwen's visual/layout/table usefulness without letting it produce canonical facts.

**Architecture:** Keep the current Docling -> Qwen semantic manifest -> Granite -> validators/review pipeline. Qwen3-VL-4B owns semantic document understanding and grounded extraction intent; Granite owns targeted candidate extraction; validators and review policy own promotion. Preserve high-recall behavior, structural validation, fallback safety, and semantic-only canary scoring before returning to Granite or full-pipeline tuning.

**Tech Stack:** Python semantic-annotation services, JSON Schema contracts, vLLM OpenAI-compatible vision serving, pytest, GPU semantic canary scripts, existing Phase 8.5 model runtime.

---

## Scope

This plan implements
`docs/superpowers/specs/2026-04-29-phase-8-5-qwen-semantic-planner-generalization-spec.md`.

It supersedes follow-on work where the current branch started drifting into
document-shaped repairs. The goal is not to tune one private PDF. The goal is to
make Qwen3-VL-4B a richer, evidence-grounded semantic understanding layer across
document classes.

## Non-Negotiable Boundaries

1. Qwen is not merely a classifier or minor router. It should use its visual,
   layout, table, OCR-style, and multi-page capabilities to inventory the
   document and propose grounded extraction intent.
2. Qwen does not produce canonical Structura facts. Granite, validators,
   provenance, and review policy still gate candidate extraction and promotion.
3. Normalization may repair structure, but it may not inject semantic intent.
4. Examples and canary expectations are document-class shaped, not
   document-instance shaped.
5. Granite fanout caps must not force Qwen to be sparse. Qwen recall and
   downstream extraction scheduling are separate concerns.

## File Structure

### Existing files to modify

- `lib/semantic_annotations/prompting.py`
  - express Qwen as semantic document understanding plus extraction intent
  - keep inventory-first, class-based, high-recall instructions
- `lib/semantic_annotations/qwen_output_normalization.py`
  - keep structural repairs only; remove semantic-intent injection
- `lib/semantic_annotations/qwen_gateway.py`
  - keep orchestration, fallback, and structured-output handling
- `lib/semantic_annotations/docling_context.py`
  - preserve whole-document context and page-window focus behavior
- `lib/semantic_annotations/docling_audit.py`
  - keep broad document-class evidence only
- `lib/semantic_annotations/manifest_merge.py`
  - preserve broad merge logic and exact page coverage
- `lib/semantic_annotations/service.py`
  - keep Qwen recall separate from Granite enqueue limits
- `scripts/gpu/run_phase8_5_semantic_canary.py`
  - keep Qwen iteration focused on semantic-only scoring
- `tests/unit/semantic_annotations/test_prompting.py`
- `tests/unit/semantic_annotations/test_gateways.py`
- `tests/unit/semantic_annotations/test_docling_audit.py`
- `tests/unit/semantic_annotations/test_docling_context.py`
- `tests/unit/semantic_annotations/test_service.py`
- `tests/unit/scripts/test_phase8_5_semantic_canary.py`

### New files to create

- none required unless prompt examples need to be extracted into a focused
  helper such as `lib/semantic_annotations/prompt_examples.py`

## Task 1: Freeze The Correct Qwen Role And Mark Drift Explicitly

**Files:**
- Modify: `tests/unit/semantic_annotations/test_prompting.py`
- Modify: `tests/unit/semantic_annotations/test_gateways.py`
- Modify: `tests/unit/scripts/test_phase8_5_semantic_canary.py`
- Modify: `docs/superpowers/specs/2026-04-29-phase-8-5-qwen-semantic-planner-generalization-spec.md`

- [ ] Add regression tests that distinguish structural normalization from
      semantic-intent mutation.
- [ ] Add prompt tests that fail if Qwen is described as "only" a classifier or
      if document-instance example names are reintroduced.
- [ ] Add prompt tests that require Qwen's visual/layout/table role to remain
      explicit:
      - page inventory
      - table and weak-table awareness
      - visual/layout signal reporting
      - extraction-scope recommendation
      - cross-page continuation awareness
- [ ] Add canary-test assertions that document-class expectations are allowed,
      but document-instance repair expectations are not.
- [ ] Keep the currently good Qwen behaviors covered:
      - recall-oriented instructions
      - 12-region contract
      - page coverage
      - whole-document context
      - semantic-only scoring

Run:

```bash
python -m pytest -q \
  tests/unit/semantic_annotations/test_prompting.py \
  tests/unit/semantic_annotations/test_gateways.py \
  tests/unit/scripts/test_phase8_5_semantic_canary.py
```

Success criteria:

- the suite clearly separates macro Qwen behavior from narrow repair drift
- future edits cannot quietly reintroduce document-instance hacks
- Qwen's role remains semantic document understanding, not a minimized router

## Task 2: Rework The Prompt Into A Semantic Inventory Contract

**Files:**
- Modify: `lib/semantic_annotations/prompting.py`
- Modify: `tests/unit/semantic_annotations/test_prompting.py`

- [ ] Keep the `phase8_5-semantic-smart-v3` recall orientation, but tighten the
      top-level prompt around generic Qwen behavior:
      - account for every page
      - inventory first, route second
      - inspect layout, tables, visual signals, OCR-like text, and page roles
      - emit all materially extractable grounded regions
      - prefer omission safety over sparse routing
      - record uncertainty rather than forcing a brittle document family
- [ ] Replace document-instance few-shot naming such as a specific private
      service invoice with class-based examples such as
      `vehicle_service_invoice`.
- [ ] Remove family-specific top-level imperative prose that tells the model how
      one class must be repaired post hoc.
- [ ] Keep examples compact but semantically rich:
      - page roles
      - document-family candidates
      - expected field names
      - routing reasons
      - weak-table handling
      - continuation handling
      - full-page/table/element/crop extraction scope
      - unsupported/generic observation behavior
- [ ] Ensure no prompt section implies canonical extraction or family-specific
      normalization.

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_prompting.py
```

Success criteria:

- prompt behavior stays broad and contract-led
- examples remain class-based and non-canonical
- Qwen is explicitly instructed to use document understanding, not just classify

## Task 3: Remove Semantic-Intent Repairs From Normalization

**Files:**
- Modify: `lib/semantic_annotations/qwen_output_normalization.py`
- Modify: `tests/unit/semantic_annotations/test_gateways.py`

- [ ] Remove or refactor normalization behavior that injects semantic intent,
      including family-specific continuation-group or full-page-image repairs.
- [ ] Keep only structural repairs:
      - duplicate collapse
      - wrapper normalization
      - out-of-window filtering
      - single-page unknown-page repair
      - bounded field cleanup
- [ ] Add tests proving normalization may repair structure but may not invent:
      - semantic types
      - continuation groups
      - `requires_full_page_image`
      - synthetic semantic regions
- [ ] Preserve normalization telemetry for structural repairs so canary runs can
      still explain what changed.

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_gateways.py
```

Success criteria:

- normalization becomes generic and defensible
- semantic intent remains Qwen-owned

## Task 4: Preserve Whole-Document Context And Page-Window Safety

**Files:**
- Modify: `lib/semantic_annotations/qwen_gateway.py`
- Modify: `lib/semantic_annotations/docling_context.py`
- Modify: `tests/unit/semantic_annotations/test_gateways.py`
- Modify: `tests/unit/semantic_annotations/test_docling_context.py`

- [ ] Preserve whole-document Docling context in both multi-image and one-page
      fallback requests.
- [ ] Preserve focused-page filtering at the adapter boundary so fallback output
      cannot violate page coverage.
- [ ] Add or keep tests proving:
      - focused-page windows still receive whole-document outline context
      - out-of-window pages are filtered structurally
      - page coverage remains exact
      - fallback reasons remain visible in manifest confidence
- [ ] Avoid adding any family-specific logic to this layer.

Run:

```bash
python -m pytest -q \
  tests/unit/semantic_annotations/test_gateways.py \
  tests/unit/semantic_annotations/test_docling_context.py
```

Success criteria:

- fallback safety remains intact
- no new semantic behavior is hidden in gateway orchestration

## Task 5: Keep Docling Evidence Broad, Not One-Off

**Files:**
- Modify: `lib/semantic_annotations/docling_audit.py`
- Modify: `tests/unit/semantic_annotations/test_docling_audit.py`

- [ ] Review current anchor vocab and thresholds for broad document-class value.
- [ ] Keep class-level evidence that helps multiple documents in the same
      family.
- [ ] Reject or remove evidence rules that exist only to make a single document
      pass.
- [ ] Add tests that describe family-level behavior, not vendor-instance
      behavior.
- [ ] Document a guardrail in code comments or tests: new anchor vocab should be
      justified by multi-document class evidence, not a single corpus example.

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_docling_audit.py
```

Success criteria:

- Docling audit stays useful without becoming a patch table for private docs

## Task 6: Expand Semantic Canary Scoring For Qwen Understanding

**Files:**
- Modify: `scripts/gpu/run_phase8_5_semantic_canary.py`
- Modify: `tests/unit/scripts/test_phase8_5_semantic_canary.py`
- Modify: `tests/fixtures/semantic_annotations/semantic_canary_expectations.example.json`

- [ ] Keep the semantic-only harness as the primary Qwen iteration tool.
- [ ] Score document-class outcomes rather than document-instance repair shapes.
- [ ] Ensure the scorecard can assert:
      - page coverage
      - page-role coverage
      - competing document-family candidates
      - minimum region count
      - required semantic classes
      - forbidden masquerade
      - weak-table awareness
      - visual/layout signal awareness
      - continuation presence when class-appropriate
      - full-page/table/element/crop extraction scope when visually necessary
      - normalization repair counts limited to structural repairs
- [ ] Add tests proving expectation files cannot encode hidden assumptions about
      one exact document's post-normalization semantics.

Run:

```bash
python -m pytest -q tests/unit/scripts/test_phase8_5_semantic_canary.py
```

Success criteria:

- canary expectations stay class-level
- the harness remains the primary Qwen tuning gate
- semantic quality is measured before Granite is blamed or tuned

## Task 7: Keep Qwen Recall Separate From Granite Fanout

**Files:**
- Modify: `lib/semantic_annotations/service.py`
- Modify: `tests/unit/semantic_annotations/test_service.py`

- [ ] Confirm the service layer still treats Qwen recall and Granite enqueue as
      separate concerns.
- [ ] Keep Qwen free to emit a richer semantic region set even when downstream
      Granite enqueue remains capped.
- [ ] Ensure service tests prove downstream pruning happens transparently and
      does not require Qwen sparsity.
- [ ] Do not reintroduce document-family-specific routing overrides here.

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_service.py
```

Success criteria:

- Qwen richness is not silently undone by service-layer assumptions

## Task 8: GPU Semantic Gate Before Any More Granite Work

**Files:**
- No code changes required
- Evidence output under `/srv/structura/objects/exports/phase85-runs/`

- [ ] Rebuild and restart only the services affected by Qwen semantic changes.
- [ ] Run the semantic-only canary on the focused private set first:
      - retail order example
      - vehicle service invoice representative example
      - medical denial/EOB example
- [ ] Then run the broader private semantic canary corpus.
- [ ] Capture and compare:
      - competing document-family candidates
      - selected document type
      - page roles
      - region count
      - weak-table behavior
      - visual/layout signal behavior
      - extraction-scope choices
      - continuation behavior
      - fallback rate
      - normalization telemetry
- [ ] Do not move back to Granite tuning until the Qwen semantic gate is clean
      enough across multiple classes.

Run:

```bash
STRUCTURA_MODEL_MODE=live \
STRUCTURA_MODEL_QWEN_SEMANTIC_URL=http://127.0.0.1:8104 \
/tank/venvs/structura/bin/python scripts/gpu/run_phase8_5_semantic_canary.py \
  --document-id <ids...> \
  --expectations-json <private_expectations.json> \
  --json-output /srv/structura/objects/exports/phase85-runs/<report>.json
```

Success criteria:

- improvements hold across classes, not just one example
- no new document-instance repair path is needed to keep the canary useful
- Qwen demonstrates semantic inventory quality before Granite is evaluated

## Task 9: Documentation And OpenWolf Cleanup

**Files:**
- Modify: `STRUCTURA_PHASE_8_5_IMPLEMENTATION_PLAN.md`
- Modify: `.wolf/cerebrum.md`
- Modify: `.wolf/buglog.json`

- [ ] Record that the Qwen generalization pass keeps the high-recall semantic
      understanding contract but rejects narrow semantic-intent repair logic.
- [ ] Update OpenWolf decisions and bug entries so a new session sees the same
      macro guardrail.
- [ ] Document that private-corpus examples are representative failure classes,
      not bespoke targets.
- [ ] Document that Qwen3-VL-4B is expected to use visual/layout/table
      understanding while still not producing canonical facts.

Run:

```bash
python -m json.tool .wolf/buglog.json >/dev/null
```

Success criteria:

- the repo guidance and session memory reflect the macro contract clearly

## Verification Matrix

Local verification:

```bash
python -m pytest -q tests/unit/semantic_annotations \
  tests/unit/scripts/test_phase8_5_semantic_canary.py \
  tests/unit/extraction/test_semantic_region_routing.py \
  tests/integration/test_phase8_5_semantic_annotations.py
ruff check lib/semantic_annotations scripts/gpu tests/unit/semantic_annotations tests/unit/scripts
mypy lib/semantic_annotations scripts/gpu/run_phase8_5_semantic_canary.py
python scripts/validate_contracts.py
```

GPU verification:

```bash
/tank/venvs/structura/bin/python -m pytest -q \
  tests/unit/semantic_annotations/test_prompting.py \
  tests/unit/semantic_annotations/test_gateways.py \
  tests/unit/semantic_annotations/test_docling_audit.py \
  tests/unit/semantic_annotations/test_service.py \
  tests/unit/scripts/test_phase8_5_semantic_canary.py
```

## Definition Of Done

This pass is done only when:

1. Qwen remains high-recall, inventory-first, and semantically rich
2. page coverage and whole-document fallback safety remain intact
3. visual/layout/table signal reporting is explicit in prompt and scoring
4. family-specific semantic-intent repairs are removed
5. examples are class-based instead of document-instance based
6. semantic-only canary scoring stays the primary Qwen tuning loop
7. the private corpus improves across multiple document classes without adding
   new document-instance hacks
