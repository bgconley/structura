# Structura Phase 12 Implementation Plan

Phase 12 is the final internal-GA and operator handoff phase. `STRUCTURA_IMPLEMENTATION_PLAN.md` does not define a separate `## Phase 12` heading; its numbered plan stops at Phase 11 with the golden corpus, regression, and release-candidate gate. This plan is therefore a derived final phase that consumes Phase 11 release evidence and turns an acceptable release candidate into a usable, supportable internal v1 milestone.

This is the last planned phase. It should not become a new feature expansion phase. Its purpose is to close accepted blockers, freeze contracts and operational assumptions, prepare the runtime for daily use, tag the release, and document the post-release operating cadence.

## Operating Rules

- Do not inspect or rely on anything under `archive/`.
- Before coding any subphase, re-read the files listed in that subphase's **Fresh Context** section. Use `wc -l` and bounded `sed -n` chunks for large files so full reads are auditable.
- When an artifact exists in both Markdown and DOCX form, read the Markdown artifact by default. Only inspect DOCX when the user explicitly asks for layout/fidelity review or when the Markdown file is missing/incomplete.
- Treat Phase 11's release-candidate evidence pack as the input gate for Phase 12. If Phase 11 did not produce a concrete stop/go recommendation, stop and complete that first.
- Phase 12 may fix release blockers and documentation gaps. It must not add new product families, ingestion channels, model routes, search modes, collaboration modes, redaction workflows, or cloud/SaaS behavior unless the user explicitly approves a scope change.
- Preserve every non-negotiable invariant: original bytes are immutable, trusted facts require concrete evidence, schema validation precedes accepted facts, low-confidence outputs create review, canonical fields and canonical line items are the default read model, search indexes are assistive, analysis is optional and cited, exports are explicit and audited, backups are tested, and ACL checks run before returning document-derived content.
- Do not weaken tests, SAST, provenance, privacy, restore, ACL, CSRF, migration, or contract parity to get to a release label.
- Keep private corpus documents, private restore outputs, database dumps, object archives, secret-bearing logs, and sensitive model outputs out of Git.
- If a release decision depends on user acceptance of a threshold, residual risk, or known issue, record that decision in the final release ledger.

## Firecrawl Evidence Rule

When APIs, external contracts, library behavior, security conventions, OpenAPI semantics, JSON Schema semantics, FastAPI/Pydantic behavior, PostgreSQL/ParadeDB/pgvector behavior, Docker Compose behavior, ZFS operations, backup/restore mechanics, SAST tooling, dependency/security audit tooling, Playwright behavior, accessibility conventions, browser security, release tagging, deployment practices, or operational runbook conventions are in play, search online with Firecrawl if there is any uncertainty.

Use primary sources where possible: official framework documentation, standards documents, package docs, project repositories, security guidance, PostgreSQL/ZFS/Docker docs, Playwright docs, OWASP guidance, or vendor docs. Save Firecrawl outputs under `.firecrawl/`, read them incrementally, and summarize the evidence in implementation notes, ADRs, release notes, or runbooks when it affects a decision. Do not use unsourced memory to settle uncertain API, security, storage, browser, restore, release, or operational behavior.

## Phase 12 Derived Required Artifact Set

Because the root implementation plan has no Phase 12 artifact list, use this derived final-release artifact set. Re-read the subphase-specific subset before coding each subphase.

