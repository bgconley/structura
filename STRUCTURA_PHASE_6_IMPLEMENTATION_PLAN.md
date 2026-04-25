# Structura Phase 6 Implementation Plan

Phase 6 adds transparent organization automation: contacts, contact aliases, document-contact links, folder ACL enforcement, watched-folder intake, filing rules, rule dry-runs, rule suggestions, rule application with audit, import/maintenance CLI commands, and the UI surfaces needed to make those workflows understandable.

This plan expands Phase 6 from `STRUCTURA_IMPLEMENTATION_PLAN.md`. It does not replace the root plan. Use the root plan for phase boundaries and this document for Phase 6 execution detail.

## Operating Rules

- Do not inspect or rely on anything under `archive/`.
- Before coding any subphase, re-read the files listed in that subphase's **Fresh Context** section. Use `wc -l` and bounded `sed -n` chunks for large files so full reads are auditable.
- When an artifact exists in both Markdown and DOCX form, read the Markdown artifact by default. Only inspect DOCX when the user explicitly asks for layout/fidelity review or the Markdown file is missing/incomplete.
- Keep generated FastAPI OpenAPI paths aligned with `contracts/api/openapi.yaml`. If implementation and contract differ, stop and resolve the contract question explicitly.
- Organization automation must be transparent and reviewable. Rule matches must explain why they matched, and high-stakes documents must default to suggestions or review tasks, not silent finalization.
- Filing rules, watched-folder intake, CLI import, and contact linking must never bypass auth, household ownership, folder ACLs, CSRF protections for browser-mutating routes, or audit requirements.
- Preserve Phase 1-5 invariants: original bytes are immutable, derived artifacts are replaceable, accepted canonical facts remain the default read model for filing/search enrichment, and search indexes remain assistive.
- Keep Phase 6 focused on contacts, filing rules, watched folders, import/maintenance CLI, rule suggestions, and auditable filing automation. Do not implement Phase 7 relationship graphs/timelines/deadlines, Phase 8 difficult-document visual retrieval, Phase 9 analysis, or Phase 10 exports except for contract-safe placeholders already present.

## Firecrawl Evidence Rule

When APIs, external contracts, library behavior, security conventions, OpenAPI semantics, FastAPI/Pydantic behavior, PostgreSQL/SQL behavior, filesystem watcher behavior, atomic file stability checks, path traversal controls, MIME detection, CLI conventions, audit patterns, React/Vite conventions, Playwright behavior, or UI accessibility conventions are in play, search online with Firecrawl if there is any uncertainty.

Use primary sources where possible: official framework documentation, standards documents, official package docs, project repositories, OS/filesystem watcher docs, security guidance, or vendor docs. Save Firecrawl outputs under `.firecrawl/`, read them incrementally, and summarize the evidence in implementation notes or ADRs when it affects a decision. Do not use unsourced memory to settle uncertain API, schema, database, filesystem, browser, worker, CLI, or security behavior.

## Phase 6 Required Artifact Set

The full Phase 6 artifact list from `STRUCTURA_IMPLEMENTATION_PLAN.md` remains required context:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/13_Golden_Master_Review_and_Merge_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/010_types_and_enums.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/filing_rule.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/folder_acl.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/design-language-v1.3.html
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv
```

The duplicate DOCX entries in the root plan are intentionally omitted here under the current repo guidance.

## 6.0 Baseline Reconciliation

Goal: confirm Phase 2 manual organization, Phase 4 accepted facts, and Phase 5 search are stable enough for transparent automation.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 6 section.
- `STRUCTURA_PHASE_2_IMPLEMENTATION_PLAN.md`, manual folders/tags/organization behavior.
- `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md`, canonical facts and review tasks.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, search projection and smart-folder behavior.
- `agents.md`.
- `.wolf/cerebrum.md`.
- `pro-merged-master-v1.2/docs/13_Golden_Master_Review_and_Merge_Plan.md`, contacts/rules adoption.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`.
- `contracts/api/openapi.yaml`.
- `database/025_baseline_identity_acl_candidate_rules.sql`.
- `apps/api/structura_api/routes_documents.py`.
- `compose.yaml`.

