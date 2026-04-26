# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-04-24T01:42:51.307Z
> Files: 261 tracked | Anatomy hits: 0 | Misses: 0

## ./

- `.DS_Store` (~3824 tok)
- `CLAUDE.md` — OpenWolf (~57 tok)
- `agents.md` — Agent operating guidance; root implementation plan as phase map, non-archive artifact references as required implementation depth, archive exclusion, Markdown-over-DOCX and chunked large-file review handling, conflict resolution, architecture stewardship, current Phase 3 baseline, Figma evidence, GPU-node runtime/test policy, and Docling worker dependency isolation (~3400 tok)
- `STRUCTURA_PLAN_INDEX.md` — Canonical planning index; source alignment policy, Markdown-first duplicate-artifact handling with DOCX parity note, UI source of truth, GPU node sync policy, stop rule (~1000 tok)
- `STRUCTURA_IMPLEMENTATION_PLAN.md` — Canonical end-to-end implementation plan; phase gates, mandatory per-phase artifact lists, API/database/event coverage, Markdown-first duplicate-artifact handling with DOCX parity note, GPU sync policy (~15500 tok)
- `STRUCTURA_PHASE_1_IMPLEMENTATION_PLAN.md` — Phase 1 execution plan; upload, object storage, Inbox, protected asset streaming, preview, Viewer, fresh-context rereads, Firecrawl evidence rules, validation gate (~5700 tok)
- `STRUCTURA_PHASE_2_IMPLEMENTATION_PLAN.md` — Phase 2 execution plan; manual filing, folders, tags, document organization, ACL/audit, smart-folder records, UI filing workflow, fresh-context rereads, Firecrawl evidence rules, validation gate (~6100 tok)
- `STRUCTURA_PHASE_3_IMPLEMENTATION_PLAN.md` — Phase 3 execution plan; preview/page-asset hardening, Docling worker, canonical artifacts, page/element/table/chunk relational rows, parse quality, debug surfaces, Gate B, fresh-context rereads, Firecrawl evidence rules (~6400 tok)
- `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md` — Phase 4 execution plan; classification, extraction validators, evidence resolver, model gateway, extraction workers, candidate normalization, canonical promotion, review APIs/UI, golden fixtures, Gate C, fresh-context rereads, Firecrawl evidence rules (~7600 tok)
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md` — Phase 5 execution plan; lexical BM25 search, embedding gateway/worker, semantic retrieval, filter-aware planner, hybrid RRF, facets/saved searches, search UI, golden benchmarks, Gate D, fresh-context rereads, Firecrawl evidence rules (~8200 tok)
- `STRUCTURA_PHASE_6_IMPLEMENTATION_PLAN.md` — Phase 6 execution plan; contacts, document-contact links, folder ACL guardrails, watched-folder API/worker, filing rules, dry-run explanations, rule suggestions/application, contacts dedupe, UI, CLI import/maintenance, phase gate, fresh-context rereads, Firecrawl evidence rules (~8800 tok)
- `STRUCTURA_PHASE_7_IMPLEMENTATION_PLAN.md` — Phase 7 execution plan; relationships, review actions, suggestion worker, related-document panel, entity/document timelines, deadlines, smart views, search/filing integration, quality fixtures, phase gate, fresh-context rereads, Firecrawl evidence rules (~8300 tok)
- `STRUCTURA_PHASE_8_IMPLEMENTATION_PLAN.md` — Phase 8 execution plan; difficult-document detection, selective visual embeddings, Qwen handwriting route, review-required uncertainty, visual retrieval contract/policy, mixed hybrid retrieval, low-text fallbacks, benchmarks, runtime observability, phase gate, fresh-context rereads, Firecrawl evidence rules (~9400 tok)
- `STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md` — Phase 9 execution plan; optional analysis workspace, analysis contracts, ACL/sensitivity/citation policy, analysis request API, context builder, prompt/model validation, worker-analysis, note persistence, Figma frame 14:990, core analysis actions, disable mode, observability, Gate E, fresh-context rereads, Firecrawl evidence rules (~10300 tok)
- `STRUCTURA_PHASE_10_IMPLEMENTATION_PLAN.md` — Phase 10 execution plan; exports, manifest/provenance, export authorization/audit, WebAuthn/passkeys, session hardening, API token lifecycle, folder ACL management, backup/restore, admin jobs, service/storage/model/extraction health, settings/admin UI, SAST, phase gate, fresh-context rereads, Firecrawl evidence rules (~11600 tok)
- `STRUCTURA_PHASE_11_IMPLEMENTATION_PLAN.md` — Phase 11 execution plan; golden corpus governance, expected answers, deterministic evaluation harness, extraction/search scoring, E2E and Playwright smoke tests, migration/contract regression, restore rehearsal, SAST/data-flow gate, performance measurements, release-candidate evidence pack, fresh-context rereads, Firecrawl evidence rules (~13200 tok)
- `STRUCTURA_PHASE_12_IMPLEMENTATION_PLAN.md` — Final derived Phase 12 execution plan; internal-GA/release handoff, Phase 11 evidence intake, blocker closure, contract/schema freeze, runtime config, operator runbooks, benchmark threshold approval, UI/security/restore/performance signoff, release notes/tagging, go/no-go, post-release cadence, fresh-context rereads, Firecrawl evidence rules (~13200 tok)
- `STRUCTURA_UI_FIGMA_QA_PLAN.md` — Canonical Figma and Playwright UI QA plan; frame ids, pixel-match rules, workflow QA, UI stop rule (~3000 tok)
- `README.md` — Implementation status through Phase 3, canonical local/GPU verification commands, Compose runtime notes, migration baseline and tracking behavior
- `Makefile` — bootstrap, test, lint, format, contracts, migrate, API/web dev, Compose, and worker-placeholder tasks
- `compose.yaml` — Postgres, API, web, default workers, profile-gated model placeholders, and Redis fallback services
- `.env.example` — Local Structura environment defaults

## Phase 0 implementation scaffold

- `apps/api/structura_api/main.py` — FastAPI app factory, router registration, request-id middleware, JSON request logging
- `apps/api/structura_api/dependencies.py` — Current-principal resolution from API token or session cookie, CSRF dependency for cookie-auth state changes
- `apps/api/structura_api/routes_auth.py` — Password and magic-link session creation, current session lookup, logout, session/CSRF cookies
- `apps/api/structura_api/routes_documents.py` — Phase 0 protected document list and asset route placeholders
- `apps/api/structura_api/routes_jobs.py` — Protected job lookup, admin job list, CSRF-protected retry endpoint
- `apps/api/structura_api/routes_admin.py` — Protected service-health snapshot endpoint
- `apps/web/` — Vite React placeholder shell pointed at the API base URL
- `contracts/` — v1.2 OpenAPI, shared schemas, and pipeline event schemas copied into active repo surface
- `database/` — Baseline SQL 001-060 plus excluded 070 query examples; BM25 compatibility edit for pinned ParadeDB PG17 image
- `docs/adr/0000-phase-0-baseline.md` — Phase 0 architecture decision record covering scaffold, auth, migrations, ParadeDB pin, and job fallback
- `infrastructure/zfs/` — Active ZFS runtime dataset plan copied from v1.2 artifacts
- `lib/auth/service.py` — Bootstrap admin, Argon2id password verification, session/magic-link/API-token service layer
- `lib/config/settings.py` — Runtime settings, contract/database paths, cookie names, session and magic-link TTLs
- `lib/contracts/` — Contract registry and generated/handwritten Pydantic DTOs for Phase 0 API routes
- `lib/db/connection.py` — psycopg connection helper with `structura, public` search path
- `lib/db/migrations.py` — Baseline migration plan, checksum tracking, legacy schema adoption, idempotent reruns
- `lib/jobs/service.py` — Safe job payload validation, create/list/get/claim/heartbeat/complete/fail/retry, service health snapshots
- `lib/observability/logging.py` — Minimal JSON request/event logging
- `scripts/bootstrap_admin.py` — Local admin bootstrap/rotation CLI
- `scripts/migrate.py` — Baseline migration entrypoint
- `scripts/validate_contracts.py` — OpenAPI/schema/event contract validation entrypoint
- `tests/unit/` — Config, contract registry, migrations, auth hashing, and job payload safety tests
- `tests/integration/` — Live Postgres baseline schema, migration idempotency, auth/session/job/service-health tests
- `workers/placeholder.py` — Placeholder worker heartbeat loop, internal health HTTP endpoint, service-health DB snapshots
- `workers/model_placeholder.py` — Profile-gated model service placeholder

## Phase 1/2 UI reference artifacts

- `docs/ui-reference/figma/inbox/` — Phase 1 Inbox Figma context, source screenshot, Playwright comparison screenshot, and comparison notes for frame `17:2`
- `docs/ui-reference/figma/viewer/` — Phase 1 Viewer Figma context, source screenshot, Playwright comparison screenshot, and comparison notes for frame `14:434`
- `docs/ui-reference/figma/folder-tag-filing/` — Phase 2 folder/tag filing composite Figma evidence set; includes context JSON, primary Inbox screenshot, handoff interaction/edge/redline screenshots, extraction-workspace reference, Playwright comparison screenshot, and scope comparison notes

## Phase 3 canonical parse implementation

- `apps/api/structura_api/routes_parse_debug.py` — Admin-scoped parse-debug API for a document; returns bounded parse metadata, current Docling artifacts as protected asset URLs, page summaries, element/table samples, and chunk samples.
- `lib/documents/parse_models.py` — Dataclasses for canonical parse results, parsed pages, elements, tables, chunks, and persistence summaries.
- `lib/documents/canonical_parse.py` — Orchestrates immutable derived Docling artifact storage, current asset upserts, relational parse replacement, document parse metadata update, and cleanup on failed persistence.
- `lib/documents/parse_repository.py` — Persistence repository for replacing `document_pages`, `document_elements`, `document_tables`, and `document_chunks`, plus document parse-state metadata.
- `lib/documents/parse_debug.py` — Read model for protected parse-debug payloads without exposing storage object URIs.
- `workers/docling/converter.py` — Lazy Docling adapter that imports Docling only inside the dedicated worker runtime and normalizes Docling output into Phase 3 parse models.
- `workers/docling/service.py` — Docling job handler; verifies the original asset, converts, persists canonical parse artifacts, refreshes page previews, and records parse failure metadata safely.
- `workers/docling/worker.py` — Queue consumer and internal health endpoint for `docling` jobs.
- `workers/docling/Dockerfile` — Dedicated Docling worker image; installs API requirements, Docling requirements, and native OpenCV/PDF shared libraries without adding Docling/Torch to API or preview images.
- `workers/previews/service.py` — Page-aware preview generation and page asset linkage for Phase 3, with cleanup of derived objects on failed database persistence.

## .claude/

- `settings.json` (~441 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)

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

## gold-master/

- `architecture.md` — System Architecture (~1616 tok)
- `data-model-and-contracts.md` — Data Model and Contracts (~1476 tok)
- `decisions.md` — Gold Master Decisions (~1343 tok)
- `external-validation.md` — External Validation (~1062 tok)
- `implementation-plan.md` — Implementation Plan (~1186 tok)
- `product-and-ux.md` — Product and UX Specification (~1180 tok)
- `README.md` — Project documentation (~905 tok)

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
