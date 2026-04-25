# Structura Phase 11 Implementation Plan

Phase 11 moves Structura from feature-complete implementation toward a release-candidate discipline. The objective is not to add broad new product scope. The objective is to measure quality, prevent quiet regressions, prove restore and migration behavior, and produce a release evidence pack that can be trusted.

This plan expands Phase 11 from `STRUCTURA_IMPLEMENTATION_PLAN.md`. It does not replace the root plan. The source artifact pack describes the same work as the benchmark corpus, regression discipline, and release-candidate phase; the root implementation plan numbers it as Phase 11 after the expanded Structura build phases.

## Operating Rules

- Do not inspect or rely on anything under `archive/`.
- Before coding any subphase, re-read the files listed in that subphase's **Fresh Context** section. Use `wc -l` and bounded `sed -n` chunks for large files so full reads are auditable.
- When an artifact exists in both Markdown and DOCX form, read the Markdown artifact by default. Only inspect DOCX when the user explicitly asks for layout/fidelity review or when the Markdown file is missing/incomplete.
- Keep Phase 11 focused on release-candidate quality: golden corpus, expected answers, extraction scoring, search scoring, Playwright smoke tests, migration-from-scratch tests, restore tests, SAST, performance checks, and final evidence. Do not add new product features unless a release blocker cannot be resolved without a tightly scoped fix.
- Preserve all Phase 0-10 invariants: original bytes are immutable, canonical parse artifacts are versioned, trusted facts require evidence, low-confidence extraction creates review, canonical accepted facts remain the default read model, search indexes are assistive, analysis remains optional and cited, exports are explicit and audited, and ACL checks run before returning document-derived data.
- Do not commit private golden-corpus documents, medical bills, legal notices, handwritten notes, model outputs containing sensitive content, restored database dumps, object-store archives, secret-bearing logs, or local backup artifacts. Keep private corpus material in secured local storage outside public source control.
- Sanitized fixtures may be committed only when they contain no real personal, medical, financial, legal, credential, or household data.
- Every evaluator and release script must be deterministic enough to compare before/after results across prompt, model, schema, indexing, chunking, or ranking changes.
- If a benchmark threshold is unclear, create the measurement and mark the threshold as a release decision instead of hard-coding an arbitrary pass condition.
- Do not weaken validation, provenance, ACL, CSRF, security, or migration checks to make the release candidate pass.

## Firecrawl Evidence Rule

When APIs, external contracts, library behavior, security conventions, OpenAPI semantics, JSON Schema semantics, FastAPI/Pydantic behavior, PostgreSQL/ParadeDB/pgvector behavior, Playwright behavior, accessibility conventions, backup/restore mechanics, ZFS operations, Docker Compose behavior, SAST tooling, dependency scanning, data-flow analysis, or release engineering practices are in play, search online with Firecrawl if there is any uncertainty.

Use primary sources where possible: official framework documentation, standards documents, package docs, project repositories, security guidance, PostgreSQL/ZFS/Docker docs, Playwright docs, OWASP guidance, or vendor docs. Save Firecrawl outputs under `.firecrawl/`, read them incrementally, and summarize the evidence in implementation notes, ADRs, or release reports when it affects a decision. Do not use unsourced memory to settle uncertain API, benchmark, restore, browser, static-analysis, schema, or security behavior.

## Phase 11 Required Artifact Set