Work:

- Confirm folder/tag/document organization routes from Phase 2 are usable and auditable.
- Confirm canonical accepted facts from Phase 4 are available for rule conditions without reading candidate tables as accepted truth.
- Confirm Phase 5 search projection refresh can be invoked after filing changes, contact links, or rule application.
- Reconcile the active OpenAPI contract with Phase 6 needs. Current contract covers list/create-or-update for contacts, filing rules, and watched folders; dry-run/apply/suggestion endpoints are not explicit and must be resolved before implementation.
- Identify implementation modules for organization services, contact services, filing rule engine, watcher worker, CLI commands, audit/event helpers, and UI views.
- Decide whether watched-folder intake will run as a new worker service or a mode of `worker-ingest`. Prefer a distinct service if it improves safety and observability.
- Confirm runtime paths: watched folders feed staging; Structura object, derived, export, cache, backup, repo, config, and log directories must not be recursively ingested.

Firecrawl Evidence:

- Use Firecrawl if OpenAPI contract extension strategy, filesystem watcher choice, stable-file detection, MIME detection, or safe path handling is uncertain.

Exit Criteria:

- Phase 6 implementation boundaries are known.
- Required contract extensions or deferrals are documented before coding.
- Automation cannot bypass manual filing, canonical fact authority, or ACL rules.

## 6.1 Contacts API And Persistence

Goal: make normalized contacts a first-class API and database surface.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 6 task list.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`, Contacts.
- `pro-merged-master-v1.2/docs/13_Golden_Master_Review_and_Merge_Plan.md`, contacts/rules.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `/api/v1/contacts`, `Contact`, and `ContactWrite`.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `contacts`, `contact_aliases`, and indexes.
- `apps/api/structura_api/routes_documents.py`, contact route skeletons.

Work:

- Implement contact list and create-or-update using household-aware authorization.
- Support query by display name, normalized name, aliases, identifiers, and contact type where indexes support it.
- Persist aliases separately from contacts and expose them in contract shape.
- Normalize names deterministically for matching without losing display spelling.
- Validate supported contact types against the database constraint and contract.
- Add audit events for contact create/update/alias changes when user-initiated.
- Add tests for create, update, list, search, aliases, identifiers, duplicate display names across households, CSRF on mutation, and cross-household denial.

Firecrawl Evidence:

- Use Firecrawl if name normalization conventions, citext/trigram behavior, Pydantic aliasing, or OpenAPI upsert semantics are uncertain.

Exit Criteria:

- Contacts are persisted and queryable.
- Contact mutations are protected and auditable.
- The API response matches contract casing.

## 6.2 Document Contact Linking And Alias Resolution

Goal: connect documents to contacts in a way that improves filing, search, and later relationship matching without silently accepting weak matches.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 6 task list.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`, contact relationships and dedupe.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, derived organization and entity-centric browsing.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, `parties` and `document_party_mentions`.
- `pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql`, `document_contacts`.
- `database/040_indexes_bm25_pgvector.sql`, party/contact indexes.
- `contracts/api/openapi.yaml`, contact schemas.

Work:

- Map existing parties/counterparty/canonical fields into suggested contacts when confidence is high enough.
- Link documents to contacts with role names, evidence JSON, and confidence.
- Preserve `document_party_mentions` compatibility while treating `contacts` as the user-facing normalized entity layer for Phase 6.
- Implement manual contact assignment and removal if the contract is extended or a Phase 2 organization action can safely carry it.
- Generate review tasks or suggestions for ambiguous contact matches, likely duplicates, or merge candidates rather than auto-merging.
- Add tests for deterministic alias matching, role assignment, evidence persistence, ambiguous match suggestions, duplicate contact candidates, manual correction, and search projection refresh.

