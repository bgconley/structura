# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-06-10T20:50:43.293Z
> Files: 530 tracked | Anatomy hits: 0 | Misses: 0

## ../../../../tmp/

- `repro_e3_empty_baseline.py` — Repro: empty-baseline + Qwen failure under STRUCTURA_DETERMINISTIC_PLANNER. (~1423 tok)

## ../../../../tmp/structura-e0-capture/

- `bmw_region_obs.sql` — Declares LIKE (~340 tok)
- `bmw_values.sql` (~368 tok)
- `claim_timeout_repro.py` — Repro: flag-on degradation swallows first-attempt retryable ModelTimeoutError. (~1535 tok)
- `corpus_inventory.sql` (~182 tok)
- `e2_lane_reasons.sql` (~218 tok)
- `e3_fingerprints.sql` (~215 tok)
- `element_bbox.sql` (~71 tok)
- `gen_fixtures.py` — Generate sanitized text-lane grid fixtures mirroring live corpus shapes. (~1899 tok)
- `kvp_expected_fields.sql` — Declares IN (~207 tok)
- `kvp_expected_fields2.sql` — Declares IN (~223 tok)
- `lane_reasons.sql` (~142 tok)
- `markdown_check.sql` (~122 tok)
- `mri_check.sql` (~211 tok)
- `repeat_check.sql` (~235 tok)
- `repeat_check2.sql` (~336 tok)
- `repro_anchor_claim.py` — Verify claim: adjacency anchor inexactness + 80-char truncation. (~959 tok)
- `repro_band_rows.py` — Adversarial repro: do Docling row_section band rows become canonical line items? (~1554 tok)
- `repro_baseline_covered.py` — Repro: does a table-grounded billing_summary kvp Qwen region suppress the (~1900 tok)
- `repro_e2_date.py` — Repro: unparseable-but-regex-admitted date spans vanish between envelope and claims. (~1055 tok)
- `repro_e2_receipt_kvp.py` — Repro: receipt_payment_summary KVP region with real corpus expected_fields. (~2545 tok)
- `repro_e3_claim.py` — Repro for the E3 claim: type-granular covered check makes docling-tagged (~2132 tok)
- `repro_e3_eviction.py` — E3 c08a3ee: does the invariant's re-appended duplicate pair evict other (~1526 tok)
- `repro_e3_invariant_paths.py` — Repro: which paths make apply_baseline_invariant append regions (E3, c08a3ee). (~2196 tok)
- `repro_e3_retryable_degrade.py` — Repro: flag-on E3 degrades permanently on FIRST retryable transient error. (~1823 tok)
- `repro_kvp_adjacency.py` — Repro: verify reviewer claims about adjacency pairing in span_candidates. (~1229 tok)
- `repro_kvp_money.py` — Repro: registry money typing mints wrong money facts from digit-bearing text spans. (~839 tok)
- `repro_kvp_projection.py` — Repro: KVP lane document_observation projection rows vs vision parity. (~1112 tok)
- `repro_ordinal_ties.py` — Repro: do (page_number, ordinal) ties change KVP span candidates / prompt bytes? (~1652 tok)
- `repro_totals_rate.py` — Adversarial repro: does _totals_amount_cell pick the rate column for totals rows? (~1311 tok)
- `repro_totals_substring.py` — Adversarial repro: does substring totals matching eat real line items? (~1652 tok)
- `repro_totals_variants.py` — Variants: (a) shipping present + tax rate captured; (b) discount % captured. (~1378 tok)
- `repro_weak_redundant.py` — Repro: weak redundant table suppression vs baseline invariant (claim check). (~1549 tok)
- `run_a_violations.sql` (~274 tok)
- `run_a_violations2.sql` (~349 tok)
- `run9_docs.sql` (~167 tok)
- `run9_events.sql` (~205 tok)
- `run9_files.sql` (~74 tok)
- `run9_tables.sql` (~127 tok)
- `source_path.sql` (~46 tok)
- `text_lane_rows.sql` (~594 tok)

## ../../.claude/projects/-Users-brennanconley-vibecode-structura/memory/

- `structura-prod-readiness-push.md` — is: warnings (~2318 tok)

## ./