```text
/Users/brennanconley/vibecode/structura/STRUCTURA_IMPLEMENTATION_PLAN.md
/Users/brennanconley/vibecode/structura/STRUCTURA_PLAN_INDEX.md
/Users/brennanconley/vibecode/structura/STRUCTURA_UI_FIGMA_QA_PLAN.md
/Users/brennanconley/vibecode/structura/STRUCTURA_PHASE_1_IMPLEMENTATION_PLAN.md
/Users/brennanconley/vibecode/structura/STRUCTURA_PHASE_2_IMPLEMENTATION_PLAN.md
/Users/brennanconley/vibecode/structura/STRUCTURA_PHASE_3_IMPLEMENTATION_PLAN.md
/Users/brennanconley/vibecode/structura/STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md
/Users/brennanconley/vibecode/structura/STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md
/Users/brennanconley/vibecode/structura/STRUCTURA_PHASE_6_IMPLEMENTATION_PLAN.md
/Users/brennanconley/vibecode/structura/STRUCTURA_PHASE_7_IMPLEMENTATION_PLAN.md
/Users/brennanconley/vibecode/structura/STRUCTURA_PHASE_8_IMPLEMENTATION_PLAN.md
/Users/brennanconley/vibecode/structura/STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md
/Users/brennanconley/vibecode/structura/STRUCTURA_PHASE_10_IMPLEMENTATION_PLAN.md
/Users/brennanconley/vibecode/structura/STRUCTURA_PHASE_11_IMPLEMENTATION_PLAN.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/001_extensions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/010_types_and_enums.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/030_constraints_and_triggers.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/050_views_and_functions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/060_seed_taxonomies.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/*.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/*.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv
/Users/brennanconley/vibecode/structura/README.md
/Users/brennanconley/vibecode/structura/Makefile
/Users/brennanconley/vibecode/structura/compose.yaml
/Users/brennanconley/vibecode/structura/.env.example
```

Also read the Phase 11 evidence pack produced by implementation, expected at a path such as:

```text
docs/release/phase-11/
```

If the actual Phase 11 report path differs, use the committed release evidence location from Phase 11.

## Phase 12 Target Deliverables

- A final blocker-disposition ledger derived from Phase 11 findings.
- A frozen API/schema/migration/contract statement for internal v1.
- Final operator runbooks for install, start, stop, backup, restore, corpus evaluation, and troubleshooting.
- Final environment/configuration guide that distinguishes required settings, optional model settings, secrets, and local-only defaults.
- Final UI acceptance record tied to Figma and Playwright evidence.
- Final security/privacy review record with no unresolved critical or high findings unless explicitly accepted by the user.
- Final benchmark threshold acceptance record for extraction, search, UI smoke, migration, restore, and performance.
- Final known-issues document with severity, workaround, owner, and post-release trigger.
- Release notes and version tag guidance.
- GPU node deployment/sync checklist, if the user asks to commit and push the release.
- A final go/no-go recommendation and post-release operating cadence.

## 12.0 Phase Boundary, Input Gate, And Release Scope

Goal: confirm that Phase 12 is the final internal-GA handoff phase and that Phase 11 produced enough evidence to proceed.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 11 section, testing matrix, open decisions, and continuous workstreams.
- `STRUCTURA_PHASE_11_IMPLEMENTATION_PLAN.md`, especially Phase 11 completion criteria.
- Phase 11 release evidence pack under `docs/release/phase-11/` or its actual path.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, GA-like internal release and production-like acceptance gates.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, Definition of done and final instruction.
- `STRUCTURA_PLAN_INDEX.md`, source alignment and stop rules.

Work:

- Verify Phase 11 is complete enough to act on:
  - migrations pass from scratch;
  - restore rehearsal passed;
  - golden search tests passed or misses are accepted with rationale;
  - extraction metrics meet approved thresholds or limitations are accepted;
  - Playwright workflow tests passed;
  - no critical data-integrity bugs remain;
  - no broken provenance links on tested trusted facts;
  - no critical security/privacy issue remains;
  - known issues are documented by severity.
- Create the Phase 12 release scope statement. It should say that only blocker fixes, release hardening, operator handoff, documentation, and final tagging are in scope.
- Create a blocker-disposition table from Phase 11:
  - finding id;
  - severity;
  - affected invariant;
  - status;
  - fix PR/commit or accepted-risk decision;
  - verification command/report;
  - release impact.
- Stop if Phase 11 evidence is absent, stale, or inconclusive. Do not replace Phase 11 with guesswork.

Firecrawl Evidence:

- Use Firecrawl if release acceptance terminology, severity definitions, or internal-GA gate practices are uncertain.

Exit Criteria:

- Phase 12 has a clear release-only scope.
- Phase 11 evidence is accepted as the input gate.
- Every open blocker is triaged before code changes begin.

## 12.1 Blocker Remediation And Non-Negotiable Invariants

Goal: resolve valid release blockers without broadening product scope.

Fresh Context:

- Phase 11 blocker-disposition ledger.
- `pro-merged-master-v1.2/AGENT_START_HERE.md`, non-negotiable rules.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, product-level acceptance.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, data integrity and security requirements.
- `pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md`.
- Relevant phase-specific plan for the code being touched.
- Relevant active code, contracts, tests, migrations, and UI reference files.