Firecrawl Evidence:

- Use Firecrawl if fuzzy matching, trigram ranking, contact dedupe patterns, or audit-safe merge workflows are uncertain.

Exit Criteria:

- Documents can be linked to contacts with evidence and confidence.
- Ambiguous matches become suggestions, not silent accepted links.
- Contact links feed filing and search enrichment.

## 6.3 Folder ACL And Organization Guardrails

Goal: make automation honor the folder/document ACL model before watched folders or rules can apply changes.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 6 required folder ACL schema.
- `pro-merged-master-v1.2/contracts/schemas/folder_acl.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, Folder and FolderWrite schemas.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `folder_acl`, `documents.acl_mode`, and `folders.acl_mode`.
- `apps/api/structura_api/dependencies.py`.
- Phase 2 folder/tag implementation files.

Work:

- Confirm or implement folder ACL helper checks for read, write, and admin permissions.
- Ensure folder list, document organization update, rule application, smart folders, and watched-folder target folder assignment all call the same ACL helper.
- Validate folder ACL schema instances where persisted or exchanged.
- Prevent rules from adding a document to a folder the actor/service principal cannot write.
- Add audit events for ACL changes and automation attempts denied by ACL.
- Add tests for private, household, custom, cross-household, missing ACL, read-only folder, rule target denial, and watched-folder target denial.

Firecrawl Evidence:

- Use Firecrawl if authorization policy patterns, SQL ACL modeling, OpenAPI schema validation, or CSRF/security conventions are uncertain.

Exit Criteria:

- Phase 6 automation cannot bypass folder ACLs.
- Denied automation is observable and auditable.
- Folder ACL behavior is tested.

## 6.4 Watched-Folder API, Policy, And Service Registration

Goal: make watched-folder configuration explicit before file monitoring begins.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, watched-folder tasks.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`, watched-folder intake and safeguards.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `/api/v1/watched-folders`, `WatchedFolder`, and `WatchedFolderWrite`.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `watched_folders`.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`.
- `pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv`.
- `compose.yaml`.

Work:

- Implement watched-folder list and create-or-update APIs with CSRF on mutation.
- Validate path policy: absolute paths only where allowed, no path traversal, no Structura output/cache/export/backup/repo/config/log/model directories, and no recursive ingestion of app-managed directories.
- Store policy JSON for enabled state, processed-file behavior, stability delay, allowed extensions, target folder/tags, and recursive/non-recursive mode.
- Add service-health registration for the watcher service.
- Add Compose profile/service if a dedicated watcher worker is selected.
- Add tests for API create/list, invalid paths, denied managed paths, duplicate path per household, disabled watcher, and policy defaults.

Firecrawl Evidence:

- Use Firecrawl if path canonicalization, symlink handling, filesystem watcher APIs, OS-specific path behavior, or Compose service health conventions are uncertain.

Exit Criteria:

- Watched folders are configurable and safe by policy.
- App output directories cannot be watched.
- Watcher runtime is visible in service health.

## 6.5 Watched-Folder Worker And PDF-Only Intake

Goal: implement safe PDF-only watched-folder ingestion through the existing ingest pipeline.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, watched-folder service tasks.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`, watcher safeguards.
- `pro-merged-master-v1.2/database/010_types_and_enums.sql`, `ingestion_source_enum`.
- `contracts/events/ingest_document_job.v1.schema.json`.
- `lib/jobs/service.py`.
- `workers/ingest/`.
- `workers/placeholder.py`.
- `lib/storage/`.
- `compose.yaml`.

Work:

