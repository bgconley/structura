# Memory

> Chronological action log. Hooks and AI append to this file automatically.
> Old sessions are consolidated by the daemon weekly.

| 00:13 | Created canonical Structura planning layer, initialized git, pushed to GitHub, and synced GPU node checkout | STRUCTURA_PLAN_INDEX.md, STRUCTURA_IMPLEMENTATION_PLAN.md, STRUCTURA_UI_FIGMA_QA_PLAN.md, .gitignore | Repo is pushed to origin/master and cloned at /tank/repos/structura on 10.25.0.50; archive/ ignored; OpenWolf handoff updated | ~9000 |
| 01:35 | Persisted implementation-source policy for future agents | .wolf/cerebrum.md, agents.md, .wolf/anatomy.md | STRUCTURA_IMPLEMENTATION_PLAN.md is recorded as sequencing source while non-archive artifacts provide required implementation depth; archive remains excluded | ~900 |
| 01:55 | Completed Structura Phase 0A-0F runtime foundation | apps/, lib/, database/, contracts/, scripts/, tests/, workers/, compose.yaml, README.md, docs/adr/0000-phase-0-baseline.md | Added FastAPI auth/session routes, Argon2id bootstrap admin, protected route dependencies, Postgres job service, worker health snapshots, idempotent migration tracking, and verified lint/tests/contracts/web build/live Compose smokes | ~25000 |
| 02:25 | Remediated valid Phase 0 review findings | apps/api/structura_api, lib/jobs, contracts/api/openapi.yaml, tests/, README.md, docs/adr/0000-phase-0-baseline.md | Fixed auth validation 500s, configurable cookie reads, protected migration diagnostics, explicit queue fallback profile, retry backoff, and OpenAPI drift; added targeted tests | ~9000 |
| 16:05 | Resolved Phase 0 SAST/type/contract findings | apps/api/structura_api, lib/db, lib/jobs, workers, apps/*/Dockerfile, pyproject.toml, Makefile, tests/unit/test_api_contract_paths.py | Added protected contract route skeletons, exact OpenAPI path parity coverage, clean mypy/pyright typing, SAST tooling target, non-root containers, and verified lint/type/SAST/tests/contracts/build/Compose/live smokes | ~14000 |
| 16:19 | Persisted artifact file-review handling preferences | .wolf/cerebrum.md, agents.md | Default to Markdown over DOCX duplicates unless layout/fidelity is requested or Markdown is incomplete; verify large reads with file length and bounded chunks to avoid terminal-output truncation | ~500 |
| 16:29 | Created Phase 1 implementation execution plan | STRUCTURA_PHASE_1_IMPLEMENTATION_PLAN.md, .wolf/anatomy.md, .wolf/cerebrum.md | Added Phase 1 subphase plan for object storage, upload API, document list/detail, protected assets, previews, Inbox, Viewer, integration tests, gates, fresh-context rereads, and Firecrawl evidence rules | ~6500 |
| 16:35 | Created Phase 2 implementation execution plan | STRUCTURA_PHASE_2_IMPLEMENTATION_PLAN.md, .wolf/anatomy.md, .wolf/cerebrum.md | Added Phase 2 subphase plan for taxonomy seeds, folder/tag APIs, document organization updates, ACL/audit, list/detail propagation, filing UI, smart-folder records, integration tests, gates, fresh-context rereads, and Firecrawl evidence rules | ~7000 |
| 16:40 | Created Phase 3 implementation execution plan | STRUCTURA_PHASE_3_IMPLEMENTATION_PLAN.md, .wolf/anatomy.md, .wolf/cerebrum.md | Added Phase 3 subphase plan for preview/page-asset hardening, preview worker orchestration, Docling worker packaging, canonical artifact persistence, relational page/element/table/chunk population, parse quality, debug API/UI, integration tests, Gate B, fresh-context rereads, and Firecrawl evidence rules | ~7600 |
| 17:44 | Created Phase 4 implementation execution plan | STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md, .wolf/anatomy.md, .wolf/cerebrum.md | Added Phase 4 subphase plan for classification, extraction validators, evidence resolver, model gateway, extraction workers, candidate normalization, canonical promotion, review APIs/UI, golden fixtures, Gate C, fresh-context rereads, and Firecrawl evidence rules | ~9000 |
| 17:58 | Created Phase 5 implementation execution plan | STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md, .wolf/anatomy.md, .wolf/cerebrum.md | Added Phase 5 subphase plan for lexical BM25 search, embedding profile/gateway, embedding worker, semantic retrieval, filter-aware planner, hybrid RRF, facets/saved searches, search UI, golden benchmarks, Gate D, fresh-context rereads, and Firecrawl evidence rules | ~9400 |
| 18:04 | Created Phase 6 implementation execution plan | STRUCTURA_PHASE_6_IMPLEMENTATION_PLAN.md, .wolf/anatomy.md, .wolf/cerebrum.md | Added Phase 6 subphase plan for contacts, document-contact links, folder ACL guardrails, watched-folder API/worker, filing rules, dry-run explanations, rule suggestions/application, contact dedupe, UI, CLI import/maintenance, phase gate, fresh-context rereads, and Firecrawl evidence rules | ~9800 |
| 18:10 | Created Phase 7 implementation execution plan | STRUCTURA_PHASE_7_IMPLEMENTATION_PLAN.md, .wolf/anatomy.md, .wolf/cerebrum.md | Added Phase 7 subphase plan for relationships, review actions, suggestion worker, related-document panel, entity/document timelines, deadlines, smart views, search/filing integration, quality fixtures, phase gate, fresh-context rereads, and Firecrawl evidence rules | ~9300 |
| 18:19 | Created Phase 8 implementation execution plan | STRUCTURA_PHASE_8_IMPLEMENTATION_PLAN.md, .wolf/anatomy.md, .wolf/cerebrum.md | Added Phase 8 subphase plan for difficult-document detection, selective visual embeddings, Qwen handwriting route, review-required uncertainty, visual retrieval contract/policy, mixed hybrid retrieval, low-text fallbacks, benchmarks, runtime observability, phase gate, fresh-context rereads, and Firecrawl evidence rules | ~10400 |
| 18:26 | Created Phase 9 implementation execution plan | STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md, .wolf/anatomy.md, .wolf/cerebrum.md | Added Phase 9 subphase plan for optional analysis workspace, analysis contracts, ACL/sensitivity/citation policy, analysis request API, context builder, prompt/model validation, worker-analysis, note persistence, Figma frame 14:990, core analysis actions, disable mode, observability, Gate E, fresh-context rereads, and Firecrawl evidence rules | ~11200 |
| 18:31 | Created Phase 10 implementation execution plan | STRUCTURA_PHASE_10_IMPLEMENTATION_PLAN.md, .wolf/anatomy.md, .wolf/cerebrum.md | Added Phase 10 subphase plan for exports, manifest/provenance, export authorization/audit, WebAuthn/passkeys, session hardening, API token lifecycle, folder ACL management, backup/restore, admin jobs, service/storage/model/extraction health, settings/admin UI, SAST, phase gate, fresh-context rereads, and Firecrawl evidence rules | ~12600 |
| 18:38 | Created Phase 11 implementation execution plan | STRUCTURA_PHASE_11_IMPLEMENTATION_PLAN.md, .wolf/anatomy.md, .wolf/cerebrum.md | Added Phase 11 subphase plan for golden corpus governance, expected answers, deterministic evaluation harness, extraction/search scoring, E2E and Playwright smoke tests, migration/contract regression, restore rehearsal, SAST/data-flow gate, performance measurements, release-candidate evidence pack, fresh-context rereads, and Firecrawl evidence rules | ~14500 |
| 18:48 | Created final Phase 12 implementation execution plan | STRUCTURA_PHASE_12_IMPLEMENTATION_PLAN.md, .wolf/anatomy.md, .wolf/cerebrum.md | Added derived final internal-GA/release handoff plan for Phase 11 evidence intake, blocker closure, contract/schema freeze, runtime config, operator runbooks, benchmark threshold approval, UI/security/restore/performance signoff, release notes/tagging, go/no-go, post-release cadence, fresh-context rereads, and Firecrawl evidence rules | ~14500 |
| 18:52 | Persisted Structura phase-plan usage rules for future sessions | .wolf/cerebrum.md, .wolf/memory.md | Recorded how to use root plan, phase plans, Fresh Context rereads, non-archive artifacts, Markdown-over-DOCX handling, Firecrawl evidence, source alignment, phase gates, Phase 11 RC scope, final Phase 12 handoff scope, and no-Phase-13 rule | ~1800 |
| 19:00 | Aligned root planning docs with Markdown-first duplicate-artifact handling | STRUCTURA_PLAN_INDEX.md, STRUCTURA_IMPLEMENTATION_PLAN.md, .wolf/anatomy.md, .wolf/cerebrum.md | Verified no material differences in the duplicate `01` and `02` Markdown/DOCX pairs, then updated the root planning layer to default to Markdown while retaining DOCX for fidelity review or suspected drift | ~2200 |
| 03:19 | Persisted GPU node runtime and milestone-test policy | agents.md, .wolf/cerebrum.md, .wolf/memory.md, .wolf/buglog.json | Recorded that milestone validation must commit/push/pull/build/test on `bgconley@10.25.0.50`, repo lives at `/tank/repos/structura`, venvs at `/tank/venvs`, runtime data and bind mounts under `/srv/structura`, models at `/srv/structura/models`, and Docker image storage is not specified by current artifacts | ~1800 |
| 03:24 | Inspected GPU node ZFS state and corrected path assumptions | agents.md, .wolf/cerebrum.md, .wolf/memory.md, .wolf/buglog.json | Verified `tank/repos` and `/tank/repos/structura` already exist, `/tank/venvs` exists on root ext4, `/srv/structura` and all expected `tank/structura*` runtime datasets are absent, and Docker root is `/var/lib/docker` on root ext4 | ~1800 |
| 03:31 | Added GPU-node Structura ZFS runtime bootstrap script | infrastructure/zfs/create_gpu_runtime_datasets.sh, infrastructure/zfs/README.md, .wolf/memory.md | Added an idempotent sudo script that creates only the `/srv/structura` runtime datasets, skips repo/venv datasets to preserve `/tank/repos/structura` and `/tank/venvs`, creates Compose subdirectories, and prints final dataset state | ~1800 |
| 03:39 | Verified GPU-node ZFS bootstrap and fixed runtime ownership logic | infrastructure/zfs/create_gpu_runtime_datasets.sh, infrastructure/zfs/README.md, .wolf/memory.md | Confirmed datasets/properties/mounts exist as expected, repo/venv datasets were not created, and Docker root is unchanged; found writable mounts were not owned for container UID 10001, then updated the script to chown API/worker/model writable dirs to `10001:bgconley` | ~1400 |
| 03:44 | Fixed editable-install packaging discovered during GPU-node bootstrap | pyproject.toml, .wolf/buglog.json, .wolf/memory.md | GPU-node `pip install -e .[dev]` failed due flat-layout auto-discovery; added explicit setuptools package discovery for `apps*`, `lib*`, and `workers*` | ~700 |
| 03:46 | Fixed missing PyYAML type stubs discovered by GPU-node SAST | pyproject.toml, .wolf/buglog.json, .wolf/memory.md | `make sast` reached mypy on the GPU node and failed on missing `yaml` stubs; added `types-PyYAML` to dev dependencies | ~500 |
| 03:52 | Fixed Playwright screenshot side effects found on GPU-node test run | tests/e2e/phase1.spec.ts, .wolf/buglog.json, .wolf/memory.md | E2E screenshots were overwriting tracked `docs/ui-reference` images on the GPU checkout; changed runtime screenshots to use Playwright `testInfo.outputPath` | ~600 |
| 03:58 | Completed GPU-node Phase 1 verification pass | /tank/repos/structura on 10.25.0.50, /tank/venvs/structura, /srv/structura, Docker Compose | Committed/pushed/pulled to GPU node, bootstrapped venv, built Compose API/web/Postgres, ran migrations, verified health, passed pytest `32 passed`, integration `9 passed`, ruff/format/contracts/SAST/type gates, web lint/build, and Playwright `1 passed`; final GPU checkout stayed clean at `cd319dd` | ~2200 |
| 03:50 | Persisted GPU-node host Node/npm policy | agents.md, .wolf/cerebrum.md, .wolf/memory.md | Recorded that the GPU host should not install or rely on host Node/npm for Structura gates; web lint/build and Playwright should use pinned container/app images such as `node:20-alpine` and `mcr.microsoft.com/playwright:v1.59.1-noble` | ~600 |
| 04:05 | Added production web serving and live-stack browser smoke | apps/web/Dockerfile, apps/web/server.mjs, apps/web/src/App.tsx, compose.yaml, playwright.config.ts, tests/e2e/phase1-live.spec.ts | Replaced Vite dev server container with static build/proxy server, changed Compose port binds to localhost defaults, and added opt-in Playwright live test for login/upload/viewer against the real API/DB stack | ~1900 |
| 04:09 | Fixed web container healthcheck after GPU-node runtime validation | compose.yaml, .wolf/buglog.json, .wolf/memory.md | Web served 200 but Compose marked it unhealthy; changed healthcheck from localhost to 127.0.0.1 to target the IPv4 listener directly | ~500 |
| 04:32 | Persisted architecture stewardship and god-module prevention policy | AGENTS.md, .wolf/cerebrum.md, .wolf/memory.md | Paused Phase 2 feature work after identifying oversized-module risk; recorded thin-route/service/repository layering, file-size warning heuristics, refactor-before-appending rules, naming guidance, and completion self-check expectations | ~1600 |
| 04:46 | Refactored in-progress Phase 2 god modules into cohesive API and web modules | apps/api/structura_api/routes_*.py, lib/documents/read_model.py, lib/organization/*.py, apps/web/src/App.tsx, apps/web/src/components, apps/web/src/api.ts, apps/web/src/types.ts | Split organization routes/service/repository/policy from document routes, moved asset streaming to its own route module, moved document read models out of the route file, and split the web shell from rendering components while preserving behavior | ~4300 |
| 05:18 | Persisted GPU-hosted Playwright live-test policy | agents.md, .wolf/cerebrum.md, .wolf/memory.md | Recorded that milestone Playwright runs must use the GPU-hosted web service at `http://10.25.0.50:13000` with the Mac only as browser/controller; GPU Compose exposes only web on LAN while API/Postgres stay loopback-only | ~500 |
| 20:30 | Completed Phase 2 hardening remediation and GPU validation | apps/api/structura_api, lib/auth, lib/jobs, workers/previews, apps/web/server.mjs, tests/, database/065_pipeline_jobs_household_scope.sql | Fixed cross-household job/admin visibility, dead-letter retry claimability, streaming proxy behavior, preview worker execution, and screenshot gates; committed through `c7187b9`, pushed, pulled to GPU, and passed GPU tests/SAST/type/web/live Playwright gates | ~2600 |
| 20:30 | Completed strict Phase 2 Figma capture pass | docs/ui-reference/figma/folder-tag-filing/ | Added composite Figma context and screenshots for folder/tag filing, handoff interaction specs, edge states, dev redlines, extraction workspace reference, and Playwright comparison screenshot; committed/pushed/pulled `f0f38d1` to GPU | ~1400 |
| 20:30 | Persisted current Phase 2 baseline and artifact rules | agents.md, .wolf/cerebrum.md, .wolf/anatomy.md, .wolf/buglog.json, .wolf/memory.md | Recorded that Phase 3 is next, Phase 2 is manual organization only, the strict Figma evidence set is complete, and the previously remediated Phase 2 defects must not regress | ~1200 |
| 21:55 | Implemented Phase 3 canonical parse foundation | apps/api/structura_api, lib/documents, workers/docling, workers/previews, apps/web, contracts/api/openapi.yaml, docs/adr/0003-phase-3-docling-parse.md | Added queued Docling conversion, isolated `worker-docling` image, immutable parse artifacts, relational pages/elements/tables/chunks, parse-debug API/UI, page preview refresh, and preserved Phase 4 seams without adding classification/extraction scope | ~5200 |
| 22:05 | Hardened Phase 3 GPU runtime packaging | workers/docling/Dockerfile, AGENTS.md, .wolf/cerebrum.md, .wolf/memory.md, .wolf/anatomy.md | Kept Docling/Torch isolated to `worker-docling`, added native OpenCV/PDF runtime libraries required by Docling, and recorded that API/previews must enqueue/read parse state rather than import Docling or convert inline | ~1200 |
| 22:20 | Fixed Docling runtime cache and OCR defaults | workers/docling/converter.py, lib/config/settings.py, compose.yaml, docs/adr/0003-phase-3-docling-parse.md | Configured Docling PDF pipeline explicitly, disabled OCR by default for deterministic digital-PDF conversion, kept table structure enabled, and routed HF/XDG/RapidOCR caches to `/srv/structura/cache` | ~1200 |
| 23:25 | Remediated Phase 3 audit gaps before Phase 4 | lib/documents, lib/jobs, lib/organization, database/066_folder_household_uniqueness.sql, database/067_document_read_acl_function.sql, apps/web, tests/, docs/ui-reference/figma/parse-debug | Added centralized document read ACL function, protected document/detail/asset and organization-write reads, scoped folder-name uniqueness by household, recovered stale running jobs, surfaced configured cookie names to web, and enforced parse-debug screenshot baselines | ~4200 |
| 23:40 | Persisted Phase 4 seam readiness | AGENTS.md, .wolf/cerebrum.md, .wolf/memory.md | Recorded that Phase 4 is ready to start from commit `5fc1587`, with canonical parse substrate, candidate/canonical/review tables, extraction/review contracts, safe job runtime, centralized document read ACL, and Viewer/parse-debug UI foundations in place | ~900 |
| 01:45 | Implemented Phase 4 extraction and review foundation | lib/extraction, lib/review, workers/extraction, apps/api/structura_api/routes_review.py, apps/web/src/components/ReviewQueue.tsx, database/068_phase4_extraction_review.sql, tests/ | Added classification, heuristic extraction gateway, receipt/invoice/EOB validators, evidence-backed candidates, canonical promotion, review actions, extraction worker, review queue UI, Phase 4 screenshots, and Phase 5-ready canonical fact/chunk projection seams in commit `d04a762` | ~7000 |
| 13:38 | Persisted Phase 3 live browser validation gap and completion rule | agents.md, .wolf/cerebrum.md, .wolf/buglog.json, .wolf/anatomy.md, .wolf/memory.md | Recorded that backend integration plus mocked Playwright is not sufficient for UI/runtime phase completion; canonical GPU live suite now includes Phase 1, Phase 2, Phase 3, and Phase 4 live specs, with Phase 3 covered by `tests/e2e/phase3-live.spec.ts` and deterministic PDF helper `tests/e2e/support/pdf.ts` | ~1100 |
| 14:35 | Implemented Phase 5 search foundation and persisted Phase 6 seams | lib/search, apps/api/structura_api/routes_search.py, workers/embeddings, database/069_phase5_search.sql, apps/web/src/components/SearchResults.tsx, docs/ui-reference/figma/search, tests/ | Added ACL-aware lexical/semantic/hybrid search, deterministic embeddings, embedding worker, saved searches, smart-folder search execution, Corpus Search UI, Phase 5 screenshot/live specs, and recorded Phase 6 projection/search integration guidance | ~9000 |
| 14:40 | Hardened Phase 4 integration tests for live worker races during Phase 5 GPU validation | tests/integration/test_phase4_extraction_review.py, .wolf/buglog.json, .wolf/memory.md | Replaced direct worker-claim assertions with opportunistic drain-plus-wait helpers so canonical GPU Compose workers can process extraction jobs without making tests flaky | ~1200 |
| 14:44 | Hardened Phase 5 search integration assertions for shared live DB state | tests/integration/test_phase5_search.py, .wolf/buglog.json, .wolf/memory.md | Removed contradictory reviewedOnly=false fixture filter, added unique semantic marker, and matched results by document ID instead of assuming rank 1 | ~900 |
| 15:05 | Hardened Phase 5 live browser suite after downstream jobs/search results exposed selector assumptions | apps/web/src/components/ParseDebugPanel.tsx, tests/e2e/phase5.spec.ts, tests/e2e/phase5-live.spec.ts, agents.md, .wolf/cerebrum.md, .wolf/buglog.json | Kept `docling_convert` visible in Parse Debug even when classify/extract/embed jobs exist, scoped Phase 5 result/evidence locators to the target result card, and recorded the shared-GPU-db locator rule for future live specs | ~1100 |
| 15:14 | Normalized Phase 5 search snippets and tightened live evidence assertion for tokenized highlights | lib/search/snippets.py, lib/search/service.py, tests/unit/test_phase5_search_units.py, tests/integration/test_phase5_search.py, tests/e2e/phase5-live.spec.ts, .wolf/cerebrum.md, .wolf/buglog.json | Phase 5 live reached the correct Viewer evidence target but BM25/highlight rendering exposed `<b>` tags and split the hyphenated marker; snippets are now plain text and the live spec asserts unique run id plus stable claim evidence text | ~1000 |
| 17:22 | Persisted Phase 5 hardening closure and Phase 6 seams | agents.md, .wolf/anatomy.md, .wolf/cerebrum.md, .wolf/buglog.json, .wolf/memory.md | Recorded commit `81abea2`, smart-folder planner parity, real ingest worker, Phase 6 placeholder contract parity, expanded facets/UI, CI workflows, refactor boundaries, GPU validation evidence, and bug-log entries for the closed Phase 5 audit gaps | ~1600 |
| 22:20 | Implemented Phase 6 transparent organization automation | apps/api/structura_api/routes_contacts.py, apps/api/structura_api/routes_automation.py, lib/contacts, lib/automation, lib/documents/ingestion.py, lib/documents/maintenance.py, workers/watched_folders, apps/web/src/components/AutomationWorkbench.tsx, contracts/api/openapi.yaml, database/072_phase6_automation.sql, scripts/structura.py, tests/, docs/ui-reference/figma/automation | Added contacts, aliases, document-contact links, duplicate merge suggestions, filing rules, dry-run explanations, accept/reject/defer suggestions, watched-folder PDF intake, operator maintenance enqueues, Automation Workbench UI, Linux screenshot baseline, and Phase 7 seam notes while preserving thin-route/service/repository boundaries | ~9000 |
| 22:35 | Fixed GPU Phase 6 validation failures | lib/automation/repository.py, tests/integration/test_phase1_documents.py, .wolf/buglog.json, .wolf/memory.md | GPU live-DB pytest found a fetch-after-update bug in rule-run persistence and a stale Phase 1 rollback monkeypatch after ingestion extraction; fixed the repository row fetch and pointed the test at `lib.documents.ingestion.create_job_with_cursor` | ~700 |
| 22:45 | Hardened Phase 6 live Playwright locator | tests/e2e/phase6-live.spec.ts, .wolf/buglog.json, .wolf/memory.md | Full live phase1-6 suite reached Phase 6 and failed because the saved rule name appeared in both status and row text; scoped the assertion/action to the target `.rule-row` | ~400 |
| 22:50 | Scoped Phase 6 dry-run live assertion | tests/e2e/phase6-live.spec.ts, .wolf/buglog.json, .wolf/memory.md | Phase 6 live then exposed duplicate matched-count text in the status banner and dry-run panel; scoped assertion to `aria-label="Rule dry-run result"` and verified Phase 6 live passes | ~400 |
| 23:05 | Persisted Phase 6 remediation closure and Phase 7 seams | agents.md, .wolf/cerebrum.md, .wolf/anatomy.md, .wolf/buglog.json, .wolf/memory.md | Recorded commits `45193ba`/`7111b83`, full rule-action parity, atomic automation apply/accept, watched-folder root/symlink hardening, deferred placeholder contract parity, expanded Automation Workbench modules, CLI execute behavior, GPU validation evidence, and Phase 7 guardrails | ~1400 |
| 03:35 | Implemented Phase 7 relationships and timelines | apps/api/structura_api/routes_relationships.py, lib/relationships, workers/relationships, database/073_phase7_relationships.sql, apps/web/src/components/RelationshipPanel.tsx, apps/web/src/components/RelationshipWorkspace.tsx, tests/, docs/ui-reference/figma/relationships-timelines | Added relationship persistence/API/worker/UI, manual create/accept/reject actions, deterministic suggestions, deadlines, timelines, relationship/deadline search filters/facets/smart views, Phase 7 screenshots/live specs, and Phase 8 visual-retrieval seams in commit `13ce60d` | ~9000 |
| 03:38 | Fixed Phase 7 GPU validation deadline refresh failure | lib/relationships/service.py | GPU live-DB pytest exposed `canonical_fields.confidence` as a non-existent column; deadline refresh now joins selected `field_candidates` for confidence and handles canonical evidence objects | ~600 |
| 03:43 | Hardened Phase 7 live and shared-worker gates | tests/e2e/phase7-live.spec.ts, tests/integration/test_phase4_extraction_review.py, agents.md, README.md, .wolf/cerebrum.md, .wolf/anatomy.md, .wolf/memory.md | Scoped Phase 7 live selectors for shared GPU DB duplicates, changed extraction rerun tests to wait for terminal job status when Compose workers claim jobs, updated Phase 7 baseline docs/memory, and validated GPU current HEAD `eebdb3d` with 97 pytest, SAST/type/web gates, Compose health, and live phase1-7 Playwright | ~1800 |
| 02:39 | Implemented Phase 8 difficult-document foundation and local preflight | lib/documents/quality.py, lib/search/visual_repository.py, lib/search/embedding_*.py, lib/extraction/*, workers/embeddings/worker.py, workers/docling/worker.py, apps/web/src/components, contracts/api/openapi.yaml, tests/ | Added quality detection, review-required document-quality tasks, selective visual embedding jobs, visual search mode/includeVisual, Qwen review-required handwriting route, difficult-document UI cues, Phase 8 mocked/live specs, Linux screenshot baseline, and Phase 9 seam guidance; local ruff/format/contracts/mypy/pytest/web lint/build/Playwright mocked preflight passed while GPU validation remains the canonical milestone gate | ~2600 |
| 03:10 | Closed Phase 8 GPU live browser races and validated milestone | apps/web/src/App.tsx, tests/e2e/phase8.spec.ts, tests/e2e/support/structuraMock.ts, AGENTS.md, .wolf/buglog.json | Fixed late-search response navigation back to Search and stale selected-document detail after worker quality persistence; committed `27cc3b0`/`4a83690`, pushed/pulled to GPU, rebuilt web, and passed GPU ruff/format/contracts/pyright/mypy/pytest 113/SAST/web lint-build/live phase1-8 Playwright | ~1200 |
| 23:45 | Began Phase 8.5 model-runtime implementation | STRUCTURA_PHASE_8_5_IMPLEMENTATION_PLAN.md, lib/model_runtime, lib/extraction/gateways, lib/search/embeddings, compose.yaml, infrastructure/models, scripts/run_model_corpus.py, docs/adr/0004-phase-8-5-local-model-runtime.md | Added explicit Qwen/Granite/text/visual model profiles, bounded HTTP/media/redaction/health primitives, truthful live extraction adapters, live embedding adapters, fixture-mode quarantine, model Compose profiles, model-corpus gate scaffolding, and Phase 9 prerequisite docs | ~4000 |
| 02:25 | Recorded Firecrawl-backed Phase 8.5 Blackwell/vLLM runtime findings | .wolf/cerebrum.md, .wolf/memory.md, .firecrawl/* | Persisted voipmonitor/cu130, vLLM KV-cache/memory, Qwen3-VL, Docker GPU placement, and model co-residency decisions; no code runtime changes made in this pass | ~900 |
| 02:45 | Hardened Phase 8.5 live model runtime placement and smoke sequencing | compose.yaml, workers/model_services, scripts/gpu/phase8_5_model_smoke.sh, scripts/gpu/probe_phase8_5_live_models.py, docs/model-runtime/phase8_5_gpu_validation.md, docs/adr/0004-phase-8-5-local-model-runtime.md | Replaced `gpus: all` with explicit Compose GPU reservations, added vLLM memory/context knobs, made `models-live` the always-on Qwen2B semantic + Granite core profile, moved Qwen3-VL 8B, text embeddings, and visual embeddings to on-demand/offload profiles, and added managed sequential smoke validation because live co-residency exhausted KV-cache on the two 24GB Blackwell cards | ~1400 |
| 03:05 | Corrected live Qwen3-VL visual embedding dimensions | lib/model_runtime/profiles.py, lib/config/settings.py, lib/model_runtime/clients/_embedding.py, database/076_phase8_5_visual_embedding_2048.sql, scripts/gpu/probe_phase8_5_live_models.py, tests/ | Live visual embedding rejected the `dimensions` override and returned native 2048-dimensional vectors; updated runtime profile/defaults, omitted unsupported OpenAI dimensions for visual embeddings, added a 2048 pgvector index migration, and aligned tests/docs | ~1200 |
| 19:38 | Persisted Phase 8.5 semantic-pipeline recalibration and anti-patterns | AGENTS.md, agents.md, .wolf/cerebrum.md, .wolf/anatomy.md, .wolf/memory.md | Recorded Docling -> Qwen3-VL 2B -> Granite as the canonical default semantic/extraction pipeline, Qwen3-VL 8B as user-selectable only, document-quality outcomes versus runtime failures, anti-patterns to avoid, visual embedding 2048-dim live behavior, and Phase 9 stop gates | ~1700 |
| 23:51 | Recorded Phase 8.5 critical extraction closure and GPU proof | agents.md, .wolf/anatomy.md, .wolf/cerebrum.md, .wolf/memory.md, .wolf/buglog.json | Captured scoped extraction persistence, Granite model-output contracts, semantic-type-driven line-item routing, BMW line-item normalization, aggregate invoice reconciliation, final `9fd1534` GPU validation, final live document IDs, zero Qwen8B invocations, zero failed jobs, and native-memory read-only limitation | ~1800 |
| 01:22 | Noted low-priority pgvector/halfvec visual-embedding awareness item | .wolf/cerebrum.md, .wolf/memory.md | Recorded that pgvector stores current 2048-dimensional visual rows as generic `vector` while indexing/searching through `halfvec(2048)`; profile-name/config drift should be cleaned up later, but this is not an immediate Phase 8.5 priority | ~400 |
| 03:15 | Tightened Qwen3-VL-4B Smart Parse page-window runtime profile | lib/model_runtime/profiles.py, compose.yaml, tests/unit/semantic_annotations/test_gateways.py, docs/superpowers, .wolf/* | Preserved the existing Qwen semantic contract while capping Smart Parse at one image per request after live BH Photo canary output omitted a Docling page annotation under multi-image fan-in; also normalized docs/tests away from the inaccurate Qwen4 shorthand | ~1200 |
| 04:20 | Realigned Phase 8.5 Docling/Qwen/Granite diagnosis path | lib/semantic_annotations, lib/extraction, lib/model_runtime, scripts/gpu/run_phase8_5_semantic_canary.py, compose.yaml, AGENTS.md, STRUCTURA_PHASE_8_5_IMPLEMENTATION_PLAN.md, .wolf/* | Restored Qwen3-VL-4B Smart Parse to four-image fan-in with exact-page-coverage fallback, added whole-document Docling context plus focused page windows, replaced first-page document-type merge with Docling/page-vote evidence, gated Granite target schemas by Docling anchors, put Granite table tags first, stopped mixed vLLM structured-output payloads, and added a semantic-only canary before full corpus reruns | ~1800 |
| 05:00 | Fixed GPU runtime object-store permissions root cause | lib/storage/service.py, infrastructure/zfs/create_gpu_runtime_datasets.sh, tests/unit/test_storage.py, agents.md, .wolf/* | Stored objects now use 0660 files and setgid group-readable directories; bootstrap repairs existing runtime trees for 10001:bgconley access so host-side Phase 8.5 diagnostics can read derived artifacts without workarounds | ~1200 |
| 09:35 | Fixed GPU ZFS bootstrap idempotency during permission repair | infrastructure/zfs/create_gpu_runtime_datasets.sh, tests/unit/test_gpu_runtime_bootstrap_script.py, .wolf/* | A live `sudo create_gpu_runtime_datasets.sh` run failed because unchanged mountpoints were reapplied on busy mounted datasets; the script now checks ZFS property values before setting and skips mounting datasets already marked mounted | ~900 |
| 09:45 | Fixed GPU ZFS bootstrap result reporting | infrastructure/zfs/create_gpu_runtime_datasets.sh, tests/unit/test_gpu_runtime_bootstrap_script.py, .wolf/* | The permission repair completed but final status printing passed literal `tank/structura/*` to ZFS; result reporting now uses `zfs list -r -d 1` and has regression coverage | ~500 |
| 09:55 | Fixed container group membership for runtime object writes | compose.yaml, tests/unit/test_compose_model_profiles.py, agents.md, .wolf/* | New object probe still produced 660 files with group 10001 because UID 10001 was not in the host operator group and could not preserve setgid on bgconley-group dirs; app/worker services now use `STRUCTURA_RUNTIME_HOST_GID` through Compose `group_add` | ~1000 |
| 10:05 | Fixed Qwen3-VL-4B semantic context-length rejection | lib/model_runtime/profiles.py, lib/semantic_annotations/qwen_gateway.py, compose.yaml, tests/, .wolf/* | BH Photo live semantic pass hit vLLM 16,384-token limit with 12,545 input tokens plus 3,840 output tokens; Smart Parse now uses a measured 24K Qwen3-VL-4B context, keeps the 3,840-token semantic output budget, and falls back to single-page windows on context-length errors | ~1200 |
| 15:08 | Added Qwen semantic-planner optimization spec and execution plan | docs/superpowers/specs/2026-04-29-phase-8-5-qwen-semantic-planner-optimization-spec.md, docs/superpowers/plans/2026-04-29-phase-8-5-qwen-semantic-planner-optimization.md, .wolf/anatomy.md, .wolf/cerebrum.md | Captured the Qwen-only Phase 8.5 hardening path: recall-oriented prompt contract, additive semantic schema fields, richer Docling context, safer merge/fanout policy, semantic-canary scorecards, and exact repo seams for each incremental change | ~2200 |
| 15:55 | Implemented Qwen semantic-planner bounded-recall contract locally | lib/semantic_annotations/prompting.py, contracts/schemas/semantic_annotation_*.v1.schema.json, lib/semantic_annotations/{docling_audit,docling_context,qwen_gateway,qwen_output_normalization,manifest_merge,service}.py, scripts/gpu/run_phase8_5_semantic_canary.py, tests/fixtures/semantic_annotations/semantic_canary_expectations.example.json | Smart Parse v3 now asks Qwen3-VL-4B for material-region recall without canonical facts, preserves planner metadata and Docling weak-table/family-tension context, raises model-output regions to 12, prioritizes line-item/payment Granite jobs within six-job smart fanout, and adds semantic-canary expectation scorecards; local focused tests, ruff, schema JSON checks, and mypy pass | ~2200 |
| 22:45 | Swapped Smart Parse semantic runtime to Qwen3-VL-8B FP8 | lib/model_runtime/profiles.py, compose.yaml, workers/model_services/start_qwen_vllm.sh, STRUCTURA_PHASE_8_5_*.md, docs/adr/0004-phase-8-5-local-model-runtime.md, AGENTS.md, .wolf/* | Replaced the default Qwen3-VL-4B semantic service with the bakeoff-winning Qwen/Qwen3-VL-8B-Instruct-FP8 profile on model-qwen-semantic:8104 while preserving the same semantic contract, prompt path, four-image fan-in, planner-resolution visual-token bounds, and Granite handoff; set vLLM max_model_len=32768, max_num_seqs=1, gpu_memory_utilization=0.88, kv_cache_dtype=fp8, mm processor cache 0, and disabled prefix caching; kept 4B as historical/canary only and left separate model-qwen HQ/rescue disabled/deferred | ~1500 |
| 07:20 | Removed legacy separate Qwen HQ/rescue runtime path | compose.yaml, lib/config/settings.py, lib/semantic_annotations, lib/extraction, apps/api, apps/web, scripts/gpu, tests, docs/adr, docs/model-runtime, agents.md, .wolf/* | Removed `STRUCTURA_QWEN8_ENABLED`, the inactive `model-qwen`/placeholder services, High Quality/Allow 8B Rescue API and UI paths, private-corpus HQ/rescue flags, and rescue enqueue behavior. Smart Parse now has one active Qwen path: Qwen3-VL-8B-Instruct-FP8 on `model-qwen-semantic:8104`; uncertainty routes to review instead of a second semantic pass. | ~1300 |
| 11:31 | Persisted latest Phase 8.5 model-pipeline state and review findings | .wolf/cerebrum.md, .wolf/anatomy.md, .wolf/memory.md, artifacts/structura-model-prompts-contracts-behaviors-20260501T082453Z-v2.zip | Recorded the active Docling -> Qwen3-VL-8B FP8 -> Granite -> validators/review pipeline, Qwen semantic-understanding role, resident corpus run `20260501T080539Z`, removed Phase 4 auto-classify/default overwrite risk, production-style no-heredoc runner preference, v2 share pack path, and remaining hardening risks from the external review validity check | ~1600 |
| 2026-06-09 | Implemented review-workflow and D8 quality-outcome surfacing batch | database/087_phase8_5_quality_outcome.sql, lib/extraction/extraction_repository.py, lib/extraction/service.py, lib/documents/read_model.py, lib/review/*, apps/api/structura_api/routes_review.py, contracts/api/openapi.yaml, contracts/schemas/review_action.v1.schema.json, apps/web/src/*, docs/adr/0005, tests/unit | Persisted ADR 0005 D8 quality outcomes on document_extractions (migration 087), exposed qualityOutcome/claimResolutionDecisions/regionJobCoverage on document detail, rerouted review rerun_extraction to a deduplicated semantic_annotate Smart Parse job, persisted requested_by/requested_by_user_id/user_intent_reason in extraction metadata_json, made observation/line-item review tasks actionable (new candidate read endpoints + accept/reject actions with audit), added deterministic web evidence-locator selection mirroring evidence_locator.py, and removed fabricated UI state (page-1-only viewer, fake highlight, 86% chip, fake pipeline zeros, dead buttons) | ~3000 |
| 21:15 | Session end: 195 writes across 95 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 194 reads | ~82604 tok |
| 21:17 | Session end: 195 writes across 95 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 194 reads | ~82604 tok |
| 21:22 | Session end: 195 writes across 95 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 194 reads | ~82604 tok |
| 21:30 | Edited lib/extraction/reconciliation_repository.py | modified maybe_reconcile_semantic_annotation() | ~681 |
| 21:30 | Edited lib/extraction/reconciliation_repository.py | modified _region_job_status_counts() | ~215 |
| 21:30 | Edited workers/extraction/worker.py | 10→11 lines | ~142 |
| 21:34 | Session end: 198 writes across 95 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 194 reads | ~83642 tok |
| 21:39 | Session end: 198 writes across 95 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 194 reads | ~83642 tok |
| 21:49 | Created lib/extraction/docling_anchor_resolution.py | — | ~938 |
| 21:49 | Edited lib/extraction/docling_anchor_resolution.py | 2→2 lines | ~37 |
| 21:49 | Edited lib/extraction/docling_anchor_resolution.py | _normalize_bbox() → normalize_bbox() | ~34 |
| 21:49 | Edited lib/extraction/evidence.py | inline fix | ~16 |
| 21:50 | Edited lib/extraction/evidence.py | inline fix | ~12 |
| 21:50 | Edited lib/extraction/region_envelope_projection.py | modified finalized_region_output() | ~563 |
| 21:50 | Edited lib/extraction/model_output_normalization.py | modified normalize_granite_region_output() | ~428 |
| 21:51 | Edited lib/extraction/model_output_normalization.py | modified _finalized_output() | ~215 |
| 21:51 | Edited lib/extraction/model_output_normalization.py | added 1 import(s) | ~60 |
| 21:53 | Created tests/unit/extraction/test_docling_anchor_resolution.py | — | ~1253 |
| 21:53 | Edited tests/unit/extraction/test_docling_anchor_resolution.py | inline fix | ~23 |
| 21:54 | Edited tests/unit/extraction/test_docling_anchor_resolution.py | modified _source() | ~249 |
| 21:56 | Session end: 210 writes across 100 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 194 reads | ~87470 tok |
| 22:10 | Edited lib/extraction/claims.py | 16→16 lines | ~160 |
| 22:10 | Edited lib/extraction/claims.py | 8→8 lines | ~96 |
| 22:11 | Edited lib/extraction/claims.py | modified _normalized_confidence() | ~187 |
| 22:11 | Edited lib/extraction/observation_repository.py | 3→3 lines | ~36 |
| 22:11 | Edited lib/extraction/observation_repository.py | added 1 import(s) | ~65 |
| 22:14 | Edited lib/extraction/claim_aggregate_reconciliation.py | modified _family_is_compatible() | ~112 |
| 22:16 | Session end: 216 writes across 102 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 194 reads | ~88126 tok |
| 22:35 | GPU validation iterations 1-4 complete | lib/extraction/{reconciliation_repository,docling_anchor_resolution,claims,claim_aggregate_reconciliation,observation_repository}.py, compose.yaml, docs/adr/0005 | Four corpus runs on P620-01 found and fixed: settled-job trigger blind spot (zero aggregates), page-only KVP evidence dropping all claims (Docling anchor resolution added), percent-style confidence overflowing numeric(5,4), dot-less observation keys skipped by family gate, unmapped embedding kill switch. Final run 20260610T021547Z: 6 aggregates incl. first receipt lane + partial aggregate with dead-letter coverage, KVP candidates restored, quality outcomes persisted, zero non-model failures | ~12000 |
| 22:35 | Session end: 216 writes across 102 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 194 reads | ~88126 tok |
| 22:45 | Session end: 216 writes across 102 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 194 reads | ~88126 tok |
| 00:57 | Edited lib/semantic_annotations/manifest_normalization.py | removed 6 lines | ~11 |
| 00:57 | Edited lib/semantic_annotations/manifest_normalization.py | 22→22 lines | ~323 |
| 00:58 | Edited lib/semantic_annotations/manifest_normalization.py | modified _normalize_region() | ~147 |
| 00:58 | Edited lib/semantic_annotations/manifest_normalization.py | 6→4 lines | ~43 |
| 01:03 | Edited scripts/gpu/run_phase8_5_semantic_canary.py | modified _semantic_report() | ~153 |
| 01:04 | Edited scripts/gpu/run_phase8_5_semantic_canary.py | 2→5 lines | ~84 |
| 01:04 | Edited scripts/gpu/run_phase8_5_semantic_canary.py | 2→6 lines | ~71 |
| 01:06 | Created .claude/worktrees/agent-a86df2a212eebdab3/lib/extraction/expected_field_coverage.py | — | ~1766 |
| 01:06 | Edited .claude/worktrees/agent-a86df2a212eebdab3/lib/extraction/service.py | added 1 import(s) | ~57 |
| 01:06 | Edited .claude/worktrees/agent-a86df2a212eebdab3/lib/extraction/service.py | added 1 condition(s) | ~208 |
| 01:06 | Edited lib/extraction/granite_budgets.py | modified granite_length_retry_budget() | ~237 |
| 01:06 | Edited .claude/worktrees/agent-a86df2a212eebdab3/lib/model_runtime/reliability_summaries.py | modified expected_field_coverage_summary() | ~760 |
| 01:06 | Edited .claude/worktrees/agent-a86df2a212eebdab3/lib/model_runtime/reliability_report.py | 13→14 lines | ~102 |
| 01:06 | Edited .claude/worktrees/agent-a86df2a212eebdab3/lib/model_runtime/reliability_report.py | 1→4 lines | ~82 |
| 01:07 | Created .claude/worktrees/agent-a86df2a212eebdab3/tests/unit/extraction/test_expected_field_coverage.py | — | ~2916 |
| 01:07 | Created .claude/worktrees/agent-a86df2a212eebdab3/tests/unit/model_runtime/test_reliability_expected_field_coverage.py | — | ~1422 |
| 01:08 | Edited lib/extraction/canonical_repository.py | added 1 import(s) | ~103 |
| 01:09 | Edited lib/extraction/canonical_repository.py | modified candidate_auto_promotion_rejection_reason() | ~161 |
| 01:09 | Created .claude/worktrees/agent-a86df2a212eebdab3/lib/semantic_annotations/input_budget.py | — | ~2558 |
| 01:09 | Edited lib/extraction/canonical_promotion_policy.py | added 1 import(s) | ~64 |
| 01:09 | Edited lib/extraction/canonical_promotion_policy.py | modified candidate_auto_promotion_rejection_reason() | ~184 |
| 01:09 | Edited .claude/worktrees/agent-a86df2a212eebdab3/scripts/gpu/run_phase8_5_semantic_canary.py | 23→28 lines | ~274 |
| 01:09 | Edited .claude/worktrees/agent-a86df2a212eebdab3/scripts/gpu/run_phase8_5_semantic_canary.py | _estimate_text_tokens() → estimate_text_tokens() | ~70 |
| 01:09 | Edited lib/extraction/canonical_repository.py | modified candidate_auto_promotion_rejection_reason() | ~39 |
| 01:10 | Edited .claude/worktrees/agent-a86df2a212eebdab3/scripts/gpu/run_phase8_5_semantic_canary.py | _estimate_text_tokens() → estimate_text_tokens() | ~73 |
| 01:10 | Edited .claude/worktrees/agent-a86df2a212eebdab3/scripts/gpu/run_phase8_5_semantic_canary.py | _image_dimensions() → image_dimensions() | ~69 |
| 01:10 | Edited .claude/worktrees/agent-a86df2a212eebdab3/scripts/gpu/run_phase8_5_semantic_canary.py | 14→14 lines | ~124 |
| 01:10 | Edited .claude/worktrees/agent-a86df2a212eebdab3/scripts/gpu/run_phase8_5_semantic_canary.py | _estimate_text_tokens() → estimate_text_tokens() | ~55 |
| 01:10 | Edited .claude/worktrees/agent-a86df2a212eebdab3/scripts/gpu/run_phase8_5_semantic_canary.py | removed 98 lines | ~8 |
| 01:10 | Edited .claude/worktrees/agent-a86df2a212eebdab3/lib/config/settings.py | 2→6 lines | ~110 |
| 01:11 | Edited .claude/worktrees/agent-a86df2a212eebdab3/lib/semantic_annotations/qwen_gateway.py | expanded (+6 lines) | ~220 |
| 01:11 | Edited .claude/worktrees/agent-a86df2a212eebdab3/lib/semantic_annotations/qwen_gateway.py | 2→4 lines | ~42 |
| 01:11 | Edited .claude/worktrees/agent-a86df2a212eebdab3/lib/semantic_annotations/qwen_gateway.py | modified _generate_manifest_for_source() | ~830 |
| 01:11 | Edited .claude/worktrees/agent-a86df2a212eebdab3/lib/semantic_annotations/qwen_gateway.py | modified _timeout_seconds_for_profile() | ~290 |
| 01:12 | Edited .claude/worktrees/agent-a86df2a212eebdab3/lib/semantic_annotations/qwen_gateway.py | modified _manifest_from_response() | ~64 |
| 01:12 | Edited .claude/worktrees/agent-a86df2a212eebdab3/lib/semantic_annotations/qwen_gateway.py | 5→10 lines | ~149 |
| 01:12 | Created .claude/worktrees/agent-a86df2a212eebdab3/tests/unit/semantic_annotations/test_input_budget.py | — | ~1596 |
| 01:13 | Edited .claude/worktrees/agent-a86df2a212eebdab3/tests/unit/semantic_annotations/test_input_budget.py | modified _estimate() | ~36 |
| 01:13 | Edited .claude/worktrees/agent-a86df2a212eebdab3/tests/unit/semantic_annotations/test_gateways.py | modified test_live_qwen_gateway_attaches_input_budget_warning_when_estimate_exceeds_budget() | ~666 |
| 01:15 | Edited .claude/worktrees/agent-a86df2a212eebdab3/.wolf/anatomy.md | expanded (+8 lines) | ~402 |
| 01:20 | Session end: 256 writes across 113 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 210 reads | ~105375 tok |
| 06:05 | Remaining-items phase complete | lib/semantic_annotations (family repairs removed), granite_budgets, canonical_promotion_policy, telemetry agent merge, tests/e2e baselines | Family-specific semantic-intent normalization deleted per generalization spec (structural-only v2, canary scores post-planning manifest); Granite length retry to 8192 ceiling; source-based auto-promotion; expected-field coverage + Qwen input-budget telemetry live; Playwright baselines regenerated; run 5: 8 aggregates vs 6, telemetry verified, zero model auto-promotions | ~15000 |
| 01:39 | Session end: 256 writes across 113 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 210 reads | ~105375 tok |
| 01:46 | Edited lib/extraction/granite_prompting.py | modified _compact_shape_for_schema() | ~136 |
| 01:50 | Session end: 257 writes across 114 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 210 reads | ~105511 tok |
| 02:12 | Session end: 257 writes across 114 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 210 reads | ~105511 tok |
| 02:25 | Edited lib/model_runtime/clients/_openai_vision.py | 12→13 lines | ~165 |
| 02:25 | Edited lib/model_runtime/clients/_openai_vision.py | modified _truncation_content_diagnostics() | ~244 |
| 02:28 | Session end: 259 writes across 115 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 210 reads | ~105920 tok |
| 02:31 | Session end: 259 writes across 115 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 210 reads | ~105920 tok |
| 02:57 | Session end: 259 writes across 115 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 210 reads | ~105920 tok |
| 03:06 | Session end: 259 writes across 115 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 210 reads | ~105920 tok |
| 03:20 | Created docs/adr/0006-extractive-first-extraction.md | — | ~1549 |
| 03:22 | Created docs/superpowers/plans/2026-06-10-extractive-first-extraction-plan.md | — | ~2652 |
| 07:55 | Clean gate achieved; extractive-first migration approved | docs/adr/0006, docs/superpowers/plans/2026-06-10-extractive-first-extraction-plan.md, workers/model_services, contracts | Run 9: 101/101 jobs, zero dead letters, 9/9 aggregates with quality outcomes after whitespace-loop root cause fixed (xgrammar disable_any_whitespace + tokenization-aware bounds). Live suite 7/8 (phase8-live killed by planner dead-letter -> E3 scope). User approved extractive-first redesign; ADR 0006 + E0-E5 plan committed; baseline pinned to run 9 | ~14000 |
| 03:23 | Session end: 261 writes across 117 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 210 reads | ~110421 tok |
| 03:25 | Session end: 261 writes across 117 files (repro_group_collapse.py, claims.py, model_output_value_parsing.py, candidate_value_parsing.py, claim_resolver.py) | 210 reads | ~110421 tok |

## Session: 2026-06-10 03:26

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 03:41 | Created ../../../../tmp/structura-e0-capture/corpus_inventory.sql | — | ~182 |
| 03:41 | Created ../../../../tmp/structura-e0-capture/run9_docs.sql | — | ~167 |
| 03:42 | Created ../../../../tmp/structura-e0-capture/run9_files.sql | — | ~74 |
| 03:42 | Created ../../../../tmp/structura-e0-capture/run9_tables.sql | — | ~127 |
| 03:48 | Edited lib/extraction/models.py | 13→15 lines | ~142 |
| 03:48 | Edited lib/extraction/source_repository.py | 12→14 lines | ~110 |
| 03:48 | Edited lib/extraction/source_repository.py | 4→8 lines | ~134 |
| 03:48 | Edited lib/config/settings.py | 1→5 lines | ~115 |
| 03:48 | Created lib/extraction/text_lane/__init__.py | — | ~113 |
| 03:49 | Created lib/extraction/text_lane/table_grid.py | — | ~2110 |
| 03:49 | Created lib/extraction/text_lane/eligibility.py | — | ~1418 |
| 03:50 | Edited compose.yaml | 10→12 lines | ~191 |
| 03:50 | Edited compose.yaml | 4→6 lines | ~102 |
| 03:50 | Edited compose.yaml | 9→11 lines | ~166 |
| 03:51 | Created ../../../../tmp/structura-e0-capture/gen_fixtures.py | — | ~1899 |
| 03:52 | Created tests/unit/extraction/text_lane/test_table_grid.py | — | ~1285 |
| 03:52 | Created tests/unit/extraction/text_lane/test_eligibility.py | — | ~1893 |
| 03:54 | Edited lib/model_runtime/contracts.py | expanded (+36 lines) | ~302 |
| 03:54 | Created lib/model_runtime/clients/_openai_text.py | — | ~1268 |
| 03:56 | Created lib/extraction/text_lane/column_labeling.py | — | ~2088 |
| 03:56 | Created lib/extraction/text_lane/table_extractor.py | — | ~3756 |
| 03:57 | Edited lib/extraction/text_lane/table_extractor.py | reduced (-6 lines) | ~19 |
| 03:57 | Created lib/extraction/text_lane/gateway.py | — | ~1861 |
| 03:58 | Created lib/extraction/gateways/routing.py | — | ~1508 |
| 03:58 | Edited lib/extraction/validators.py | modified validate_text_lane_region_payload() | ~414 |
| 03:58 | Edited lib/extraction/service.py | 1→5 lines | ~44 |
| 03:58 | Edited lib/extraction/service.py | modified is_model_source_engine() | ~352 |
| 03:58 | Edited lib/extraction/service.py | 8→11 lines | ~137 |
| 03:59 | Created tests/unit/extraction/text_lane/test_column_labeling.py | — | ~1511 |
| 04:00 | Created tests/unit/extraction/text_lane/test_table_extractor.py | — | ~2394 |
| 04:00 | Edited tests/unit/extraction/text_lane/test_table_extractor.py | 11→13 lines | ~155 |
| 04:01 | Created tests/unit/extraction/text_lane/test_text_lane_gateway.py | — | ~2861 |
| 04:02 | Edited tests/unit/extraction/text_lane/test_text_lane_gateway.py | 2→2 lines | ~34 |
| 04:03 | Edited lib/extraction/text_lane/table_grid.py | modified _offset() | ~109 |
| 04:04 | Created scripts/gpu/check_text_lane_eligibility.py | — | ~1610 |
| 04:05 | Edited scripts/gpu/check_text_lane_eligibility.py | added 1 import(s) | ~21 |
| 04:05 | Edited scripts/gpu/check_text_lane_eligibility.py | inline fix | ~17 |
| 04:05 | Edited scripts/gpu/check_text_lane_eligibility.py | inline fix | ~11 |
| 04:35 | Implemented extractive-first E0+E1 text lane behind default-off flags | lib/extraction/text_lane/*, lib/model_runtime/clients/_openai_text.py, lib/extraction/{gateways/routing.py,service.py,validators.py,models.py,source_repository.py}, lib/config/settings.py, compose.yaml, scripts/gpu/check_text_lane_eligibility.py, tests/ | E0: TableGrid parser over table_json data.grid with run-9-shape fixtures, text_lane_eligibility quality+table-signal screens, STRUCTURA_TEXT_LANE_TABLES/KVP flags in compose. E1: enum column-role labeling on qwen-semantic cached by family+header fingerprint, verbatim-cell extractor emitting Granite-parity RegionExtractionEnvelope with docling row anchors and totals-row facts, routing seam with TextLaneAbstention fallback, review-gated text-lane validator, lane telemetry. 1049 unit tests/ruff/contracts pass locally; adversarial review workflow before commit and GPU A/B gate | ~95000 |
| 04:40 | Created ../../../../tmp/structura-e0-capture/repro_totals_substring.py | — | ~1652 |
| 04:41 | Created ../../../../tmp/structura-e0-capture/repro_totals_rate.py | — | ~1347 |
| 04:41 | Edited ../../../../tmp/structura-e0-capture/repro_totals_rate.py | 19→17 lines | ~156 |
| 04:42 | Created ../../../../tmp/structura-e0-capture/repro_totals_variants.py | — | ~1378 |
| 04:45 | Created ../../../../tmp/structura-e0-capture/repro_band_rows.py | — | ~1554 |
| 04:53 | Edited lib/extraction/text_lane/table_extractor.py | added 1 import(s) | ~51 |
| 04:53 | Edited lib/extraction/text_lane/table_extractor.py | expanded (+16 lines) | ~169 |
| 04:53 | Edited lib/extraction/text_lane/table_extractor.py | expanded (+7 lines) | ~96 |
| 04:53 | Edited lib/extraction/text_lane/table_extractor.py | _totals_fact() → _classify_totals_row() | ~350 |
| 04:53 | Edited lib/extraction/text_lane/table_extractor.py | 4→5 lines | ~71 |
| 04:53 | Edited lib/extraction/text_lane/table_extractor.py | 6→7 lines | ~65 |
| 04:54 | Edited lib/extraction/text_lane/table_extractor.py | modified _classify_totals_row() | ~1195 |
| 04:54 | Edited lib/extraction/text_lane/table_extractor.py | 6→5 lines | ~38 |
| 04:54 | Edited lib/extraction/text_lane/table_extractor.py | 19→17 lines | ~160 |
| 04:54 | Edited lib/extraction/text_lane/table_grid.py | added 1 import(s) | ~81 |
| 04:54 | Edited lib/extraction/text_lane/table_grid.py | modified header_row_indexes() | ~639 |
| 04:55 | Edited lib/extraction/text_lane/column_labeling.py | 7→7 lines | ~88 |
| 04:55 | Edited lib/extraction/text_lane/column_labeling.py | expanded (+18 lines) | ~265 |
| 04:55 | Edited lib/extraction/text_lane/column_labeling.py | modified clear_column_label_cache() | ~253 |
| 04:56 | Edited lib/extraction/text_lane/gateway.py | modified values() | ~384 |
| 04:56 | Edited lib/extraction/text_lane/gateway.py | added 1 import(s) | ~87 |
| 04:56 | Edited lib/extraction/text_lane/gateway.py | 7→8 lines | ~92 |
| 04:56 | Edited lib/extraction/text_lane/gateway.py | 3→1 lines | ~28 |
| 04:57 | Edited lib/extraction/text_lane/table_extractor.py | 3→5 lines | ~99 |
| 04:57 | Edited lib/extraction/text_lane/table_extractor.py | modified _phrase_matches() | ~96 |
| 04:58 | Created tests/unit/extraction/text_lane/test_review_regressions.py | — | ~3649 |
| 04:58 | Edited lib/extraction/text_lane/gateway.py | modified _row_has_parseable_money() | ~228 |
| 05:15 | Edited docs/adr/0006-extractive-first-extraction.md | expanded (+18 lines) | ~364 |
| 05:19 | Edited lib/extraction/text_lane/eligibility.py | 5→4 lines | ~44 |
| 05:19 | Edited lib/extraction/text_lane/eligibility.py | modified _difficult_page_reasons() | ~155 |
| 05:22 | Created ../../../../tmp/structura-e0-capture/markdown_check.sql | — | ~122 |
| 05:23 | Edited lib/extraction/text_lane/eligibility.py | expanded (+6 lines) | ~320 |
| 05:23 | Edited lib/extraction/text_lane/eligibility.py | 9→8 lines | ~82 |
| 05:23 | Edited lib/extraction/text_lane/eligibility.py | 6→6 lines | ~49 |
| 05:23 | Edited lib/extraction/text_lane/eligibility.py | removed 9 lines | ~8 |
| 05:23 | Edited scripts/gpu/check_text_lane_eligibility.py | 5→4 lines | ~70 |
| 05:23 | Edited scripts/gpu/check_text_lane_eligibility.py | modified evaluate_document() | ~214 |
| 05:23 | Edited tests/unit/extraction/text_lane/test_eligibility.py | modified test_usable_grid_on_text_page_is_text_lane() | ~272 |
| 05:24 | Edited tests/unit/extraction/text_lane/test_eligibility.py | modified test_single_column_grid_routes_to_vision() | ~216 |
| 05:24 | Edited tests/unit/extraction/text_lane/test_text_lane_gateway.py | inline fix | ~25 |
| 05:28 | Created ../../../../tmp/structura-e0-capture/source_path.sql | — | ~46 |
| 05:32 | Created scripts/gpu/compare_text_lane_gate.py | — | ~1986 |
| 05:33 | Edited scripts/gpu/compare_text_lane_gate.py | 2→4 lines | ~37 |
| 05:40 | Created ../../../../tmp/structura-e0-capture/run_a_violations.sql | — | ~274 |
| 05:40 | Created ../../../../tmp/structura-e0-capture/run_a_violations2.sql | — | ~349 |
| 05:42 | Created ../../../../tmp/structura-e0-capture/run9_events.sql | — | ~205 |
| 05:47 | Created ../../../../tmp/structura-e0-capture/lane_reasons.sql | — | ~142 |
| 05:48 | Created ../../../../tmp/structura-e0-capture/text_lane_rows.sql | — | ~594 |
| 05:49 | Created ../../../../tmp/structura-e0-capture/bmw_region_obs.sql | — | ~340 |
| 05:51 | Created ../../../../tmp/structura-e0-capture/bmw_values.sql | — | ~368 |
| 05:57 | Created ../../../../tmp/structura-e0-capture/repeat_check.sql | — | ~235 |
| 05:57 | Created ../../../../tmp/structura-e0-capture/repeat_check2.sql | — | ~336 |
| 05:58 | Edited lib/config/settings.py | 4→6 lines | ~125 |
| 05:59 | Edited docs/adr/0006-extractive-first-extraction.md | modified regressed() | ~471 |
| 06:05 | E1 GPU A/B gate passed; table-lane defaults flipped on | scripts/gpu/{check_text_lane_eligibility,compare_text_lane_gate}.py, lib/config/settings.py, compose.yaml, docs/adr/0006, .wolf/buglog.json | Runs 20260610T093120Z-text-lane-e1-a + 095035Z-e1-b vs pinned run-9: zero dead letters, line items >= baseline everywhere, BMW aggregate 10=10, 100% concrete evidence on text-lane claims, text-lane envelopes byte-identical across runs, full-corpus canonical fingerprints identical. Lane fired on BMW service-lines + BH order tables; abstentions (money_columns_sparse on BH cell-loss table, no_money_column on EOB grid, no_grounded_docling_table on page-grounded receipts) all routed to vision safely. Found baseline-inherited: aggregate admission events NULL run_id; rejected-inserted identity collisions; docling_audit table signal blind to data.grid (eligibility now grid-derived). Acceptance evaluator fails run-9's own report identically - documented, not a regression | ~60000 |
| 06:03 | Edited ../../.claude/projects/-Users-brennanconley-vibecode-structura/memory/structura-prod-readiness-push.md | modified pivot() | ~931 |
| 06:04 | Created ../../../../tmp/structura-e0-capture/kvp_expected_fields.sql | — | ~207 |
| 06:05 | Created ../../../../tmp/structura-e0-capture/kvp_expected_fields2.sql | — | ~223 |
| 06:07 | Created lib/extraction/text_lane/span_candidates.py | — | ~3151 |
| 06:08 | Created ../../../../tmp/structura-e0-capture/element_bbox.sql | — | ~71 |
| 06:09 | Edited lib/extraction/text_lane/span_candidates.py | modified _bbox() | ~470 |
| 06:09 | Created lib/extraction/text_lane/span_selection.py | — | ~1893 |
| 06:10 | Created lib/extraction/text_lane/kvp_extractor.py | — | ~2236 |
| 06:10 | Edited lib/extraction/text_lane/eligibility.py | 4→7 lines | ~95 |
| 06:11 | Edited lib/extraction/text_lane/eligibility.py | modified text_lane_kvp_eligibility() | ~650 |
| 06:11 | Created lib/extraction/text_lane/kvp_gateway.py | — | ~1551 |
| 06:12 | Edited lib/extraction/gateways/routing.py | modified __init__() | ~126 |
| 06:12 | Edited lib/extraction/gateways/routing.py | added 1 condition(s) | ~572 |
| 06:12 | Edited lib/extraction/gateways/routing.py | 14→16 lines | ~190 |
| 06:12 | Edited lib/extraction/gateways/routing.py | expanded (+6 lines) | ~180 |
| 06:13 | Created tests/unit/extraction/text_lane/test_kvp_lane.py | — | ~4686 |
| 06:14 | Edited tests/unit/extraction/text_lane/test_kvp_lane.py | 4→5 lines | ~84 |
| 06:40 | Implemented E2 extractive KVP lane behind default-off STRUCTURA_TEXT_LANE_KVP | lib/extraction/text_lane/{span_candidates,span_selection,kvp_extractor,kvp_gateway}.py, eligibility.py, lib/extraction/gateways/routing.py, tests/unit/extraction/text_lane/test_kvp_lane.py | Deterministic bounded span candidates (label adjacency + typed regexes, BOTTOMLEFT-aware bbox math, positional ids), closed-enum span selection on qwen-semantic with prompt-hash cache, claims born verbatim from selected spans (registry-exact keys -> family facts, others dot-less observations), KVP routing with abstention fallback. 1069 unit tests/ruff/mypy clean; commit e9288c7; adversarial review workflow running before the E2 GPU gate | ~40000 |

## 2026-06-10 E2 determinism review (subagent)
- Reviewed e9288c7 (KVP lane) for E2 gate repeatability. Root determinism dependency: source.elements order via `ORDER BY p.page_number, e.ordinal` where (page, ordinal) is non-unique (docling converter restarts ordinal per texts/pictures/groups collection; no-prov items default page 1; no unique constraint or document_id index on document_elements). Ties feed _dedupe first-wins, adjacency label winner, [:80] truncation, prompt sha, and s{page}_{ordinal}_{start}_{end} span-id collisions.
- _SELECTION_CACHE persists in worker-extraction across gate runs A/B (never cleared in prod); run B is served run A's selections when prompts are byte-identical, making the gate tautological for the selection step; cache misses fall to vLLM greedy decoding which is not bit-stable under batching.
- Verified fail-safe: cross-document prompt-hash reuse is safe (identical prompt => identical span vocabulary; extractor resolves ids against current doc spans; unknown ids null on live path; all-unresolved => no_extractable_values abstention). canonicalOutput fingerprint excludes from_cache/modelInvoked telemetry.
- Adjacency (right-of/below-of) spans carry whitespace-collapsed value_text but raw-text text_span offsets => inexact anchors vs the E2 "exact anchors" criterion.
| 06:36 | Created ../../../../tmp/structura-e0-capture/repro_e2_date.py | — | ~1055 |
| 06:38 | Created ../../../../tmp/structura-e0-capture/repro_ordinal_ties.py | — | ~1652 |
| 06:39 | Created ../../../../tmp/structura-e0-capture/repro_kvp_money.py | — | ~839 |
| 06:40 | Created ../../../../tmp/structura-e0-capture/repro_e2_receipt_kvp.py | — | ~2548 |
| 06:40 | Created ../../../../tmp/structura-e0-capture/repro_kvp_adjacency.py | — | ~1229 |
| 06:40 | Edited ../../../../tmp/structura-e0-capture/repro_e2_receipt_kvp.py | inline fix | ~19 |
| 06:42 | Created ../../../../tmp/structura-e0-capture/repro_anchor_claim.py | — | ~950 |
| 06:42 | Edited ../../../../tmp/structura-e0-capture/repro_anchor_claim.py | 3→3 lines | ~61 |
| 06:47 | Created ../../../../tmp/structura-e0-capture/repro_kvp_projection.py | — | ~1111 |
| 06:48 | Edited ../../../../tmp/structura-e0-capture/repro_kvp_projection.py | inline fix | ~19 |
| 06:52 | Edited lib/extraction/text_lane/span_candidates.py | expanded (+6 lines) | ~141 |
| 06:52 | Edited lib/extraction/text_lane/kvp_extractor.py | added 1 import(s) | ~78 |
| 06:52 | Edited lib/extraction/text_lane/kvp_extractor.py | expanded (+6 lines) | ~311 |
| 06:53 | Edited lib/extraction/text_lane/kvp_gateway.py | added 1 import(s) | ~70 |
| 06:53 | Edited lib/extraction/text_lane/kvp_gateway.py | modified _family_is_first_class() | ~184 |
| 06:53 | Edited lib/extraction/text_lane/kvp_gateway.py | modified _family_is_first_class() | ~74 |
| 07:02 | Created ../../../../tmp/structura-e0-capture/e2_lane_reasons.sql | — | ~218 |
| 07:12 | Created ../../../../tmp/structura-e0-capture/mri_check.sql | — | ~211 |
| 07:13 | Edited lib/extraction/text_lane/kvp_gateway.py | expanded (+6 lines) | ~286 |
| 07:13 | Edited lib/extraction/text_lane/kvp_gateway.py | modified _family_is_first_class() | ~146 |
| 07:46 | Edited lib/config/settings.py | 6→7 lines | ~147 |
| 07:46 | Edited docs/adr/0006-extractive-first-extraction.md | expanded (+21 lines) | ~413 |
| 07:35 | E2 KVP lane gated; STRUCTURA_TEXT_LANE_KVP defaults on | lib/extraction/text_lane/{span_candidates,span_selection,kvp_extractor,kvp_gateway}.py, lib/config/settings.py, compose.yaml, docs/adr/0006 | Pre-gate review (16 agents) fixed money-regex mid-number matches, unvalidated date spans, first-class dead-end claims; run C exposed the effective-family hole (MRI denial 17->0 obs) fixed by keying abstention on the candidate layer's family fallback. Gate runs e2-e/e2-f vs run-9: Phenix obs 10->17, UWM 14->16 with exact anchors, fingerprints identical across runs, zero dead letters, receipt registry facts 2->5. KVP lane fired on Phenix/UWM/receipt-summary regions; MRI/medical_eob KVP correctly abstains to vision | ~55000 |
| 07:48 | Edited ../../.claude/projects/-Users-brennanconley-vibecode-structura/memory/structura-prod-readiness-push.md | modified gated() | ~471 |
| 08:04 | Created lib/semantic_annotations/deterministic_plan.py | — | ~2113 |
| 08:04 | Edited lib/semantic_annotations/service.py | expanded (+10 lines) | ~128 |
| 08:05 | Edited lib/semantic_annotations/service.py | 6→4 lines | ~78 |
| 08:05 | Edited lib/semantic_annotations/service.py | modified _planned_manifest_result() | ~498 |
| 08:05 | Edited lib/config/settings.py | expanded (+7 lines) | ~156 |
| 08:06 | Created tests/unit/semantic_annotations/test_deterministic_plan.py | — | ~1839 |
| 16:11 | Edited tests/unit/semantic_annotations/test_deterministic_plan.py | 9→13 lines | ~198 |
| 08:20 | Implemented E3 deterministic-primary planner behind default-off STRUCTURA_DETERMINISTIC_PLANNER | lib/semantic_annotations/deterministic_plan.py, lib/semantic_annotations/service.py, lib/config/settings.py, compose.yaml, tests/unit/semantic_annotations/test_deterministic_plan.py | Baseline plan built model-free from docling_targets builders, run-stable fingerprint (no per-run UUIDs), plan-superset invariant enforced after Qwen augmentation with telemetry, Qwen protocol/timeout/service failures degrade to baseline-only review-required manifests instead of dead-lettering the document (the phase8-live failure class). 8 new tests, 1082 total green, commit c08a3ee; adversarial review workflow running before the E3 GPU gate | ~35000 |
| 16:14 | Created ../../../../tmp/structura-e0-capture/e3_fingerprints.sql | — | ~215 |
| 16:23 | Created ../../../../tmp/structura-e0-capture/repro_e3_invariant_paths.py | — | ~2196 |
| 16:32 | Created ../../../../tmp/structura-e0-capture/repro_e3_retryable_degrade.py | — | ~1823 |
| 16:33 | Created ../../../../tmp/structura-e0-capture/repro_baseline_covered.py | — | ~1900 |
| 16:35 | Created ../../../../tmp/structura-e0-capture/claim_timeout_repro.py | — | ~1535 |
| 16:37 | Created ../../../../tmp/repro_e3_empty_baseline.py | — | ~1423 |
| 16:38 | Created ../../../../tmp/structura-e0-capture/repro_e3_eviction.py | — | ~1526 |
| 16:41 | Created ../../../../tmp/structura-e0-capture/repro_weak_redundant.py | — | ~1549 |
| 16:42 | Created ../../../../tmp/structura-e0-capture/repro_e3_claim.py | — | ~2132 |
| 16:50 | Edited lib/semantic_annotations/deterministic_plan.py | modified deterministic_baseline_manifest() | ~410 |
| 16:50 | Edited lib/semantic_annotations/deterministic_plan.py | modified _baseline_region_covered() | ~286 |
| 16:50 | Edited lib/semantic_annotations/deterministic_plan.py | added 1 import(s) | ~72 |
| 16:50 | Edited lib/semantic_annotations/service.py | except() → failure() | ~407 |
| 16:50 | Edited lib/semantic_annotations/service.py | 5→1 lines | ~18 |