The full Phase 11 artifact list from `STRUCTURA_IMPLEMENTATION_PLAN.md` remains required context. Under the current repo guidance, duplicate DOCX entries are omitted here because the Markdown files are the default source unless DOCX fidelity is explicitly requested.

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/001_extensions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/010_types_and_enums.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/030_constraints_and_triggers.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/050_views_and_functions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/060_seed_taxonomies.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/070_query_examples.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/ingest_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/classify_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/extract_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/embed_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/analyze_documents_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/analysis_note.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/canonical_field.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/document_classification.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/field_candidate.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/filing_rule.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/folder_acl.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/invoice.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/medical_eob.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/receipt.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/review_action.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv
```

## Phase 11 Target Deliverables

- A secured local golden corpus manifest with representative receipts, invoices, EOBs and medical bills, warranties, legal notices, handwritten notes, and long reference PDFs.
- Versioned expected-answer files for classification, fields, line items, review expectations, evidence expectations, relationships, and search queries.
- A deterministic corpus ingestion/evaluation harness that records results in `evaluation_runs` and writes safe report artifacts.
- Extraction scoring for required fields, numeric correctness, arithmetic consistency, evidence validity, review-task behavior, and canonical promotion.
- Search scoring for lexical, semantic, hybrid, filter, facet, relationship, and difficult-document queries.
- Playwright UI smoke tests for core workflows and Figma-aligned release views.
- Migration-from-scratch tests and contract compatibility checks.
- Restore rehearsal scripts or procedures with recorded evidence.
- Full static-analysis, SAST, dependency, formatting, runtime, and architectural validation status.
- A release-candidate evidence pack with known issues, risk disposition, and the final stop/go recommendation.

## 11.0 Baseline Reconciliation And Release Scope

Goal: confirm that Phase 11 is an evaluation and release-candidate phase, not a new feature-build phase.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 11 section.
- `STRUCTURA_PLAN_INDEX.md`, source alignment policy and stop rule.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`, Playwright and Figma QA expectations.
- `STRUCTURA_PHASE_1_IMPLEMENTATION_PLAN.md` through `STRUCTURA_PHASE_10_IMPLEMENTATION_PLAN.md`, especially phase gates and invariants.
- `pro-merged-master-v1.2/AGENT_START_HERE.md`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, product-level acceptance.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, benchmark corpus and release candidate phase.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, release requirements.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, corpus and release gates.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`.
- Active `README.md`, `Makefile`, `pyproject.toml`, `package.json`, and `compose.yaml`.

Work:

- Create a Phase 11 release-candidate checklist that maps every Phase 0-10 gate to concrete evidence, command output, report files, or known-issue entries.
- Reconcile the root Phase 11 section with the source artifact's benchmark/release-candidate phase. Treat both as the same acceptance discipline even though the numbering differs.
- Define blocker classes:
  - critical: data loss, original overwrite, silent accepted invalid extraction, broken provenance on trusted values, ACL bypass, raw object path exposure, broken restore, broken migration from scratch, public contract drift, secret leakage, unhandled corruption;
  - high: major workflow failure, missing required benchmark class, material search/extraction regression, SAST finding with plausible exploitability, broken export audit;
  - medium: incomplete report coverage, flaky smoke test, non-blocking performance miss, undocumented known issue;
  - low: polish, report formatting, minor non-release UI mismatch.
- Decide where release evidence will live. Prefer committed sanitized reports under `docs/release/` and local private outputs under a gitignored `.local/` or configured external path.
- Confirm `.gitignore` excludes private corpus files, restore outputs, dumps, backups, and Firecrawl output if those outputs may include sensitive decision evidence.
- Record any required contract or architecture gaps before starting measurement. A missing core endpoint is not a benchmark failure; it is an implementation blocker.

Firecrawl Evidence:

- Use Firecrawl if release-candidate checklist conventions, severity definitions, SAST gate conventions, or benchmark reporting practices are uncertain.

Exit Criteria:

- Phase 11 scope is explicitly limited to measurement, regression, restore, migration, security, and release-readiness.
- Every prior phase gate has a planned evidence source.
- Critical blocker definitions are written before running benchmarks.

## 11.1 Secure Golden Corpus Governance And Storage

Goal: assemble the representative corpus without leaking private source documents into the repo.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 11 corpus tasks.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, Golden corpus design.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, privacy, storage, and release requirements.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, product-level acceptance.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, false trust, parse quality, search, handwriting, and storage-sprawl risks.
- Active `.gitignore`, `README.md`, and storage settings.

Work:

- Define local corpus roots for private originals and sanitized fixtures. Private roots must live outside public source control.
- Define corpus naming and versioning: `corpus_name`, `corpus_version`, sample id, source type, document family, difficulty flags, sensitivity class, expected review behavior, and notes.
- Assemble the starter target composition from the testing artifact:
  - 10 receipts;
  - 10 invoices;
  - 10 EOBs or medical bills;
  - 5 warranties;
  - 5 legal notices or agreements;
  - 5 handwritten notes;
  - 5 long reference PDFs.
- Mark each sample as private, sanitized, generated, or synthetic. Do not mix unknown provenance samples into committed fixtures.
- Capture ambiguity notes. A benchmark sample can intentionally have uncertain fields, but the expected review behavior must say so.
- Add corpus integrity checks for original byte hash, MIME type, size, page count, and stable sample id.
- Store only manifest metadata and sanitized expected-answer examples in Git. Keep private document bytes and raw sensitive evaluation output local.
- Document how an agent should run the benchmark without seeing or committing private files accidentally.

Firecrawl Evidence:

- Use Firecrawl if secure local test-data handling, gitignore patterns for private datasets, anonymization conventions, or sensitive-fixture practices are uncertain.

Exit Criteria:

- Corpus storage boundaries are clear and enforced.
- Representative document classes are planned with minimum counts.
- Private data cannot be committed through the normal workflow.

## 11.2 Expected Answers, Labels, And Evaluation Contracts

Goal: make expected outputs versioned, machine-checkable, and tied to existing Structura contracts.

Fresh Context:

- `pro-merged-master-v1.2/contracts/README.md`, contract design rules.
- `pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/document_classification.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/receipt.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/invoice.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/medical_eob.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/field_candidate.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/canonical_field.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/review_action.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/analysis_note.v1.schema.json`.
- Active `contracts/schemas/*.json` and `lib/contracts/`.

Work:

- Define expected-answer schemas for corpus samples. Keep them thin wrappers around existing contracts instead of inventing incompatible structures.
- Each sample should support expected:
  - document family and optional subtype;
  - route profile;
  - required key fields and acceptable aliases;
  - numeric tolerance and currency expectations;
  - line-item expectations where useful;
  - evidence requirements using page number plus concrete locator;
  - review expectation for ambiguity, low confidence, arithmetic failure, handwriting, or missing fields;
  - search queries and expected top-k inclusion;
  - optional relationship/deadline expectations.
- Version expected answers separately from extraction schemas. A correction to the ground truth should be auditable as a corpus-version change, not hidden in a test rewrite.
- Add validators that load every expected-answer file and check references to known corpus sample ids and contract schema versions.
- Treat "unknown" and "not present" differently. Missing source data should not be scored as model failure if the document genuinely lacks the field.
- Decide whether expected evidence scoring starts with structural validity only or requires exact locator overlap. Document the first threshold before running the corpus.

Firecrawl Evidence:

- Use Firecrawl if JSON Schema composition, validator behavior, field-level scoring formats, or evidence-overlap scoring conventions are uncertain.

Exit Criteria:

- Every benchmark sample can be described by machine-valid expected-answer metadata.
- Expected answers align with existing Structura schemas and provenance rules.
- Ambiguity and review expectations are explicit.

## 11.3 Corpus Intake And Deterministic Run Harness

Goal: make the corpus runnable from a clean environment without hand-driven setup.

Fresh Context:

- `pro-merged-master-v1.2/contracts/events/README.md`.
- `pro-merged-master-v1.2/contracts/events/ingest_document_job.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/events/classify_document_job.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/events/extract_document_job.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/events/embed_document_job.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/events/analyze_documents_job.v1.schema.json`.
- `pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql`, `evaluation_runs` and service health.
- Active `lib/jobs/service.py`, worker packages, `scripts/`, and `tests/`.
- Active settings for object roots, queue profile, and local runtime.

Work:

- Implement a deterministic evaluation CLI or script family that can:
  - create an isolated evaluation database state or namespace;
  - import corpus manifests and originals through normal upload/intake paths where possible;
  - wait for configured pipeline stages;
  - run selected evaluator suites;
  - write safe reports;
  - record `evaluation_runs` rows for extraction, search, pipeline, and end-to-end runs.
- Support dry-run mode that validates corpus paths, labels, settings, and available services without ingesting files.
- Support stage selection: ingest only, parse only, extraction, embeddings, search, UI smoke, restore, full.
- Ensure reruns are idempotent. Re-running the same corpus version should not create hidden duplicate truth or invalidate baseline comparisons.
- Capture app commit, schema version, prompt version, model version, model profile, runtime profile, and evaluator version in every report.
- Make failures actionable: sample id, stage, expected value, actual value, metric delta, error summary, and pointers to safe logs.
- Keep private raw document content and raw model output out of committed reports.

Firecrawl Evidence:

- Use Firecrawl if CLI testing conventions, deterministic evaluation report patterns, job retry handling, or JSON report formats are uncertain.

Exit Criteria:

- The golden corpus can be run through a repeatable command.
- Evaluation results are recorded in the database and written to report artifacts.
- The harness can run without exposing private corpus bytes in Git output.

## 11.4 Extraction Scoring And Review Regression

Goal: measure typed extraction quality at field level and verify review-required behavior.

Fresh Context:

- `pro-merged-master-v1.2/docs/01_App_Specification.md`, typed extraction and review requirements.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, extraction evaluation.
- `pro-merged-master-v1.2/contracts/schemas/receipt.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/invoice.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/medical_eob.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/field_candidate.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/canonical_field.v1.schema.json`.
- Active extraction validators, review services, evidence helpers, and canonical fact implementation.

Work:

- Implement scoring for receipt, invoice, and medical EOB outputs:
  - required field presence rate;
  - exact-match accuracy for stable string fields;
  - normalized-date accuracy;
  - numeric accuracy with configured tolerance;
  - currency correctness;
  - line-item inclusion and amount correctness;
  - arithmetic consistency pass rate;
  - schema validation pass/fail;
  - evidence structural validity;
  - review-task creation on bad, ambiguous, low-confidence, or failed-validation inputs.
- Score canonical accepted facts separately from raw model output. The release candidate is judged by what the app trusts and shows by default, not only by a raw model JSON blob.
- Verify that invalid or low-confidence outputs create review tasks and are not silently promoted.
- Verify manual corrections update canonical values while preserving `canonical_fact_history` and review events.
- Add regression reports by document family and difficulty flag: digital-native, scanned, table-heavy, handwriting-heavy, long document, low text, legal, medical, financial.
- Provide threshold hooks. Initial thresholds may be user-approved after the first measured run, but the evaluator must report enough detail to make that decision.

Firecrawl Evidence:

- Use Firecrawl if extraction metric definitions, numeric tolerance practices, JSON Schema validation semantics, or model-output evaluation conventions are uncertain.

Exit Criteria:

- Extraction scoring reports field-level successes and failures.
- Review-required behavior is measured, not inferred.
- No accepted trusted fact can pass without schema validation and evidence.

## 11.5 Search Benchmark Scoring

Goal: prove lexical, semantic, hybrid, filter, facet, and difficult-document retrieval quality on fixed queries.

Fresh Context:

- `pro-merged-master-v1.2/docs/01_App_Specification.md`, search and retrieval requirements.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, search evaluation.
- `pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql`.
- `pro-merged-master-v1.2/database/050_views_and_functions.sql`, `rrf_score`.
- `pro-merged-master-v1.2/database/070_query_examples.sql`.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `/api/v1/search`.
- Active search services, embedding worker, search API, and search UI.

Work:

- Create benchmark query sets for:
  - exact lexical queries;
  - natural-language semantic queries;
  - hybrid queries requiring both exact terms and concept matching;
  - filtered queries by family, date, amount, folder, tag, review status, and sensitivity;
  - relationship/timeline queries;
  - low-text, handwriting-heavy, and visually distinctive documents;
  - long reference PDFs.
- For each query, define expected top-k inclusion and optional expected rank targets.
- Measure hit rate at k, mean reciprocal rank where practical, expected-inclusion failures, facet correctness, filter correctness, snippet usefulness, and result ACL correctness.
- Compare lexical-only, semantic-only, and hybrid results. Hybrid should be visibly and measurably better than either single mode on the chosen benchmark where both signals matter.
- Record model profile, embedding dimension, chunking strategy, BM25 index definition, RRF weights, reranker state, and corpus version in every report.
- Detect regressions caused by changes to chunking, indexes, embedding model, embedding dimensions, filters, ranking weights, reranking, or relationship traversal.

Firecrawl Evidence:

- Use Firecrawl if ParadeDB BM25 behavior, pgvector index behavior, RRF math, search evaluation metrics, or benchmark reporting conventions are uncertain.

Exit Criteria:

- Search quality is measured against fixed queries.
- Hybrid retrieval has explicit evidence of improvement on relevant cases.
- Search filters and ACL behavior are part of the benchmark.

## 11.6 End-To-End Pipeline Regression

Goal: validate full product workflows instead of isolated units only.

Fresh Context:

- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, end-to-end tests and manual QA checklist.
- `STRUCTURA_PHASE_1_IMPLEMENTATION_PLAN.md`, upload/inbox/viewer.
- `STRUCTURA_PHASE_2_IMPLEMENTATION_PLAN.md`, manual filing.
- `STRUCTURA_PHASE_3_IMPLEMENTATION_PLAN.md`, canonical parse.
- `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md`, extraction/review.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, search.
- `STRUCTURA_PHASE_7_IMPLEMENTATION_PLAN.md`, relationships/timelines.
- `STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md`, analysis workspace.
- `STRUCTURA_PHASE_10_IMPLEMENTATION_PLAN.md`, exports, auth hardening, backups, and operations.
- Active API, web app, worker packages, and tests.

Work:

- Build E2E regression flows for:
  - upload document -> inbox row -> preview -> viewer;
  - parse -> page/chunk rows -> debug evidence;
  - classify -> extract -> validation -> review task;
  - evidence jump -> accept/correct field -> canonical history;
  - folder/tag filing -> smart folder update;
  - search -> open result -> protected asset route;
  - relationship create/confirm -> related panel/timeline;
  - analysis request -> cited analysis note, if enabled;
  - export request -> export job -> manifest/provenance, if Phase 10 export implementation exists;
  - admin failed-job retry.
- Include restart or worker-resume checks where practical.
- Assert no raw object storage paths appear in browser DOM, API payloads, logs intended for normal operators, export manifests, or safe reports.
- Keep tests deterministic by using controlled fixture data, stable clock handling where needed, and isolated database/object roots.
- Separate release smoke tests from long corpus evaluations so developers can run a fast suite before the full RC run.

Firecrawl Evidence:

- Use Firecrawl if Playwright, FastAPI test-client behavior, browser file uploads, async worker waiting, or deterministic E2E practices are uncertain.

Exit Criteria:

- The core product workflow works through real API/UI boundaries.
- Regression failures point to a precise stage and sample.
- Release smoke tests cover the minimum user path without requiring the full corpus.

## 11.7 Playwright UI Smoke And Figma Regression

Goal: verify that release-candidate UI still supports the Figma-aligned workbench workflows.

Fresh Context:

- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- Figma frame `17:2` for Home / Document Operations.
- Figma frame `14:434` for Document Viewer.
- Figma frame `14:611` for Extraction Workspace.
- Figma frame `14:797` for Search.
- Figma frame `14:990` for Analysis.
- Figma handoff frames `35:2`, `35:7`, `35:12`, and `35:17`.
- Active `apps/web/src/`, Playwright setup, and UI reference artifacts.

Work:

- Create or extend Playwright smoke tests for:
  - sign-in/session;
  - upload and inbox display;
  - document selection and right inspector;
  - document viewer open and protected asset usage;
  - review task list and evidence jump;
  - field accept/edit action;
  - folder/tag filing action;
  - search and result open;
  - analysis workspace disabled/enabled states;
  - admin jobs and retry visibility;
  - export action visibility and confirmation where implemented.
- Capture screenshots at release viewports and compare against the saved Figma references or documented accepted deltas.
- Validate key edge states: empty corpus, processing, workers offline, failed extraction, no review items, low confidence, original temporarily unavailable, and duplicate suspect.
- Include keyboard focus, obvious accessibility checks, text overflow checks, and responsive layout checks for release-critical screens.
- If a Figma ambiguity or conflict affects release UI behavior, stop and ask the user rather than inventing a new UX direction.

Firecrawl Evidence:

- Use Firecrawl if Playwright screenshot behavior, accessibility check tooling, browser file-upload testing, or UI regression conventions are uncertain.

Exit Criteria:

- Release-critical screens have smoke coverage.
- Pixel or interaction deltas are recorded rather than hidden.
- UI does not regress into a developer-console experience.

## 11.8 Migration-From-Scratch And Contract Compatibility

Goal: prove a clean install and public contracts still match implementation.

Fresh Context:

- `pro-merged-master-v1.2/database/README.md`.
- `pro-merged-master-v1.2/database/001_extensions.sql`.
- `pro-merged-master-v1.2/database/010_types_and_enums.sql`.
- `pro-merged-master-v1.2/database/020_core_tables.sql`.
- `pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql`.
- `pro-merged-master-v1.2/database/030_constraints_and_triggers.sql`.
- `pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql`.
- `pro-merged-master-v1.2/database/050_views_and_functions.sql`.
- `pro-merged-master-v1.2/database/060_seed_taxonomies.sql`.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`.
- Active `database/`, `contracts/`, `scripts/migrate.py`, `scripts/validate_contracts.py`, and migration tests.

Work:

- Run and, if needed, extend migration-from-scratch tests against a blank database with the intended PostgreSQL/ParadeDB/pgvector image.
- Validate all baseline SQL files apply in documented order, excluding `070_query_examples.sql` from required boot while keeping it checked as example syntax where practical.
- Validate extensions and fallback behavior: `pg_search`, `pgvector`, `ltree`, optional PGMQ, and Redis fallback profile assumptions.
- Confirm generated FastAPI OpenAPI paths match active `contracts/api/openapi.yaml`. Internal health probes should not create public contract drift.
- Validate every JSON Schema and event schema through the active registry.
- Validate DTO and API response shapes for the paths exercised by Phase 11 tests.
- Verify migration idempotency, legacy adoption behavior, and schema checksum tracking remain intact.
- Include a report section listing any contract extensions made in earlier phases and their test coverage.

Firecrawl Evidence:

- Use Firecrawl if PostgreSQL extension behavior, ParadeDB index syntax, pgvector index behavior, OpenAPI 3.1 semantics, JSON Schema draft behavior, or FastAPI OpenAPI generation behavior is uncertain.

Exit Criteria:

- A fresh database can be migrated and used.
- Active API and contract files are aligned.
- Schema and event validation is part of the release gate.

## 11.9 Restore And Operational Recovery Rehearsal

Goal: prove the private archive can be restored, not merely backed up.

Fresh Context:

- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, backup, restore, and operational expectations.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, release candidate gates.
- `pro-merged-master-v1.2/infrastructure/README.md`.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`.
- `pro-merged-master-v1.2/infrastructure/zfs/README.md`.
- `pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv`.
- `STRUCTURA_PHASE_10_IMPLEMENTATION_PLAN.md`, backup and restore subphases.
- Active Compose, storage settings, backup scripts, restore scripts, and admin service-health code.

Work:

- Define a restore rehearsal that covers Postgres state, canonical objects, derived objects required for browse/search quality, config, and release scripts.
- Restore into an isolated target, not over the active local development database or object root.
- After restore, verify:
  - document row count and expected sample ids;
  - original asset hashes and byte sizes;
  - document-to-asset references;
  - canonical parse/current extraction references;
  - review tasks and audit history;
  - search index availability or rebuild instructions;
  - export bundle treatment and retention policy;
  - service health/admin visibility.
- Document which datasets are mandatory backups, optional backups, rebuildable caches, and never-backup temporary locations.
- Ensure logs and restore evidence do not include secrets, raw private document text, raw object URIs, or private corpus bytes.
- Record restore duration, manual steps, known limitations, and exact command sequence.

Firecrawl Evidence:

- Use Firecrawl if Postgres logical/physical backup behavior, ZFS snapshot/replication behavior, Docker volume restore behavior, or object-store consistency checks are uncertain.

Exit Criteria:

- Restore rehearsal has passed in an isolated target.
- Object and database integrity are checked after restore.
- Recovery instructions are concrete enough for a future operator.

## 11.10 Security, Privacy, SAST, And Data-Flow Gate

Goal: make the release candidate pass static and security validation without weakening product security boundaries.

Fresh Context:

- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`.
- `STRUCTURA_PHASE_10_IMPLEMENTATION_PLAN.md`, auth hardening, ACL, exports, SAST, and operational QA.
- Active `Makefile`, `pyproject.toml`, API routes, auth service, storage service, workers, and web code.
- Active tests covering auth, CSRF, API tokens, folder ACL, protected assets, exports, jobs, and admin health.

Work:

- Run and report:
  - formatting check;
  - lint;
  - type checking;
  - Bandit;
  - Semgrep;
  - Pyright;
  - mypy;
  - dependency/audit checks appropriate for Python and Node;
  - secrets scan if a project-standard tool is available.
- Add or refine data-flow checks for:
  - raw object-store URI exposure;
  - document content in logs/errors;
  - raw prompts/model outputs in normal logs;
  - export authorization;
  - protected asset access;
  - folder/document ACL;
  - CSRF on browser mutating routes;
  - API-token scope enforcement;
  - path traversal and archive extraction safety;
  - unsafe eval/exec/deserialization patterns.
- Treat tool absence as a release evidence issue. Either install/configure the toolchain under the project bootstrap path or document why a tool cannot run in this environment.
- Do not suppress SAST findings without rationale and a test or code reference.
- Confirm Docker images and runtime containers do not require root unless explicitly justified.

Firecrawl Evidence:

- Use Firecrawl if SAST tool configuration, OWASP guidance, Semgrep/Bandit/Pyright behavior, CSRF conventions, secure cookie conventions, or dependency-audit practices are uncertain.

Exit Criteria:

- Static and security tool status is known and documented.
- Any open security finding is severity-triaged with rationale.
- No critical or high security issue remains unaddressed for RC.

## 11.11 Performance, Reliability, And Resource Measurements

Goal: validate release-candidate behavior against the single-node nonfunctional targets.

Fresh Context:

- `pro-merged-master-v1.2/docs/01_App_Specification.md`, performance and reliability targets.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, performance, observability, and failure handling.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`.
- Active API, worker, search, model-placeholder/model-service, Compose, and observability surfaces.

Work:

- Measure the release-critical NFR targets where implementation exists:
  - health endpoints under 100 ms;
  - inbox list under 500 ms median on moderate corpus;
  - document detail metadata under 500 ms median;
  - cached first page visible within target UI smoke conditions;
  - lexical search under 300 ms median;
  - hybrid search under 1 second median excluding optional heavy rerank;
  - review action submit under 500 ms median;
  - upload acknowledgement row appears within 2 seconds after upload completion;
  - service health/admin endpoints respond under normal load.
- Measure worker reliability:
  - retry behavior;
  - dead-letter visibility;
  - idempotent reprocessing;
  - restart recovery;
  - partial model outage degradation;
  - queue depth and job age reporting.
- Measure storage growth by artifact class during a corpus run: canonical originals, derived parse assets, thumbnails/page images, raw model output, normalized extraction JSON, embeddings, exports, logs, and cache.
- Record hardware/runtime profile and model profile for each measurement so future regressions are comparable.
- Separate hard release blockers from tuning backlog items. A slow benchmark without data loss may be high or medium depending on user impact; silent corruption is critical.

Firecrawl Evidence:

- Use Firecrawl if load-testing tools, timing methodology, Docker resource measurement, GPU metric collection, browser performance APIs, or service-health conventions are uncertain.

Exit Criteria:

- Release-critical latency and reliability measurements are recorded.
- Queue and worker degradation behavior is visible.
- Resource growth risks are documented before release.

## 11.12 Release Candidate Evidence Pack And Stop Gate

Goal: produce the final Phase 11 release-readiness report and stop for human review.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 11 Done criteria.
- `STRUCTURA_PLAN_INDEX.md`, stop rule.
- `pro-merged-master-v1.2/AGENT_START_HERE.md`, stop/go gates and deliverable philosophy.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, release candidate checklist.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, release requirements.
- All Phase 11 report outputs, benchmark reports, test logs, restore evidence, SAST results, and known-issue notes.

Work:

- Create a release evidence pack under a committed documentation path such as `docs/release/phase-11/` with private details redacted or kept out of Git.
- Include:
  - phase scope and commit/runtime profile;
  - required artifact review statement;
  - corpus manifest summary without private content;
  - extraction metrics summary;
  - search metrics summary;
  - UI smoke and Figma regression summary;
  - migration-from-scratch status;
  - restore rehearsal status;
  - SAST/static-analysis status;
  - performance and reliability status;
  - contract compatibility status;
  - known issues by severity;
  - explicit critical/high blocker list;
  - recommended stop/go decision.
- Confirm the minimum release-candidate criteria:
  - migrations succeed from scratch;
  - golden search tests pass or misses are accepted with rationale;
  - extraction metrics are acceptable or known limitations are documented;
  - restore rehearsal passes;
  - no critical data-integrity bugs remain;
  - no silent overwrite of originals;
  - no broken provenance links on tested trusted facts;
  - no critical security/privacy issue remains;
  - known-severity issues are documented.
- Stop after producing the evidence pack and wait for user review. Do not proceed into post-RC feature work without explicit instruction.

Firecrawl Evidence:

- Use Firecrawl if release report structure, severity communication, or benchmark acceptance reporting practices are uncertain.

Exit Criteria:

- Phase 11 has a complete evidence pack.
- The release candidate has a concrete stop/go recommendation.
- The agent stops for user review.

## Suggested Phase 11 Verification Command Suite

Adapt exact commands to the implemented project state, but the release evidence should cover this shape:

```bash
python3 -m compileall -q apps lib workers scripts tests
python3 -m ruff format --check .
make lint
make contracts
make sast
python3 -m pytest
npm --workspace apps/web run build
```

Expected Phase 11 additions may include commands like:

```bash
python3 scripts/evaluate_golden_corpus.py --corpus <private-corpus-root> --stage full --report docs/release/phase-11/evaluation.json
python3 scripts/score_extraction.py --run-id <evaluation-run-id>
python3 scripts/score_search.py --run-id <evaluation-run-id>
npx playwright test
```

If any command cannot run because a tool is unavailable, record that as release evidence and either install/configure the tool through the normal bootstrap path or mark it as an open release issue with severity.

## Phase 11 Completion Criteria

Phase 11 is complete only when:

- the golden corpus is secured and runnable;
- expected answers are versioned and validated;
- extraction and search quality are measured on the corpus;
- Playwright smoke tests cover release-critical UI flows;
- migration-from-scratch passes;
- restore rehearsal passes;
- static analysis, SAST, type checking, formatting, lint, contracts, and runtime checks have run or are explicitly documented as unavailable;
- performance and reliability measurements are recorded against the nonfunctional targets;
- all critical issues are resolved;
- high issues are either resolved or explicitly accepted by the user;
- the release evidence pack is written;
- the agent stops for user review.