- Implement a watcher loop that reads enabled watched-folder configs and scans or subscribes to filesystem events.
- Accept PDF files only for the first Phase 6 implementation; reject non-PDF files with an ingest log/audit entry.
- Ignore partial files until stable by size and mtime over a configurable delay.
- Compute file hash before enqueueing ingest and suppress duplicates by hash.
- Move or link files into staging according to policy, then create an ingest job with `ingestion_source` set to `watched_folder` and source path metadata.
- Support processed-file policy: leave in place, move to `processed/`, or move to `failed/` where allowed.
- Implement pause/resume by honoring the `enabled` flag and safe shutdown.
- Add tests for stable-file detection, partial-file ignore, PDF allowlist, non-PDF rejection, duplicate hash, source path recording, processed/failed policy, no-recursion guard, and job creation.

Firecrawl Evidence:

- Use Firecrawl for file watching libraries, cross-platform file stability checks, atomic rename behavior, MIME sniffing, symlink safety, or Python filesystem APIs when uncertain.

Exit Criteria:

- PDF watched-folder ingest creates normal ingest jobs.
- Partial and duplicate files are handled safely.
- App-managed directories are never recursively ingested.

## 6.6 Filing Rule Schema, Validation, And Storage

Goal: persist inspectable filing rules with strict condition/action validation.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, filing rule tasks.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`, Filing rules and Rule safety.
- `pro-merged-master-v1.2/contracts/schemas/filing_rule.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `/api/v1/filing-rules`, `FilingRule`, and `FilingRuleWrite`.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `filing_rules` and `filing_rule_runs`.
- `apps/api/structura_api/routes_documents.py`.

Work:

- Implement filing rule list and create-or-update APIs with CSRF on mutation.
- Validate rule JSON against `filing_rule.v1.schema.json` and the OpenAPI schema.
- Define allowed condition fields from accepted document metadata and canonical facts: document family, subtype, counterparty/contact, tags, folders, dates, amounts, review status, sensitivity, text/search matches, and selected canonical field paths.
- Define allowed actions: add folder, set primary folder, add tag, set sensitivity, create review task, and set document type where policy allows.
- Store `conditions_json`, `actions_json`, priority, enabled state, `review_required`, created_by, and last-run metadata.
- Add tests for schema validation, unknown condition fields, unknown actions, priority ordering, disabled rules, CSRF, cross-household denial, and contract response shape.

Firecrawl Evidence:

- Use Firecrawl if JSON Schema draft behavior, Pydantic validation, rule-engine conventions, or OpenAPI representation of arbitrary condition/action objects is uncertain.

Exit Criteria:

- Filing rules are persisted and contract-valid.
- Invalid or unsafe rules are rejected.
- Rules are inspectable before execution.

## 6.7 Filing Rule Dry-Run Engine And Explanations

Goal: evaluate rules without mutating documents and show exactly why each rule matched or did not match.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, rule dry-run and explanation tasks.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`, dry-run output and Rule safety.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, machine uncertainty and auditability.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `filing_rule_runs`.
- Phase 4 canonical fact services.
- Phase 5 search/query services where text/search conditions are used.

Work:

- Implement a deterministic rule evaluation engine with condition operators `eq`, `neq`, `contains`, `in`, `gte`, `lte`, `exists`, and `regex`.
- Evaluate against a normalized document context built from document metadata, folders/tags, contacts, canonical facts, review state, and optional search text.
- Produce explanation JSON with per-condition result, observed value, expected value, matched evidence/source, proposed actions, blocked actions, and safety classification.
- Persist dry-run rows in `filing_rule_runs` with mode `dry_run`.
- Add a contract reconciliation step for exposing dry-run. If adding `POST /api/v1/filing-rules/{ruleId}/dry-run` or equivalent, update OpenAPI and implementation together.
- Add tests for all operators, missing fields, regex safety, canonical fact lookup, contact lookup, proposed actions, blocked ACL actions, explanation shape, and no mutations.

Firecrawl Evidence:

- Use Firecrawl if regex safety, rule-engine design, ReDoS mitigation, explanation UX conventions, or OpenAPI action endpoint design is uncertain.

Exit Criteria:

- Rules can be dry-run safely.
- Every match has a useful explanation.
- Dry-run does not mutate documents.

## 6.8 Rule Suggestions In Inbox And Review

Goal: turn rule matches into reviewable suggestions where automation should not silently apply changes.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, rule suggestions in Inbox/Review.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`, high-stakes safety.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, suggested/unresolved/review-required states.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, organization and review stories.
- `database/020_core_tables.sql`, `review_tasks` and `review_events`.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `filing_rule_runs`.
- Phase 4 review task APIs.