Work:

- Fix only validated release blockers or explicitly approved high-severity issues.
- For each fix, re-read the owning phase plan and artifacts before editing. Examples:
  - upload/original asset issue: re-read Phase 1 plan and object storage artifacts;
  - folder/tag/ACL issue: re-read Phase 2 and Phase 10 plans plus ACL schema;
  - parse/evidence issue: re-read Phase 3 and evidence contracts;
  - extraction/review issue: re-read Phase 4, schemas, canonical/candidate artifacts;
  - search issue: re-read Phase 5 and query/index artifacts;
  - relationships/deadlines issue: re-read Phase 7 artifacts;
  - difficult-document issue: re-read Phase 8 artifacts;
  - analysis issue: re-read Phase 9 artifacts;
  - export/auth/backup/admin issue: re-read Phase 10 artifacts;
  - benchmark/release evidence issue: re-read Phase 11 artifacts.
- Require a targeted verification command for every blocker fix.
- Update tests in the same change set as the fix.
- Update the blocker-disposition ledger with the final verification result.
- If a blocker cannot be fixed without a feature redesign, stop and present the tradeoff rather than slipping it into Phase 12.

Firecrawl Evidence:

- Use Firecrawl if a blocker involves external API behavior, security conventions, database semantics, browser behavior, backup/restore mechanics, library behavior, or any uncertain implementation convention.

Exit Criteria:

- Critical blockers are resolved.
- High blockers are resolved or explicitly accepted by the user.
- Every fix has a verification result and a linked release note entry.

## 12.2 Contract, Schema, Migration, And Data-Authority Freeze

Goal: freeze the internal v1 public and persistence surface so release behavior is reproducible.

Fresh Context:

- `pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md`.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, data authority, evidence, contract, and storage normalization.
- `pro-merged-master-v1.2/contracts/README.md`.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`.
- `pro-merged-master-v1.2/contracts/schemas/*.schema.json`.
- `pro-merged-master-v1.2/contracts/events/*.schema.json`.
- `pro-merged-master-v1.2/database/README.md`.
- Active `contracts/`, `database/`, `scripts/validate_contracts.py`, migration code, DTOs, API routes, and contract tests.

Work:

- Freeze OpenAPI paths and security scheme semantics for internal v1. Any change after this point requires a release note and compatibility rationale.
- Validate generated FastAPI OpenAPI paths match active `contracts/api/openapi.yaml`.
- Validate JSON Schema and event-schema registries.
- Validate database migrations apply from scratch and rerun idempotently.
- Confirm canonical read paths:
  - UI, filters, filing rules, exports, search enrichment, and summaries prefer `canonical_fields` and `canonical_line_items`;
  - candidate tables remain review/provenance inputs;
  - original bytes remain immutable source artifacts;
  - structural artifacts remain versioned derivatives.
- Confirm all trusted evidence still requires page number plus a concrete locator.
- Record final schema/app/contract versions in the release notes.
- If any SQL or contract file changes during Phase 12, update ADR or release notes explaining why the freeze changed.

Firecrawl Evidence:

- Use Firecrawl if OpenAPI 3.1, JSON Schema draft behavior, FastAPI OpenAPI generation, PostgreSQL extension behavior, ParadeDB, pgvector, or migration compatibility is uncertain.

Exit Criteria:

- API, schema, migrations, and data-authority behavior are frozen and verified.
- The release notes identify the final contract and schema versions.
- Contract drift is zero or explicitly documented with user approval.

## 12.3 Runtime Configuration, Deployment, And Local-First Exposure

Goal: make the internal release start predictably and stay local-first by default.

Fresh Context:

- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, local-first and secret handling.
- `pro-merged-master-v1.2/infrastructure/README.md`.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`.
- `pro-merged-master-v1.2/infrastructure/zfs/README.md`.
- `pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv`.
- `STRUCTURA_PLAN_INDEX.md`, GPU node sync policy.
- Active `compose.yaml`, `.env.example`, `README.md`, Dockerfiles, settings, and startup scripts.

Work:

- Verify `.env.example` documents required and optional settings without real secrets.
- Confirm local-only defaults:
  - no public internet exposure assumed;
  - no document-content egress by default;
  - model services are local or explicitly disabled;
  - reverse proxy, TLS, VPN/Tailscale assumptions are documented if enabled.
- Verify service names, object paths, queue names, cookie names, logs, manifests, examples, and docs consistently use `Structura`.
- Validate Docker Compose profiles for API, web, Postgres, workers, model placeholders/services, and optional Redis fallback.
- Confirm persistent mounts align with the ZFS dataset matrix.
- Confirm application virtualenv guidance for GPU node uses `/tank/venvs`, not the repo.
- Document first-run sequence:
  - bootstrap dependencies;
  - create datasets or verify mounts;
  - configure env;
  - migrate database;
  - bootstrap admin;
  - start services;
  - run smoke checks;
  - run corpus evaluation if private corpus is available.
- If committing and pushing the final release, follow the GPU node sync policy after push.

Firecrawl Evidence:

- Use Firecrawl if Docker Compose behavior, reverse proxy/TLS behavior, ZFS property behavior, or local deployment security assumptions are uncertain.

Exit Criteria:

- Runtime configuration is documented and reproducible.
- Local-first exposure is preserved by default.
- First-run instructions are concrete enough for the operator.

## 12.4 Operator Runbooks And Recovery Workflows

Goal: make common operator tasks executable without reading the implementation code.

Fresh Context:

- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, backup, observability, and failure handling.
- `STRUCTURA_PHASE_10_IMPLEMENTATION_PLAN.md`, backup/restore, admin jobs, health, settings.
- `STRUCTURA_PHASE_11_IMPLEMENTATION_PLAN.md`, restore rehearsal and evidence pack.
- Phase 11 restore evidence.
- Active `README.md`, scripts, Compose config, admin routes, and tests.

Work:

- Write or update runbooks for:
  - start/stop/restart;
  - migrate from scratch;
  - bootstrap or rotate admin credential;
  - manage sessions, passkeys, and API tokens where implemented;
  - run workers;
  - inspect service health;
  - retry failed or dead-letter jobs;
  - run golden corpus evaluation;
  - create backups;
  - restore into an isolated target;
  - check object/DB consistency;
  - rotate logs or clean caches safely;
  - troubleshoot model-server outages;
  - troubleshoot search/index freshness;
  - produce an export bundle and audit it.
- Distinguish safe maintenance tasks from tasks requiring downtime.
- Include exact commands, expected outputs, and rollback notes where possible.
- Document what not to do:
  - do not edit DB rows manually to "accept" extraction;
  - do not overwrite canonical originals;
  - do not expose raw object directories through the web server;
  - do not restore over an active archive without a tested plan.

Firecrawl Evidence:

- Use Firecrawl if operational runbook conventions, Postgres restore practices, Docker Compose maintenance, ZFS snapshots, or service health conventions are uncertain.

Exit Criteria:

- Operator runbooks cover daily operation and emergency recovery.
- Runbooks reference tested commands, not aspirational procedures.
- Risky operations are clearly marked.

## 12.5 Benchmark Threshold Approval And Regression Lock

Goal: convert Phase 11 measurements into approved release thresholds and future regression gates.

Fresh Context:

- Phase 11 extraction, search, UI, migration, restore, SAST, and performance reports.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, regression discipline and production-like gates.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, search, handwriting, parse quality, and model-serving risks.
- Active corpus evaluation scripts, expected-answer files, benchmark reports, and CI/local test documentation.

Work:

- Record approved thresholds for:
  - classification accuracy;
  - required field presence;
  - exact-match header-field accuracy;
  - numeric/amount correctness;
  - arithmetic consistency;
  - review-task creation on bad inputs;
  - evidence validity;
  - lexical search hit rate;
  - semantic search hit rate;
  - hybrid search improvement;
  - query latency;
  - Playwright workflow pass rate;
  - restore success;
  - migration-from-scratch success.
- Mark threshold owners and update cadence.
- Decide which benchmark suites are mandatory before future releases, before prompt/model changes, and before schema/index/ranking changes.
- Document allowed regressions. A regression must be deliberate, justified, and paired with user-visible improvement or risk reduction.
- Ensure private corpus outputs remain outside public Git while sanitized summaries are committed.

Firecrawl Evidence:

- Use Firecrawl if benchmark threshold setting, retrieval metrics, extraction scoring, or regression-report conventions are uncertain.

Exit Criteria:

- Release thresholds are approved or explicitly deferred with rationale.
- Future regression gates are documented.
- Benchmark outputs are safe to store and compare.

## 12.6 Final UI, Figma, Accessibility, And Workflow Acceptance

Goal: verify that the internal release still feels like the intended calm evidence workbench and passes core workflows.

Fresh Context:

- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`.
- Phase 11 Playwright and screenshot reports.
- Figma frames `17:2`, `14:434`, `14:611`, `14:797`, `14:990`, `35:2`, `35:7`, `35:12`, and `35:17`.
- Active `apps/web/src/`, UI tests, screenshots, and UI reference artifacts.

Work:

- Re-run release-critical Playwright flows:
  - sign in;
  - upload;
  - inbox row appears;
  - protected viewer opens;
  - evidence inspector updates;
  - review queue action;
  - evidence jump;
  - field correction;
  - folder/tag filing;
  - search and result open;
  - relationship/timeline where implemented;
  - analysis disabled/enabled state;
  - export/admin health where implemented.
- Compare release screenshots against Figma references or documented accepted deltas.
- Validate edge states: empty corpus, processing, workers offline, original unavailable, duplicate suspect, low-confidence extraction, no review items, failed extraction, and search no results.
- Check accessibility basics: focus order, keyboard reachability, accessible names, no color-only status, text overflow, and responsive inspector/drawer behavior.
- If Figma and implementation conflict on visible behavior, use the UI stop rule and ask the user.

Firecrawl Evidence:

- Use Firecrawl if Playwright behavior, accessibility checks, browser screenshot conventions, or UI regression methods are uncertain.

Exit Criteria:

- UI acceptance evidence is recorded.
- Any remaining visual or workflow mismatch is documented and accepted.
- Release-critical workflows are usable without developer intervention.

## 12.7 Security, Privacy, And Compliance-Like Final Review

Goal: ensure the internal release is safe enough for a private archive containing medical, legal, and financial documents.

Fresh Context:

- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`.
- `STRUCTURA_PHASE_10_IMPLEMENTATION_PLAN.md`, auth hardening, ACL, export audit, backup/restore, SAST.
- `STRUCTURA_PHASE_11_IMPLEMENTATION_PLAN.md`, SAST/data-flow gate.
- Phase 11 security reports and known issues.
- Active auth, asset, export, ACL, logging, worker, and admin code.

Work:

- Confirm final status of:
  - authentication routes;
  - session timeout/logout/revoke behavior;
  - CSRF on browser-mutating routes;
  - API-token lifecycle and scopes;
  - folder/document ACL behavior;
  - protected asset streaming;
  - export authorization and audit;
  - no raw object URI exposure;
  - no raw sensitive content in normal logs/errors;
  - secret handling;
  - default local-only network posture;
  - Docker non-root behavior where applicable;
  - dependency and SAST findings.
- Re-run the final security/static command suite or cite the unchanged Phase 11 report if no code has changed since.
- Create a release security summary:
  - resolved findings;
  - accepted risks;
  - deferred issues;
  - mitigations;
  - required operator settings.
- If any critical security or privacy issue remains, do not mark Phase 12 complete.

Firecrawl Evidence:

- Use Firecrawl if OWASP guidance, cookie/CSRF conventions, WebAuthn/passkey behavior, API-token conventions, SAST tool behavior, or Docker hardening conventions are uncertain.

Exit Criteria:

- No unresolved critical security/privacy issue remains.
- High security/privacy issues are resolved or explicitly accepted by the user.
- Security expectations are documented for operation.

## 12.8 Backup, Restore, Disaster Recovery, And Restart Signoff

Goal: prove the archive can survive realistic operational interruptions.

Fresh Context:

- Phase 11 restore evidence.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, reliability and backup requirements.
- `pro-merged-master-v1.2/infrastructure/zfs/README.md`.
- `pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv`.
- `STRUCTURA_PHASE_10_IMPLEMENTATION_PLAN.md`, backup/restore plan.
- Active backup/restore scripts, object roots, Compose config, and runbooks.

Work:

- Rehearse or verify the latest restore evidence after any Phase 12 changes.
- Validate isolated restore target:
  - database opens;
  - documents list;
  - original asset hashes match;
  - protected assets stream;
  - canonical/current extraction references resolve;
  - review and audit history survive;
  - search is available or rebuildable through documented commands;
  - service health reflects restored services.
- Run restart/recovery smokes:
  - API restart;
  - worker restart;
  - Postgres restart;
  - model service down/degraded behavior;
  - failed-job retry.
- Confirm backup class for every dataset: mandatory, optional, rebuildable, or temporary.
- Record restore duration and any manual steps.

Firecrawl Evidence:

- Use Firecrawl if Postgres backup/restore behavior, ZFS snapshot/replication behavior, Docker restart behavior, or object consistency validation is uncertain.

Exit Criteria:

- Latest restore evidence is valid after Phase 12 changes.
- Restart behavior is documented and tested enough for internal use.
- Disaster recovery instructions are actionable.

## 12.9 Performance, Capacity, And Resource Signoff

Goal: make the first internal release honest about single-node performance and resource limits.

Fresh Context:

- Phase 11 performance and reliability measurements.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, performance targets.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, observability and failure handling.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, model-serving memory and storage-sprawl risks.
- Active observability/admin health surfaces, Compose profiles, worker services, model services, and storage usage reports.

Work:

- Confirm final release measurements for:
  - health endpoint latency;
  - inbox list latency;
  - document detail latency;
  - lexical search latency;
  - hybrid search latency;
  - review action latency;
  - upload acknowledgement behavior;
  - worker queue depth and job age;
  - model-server status;
  - storage by artifact class;
  - memory/GPU pressure if model services are active.
- Record known capacity assumptions:
  - corpus size tested;
  - document classes tested;
  - model profile tested;
  - embedding dimensions;
  - hardware profile;
  - Compose profiles enabled.
- Document tuning knobs and when to revisit architecture, such as corpus growth, multi-user support, model-serving bottlenecks, or a superior parser.
- Mark any performance misses as accepted, blocking, or deferred with a concrete follow-up.

Firecrawl Evidence:

- Use Firecrawl if performance measurement methods, browser timing APIs, Docker resource metrics, GPU monitoring, or Postgres/search tuning conventions are uncertain.

Exit Criteria:

- Performance and capacity assumptions are documented.
- Release-blocking performance issues are resolved or accepted.
- Operators know what symptoms require tuning or architectural review.

## 12.10 Documentation, ADR, Release Notes, And Known-Issue Ledger

Goal: make the internal release understandable after implementation context fades.

Fresh Context:

- `pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md`.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`.
- `STRUCTURA_IMPLEMENTATION_PLAN.md`, open technical decisions and continuous workstreams.
- Phase 11 and Phase 12 evidence outputs.
- Active `README.md`, ADRs, runbooks, `.env.example`, and release docs.

Work:

- Update release notes with:
  - version;
  - date;
  - commit hash;
  - implemented phase coverage;
  - contract/schema versions;
  - migration state;
  - model profiles;
  - benchmark summary;
  - restore status;
  - known issues;
  - operator actions required.
- Update ADRs when implementation differs from baseline decisions.
- Update known issues with severity, workaround, owner, and revisit trigger.
- Update README and runbooks so they match actual commands and paths.
- Document deferred enhancements explicitly, including email ingestion, mobile companion/share extension, redaction workflows, active learning/fine-tuning, richer reminders, and broader collaboration.
- Ensure docs do not include private corpus content, secrets, raw object paths, or sensitive excerpts.

Firecrawl Evidence:

- Use Firecrawl if release-note conventions, ADR conventions, or operational documentation practices are uncertain.

Exit Criteria:

- Release docs match actual behavior.
- Architectural deviations are recorded.
- Known issues and deferred features are explicit.

## 12.11 Release Packaging, Version Tagging, And Deployment Sync

Goal: package the internal release in a way that can be reproduced and synced to the target node when requested.

Fresh Context:

- `STRUCTURA_PLAN_INDEX.md`, GPU node sync policy.
- Active `git status`, release notes, README, Makefile, Compose files, Dockerfiles, contracts, migrations, and tests.
- Phase 12 final verification report.

Work:

- Confirm the working tree only contains intended release changes.
- Confirm generated/private artifacts are excluded or intentionally committed.
- Run final verification command suite after all code/doc changes.
- Prepare the release commit message and tag name, if the user asks to commit/tag.
- Suggested tag format: `v0.1.0-internal` or another explicit internal-release tag approved by the user.
- If committing and pushing:
  - commit intentionally;
  - push to GitHub;
  - SSH to the GPU node;
  - update `/tank/repos/structura`;
  - confirm the target checkout is on the pushed commit;
  - keep virtualenvs under `/tank/venvs`.
- Do not perform destructive deployment actions or overwrite active data without explicit user approval.

Firecrawl Evidence:

- Use Firecrawl if release-tagging conventions, GitHub release conventions, Docker packaging, or deployment synchronization practices are uncertain.

Exit Criteria:

- Release package is reproducible.
- Tag/commit/sync steps are documented and run only with user approval.
- No private artifacts are included unintentionally.

## 12.12 Final Go/No-Go And Post-Release Operating Cadence

Goal: close the final phase with a clear decision and operating plan.

Fresh Context:

- Phase 12 blocker ledger, final verification, release notes, runbooks, and known issues.
- Phase 11 evidence pack.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, production-like acceptance gates.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, Definition of done.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, review cadence and revisit triggers.

Work:

- Produce the final release decision document:
  - go/no-go recommendation;
  - unresolved blockers;
  - accepted risks;
  - benchmark threshold status;
  - restore and migration status;
  - security status;
  - UI/workflow status;
  - performance status;
  - operator readiness status.
- Confirm first usable release definition:
  - upload, store, and browse documents;
  - Docling canonical parsing durable and visible;
  - receipt, invoice, and EOB extraction functional with review flows;
  - hybrid search good on curated golden set;
  - folders, tags, smart folders, and related documents work;
  - backups and restore rehearsed;
  - analysis optional, cited, and bounded.
- Define post-release cadence:
  - run golden corpus after prompt/model/schema/index/ranking changes;
  - run restore rehearsal on a schedule;
  - review risks after meaningful corpus growth;
  - review model-serving capacity after heavy usage;
  - inspect known issues before each maintenance release;
  - keep SAST/lint/type/contracts in normal verification.
- Stop after the final release decision. Do not create a Phase 13 or continue into new feature work without explicit user direction.

Firecrawl Evidence:

- Use Firecrawl if go/no-go reporting, release acceptance, operational cadence, or maintenance-release conventions are uncertain.

Exit Criteria:

- Final go/no-go decision is written.
- Post-release operating cadence is documented.
- Phase 12 is closed as the final planned phase.

## Suggested Phase 12 Verification Command Suite

Adapt exact commands to the implemented project state, but the final release should cover this shape:

```bash
python3 -m compileall -q apps lib workers scripts tests
python3 -m ruff format --check .
make lint
make contracts
make sast
python3 -m pytest
npm --workspace apps/web run build
npx playwright test
```

Expected final-release additions may include:

```bash
python3 scripts/evaluate_golden_corpus.py --corpus <private-corpus-root> --stage full --report docs/release/phase-12/evaluation.json
python3 scripts/score_extraction.py --run-id <evaluation-run-id>
python3 scripts/score_search.py --run-id <evaluation-run-id>
python3 scripts/restore_rehearsal.py --target <isolated-restore-target>
python3 scripts/check_object_db_consistency.py
```

If any command cannot run because a tool is unavailable, record it in the final release evidence and either install/configure the tool through the normal bootstrap path or mark it as an accepted release issue.

## Phase 12 Completion Criteria

Phase 12 is complete only when:

- Phase 11 evidence has been accepted as the RC input gate;
- all critical issues are resolved;
- high issues are resolved or explicitly accepted by the user;
- API, schema, migration, and data-authority behavior are frozen;
- local-first runtime configuration is documented;
- operator runbooks are complete enough for daily use and recovery;
- benchmark thresholds are approved or explicitly deferred;
- UI/Figma/Playwright acceptance is recorded;
- security/privacy/SAST status is final;
- backup/restore and restart evidence is current;
- performance and capacity assumptions are documented;
- release notes, ADR updates, and known issues are written;
- release package/tag/deployment-sync steps are documented or completed with user approval;
- final go/no-go decision is written;
- the agent stops and waits for user instruction.