- `.DS_Store` (~3824 tok)
- `CLAUDE.md` — OpenWolf (~57 tok)
- `compose.yaml` — Docker Compose: 7 services (~6767 tok)
- `STRUCTURA_IMPLEMENTATION_PLAN.md` — Canonical end-to-end implementation plan; phase gates, mandatory per-phase artifact lists, API/database/event coverage, Markdown-first duplicate-artifact handling with DOCX parity note, GPU sync policy (~15500 tok)
- `STRUCTURA_PHASE_1_IMPLEMENTATION_PLAN.md` — Phase 1 execution plan; upload, object storage, Inbox, protected asset streaming, preview, Viewer, fresh-context rereads, Firecrawl evidence rules, validation gate (~5700 tok)
- `STRUCTURA_PHASE_10_IMPLEMENTATION_PLAN.md` — Phase 10 execution plan; exports, manifest/provenance, export authorization/audit, WebAuthn/passkeys, session hardening, API token lifecycle, folder ACL management, backup/restore, admin jobs, service/storage/model/extraction health, settings/admin UI, SAST, phase gate, fresh-context rereads, Firecrawl evidence rules (~11600 tok)
- `STRUCTURA_PHASE_11_IMPLEMENTATION_PLAN.md` — Phase 11 execution plan; golden corpus governance, expected answers, deterministic evaluation harness, extraction/search scoring, E2E and Playwright smoke tests, migration/contract regression, restore rehearsal, SAST/data-flow gate, performance measurements, release-candidate evidence pack, fresh-context rereads, Firecrawl evidence rules (~13200 tok)
- `STRUCTURA_PHASE_12_IMPLEMENTATION_PLAN.md` — Final derived Phase 12 execution plan; internal-GA/release handoff, Phase 11 evidence intake, blocker closure, contract/schema freeze, runtime config, operator runbooks, benchmark threshold approval, UI/security/restore/performance signoff, release notes/tagging, go/no-go, post-release cadence, fresh-context rereads, Firecrawl evidence rules (~13200 tok)
- `STRUCTURA_PHASE_2_IMPLEMENTATION_PLAN.md` — Phase 2 execution plan; manual filing, folders, tags, document organization, ACL/audit, smart-folder records, UI filing workflow, fresh-context rereads, Firecrawl evidence rules, validation gate (~6100 tok)
- `STRUCTURA_PHASE_3_IMPLEMENTATION_PLAN.md` — Phase 3 execution plan; preview/page-asset hardening, Docling worker, canonical artifacts, page/element/table/chunk relational rows, parse quality, debug surfaces, Gate B, fresh-context rereads, Firecrawl evidence rules (~6400 tok)
- `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md` — Phase 4 execution plan; classification, extraction validators, evidence resolver, model gateway, extraction workers, candidate normalization, canonical promotion, review APIs/UI, golden fixtures, Gate C, fresh-context rereads, Firecrawl evidence rules (~7600 tok)
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md` — Phase 5 execution plan; lexical BM25 search, embedding gateway/worker, semantic retrieval, filter-aware planner, hybrid RRF, facets/saved searches, search UI, golden benchmarks, Gate D, fresh-context rereads, Firecrawl evidence rules (~8200 tok)
- `STRUCTURA_PHASE_6_IMPLEMENTATION_PLAN.md` — Phase 6 execution plan; contacts, document-contact links, folder ACL guardrails, watched-folder API/worker, filing rules, dry-run explanations, rule suggestions/application, contacts dedupe, UI, CLI import/maintenance, phase gate, fresh-context rereads, Firecrawl evidence rules (~8800 tok)
- `STRUCTURA_PHASE_7_IMPLEMENTATION_PLAN.md` — Phase 7 execution plan; relationships, review actions, suggestion worker, related-document panel, entity/document timelines, deadlines, smart views, search/filing integration, quality fixtures, phase gate, fresh-context rereads, Firecrawl evidence rules (~8300 tok)
- `STRUCTURA_PHASE_8_IMPLEMENTATION_PLAN.md` — Phase 8 execution plan; difficult-document detection, selective visual embeddings, Qwen handwriting route, review-required uncertainty, visual retrieval contract/policy, mixed hybrid retrieval, low-text fallbacks, benchmarks, runtime observability, phase gate, fresh-context rereads, Firecrawl evidence rules (~9400 tok)
- `STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md` — Phase 9 execution plan; optional analysis workspace, analysis contracts, ACL/sensitivity/citation policy, analysis request API, context builder, prompt/model validation, worker-analysis, note persistence, Figma frame 14:990, core analysis actions, disable mode, observability, Gate E, fresh-context rereads, Firecrawl evidence rules (~10300 tok)
- `STRUCTURA_PLAN_INDEX.md` — Canonical planning index; source alignment policy, Markdown-first duplicate-artifact handling with DOCX parity note, UI source of truth, GPU node sync policy, stop rule (~1000 tok)
- `STRUCTURA_UI_FIGMA_QA_PLAN.md` — Canonical Figma and Playwright UI QA plan; frame ids, pixel-match rules, workflow QA, UI stop rule (~3000 tok)

## .claude/

- `settings.json` (~441 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)

## .claude/worktrees/agent-a86df2a212eebdab3/.wolf/

- `anatomy.md` — anatomy.md (~11932 tok)

## .claude/worktrees/agent-a86df2a212eebdab3/lib/config/

- `settings.py` — Settings: reject_historical_live_semantic_profiles, canonical_objects_root, derived_objects_root, ex (~1120 tok)

## .claude/worktrees/agent-a86df2a212eebdab3/lib/extraction/

- `expected_field_coverage.py` — Expected-field vs produced-field coverage telemetry for region extractions. (~1766 tok)
- `service.py` — ExtractionServiceError: create_job, classify_document, extract_document (~4278 tok)

## .claude/worktrees/agent-a86df2a212eebdab3/lib/model_runtime/

- `reliability_report.py` — build_phase85_reliability_report (~997 tok)
- `reliability_summaries.py` — planner_summary, candidate_admission_summary, contract_summary, evidence_summary (~4539 tok)

## .claude/worktrees/agent-a86df2a212eebdab3/lib/semantic_annotations/

- `input_budget.py` — Pure Qwen semantic input-budget estimation shared by canary and live path. (~2558 tok)
- `qwen_gateway.py` — SemanticVisionClientProtocol: generate, from_settings, generate, annotate (~7727 tok)

## .claude/worktrees/agent-a86df2a212eebdab3/scripts/gpu/

- `run_phase8_5_semantic_canary.py` — main, build_parser, parse_args (~8248 tok)

## .claude/worktrees/agent-a86df2a212eebdab3/tests/unit/extraction/

- `test_expected_field_coverage.py` — _EnvelopeGateway: test_normalized_field_name_collapses_to_snake_case, test_exact_and_dotted_fact_nam (~2916 tok)

## .claude/worktrees/agent-a86df2a212eebdab3/tests/unit/model_runtime/

- `test_reliability_expected_field_coverage.py` — test_expected_field_coverage_summary_aggregates_current_region_rows, test_expected_field_coverage_su (~1422 tok)

## .claude/worktrees/agent-a86df2a212eebdab3/tests/unit/semantic_annotations/

- `test_gateways.py` — class: generate, test_fixture_gateway_has_explicit_fixture_provenance, test_fixture_gateway_infers_t (~17607 tok)
- `test_input_budget.py` — test_estimate_text_tokens_matches_canary_heuristic, test_image_dimensions_parses_png_and_jpeg_header (~1598 tok)

## Deterministic-primary planner E3 (2026-06-10, ADR 0006)

- `lib/semantic_annotations/deterministic_plan.py` — Model-free baseline manifest via docling_targets builders over an empty manifest; run-stable baseline fingerprint (semantic types/granite tasks/table positions/expected fields, no UUIDs); apply_baseline_invariant enforcing plan ⊇ baseline with telemetry; baseline_only_result degrading Qwen failures to review-required baseline coverage (~1500 tok)
- `tests/unit/semantic_annotations/test_deterministic_plan.py` — Baseline construction, fingerprint cross-ingest stability, invariant enforcement/coverage, failure degradation, service flag on/off behavior (~2200 tok)

## Extractive-first KVP lane E2 (2026-06-10, ADR 0006)

- `lib/extraction/text_lane/kvp_extractor.py` — Selected spans -> RegionExtractionEnvelope: registry-exact expected keys mint family facts under canonical keys (strict money/date typing), others stay dot-less observation keys; element/text-span docling anchors (~1300 tok)
- `lib/extraction/text_lane/kvp_gateway.py` — TextLaneKvpExtractionGateway with abstentions and Granite-parity GatewayExtraction (~1100 tok)
- `lib/extraction/text_lane/span_candidates.py` — Bounded (<=80/page) deterministic value spans from Docling elements: label:value colon pairs, right-of/below-of bbox adjacency (BOTTOMLEFT-aware reading-space normalization), typed regexes (money/date/identifier/phone/zip/email); positional span ids stable across runs (~1900 tok)
- `lib/extraction/text_lane/span_selection.py` — Closed span-id enum selection schema/prompt over expected keys, LiveSpanSelector on qwen-semantic text endpoint, prompt-fingerprint in-process cache, selections_from_payload id validation (~1400 tok)
- `tests/unit/extraction/text_lane/test_kvp_lane.py` — Span builders/ids, selection schema/prompt/cache, extractor claims+registry facts, eligibility screens, routing text/fallback, abstentions (~2600 tok)

## Extractive-first text lane E0+E1 (2026-06-10, ADR 0006)

- `lib/extraction/text_lane/__init__.py` — Package doc: extractive text lane; models select via closed enums, never transcribe values (~150 tok)
- `lib/extraction/text_lane/column_labeling.py` — Enum micro-schema column-role labeling (registry line-item field_map keys + ignore) via text-only qwen-semantic call, temperature 0/seed 0, in-process cache by (family, header fingerprint), prompt/schema builders, roles_from_payload (~1300 tok)
- `lib/extraction/text_lane/eligibility.py` — `text_lane_eligibility(source, semantic_task)`: line-item semantic type + grounded Docling table + usable grid + strong audit table signal + non-difficult page (quality.py reasons) -> LaneDecision(lane, reason) telemetry (~900 tok)
- `lib/extraction/text_lane/gateway.py` — TextLaneTableExtractionGateway producing Granite-parity GatewayExtraction (regionEnvelope normalization_json, route source_engine=docling, method text_lane_table.v1); TextLaneAbstention for labeling failure/all-ignore/no-description/no-rows fallback (~1200 tok)
- `lib/extraction/text_lane/table_extractor.py` — TableGrid + roles -> RegionExtractionEnvelope: verbatim cell values parsed with parse_decimal_text, row-level docling EvidenceRefs (page/table_id/row_index/bbox union), totals-row keyword facts per family instead of line items, lane coverage telemetry (~1800 tok)
- `lib/extraction/text_lane/table_grid.py` — Typed TableGrid/TableGridCell parser for `document_tables.table_json["data"]["grid"]`: span-duplicate dedupe, positional span-resolving accessors, leading header-block detection from column_header flags with first-row fallback, multi-row header labels, header fingerprint for label caching (~1500 tok)
- `lib/model_runtime/clients/_openai_text.py` — OpenAITextGenerateClient: text-only strict json_schema chat against OpenAI-compatible endpoints, shares response handling with the vision client (~900 tok)
- `scripts/gpu/check_text_lane_eligibility.py` — E0 gate check printing per-table lane verdicts and per-document rollups for corpus documents (read-only, GPU host venv) (~1000 tok)
- `tests/fixtures/text_lane/` — Sanitized grid fixtures mirroring live shapes: service_lines (flags H.H + balance row), retail_order_items (3 noisy header rows + col-span duplication), escrow_activity (no cell bboxes, multi-row spanned headers, empty row) (~1200 tok)
- `tests/unit/extraction/text_lane/` — Grid round-trip/span/header/fingerprint tests, eligibility lane tests, labeling schema/prompt/cache tests, extractor verbatim/anchor/totals/claims/repeatability tests, routing/abstention/flag-off and service validation+coverage tests (~3200 tok)

## Phase 0 implementation scaffold


## Phase 1/2 UI reference artifacts


## Phase 3 canonical parse implementation


## Phase 5 search additions

- `.github/workflows/ci.yml` — Repository CI workflow for Python quality gates, contracts, tests, SAST, web lint/build, and Compose config (~500 tok)
- `.github/workflows/gpu-live-smoke.yml` — Manual self-hosted workflow for pinned-container Playwright live smoke against GPU-hosted web (~350 tok)
- `apps/api/structura_api/routes_search.py` — Thin FastAPI routes for corpus search and household-scoped saved searches (~450 tok)
- `apps/web/src/components/SearchFilterPanel.tsx` — Phase 5 search filter panel and request-payload builder for mode, family, folder, tag, review status, sensitivity, date, amount, and reviewed-only filters (~1900 tok)
- `apps/web/src/components/SearchResults.css` — Phase 5 search surface styles (~1900 tok)
- `apps/web/src/components/SearchResults.tsx` — Phase 5 Corpus Search shell with query card, ranked results, facets, evidence jumps, and saved-search action (~1500 tok)
- `apps/web/src/searchApi.ts` — Browser API client for search and saved-search calls (~250 tok)
- `database/069_phase5_search.sql` — Search projection refresh, BM25 index refresh, embedding uniqueness, saved-search household columns, and smart-folder saved-query matcher (~1700 tok)
- `database/071_phase5_search_guardrails.sql` — Phase 5 hardening migration replacing `document_matches_saved_query` with supported-key guardrails and broader filter handling (~1200 tok)
- `lib/documents/list_repository.py` — Document-list read repository using shared search filter SQL for text search, manual folders, smart folders, ACLs, and pagination (~1900 tok)
- `lib/documents/summary_mapping.py` — Small document summary row-to-contract mapper and list coercion helpers (~300 tok)
- `lib/search/benchmark.py` — Tiny search benchmark metric helpers for hit-rate-at-k and MRR regression tracking (~350 tok)
- `lib/search/embedding_gateway.py` — Deterministic local text embedding adapter and vector helpers (~700 tok)
- `lib/search/embedding_repository.py` — Projection refresh and embedding persistence repository (~900 tok)
- `lib/search/embedding_service.py` — Document embedding orchestration and idempotent refresh summary (~450 tok)
- `lib/search/hybrid.py` — Reciprocal-rank fusion primitives (~450 tok)
- `lib/search/jobs.py` — Embedding job enqueue helper for the `embeddings` queue (~300 tok)
- `lib/search/projection.py` — Shared projection refresh and embedding enqueue seam for later phases (~200 tok)
- `lib/search/query.py` — Search request parser and normalized filter DTOs (~550 tok)
- `lib/search/repository.py` — ACL-aware lexical/semantic/facet SQL repository for Phase 5 search (~2200 tok)
- `lib/search/saved_query.py` — Saved-query parser/validator that maps smart-folder JSON into canonical `SearchFilters` and rejects unsupported keys (~1200 tok)
- `lib/search/saved_searches.py` — Household-scoped saved-search persistence API (~550 tok)
- `lib/search/service.py` — Search orchestration and result DTO mapping for lexical, semantic, and hybrid modes (~1300 tok)
- `tests/e2e/phase5-live.spec.ts` — GPU live upload/search/evidence browser smoke (~650 tok)
- `tests/e2e/phase5.spec.ts` — Mocked Phase 5 search UI and screenshot gate (~450 tok)
- `tests/integration/test_phase5_search.py` — Live DB integration coverage for search, embeddings, smart folders, saved searches, and ACL negatives (~2100 tok)
- `tests/unit/test_phase5_search_units.py` — Unit coverage for parser, deterministic embeddings, and RRF (~550 tok)
- `workers/embeddings/worker.py` — Phase 5 embedding worker loop and job handling (~750 tok)
- `workers/ingest/worker.py` — Real ingest queue consumer that claims upload ingest jobs, verifies original assets, completes jobs, and records worker health (~900 tok)

## Phase 6 automation additions

- `apps/api/structura_api/routes_automation.py` — Thin filing-rule, suggestion, watched-folder, and import-status API routes (~900 tok)
- `apps/api/structura_api/routes_contacts.py` — Thin contact and document-contact API routes with CSRF-protected writes (~700 tok)
- `apps/web/src/automationApi.ts` — Browser API client for contacts, filing rules, suggestions, watched folders, and import status (~500 tok)
- `apps/web/src/components/AutomationContactsPanel.tsx` — Contact/alias detail, duplicate merge suggestion display, and merge action UI (~900 tok)
- `apps/web/src/components/automationFormatting.ts` — Automation UI formatting helpers for labels, statuses, and action/condition summaries (~250 tok)
- `apps/web/src/components/AutomationImportsPanel.tsx` — Import-status summary cards for watched-folder intake status (~250 tok)
- `apps/web/src/components/AutomationRulesPanel.tsx` — Filing-rule builder/editor controls, pause/resume, action/condition inputs, dry-run controls, and explanation display (~1700 tok)
- `apps/web/src/components/AutomationSuggestionsPanel.tsx` — Reviewable filing suggestions with proposed/blocked action explanations and accept/reject/defer controls (~650 tok)
- `apps/web/src/components/AutomationTabs.tsx` — Small tab selector for Automation Workbench panel navigation (~250 tok)
- `apps/web/src/components/AutomationWatchedPanel.tsx` — Watched-folder policy/root/stability/processed-file controls plus pause/resume UI (~900 tok)
- `apps/web/src/components/AutomationWorkbench.tsx` — Phase 6 automation UI shell that composes focused automation panels, tab state, and shared status handling (~700 tok)
- `database/072_phase6_automation.sql` — Phase 6 state migration for watched-folder owner, filing-rule run decision state, blocked action state, indexes, and update trigger (~600 tok)
- `lib/automation/action_application.py` — Cursor-based filing-rule action dispatcher for folder, tag, sensitivity, document-family, and review-task effects (~1200 tok)
- `lib/automation/repository.py` — Filing-rule and suggestion persistence plus automation audit writes (~1900 tok)
- `lib/automation/rule_engine.py` — Pure rule evaluation, condition explanations, high-stakes review guardrails, and writable-folder action blocking (~1300 tok)
- `lib/automation/rule_policy.py` — Filing-rule validation for supported fields/operators/actions and regex safety (~700 tok)
- `lib/automation/service.py` — Filing-rule orchestration, dry-run/apply/suggest/accept/reject/defer behavior, atomic action application, and post-commit projection refresh (~2100 tok)
- `lib/automation/watched_folder_policy.py` — Watch-path validation, managed-runtime path blocking, file stability, and PDF candidate filtering (~800 tok)
- `lib/automation/watched_folder_repository.py` — Watched-folder persistence, enabled watcher listing, scan metrics, and import-status reads (~700 tok)
- `lib/automation/watched_folders.py` — Watched-folder API service, target-folder ACL validation, and DTO mapping (~800 tok)
- `lib/contacts/policy.py` — Contact/alias normalization and contact write validation (~450 tok)
- `lib/contacts/repository.py` — Contact, alias, document-contact, merge suggestion, merge, and contact audit persistence (~1700 tok)
- `lib/contacts/service.py` — Contact CRUD, document-contact linking, duplicate merge, and projection-refresh orchestration (~1100 tok)
- `lib/documents/ingestion.py` — Shared document ingestion service extracted from document upload route for web/API/watched-folder reuse (~2300 tok)
- `lib/documents/maintenance.py` — Operator maintenance enqueue helpers for document reprocess and search projection rebuild jobs (~650 tok)
- `lib/organization/document_organization.py` — Cursor-based document organization mutation helper shared by manual filing and automation atomic apply flows (~1000 tok)
- `scripts/structura.py` — Operator CLI for dry-run/bulk import validation, reprocess enqueue, search rebuild enqueue, evaluation guidance, and backup/restore checks (~800 tok)
- `tests/e2e/phase6-live.spec.ts` — GPU live Phase 6 automation UI smoke (~500 tok)
- `tests/e2e/phase6.spec.ts` — Mocked Phase 6 automation UI workflow and Linux screenshot gate (~700 tok)
- `tests/integration/test_phase6_automation.py` — Live DB coverage for contacts, document contacts, all supported rule actions, atomic rollback, suggestions, watched-folder roots/symlinks, and dedupe/merge (~2400 tok)
- `tests/unit/test_phase6_automation_units.py` — Unit coverage for rule engine and watched-folder path policy (~700 tok)
- `tests/unit/test_phase6_cli.py` — CLI dry-run import validation and execute-mode upload coverage (~500 tok)
- `workers/watched_folders/worker.py` — Dedicated watched-folder scanner that imports stable PDFs through shared ingestion and records scan counts (~1300 tok)

## Phase 7 relationship additions

- `apps/api/structura_api/routes_relationships.py` — Thin relationship/deadline/timeline/smart-view API routes with protected reads and CSRF-protected decisions (~800 tok)
- `apps/web/src/components/RelationshipPanel.tsx` — Viewer related-document panel for manual link creation and suggested relationship accept/reject actions (~1000 tok)
- `apps/web/src/components/RelationshipWorkspace.tsx` — Relationships/Timelines workspace for links, deadlines, smart views, and timeline navigation (~800 tok)
- `apps/web/src/relationshipsApi.ts` — Browser API client for relationship, deadline, timeline, and smart-view endpoints (~500 tok)
- `database/073_phase7_relationships.sql` — Relationship status/review metadata, deadline guardrails, indexes, and saved-query relationship/deadline support (~1300 tok)
- `lib/relationships/deadline_repository.py` — Deadline list/upsert persistence (~450 tok)
- `lib/relationships/jobs.py` — Relationship job enqueue helper for the `relationships` queue (~250 tok)
- `lib/relationships/relationship_repository.py` — Relationship list/get/upsert/decision/review-task/audit/context persistence (~2100 tok)
- `lib/relationships/repository.py` — Compatibility facade re-exporting focused relationship repositories (~200 tok)
- `lib/relationships/service.py` — Relationship/deadline/timeline/smart-view orchestration and DTO mapping (~2200 tok)
- `lib/relationships/suggestions.py` — Deterministic duplicate/contact/family relationship suggestion rules (~650 tok)
- `lib/relationships/timeline_repository.py` — Timeline and relationship/deadline smart-view projection SQL (~1000 tok)
- `tests/e2e/phase7-live.spec.ts` — GPU live Phase 7 relationship creation and relationship/timeline workspace smoke (~450 tok)
- `tests/e2e/phase7.spec.ts` — Mocked Phase 7 relationships/timelines UI workflow and Linux screenshot gate (~450 tok)
- `tests/integration/test_phase7_relationships.py` — Live DB coverage for manual relationships, timeline/search decisions, and idempotent worker suggestions (~1000 tok)
- `tests/unit/test_phase7_relationship_units.py` — Unit coverage for relationship/deadline search filters, saved-query parsing, and self-link validation (~400 tok)
- `workers/relationships/worker.py` — Real relationship worker loop for deadline refresh and relationship suggestions (~750 tok)

## Phase 8 difficult-document additions

- `lib/documents/quality.py` — Deterministic difficult-document quality detection, page/document metadata persistence, handwriting/review flags, and document-quality review-task creation (~1700 tok)
- `lib/review/task_repository.py` — Shared review-task upsert helper used by extraction and document-quality workflows (~450 tok)
- `lib/search/embedding_gateway.py` — Deterministic text and visual embedding profiles plus vector/content-hash helpers (~800 tok)
- `lib/search/embedding_repository.py` — Text/visual embedding source lookup and active embedding persistence (~1500 tok)
- `lib/search/embedding_service.py` — Text/visual/mixed embedding orchestration with modality counts and idempotent persistence (~900 tok)
- `lib/search/service.py` — Search orchestration for lexical, semantic, visual, and hybrid-with-visual retrieval modes (~1700 tok)
- `lib/search/visual_repository.py` — ACL-aware visual vector retrieval SQL for page-level visual embeddings (~900 tok)
- `tests/e2e/phase8-live.spec.ts` — GPU live Phase 8 upload, quality cue, and visual search smoke (~550 tok)
- `tests/e2e/phase8.spec.ts` — Mocked Phase 8 difficult-document UI workflow and Linux screenshot gate (~500 tok)
- `tests/integration/test_phase8_difficult_documents_integration.py` — Live DB coverage for quality detection, review task creation, visual embeddings/search ACL, and Qwen handwriting review-required routing (~2400 tok)
- `tests/unit/test_phase8_difficult_documents.py` — Unit coverage for quality classifier, visual search contract, visual embedding profile/modality validation, RRF visual fusion, and Phase 8 benchmark cases (~900 tok)
- `workers/embeddings/worker.py` — Embedding worker with validated text/visual/mixed modality payload handling and service-health modality metrics (~850 tok)

## Phase 8.5 critical extraction closure additions

- `contracts/model_outputs/granite_invoice_line_items.v1.schema.json` — Granite task contract for invoice service/line-item table output before Structura canonical normalization (~350 tok)
- `contracts/model_outputs/granite_medical_service_lines.v1.schema.json` — Granite task contract for EOB covered-service line output before canonical medical EOB mapping (~250 tok)
- `contracts/model_outputs/granite_payment_summary.v1.schema.json` — Granite task contract for payment-summary KVP output before canonical invoice mapping (~250 tok)
- `database/078_phase8_5_region_extraction_scope.sql` — Adds scoped extraction persistence columns, JSON object checks, and current-row indexes for document, semantic-region, and aggregate extraction rows (~800 tok)
- `docs/superpowers/plans/2026-04-29-phase-8-5-qwen-semantic-planner-generalization.md` — Follow-on implementation plan that reframes Qwen3-VL-4B as semantic document understanding plus extraction intent, rejects document-instance repair paths, and requires structural-only normalization plus class-level canary scoring (~1900 tok)
- `docs/superpowers/plans/2026-04-29-phase-8-5-qwen-semantic-planner-optimization.md` — Qwen-only implementation plan that phases prompt/schema/context/merge/fanout/canary changes, maps each step to the current semantic code seams, and defines local plus GPU semantic-canary gates before more Granite tuning (~2600 tok)
- `docs/superpowers/plans/2026-04-29-phase-8-5-qwen3-vl-4b-smart-parse-canary.md` — Qwen3-VL-4B Smart Parse implementation plan, Qwen8 disabled/deferred behavior, canary corpus gate, and runtime profile notes (~1500 tok)
- `docs/superpowers/plans/2026-04-29-phase85-critical-extraction-closure.md` — Executed closure plan and verification checklist for scoped persistence, Granite contracts, normalization, reconciliation, and GPU proof (~1200 tok)
- `docs/superpowers/specs/2026-04-29-phase-8-5-qwen-semantic-planner-generalization-spec.md` — Follow-on spec that makes Qwen3-VL-4B the semantic document-understanding layer for page/layout/table/visual inventory and extraction intent while keeping canonical facts behind Granite, validators, and review policy (~2500 tok)
- `docs/superpowers/specs/2026-04-29-phase-8-5-qwen-semantic-planner-optimization-spec.md` — Qwen semantic-planner hardening spec covering recall-oriented prompt contracts, additive manifest fields, Docling context upgrades, merge/fanout rules, persistence strategy, and semantic-only definition of done (~2400 tok)
- `docs/superpowers/specs/2026-04-29-phase-8-5-qwen3-vl-4b-smart-parse-canary-spec.md` — Qwen3-VL-4B Smart Parse spec, contract preservation rules, historical notes, and validation criteria; current runtime now uses four-image adaptive fan-in with one-page fallback (~1500 tok)
- `lib/extraction/granite_prompting.py` — Builds Granite prompts for generic, table, and KVP semantic tasks with Docling table/page context and schema instructions (~1200 tok)
- `lib/extraction/model_output_normalization.py` — Maps Granite task output, BMW-style flat fields, and wrapped `data.invoice_line_items` into canonical invoice/EOB payload fragments while recording repairs/rejected fields and filtering section headings (~2600 tok)
- `lib/extraction/model_output_schemas.py` — Selects Granite model-output schema by canonical schema, semantic type, and Granite task; semantic type can override a mistaken `granite_task=kvp` for line-item regions (~450 tok)
- `lib/extraction/normalization.py` — Converts normalized extraction JSON into field, line-item, and observation candidates; includes current exact/sparse line-item dedupe and observation dedupe before persistence (~1400 tok)
- `lib/extraction/reconciliation_repository.py` — DB orchestration for terminal-region aggregate persistence; loads current region rows and document-level fallback, then persists aggregate extraction/candidates (~1700 tok)
- `lib/extraction/reconciliation.py` — Pure invoice region reconciliation that merges current semantic-region line items, totals, payment/document fallback fields, and provenance metadata into aggregate invoice JSON (~1300 tok)
- `lib/model_runtime/clients/_openai_vision.py` — Shared OpenAI-compatible vision client for Qwen/Granite; builds image+prompt payloads, enforces one structured-output mechanism per request, captures usage/finish reason, rejects truncated JSON, and falls back to JSON-object mode when allowed (~900 tok)
- `lib/semantic_annotations/docling_audit.py` — Builds Docling-only audit summaries for page/table counts, page snippets, table signal strength/weakness, lexical anchor counts, family hints, and family-tension telemetry used by semantic canary/schema-fit checks (~900 tok)
- `lib/semantic_annotations/docling_context.py` — Builds compact Docling context for Qwen, including full-document page outline/table inventory plus an explicit focus-page contract so multi-image windows treat `pageOutline` as context-only and keep output pages/regions scoped to input images (~1000 tok)
- `lib/semantic_annotations/manifest_merge.py` — Merges Qwen page/window semantic manifests with weighted page votes, Docling anchor hints, conflict downgrade, planner metadata serialization, document-type candidates, and document-type resolution telemetry (~1400 tok)
- `lib/semantic_annotations/prompting.py` — Owns Qwen semantic prompt assembly and prompt-version constants; Smart Parse v3 is bounded-recall, forbids canonical facts, uses compact document-class examples, and keeps Docling context compact while asking for page/layout/table/visual inventory (~1300 tok)
- `lib/semantic_annotations/schema_fit.py` — Gates Granite target schema selection with Docling lexical family evidence so unanchored invoice/receipt/EOB guesses become `document_observation` (~700 tok)
- `lib/semantic_annotations/semantic_family.py` — Reconciles Qwen manifest document type with Docling anchor evidence and source family; writes Phase 8.5 semantic classification metadata and can supersede/downgrade Phase 4 family safely (~1200 tok)
- `lib/semantic_annotations/target_schema_policy.py` — Canonical target-schema preference layer from semantic type, document hint, model target, Phase 4 fallback metadata, and source family into invoice/receipt/medical_eob/document_observation (~450 tok)
- `lib/semantic_annotations/task_routing.py` — Repairs line-item semantic regions so table-oriented semantic types get Granite `tables_json` even when the model emitted a weaker task label (~200 tok)
- `scripts/gpu/run_phase8_5_resident_corpus.py` — Production-style Phase 8.5 corpus harness that ingests PDFs, waits on resident live workers, cancels text embedding jobs by default for the model gate, and reports jobs, semantic annotations/regions, extractions, fields, line items, observations, and embeddings without heredoc startup (~1800 tok)
- `scripts/gpu/run_phase8_5_semantic_canary.py` — Semantic-only GPU canary harness for existing document IDs or PDFs; runs Docling audit plus Qwen semantic annotation and emits fan-in/fallback/schema-fit/token-budget telemetry plus optional expectation scorecards without Granite (~1400 tok)
- `tests/fixtures/semantic_annotations/semantic_canary_expectations.example.json` — Committed class-level example shape for private semantic-canary expectations: required/forbidden document families, document-family candidates, page roles, semantic types, target schemas, source signals, extraction scopes, continuation groups, full-page flags, and region attributes (~700 tok)
- `tests/unit/extraction/test_reconciliation.py` — Regression coverage for aggregate invoice merge, line-item/payment preservation, heading filtering, and document fallback fields (~800 tok)
- `tests/unit/semantic_annotations/test_prompting.py` — Prompt-contract regression tests proving Smart Parse asks for material-region recall, page inventory, Docling grounding, semantic metadata, Qwen visual/layout/table awareness, and excludes old sparse-target and document-instance wording (~500 tok)

## Playwright validation


## Review-workflow and D8 quality-outcome surfacing additions (2026-06-09)

- `apps/web/src/evidence.ts` — Deterministic richer-anchor-first evidence locator selection mirroring `lib/extraction/evidence_locator.py` for jump targets and card labels (~500 tok)
- `database/087_phase8_5_quality_outcome.sql` — Adds `document_extractions.quality_outcome` (D8 vocabulary CHECK + current-row index) and expands `extraction_observations.status` to allow review `accepted` (~250 tok)
- `lib/review/candidate_decision_repository.py` — Accept/reject persistence for observation and line-item candidates with audit events, task clearing, and document review-status refresh (~700 tok)
- `tests/unit/documents/test_read_model_payloads.py` — Coverage for qualityOutcome/claimResolutionDecisions/regionJobCoverage projection on document detail extraction payloads (~450 tok)
- `tests/unit/review/` — Unit coverage for Smart Parse rerun routing, review mappers (task metadata, evidence sanitization), and observation/line-item decision dispatch (~900 tok)

## Telemetry additions: expected-field coverage and Qwen input budget (2026-06-10)

- `lib/extraction/expected_field_coverage.py` — Compares Qwen plan `expected_fields` against region-envelope claim-bearing output (fact/observation names, populated line-item/table-row fields) with normalized snake-case exact-or-substring matching; builds the compact `expected_field_coverage` normalization_json entry (~700 tok)
- `lib/semantic_annotations/input_budget.py` — Pure Qwen input-budget estimators shared by the semantic canary and live gateway: text-token heuristic, PNG/JPEG dimension parsing, visual-token grid estimate with profile pixel clamping, conservative request estimate, and threshold-based structured warning (~1100 tok)
- `tests/unit/extraction/test_expected_field_coverage.py` — Coverage matching rules, missing-envelope zero coverage, dedupe, bookkeeping-key exclusion, and ExtractionService normalization_json recording (~1100 tok)
- `tests/unit/model_runtime/test_reliability_expected_field_coverage.py` — expectedFieldCoverage rollup aggregation over current semantic-region extraction rows and report wiring (~600 tok)
- `tests/unit/semantic_annotations/test_input_budget.py` — Estimator parity with canary math, profile pixel clamping, unknown-dimension fallback, and warning threshold behavior (~700 tok)

## claude-desktop-46/

- `docvault-architecture-brainstorm.md` — DocVault — AI-Augmented Life Document Filing System (~12767 tok)

## claude/docs/plans/

- `2026-04-20-structura-design.md` — Structura — Validated Design Document (~21460 tok)

## claude/docs/plans/2026-04-20-structura/

- `docker-compose.yml` — Docker Compose services (~4145 tok)
- `repo-layout.md` — Structura — Authoritative Repository Layout (~2594 tok)
- `schema.sql` — Database schema (~4943 tok)

## claude/docs/plans/2026-04-20-structura/doc-types/

- `general_correspondence.schema.json` (~542 tok)
- `invoice.schema.json` (~706 tok)
- `legal_letter.schema.json` (~614 tok)
- `medical_eob.schema.json` (~777 tok)
- `prescription.schema.json` (~656 tok)
- `receipt.schema.json` (~647 tok)
- `statement.schema.json` (~706 tok)
- `tax_form.schema.json` (~630 tok)

## claude/docs/plans/2026-04-20-structura/prompts/

- `granite-extraction.md` — Granite Vision Extraction Prompt Template (~446 tok)
- `qwen3vl-extraction.md` — Qwen3-VL Extraction Prompt Template (~573 tok)

## claude46/docs/plans/

- `2026-04-20-structura-design.md` — Structura — Design Document (~13431 tok)
- `api-design.md` — Structura — API Endpoint Design (~4560 tok)
- `docker-compose.md` — Structura — Docker Compose Configuration (~4029 tok)
- `extraction-schemas.md` — Structura — Document Type Extraction Schemas (~4971 tok)
- `implementation-plan.md` — Structura — Implementation Plan (~4636 tok)

## codex/

- `agentic-build-handoff-index.md` — Structura Agentic Build Handoff Index (~1213 tok)
- `docker-compose.yml` — Docker Compose services (~1630 tok)
- `document-filing-system-architecture.md` — AI-Native Document Filing Cabinet: Architecture Brief (~5434 tok)
- `document-ingestion-adjudication-schema.sql` — First-pass ingestion and adjudication schema (~3454 tok)
- `dual-model-extraction-addendum.md` — Dual-Model Extraction Addendum (~1041 tok)

## codex/adrs/

- `0001-docling-is-canonical-parser.md` — ADR 0001: Docling Is the Canonical Parser (~487 tok)
- `0002-qwen-primary-granite-specialist.md` — ADR 0002: Qwen Is Primary, Granite Is the Structured Specialist (~608 tok)
- `0003-host-managed-zfs-and-object-storage.md` — ADR 0003: Host-Managed ZFS Datasets and Object Storage Layout (~528 tok)

## codex/contracts/

- `openapi.yaml` — Declares resources (~9180 tok)
- `pipeline-and-data-contracts.md` — Pipeline and Data Contracts (~2846 tok)

## codex/database/

- `database-schema-overview.md` — Database Schema Overview (~2328 tok)

## codex/migrations/

- `001_bootstrap.sql` — SQL: 1 function(s) (~778 tok)
- `002_document_core.sql` — SQL: tables: folders, documents, document_files, document_pages (~1724 tok)
- `003_extraction_adjudication.sql` — SQL: tables: ingestion_jobs, extraction_runs, extraction_artifacts, field_candidates (~2318 tok)
- `004_search_and_filing.sql` — SQL: tables: document_chunks, page_multimodal_embeddings (~628 tok)
- `005_schema_registry.sql` — SQL: tables: document_schema_registry, extraction_profiles (~731 tok)

## codex/ops/

- `deployment-and-runtime-plan.md` — Deployment and Runtime Plan (~1806 tok)
- `production-readiness-checklist.md` — Production Readiness Checklist (~1345 tok)
- `security-privacy-threat-model.md` — Security and Privacy Threat Model (~2732 tok)
- `zfs-dataset-plan.md` — ZFS Dataset Plan (~2655 tok)

## codex/planning/

- `agentic-coder-playbook.md` — Agentic Coder Playbook (~2563 tok)
- `phased-implementation-plan.md` — Structura Phased Implementation Plan (~2059 tok)

## codex/research/

- `research-informed-artifact-plan.md` — Research-Informed Artifact Plan (~1491 tok)

## codex/schemas/document_types/

- `contract.schema.json` (~659 tok)
- `eob.schema.json` (~1074 tok)
- `invoice.schema.json` (~1260 tok)
- `note.schema.json` (~403 tok)
- `README.md` — Project documentation (~229 tok)
- `receipt.schema.json` (~912 tok)

## codex/services/api/

- `Dockerfile` — Docker container definition (~70 tok)
- `requirements.txt` — Python dependencies (~24 tok)

## codex/services/api/app/

- `__init__.py` — Structura document services. (~10 tok)
- `config.py` — Settings: postgres_dsn, get_settings (~492 tok)
- `db.py` — get_db, wait_for_database (~251 tok)
- `main.py` (~110 tok)
- `migrate.py` — main (~169 tok)
- `planner.py` — from: build_plan (~1372 tok)
- `repository.py` — URL configuration (~2528 tok)
- `worker.py` — process_next_job, main (~741 tok)

## codex/services/api/app/routers/

- `__init__.py` — API routers. (~6 tok)
- `health.py` — API: GET (1 endpoints) (~135 tok)
- `ingestion.py` — API: GET, POST (4 endpoints) (~795 tok)

## codex/services/api/app/schemas/

- `__init__.py` — API schemas. (~6 tok)
- `api.py` — Pydantic: PlannedRun (56 fields) (~690 tok)

## codex/services/model-granite/

- `Dockerfile` — Docker container definition (~51 tok)
- `entrypoint.sh` (~291 tok)

## codex/specs/

- `app-specification.md` — Structura Application Specification (~2851 tok)
- `system-design-spec.md` — Structura System Design Specification (~1693 tok)

## codex/stories/

- `user-stories-and-acceptance-criteria.md` — User Stories and Acceptance Criteria (~2044 tok)

## codex/testing/

- `evaluation-and-test-strategy.md` — Evaluation and Test Strategy (~1538 tok)

## docs/adr/

- `0006-extractive-first-extraction.md` — ADR 0006: Extractive-First Extraction Architecture (~2533 tok)

## docs/superpowers/plans/

- `2026-06-10-extractive-first-extraction-plan.md` — Extractive-First Extraction Migration Plan (E0-E5) (~2486 tok)

## gold-master/

- `architecture.md` — System Architecture (~1616 tok)
- `data-model-and-contracts.md` — Data Model and Contracts (~1476 tok)
- `decisions.md` — Gold Master Decisions (~1343 tok)
- `external-validation.md` — External Validation (~1062 tok)
- `implementation-plan.md` — Implementation Plan (~1186 tok)
- `product-and-ux.md` — Product and UX Specification (~1180 tok)
- `README.md` — Project documentation (~905 tok)

## lib/config/

- `settings.py` — Settings: reject_historical_live_semantic_profiles, canonical_objects_root, derived_objects_root, ex (~1372 tok)

## lib/extraction/

- `canonical_promotion_policy.py` — candidate_auto_promotion_rejection_reason (~512 tok)
- `canonical_repository.py` — promote_candidates, create_review_tasks, upsert_canonical_field, canonical_is_human_controlled (~3007 tok)
- `claim_aggregate_reconciliation.py` — from: resolve_claim_regions_for_family, source_families_from_claims (~1046 tok)
- `claims.py` — ClaimAnchor: as_json, identity_json, as_json, claims_from_region_envelope + 1 more (~5227 tok)
- `docling_anchor_resolution.py` — resolve_docling_anchors_for_envelope (~938 tok)
- `evidence.py` — from: for_value, first_page_evidence, has_concrete_evidence, has_structural_value_anchor + 3 more (~1620 tok)
- `granite_budgets.py` — from: granite_budget_for_task, granite_length_retry_budget (~1045 tok)
- `granite_prompting.py` — granite_prompt (~3708 tok)
- `model_output_normalization.py` — normalize_granite_region_output, finalize, invoice_line_item_dicts_from_payload (~8666 tok)
- `models.py` — ParsedPageText: full_text, family, route_profile, confidence + 4 more (~1977 tok)
- `observation_repository.py` — insert_observation_candidate (~566 tok)
- `reconciliation_repository.py` — aggregate: maybe_reconcile_semantic_annotation (~4998 tok)
- `region_envelope_projection.py` — finalized_region_output (~652 tok)
- `service.py` — ExtractionServiceError: create_job, classify_document, extract_document (~4445 tok)
- `source_repository.py` — load_extraction_source, require_document_readable (~2268 tok)
- `validators.py` — validate_extraction_payload, validate_text_lane_region_payload, validate_semantic_region_payload (~3826 tok)

## lib/extraction/gateways/

- `routing.py` — ModelRoutingExtractionGateway: extract, default_extraction_gateway (~1916 tok)

## lib/extraction/text_lane/

- `__init__.py` — Extractive-first text lane (ADR 0006). (~113 tok)
- `column_labeling.py` — Model column-role labeling for the extractive table lane (ADR 0006 X2). (~2311 tok)
- `eligibility.py` — Text-lane eligibility: which regions may extract from Docling text. (~2084 tok)
- `gateway.py` — Text-lane extraction gateway (ADR 0006 X2, migration phase E1). (~2222 tok)
- `kvp_extractor.py` — Deterministic KVP extraction from selected spans (ADR 0006, E2). (~2363 tok)
- `kvp_gateway.py` — KVP text-lane extraction gateway (ADR 0006 X2, migration phase E2). (~1962 tok)
- `span_candidates.py` — Deterministic KVP span candidates from Docling elements (ADR 0006, E2). (~3485 tok)
- `span_selection.py` — Model span selection for the extractive KVP lane (ADR 0006 X2, E2). (~1893 tok)
- `table_extractor.py` — Deterministic line-item extraction from the Docling cell grid (ADR 0006). (~4658 tok)
- `table_grid.py` — Typed access to the Docling table cell grid persisted in table_json. (~2404 tok)

## lib/model_runtime/

- `contracts.py` — ModelImageInput: validated_sha256, sha256 (~860 tok)

## lib/model_runtime/clients/

- `_openai_text.py` — OpenAITextGenerateClient: generate (~1268 tok)
- `_openai_vision.py` — OpenAIVisionGenerateClient: generate (~2786 tok)

## lib/semantic_annotations/

- `deterministic_plan.py` — Deterministic-primary planning (ADR 0006 X4, migration phase E3). (~2386 tok)
- `manifest_normalization.py` — normalize_result_for_planning, normalize_manifest_for_planning (~8248 tok)
- `service.py` — SemanticAnnotationGateway: annotate, create_job, annotate_document (~7358 tok)

## pro-merged-master-v.beta/

- `.DS_Store` (~1640 tok)
- `AGENT_START_HERE.md` — Agent start here (~1783 tok)
- `MANIFEST_v1.2.md` — Manifest v1.2 (~1761 tok)
- `MANIFEST.txt` (~604 tok)
- `README.md` — Project documentation (~2299 tok)

## pro-merged-master-v.beta/contracts/

- `.DS_Store` (~1640 tok)
- `README.md` — Project documentation (~964 tok)

## pro-merged-master-v.beta/contracts/api/

- `openapi.yaml` (~6123 tok)

## pro-merged-master-v.beta/contracts/events/

- `analyze_documents_job.v1.schema.json` (~554 tok)
- `classify_document_job.v1.schema.json` (~425 tok)
- `embed_document_job.v1.schema.json` (~537 tok)
- `extract_document_job.v1.schema.json` (~528 tok)
- `ingest_document_job.v1.schema.json` (~633 tok)
- `README.md` — Project documentation (~177 tok)

## pro-merged-master-v.beta/contracts/schemas/

- `analysis_note.v1.schema.json` (~653 tok)
- `canonical_field.v1.schema.json` (~538 tok)
- `common_defs.schema.json` (~1587 tok)
- `document_classification.v1.schema.json` (~543 tok)
- `field_candidate.v1.schema.json` (~686 tok)
- `filing_rule.v1.schema.json` (~668 tok)
- `folder_acl.v1.schema.json` (~265 tok)
- `invoice.v1.schema.json` (~1306 tok)
- `medical_eob.v1.schema.json` (~1436 tok)
- `receipt.v1.schema.json` (~1088 tok)
- `review_action.v1.schema.json` (~472 tok)

## pro-merged-master-v.beta/database/

- `001_extensions.sql` (~86 tok)
- `010_types_and_enums.sql` — Declares AS (~1011 tok)
- `020_core_tables.sql` — SQL: tables: ingest_batches, documents, document_assets, document_pages, 1 alter(s) (~4827 tok)
- `025_baseline_identity_acl_candidate_rules.sql` — 025_baseline_identity_acl_candidate_rules.sql (~5429 tok)
- `030_constraints_and_triggers.sql` — SQL: 1 function(s) (~1210 tok)
- `040_indexes_bm25_pgvector.sql` (~1569 tok)
- `050_views_and_functions.sql` — SQL: 5 view(s), 1 function(s) (~798 tok)
- `060_seed_taxonomies.sql` (~642 tok)
- `070_query_examples.sql` (~639 tok)
- `README.md` — Project documentation (~593 tok)

## pro-merged-master-v.beta/docs/

- `01_App_Specification.md` — App specification (~7312 tok)
- `02_Phased_Implementation_Plan.md` — Phased implementation plan (~6104 tok)
- `03_Agent_Bootstrap_and_Execution_Order.md` — Agent bootstrap and execution order (~1339 tok)
- `04_User_Stories_and_Acceptance_Criteria.md` — User stories and acceptance criteria (~1809 tok)
- `05_Nonfunctional_Requirements_Security_Privacy_Observability.md` — Nonfunctional requirements, security, privacy, and observability (~1316 tok)
- `06_Testing_QA_and_Release_Strategy.md` — Testing, QA, and release strategy (~987 tok)
- `07_Repository_Layout_and_Coding_Standards.md` — Repository layout and coding standards (~728 tok)
- `08_ZFS_Datasets_and_Storage_Plan.md` — ZFS datasets and storage plan (~1025 tok)
- `09_Deployment_and_Runtime_Architecture.md` — Deployment and runtime architecture (~679 tok)
- `10_Architectural_Decision_Record_Summary.md` — Architectural decision record summary (~1185 tok)
- `11_Model_Routing_and_Output_Contracts.md` — Model routing and output contracts (~1491 tok)
- `12_Risk_Register_and_Open_Questions.md` — Risk register and open questions (~604 tok)
- `13_Golden_Master_Review_and_Merge_Plan.md` — 13 — Golden Master Review and Merge Plan (~2345 tok)
- `14_Canonicalization_Candidate_Authority_Model.md` — 14 — Canonicalization, Candidate, and Authority Model (~1555 tok)
- `15_PGMQ_and_Worker_Strategy.md` — 15 — PGMQ and Worker Strategy (~863 tok)
- `16_Auth_ACL_Household_Model.md` — 16 — Auth, ACL, and Household Model (~724 tok)
- `17_Rules_Contacts_and_Watched_Folder_Addendum.md` — 17 — Rules, Contacts, and Watched-Folder Addendum (~739 tok)
- `18_Filter_Aware_Vector_Search_Addendum.md` — 18 — Filter-Aware Vector Search Addendum (~697 tok)
- `19_v1.2_Normalization_and_Source_of_Truth.md` — v1.2 normalization and source of truth (~817 tok)
- `20_Codex_xhigh_Feedback_Resolution.md` — Codex xhigh feedback resolution (~780 tok)

## pro-merged-master-v.beta/infrastructure/

- `README.md` — Project documentation (~196 tok)
- `runtime_service_matrix.csv` (~874 tok)

## pro-merged-master-v.beta/infrastructure/zfs/

- `create_datasets.sh` (~759 tok)
- `dataset_matrix.csv` (~675 tok)
- `README.md` — Project documentation (~304 tok)

## pro-merged-master-v1.2/

- `.DS_Store` (~3824 tok)
- `AGENT_START_HERE.md` — Agent start here (~1867 tok)
- `design-language-v1.3.html` — Structura v1.3 Design Language (~7800 tok)
- `MANIFEST_v1.3.md` — Manifest v1.3 (~1907 tok)
- `MANIFEST.txt` (~630 tok)
- `README.md` — Project documentation (~2580 tok)

## pro-merged-master-v1.2/contracts/

- `README.md` — Project documentation (~976 tok)

## pro-merged-master-v1.2/contracts/api/

- `openapi.yaml` (~12725 tok)

## pro-merged-master-v1.2/contracts/events/

- `analyze_documents_job.v1.schema.json` (~539 tok)
- `classify_document_job.v1.schema.json` (~426 tok)
- `embed_document_job.v1.schema.json` (~536 tok)
- `extract_document_job.v1.schema.json` (~528 tok)
- `ingest_document_job.v1.schema.json` (~633 tok)
- `README.md` — Project documentation (~177 tok)

## pro-merged-master-v1.2/contracts/schemas/

- `analysis_note.v1.schema.json` (~638 tok)
- `canonical_field.v1.schema.json` (~572 tok)
- `common_defs.schema.json` (~1907 tok)
- `document_classification.v1.schema.json` (~544 tok)
- `field_candidate.v1.schema.json` (~718 tok)
- `filing_rule.v1.schema.json` (~690 tok)
- `folder_acl.v1.schema.json` (~286 tok)
- `invoice.v1.schema.json` (~1306 tok)
- `medical_eob.v1.schema.json` (~1437 tok)
- `receipt.v1.schema.json` (~1088 tok)
- `review_action.v1.schema.json` (~472 tok)

## pro-merged-master-v1.2/database/

- `001_extensions.sql` (~86 tok)
- `010_types_and_enums.sql` — Declares AS (~1016 tok)
- `020_core_tables.sql` — SQL: tables: ingest_batches, documents, document_assets, document_pages, 1 alter(s) (~4827 tok)
- `025_baseline_identity_acl_candidate_rules.sql` — 025_baseline_identity_acl_candidate_rules.sql (~5470 tok)
- `030_constraints_and_triggers.sql` — SQL: 1 function(s) (~1210 tok)
- `040_indexes_bm25_pgvector.sql` (~1569 tok)
- `050_views_and_functions.sql` — SQL: 5 view(s), 1 function(s) (~799 tok)
- `060_seed_taxonomies.sql` (~642 tok)
- `070_query_examples.sql` (~639 tok)
- `README.md` — Project documentation (~645 tok)

## pro-merged-master-v1.2/docs/

- `01_App_Specification.md` — App specification (~7499 tok)
- `02_Phased_Implementation_Plan.md` — Phased implementation plan (~6156 tok)
- `03_Agent_Bootstrap_and_Execution_Order.md` — Agent bootstrap and execution order (~1352 tok)
- `04_User_Stories_and_Acceptance_Criteria.md` — User stories and acceptance criteria (~1809 tok)
- `05_Nonfunctional_Requirements_Security_Privacy_Observability.md` — Nonfunctional requirements, security, privacy, and observability (~1367 tok)
- `06_Testing_QA_and_Release_Strategy.md` — Testing, QA, and release strategy (~987 tok)
- `07_Repository_Layout_and_Coding_Standards.md` — Repository layout and coding standards (~728 tok)
- `08_ZFS_Datasets_and_Storage_Plan.md` — ZFS datasets and storage plan (~1292 tok)
- `09_Deployment_and_Runtime_Architecture.md` — Deployment and runtime architecture (~699 tok)
- `10_Architectural_Decision_Record_Summary.md` — Architectural decision record summary (~1485 tok)
- `11_Model_Routing_and_Output_Contracts.md` — Model routing and output contracts (~1562 tok)
- `12_Risk_Register_and_Open_Questions.md` — Risk register and open questions (~604 tok)
- `13_Golden_Master_Review_and_Merge_Plan.md` — 13 — Golden Master Review and Merge Plan (~2347 tok)
- `14_Canonicalization_Candidate_Authority_Model.md` — 14 — Canonicalization, Candidate, and Authority Model (~1668 tok)
- `15_PGMQ_and_Worker_Strategy.md` — 15 — PGMQ and Worker Strategy (~865 tok)
- `16_Auth_ACL_Household_Model.md` — 16 — Auth, ACL, and Household Model (~750 tok)
- `17_Rules_Contacts_and_Watched_Folder_Addendum.md` — 17 — Rules, Contacts, and Watched-Folder Addendum (~741 tok)
- `18_Filter_Aware_Vector_Search_Addendum.md` — 18 — Filter-Aware Vector Search Addendum (~699 tok)
- `19_v1.2_Normalization_and_Source_of_Truth.md` — v1.2 normalization and source of truth (~886 tok)
- `20_Codex_xhigh_Feedback_Resolution.md` — Codex xhigh feedback resolution (~861 tok)
- `21_v1.3_Normalization_and_Design_Language.md` — v1.3 normalization and design language (~2672 tok)

## pro-merged-master-v1.2/infrastructure/

- `README.md` — Project documentation (~196 tok)
- `runtime_service_matrix.csv` (~947 tok)

## pro-merged-master-v1.2/infrastructure/zfs/

- `create_datasets.sh` (~759 tok)
- `dataset_matrix.csv` (~683 tok)
- `README.md` — Project documentation (~304 tok)

## pro-merged-master/

- `.DS_Store` (~1640 tok)
- `AGENT_START_HERE.md` — Agent start here (~1668 tok)
- `MANIFEST_v1.1.md` — Manifest — DocVault Agentic Coder Pack v1.1 Merged (~1706 tok)
- `MANIFEST.txt` (~453 tok)
- `README.md` — Project documentation (~1834 tok)

## pro-merged-master/contracts/

- `.DS_Store` (~1640 tok)
- `README.md` — Project documentation (~846 tok)

## pro-merged-master/contracts/api/

- `openapi.yaml` (~4529 tok)

## pro-merged-master/contracts/events/

- `analyze_documents_job.v1.schema.json` (~554 tok)
- `classify_document_job.v1.schema.json` (~425 tok)
- `embed_document_job.v1.schema.json` (~537 tok)
- `extract_document_job.v1.schema.json` (~528 tok)
- `ingest_document_job.v1.schema.json` (~636 tok)
- `README.md` — Project documentation (~177 tok)

## pro-merged-master/contracts/schemas/

- `analysis_note.v1.schema.json` (~653 tok)
- `canonical_field.v1.schema.json` (~538 tok)
- `common_defs.schema.json` (~1587 tok)
- `document_classification.v1.schema.json` (~543 tok)
- `field_candidate.v1.schema.json` (~686 tok)
- `filing_rule.v1.schema.json` (~668 tok)
- `folder_acl.v1.schema.json` (~265 tok)
- `invoice.v1.schema.json` (~1306 tok)
- `medical_eob.v1.schema.json` (~1436 tok)
- `receipt.v1.schema.json` (~1088 tok)
- `review_action.v1.schema.json` (~472 tok)

## pro-merged-master/database/

- `001_extensions.sql` (~86 tok)
- `010_types_and_enums.sql` — Declares AS (~986 tok)
- `020_core_tables.sql` — SQL: tables: ingest_batches, documents, document_assets, document_pages, 1 alter(s) (~4827 tok)
- `030_constraints_and_triggers.sql` — SQL: 1 function(s) (~846 tok)
- `040_indexes_bm25_pgvector.sql` (~1433 tok)
- `050_views_and_functions.sql` — SQL: 5 view(s), 1 function(s) (~798 tok)
- `060_seed_taxonomies.sql` (~642 tok)
- `070_query_examples.sql` (~639 tok)
- `080_gold_master_delta_schema.sql` — 080_gold_master_delta_schema.sql (~5250 tok)
- `README.md` — Project documentation (~509 tok)

## pro-merged-master/docs/

- `01_App_Specification.md` — App specification (~7283 tok)
- `02_Phased_Implementation_Plan.md` — Phased implementation plan (~5807 tok)
- `03_Agent_Bootstrap_and_Execution_Order.md` — Agent bootstrap and execution order (~1207 tok)
- `04_User_Stories_and_Acceptance_Criteria.md` — User stories and acceptance criteria (~1809 tok)
- `05_Nonfunctional_Requirements_Security_Privacy_Observability.md` — Nonfunctional requirements, security, privacy, and observability (~1271 tok)
- `06_Testing_QA_and_Release_Strategy.md` — Testing, QA, and release strategy (~987 tok)
- `07_Repository_Layout_and_Coding_Standards.md` — Repository layout and coding standards (~714 tok)
- `08_ZFS_Datasets_and_Storage_Plan.md` — ZFS datasets and storage plan (~1011 tok)
- `09_Deployment_and_Runtime_Architecture.md` — Deployment and runtime architecture (~658 tok)
- `10_Architectural_Decision_Record_Summary.md` — Architectural decision record summary (~1038 tok)
- `11_Model_Routing_and_Output_Contracts.md` — Model routing and output contracts (~1491 tok)
- `12_Risk_Register_and_Open_Questions.md` — Risk register and open questions (~604 tok)
- `13_Golden_Master_Review_and_Merge_Plan.md` — 13 — Golden Master Review and Merge Plan (~2307 tok)
- `14_Canonicalization_Candidate_Authority_Model.md` — 14 — Canonicalization, Candidate, and Authority Model (~1521 tok)
- `15_PGMQ_and_Worker_Strategy.md` — 15 — PGMQ and Worker Strategy (~800 tok)
- `16_Auth_ACL_Household_Model.md` — 16 — Auth, ACL, and Household Model (~571 tok)
- `17_Rules_Contacts_and_Watched_Folder_Addendum.md` — 17 — Rules, Contacts, and Watched-Folder Addendum (~705 tok)
- `18_Filter_Aware_Vector_Search_Addendum.md` — 18 — Filter-Aware Vector Search Addendum (~663 tok)

## pro-merged-master/infrastructure/

- `README.md` — Project documentation (~165 tok)
- `runtime_service_matrix.csv` (~737 tok)

## pro-merged-master/infrastructure/zfs/

- `create_datasets.sh` (~748 tok)
- `dataset_matrix.csv` (~661 tok)
- `README.md` — Project documentation (~304 tok)

## qwen3-122/

- `first-pass-plan.md` — DocVault: AI-Augmented Personal Document Management System (~30226 tok)

## scripts/gpu/

- `check_text_lane_eligibility.py` — E0 gate check: text-lane eligibility over live corpus documents. (~1540 tok)
- `compare_text_lane_gate.py` — E1 gate comparison: text-lane corpus run(s) vs the pinned baseline report. (~1987 tok)
- `run_phase8_5_semantic_canary.py` — main, build_parser, parse_args (~9270 tok)

## tests/unit/extraction/

- `test_docling_anchor_resolution.py` — test_page_only_evidence_upgrades_to_docling_element_anchor, test_page_only_evidence_falls_back_to_pa (~1324 tok)

## tests/unit/extraction/text_lane/

- `test_column_labeling.py` — from: generate, test_line_item_roles_come_from_claim_registry, test_schema_is_strict_closed_enum, te (~1511 tok)
- `test_eligibility.py` — test_usable_grid_on_text_page_is_text_lane, test_empty_markdown_does_not_disqualify_a_rich_grid, tes (~2061 tok)
- `test_kvp_lane.py` — _StaticSelector: test_span_candidates_cover_labeled_pairs_and_typed_regexes, test_selection_schema_i (~4705 tok)
- `test_review_regressions.py` — Regression coverage for the 2026-06-10 adversarial review findings. (~3649 tok)
- `test_table_extractor.py` — test_line_items_are_verbatim_with_row_anchors, test_totals_row_emits_family_fact_not_line_item, test (~2413 tok)
- `test_table_grid.py` — test_service_lines_grid_round_trip, test_retail_grid_dedupes_span_duplicates_and_detects_header_bloc (~1285 tok)
- `test_text_lane_gateway.py` — _StaticLabeler: label_columns, extract, extract, test_eligible_line_item_region_routes_to_text_lane (~2854 tok)

## tests/unit/semantic_annotations/

- `test_deterministic_plan.py` — _FailingGateway: test_baseline_manifest_plans_tables_without_a_model, test_baseline_fingerprint_is_s (~3162 tok)

## workers/extraction/

- `worker.py` — ExtractionWorkerError: parse_args, process_next_extraction_job, main, handle_stop (~3680 tok)