Work:

- Run enabled rules in suggestion mode after classification/extraction/review correction and after watched-folder ingest.
- Create suggestions for folder/tag/sensitivity/type actions when `review_required` is true or when document family/sensitivity is high-stakes.
- Represent suggestions as review tasks, review events, or a contract-extended suggestion endpoint; resolve the contract before coding.
- Include rule name, priority, conditions matched, proposed actions, explanation, and safety reason.
- Add accept/reject/defer behavior through review actions or a contract-extended automation action endpoint.
- Add tests for suggested folder, suggested tag, suggested sensitivity, high-stakes default-to-review, disabled rule ignored, duplicate suggestions suppressed, accept/reject audit, and Inbox/Review visibility.

Firecrawl Evidence:

- Use Firecrawl if workflow/audit conventions, REST action semantics, CSRF handling, or UI accessibility for suggestion panels is uncertain.

Exit Criteria:

- Rule suggestions appear where users already review documents.
- High-stakes documents are not silently finalized.
- Accept/reject decisions are auditable.

## 6.9 Rule Application, Audit, And Projection Refresh

Goal: safely apply approved rule actions and keep organization/search state consistent.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, filing rules with audit.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`, audit applied actions.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, audit and organization requirements.
- `database/020_core_tables.sql`, folders/tags/audit/review tables.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `filing_rule_runs`.
- Phase 2 document organization services.
- Phase 5 search projection refresh services.

Work:

- Apply approved actions through the same service paths used by manual organization, not ad hoc SQL.
- Enforce ACL, CSRF, household, and high-stakes safety checks immediately before mutation.
- Persist `filing_rule_runs` with mode `apply`, matched status, proposed actions, applied actions, blocked actions, and explanation.
- Write audit events and review events for each user-visible change.
- Refresh search projections and smart folder state after folder/tag/contact/canonical organization changes.
- Ensure application is idempotent: repeated approval does not duplicate folders, tags, memberships, review tasks, or audit side effects.
- Add tests for apply folder, set primary folder, add tag, set sensitivity, create review task, set document type where allowed, ACL denial, high-stakes denial, idempotency, audit rows, and search projection refresh.

Firecrawl Evidence:

- Use Firecrawl if transaction isolation, audit-event design, idempotency patterns, SQL upsert behavior, or CSRF/security conventions are uncertain.

Exit Criteria:

- Rule application is safe, idempotent, and auditable.
- Manual and automated filing share behavior.
- Search/smart-folder surfaces update after rule application.

## 6.10 Contacts Merge And Dedupe Tools

Goal: let users clean up duplicate contacts without losing document-contact history.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, contacts task list.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`, suggested merge/dedupe tasks and implementation order.
- `database/025_baseline_identity_acl_candidate_rules.sql`, contacts, aliases, document_contacts.
- `contracts/api/openapi.yaml`, contact schemas.
- Phase 4 review task APIs.

Work:

- Detect likely duplicate contacts from normalized name, aliases, identifiers, address, and document co-occurrence.
- Generate reviewable merge suggestions, not automatic merges.
- If merge endpoint is added, update OpenAPI and implementation together.
- Merge aliases, identifiers, document links, and metadata in a way that preserves audit history and prevents orphaned rows.
- Add undo/review visibility where practical by recording merge decisions and old/new contact IDs.
- Add tests for duplicate suggestion, merge preview, merge apply, alias transfer, document contact transfer, conflict handling, cross-household denial, and audit/history preservation.

Firecrawl Evidence:

- Use Firecrawl if dedupe scoring, entity merge UX, SQL merge transactions, or audit-safe merge patterns are uncertain.

Exit Criteria:

- Duplicate contacts can be reviewed and merged safely.
- Contact history and document links are preserved.
- Merge behavior is auditable.

## 6.11 Phase 6 UI Surfaces

Goal: make contacts, rules, watched folders, and suggestions usable without turning the app into a developer console.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 6 UI tasks.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `pro-merged-master-v1.2/design-language-v1.3.html`.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`, UI surfaces.
- `contracts/api/openapi.yaml`, contacts, filing rules, watched folders, and review task schemas.
- `apps/web/src/App.tsx`.
- `apps/web/src/styles.css`.

Work:

- Add Contacts page: searchable contact list, contact detail, aliases, identifiers, linked documents, and duplicate suggestions.
- Add Rules page: rule list, create/edit form, enabled state, priority, conditions/actions editor, last-run summary, and dry-run access.
- Add Rule dry-run modal/panel: matched documents, proposed actions, blocked actions, and per-condition explanations.
- Add Watch-folder settings: path, enabled state, policy, last scan, accepted/rejected counts, errors, and pause/resume.
- Add suggested filing explanation panel in Inbox/Review, with accept/reject/defer and source rule explanation.
- Add import status page or section for watched-folder and CLI bulk imports.
- Keep selected document context stable when accepting suggestions or changing rules.
- Add Playwright tests for contact search/detail, rule create/edit, dry-run explanation, suggestion accept/reject, watched-folder settings, import status, keyboard/focus flow, no-result states, and responsive layout.

Firecrawl Evidence:

- Use Firecrawl for uncertain React/Vite patterns, WAI-ARIA table/dialog/form/listbox behavior, rule-builder accessibility, path input UX, or Playwright locator conventions.

Exit Criteria:

- Contacts, rules, watcher settings, and suggestions are usable.
- Rule explanations are visible before application.
- The UI remains a calm evidence workbench.

## 6.12 CLI Import And Maintenance Commands

Goal: provide safe local operator commands for bulk import and maintenance without bypassing application invariants.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, CLI task list.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`, CLI and import.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md` if present in current context from prior phases.
- `pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv`.
- `contracts/events/ingest_document_job.v1.schema.json`.
- `lib/jobs/service.py`.
- `scripts/`.
- `Makefile`.

Work:

- Add CLI commands for bulk import, dry-run import, reprocess document, rebuild search projection, run evaluation set, and backup/restore checks.
- Use existing API token or local admin auth path; do not add an unauthenticated privileged backdoor.
- For bulk import, default to dry-run first and PDF-only unless explicitly configured otherwise.
- For reprocess and rebuild search, enqueue normal jobs rather than mutating downstream tables directly.
- For evaluation, reuse Phase 5 benchmark/evaluation hooks where possible.
- For backup/restore checks, perform non-destructive validation and status reporting; leave full restore implementation to Phase 10 unless an existing script already supports it.
- Add tests for CLI parsing, dry-run output, safe path validation, job creation, auth failure, no raw path leakage in logs, and non-destructive backup/restore checks.

Firecrawl Evidence:

- Use Firecrawl if Python CLI framework behavior, terminal output conventions, backup command safety, path validation, or API-token auth conventions are uncertain.

Exit Criteria:

- Operators can bulk import and run maintenance safely.
- CLI commands use normal job/audit paths.
- Destructive or high-impact actions require explicit confirmation or remain dry-run.

## 6.13 Integration, Security, And Runtime Coverage

Goal: prove Phase 6 works with the existing ingest, filing, review, and search workflows.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 6 gate.
- `STRUCTURA_PHASE_1_IMPLEMENTATION_PLAN.md`, upload/asset guarantees.
- `STRUCTURA_PHASE_2_IMPLEMENTATION_PLAN.md`, manual filing and ACL.
- `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md`, review tasks and canonical facts.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, search projection and smart folders.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`.
- `pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv`.
- `tests/`.
- `compose.yaml`.

Work:

- Add end-to-end tests for watched-folder PDF -> ingest job -> document -> parse/extraction/search -> filing suggestion.
- Add integration tests for contact creation -> document contact link -> rule condition match -> suggestion -> accepted action -> audit -> search projection refresh.
- Add security tests for CSRF on all browser mutations, API-token watched-folder/CLI flows, folder ACL denial, cross-household denial, path traversal denial, symlink denial where applicable, and managed-directory watch denial.
- Add runtime tests for watcher pause/resume, service health, worker shutdown, duplicate suppression, and failed-file handling.
- Add logging checks to ensure source paths are bounded/safe and raw document text is not emitted.
- Add no-regression tests for Phase 2 manual filing, Phase 4 review actions, and Phase 5 search after automation changes.

Firecrawl Evidence:

- Use Firecrawl if filesystem security, symlink race handling, test harness behavior, Compose health checks, or API-token service-auth conventions are uncertain.

Exit Criteria:

- Phase 6 works end to end.
- Security boundaries remain intact.
- Prior filing, review, and search behavior does not regress.

## 6.14 Contract, Static Analysis, Runtime, UI, And Phase 6 Gate

Goal: prove transparent organization automation is stable before moving into relationship/timeline work.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 6 gate.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `Makefile`.
- `pyproject.toml`.
- `package.json`.
- `apps/web/package.json`.
- `tests/`.
- `compose.yaml`.

Work:

- Run formatting and lint checks.
- Run mypy/pyright/SAST checks using the repo targets.
- Run OpenAPI/schema contract validation, including `filing_rule.v1.schema.json` and `folder_acl.v1.schema.json`.
- Run backend unit and integration tests.
- Run watched-folder worker tests, filing rule engine tests, contact service tests, ACL tests, CLI tests, audit tests, and search projection refresh tests.
- Run web build.
- Run Playwright UI workflow and screenshot validation for Contacts, Rules, Watch-folder settings, Rule dry-run modal, suggested filing panel, and Import status surfaces.
- Run local Compose smoke where practical: API health, worker health, upload/list/detail, filing, parse, extraction/review, search, contact CRUD, watched-folder config, watcher health, PDF watcher import, rule dry-run, rule suggestion, rule application, and CLI dry-run.
- Confirm Phase 6 gate from `STRUCTURA_IMPLEMENTATION_PLAN.md`: folder/tag filing workflow and rule suggestions are usable and auditable.
- Document intentional deferrals: relationship graph/timeline UX, deadlines/reminders, missing companion document suggestions, email import, non-PDF watched-folder ingest, destructive restore, production-scale dedupe, and advanced policy automation.

Firecrawl Evidence:

- If a gate fails due to tool behavior, dependency behavior, browser/API semantics, SQL behavior, JSON Schema behavior, filesystem behavior, CLI behavior, or security convention that is not locally obvious, use Firecrawl to find primary-source evidence before changing code.

Exit Criteria:

- Contacts improve filing and search enrichment.
- Rules explain why they matched.
- Watched-folder intake is safe and observable.
- High-stakes documents default to suggestions or review.
- Filing workflow and rule suggestions are usable and auditable.

## Stop Point

Stop after Phase 6 gate validation and report:

- Files changed.
- Tests and checks run.
- Contract extensions or deferrals.
- Watched-folder safety decisions.
- CLI commands added.
- Any deferred work and the phase it belongs to.
- Any Firecrawl-sourced evidence that materially shaped implementation decisions.

Do not continue into Phase 7 without explicit user instruction.
