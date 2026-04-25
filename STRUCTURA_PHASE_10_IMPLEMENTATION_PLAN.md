# Structura Phase 10 Implementation Plan

Phase 10 makes Structura safe for daily private archive use. It finishes export workflows, hardens authentication and access control, adds operational backup and restore procedures, and makes admin visibility strong enough for a self-hosted sensitive document system.

This plan expands Phase 10 from `STRUCTURA_IMPLEMENTATION_PLAN.md`. It does not replace the root plan. Use the root plan for phase boundaries and this document for Phase 10 execution detail.

## Operating Rules

- Do not inspect or rely on anything under `archive/`.
- Before coding any subphase, re-read the files listed in that subphase's **Fresh Context** section. Use `wc -l` and bounded `sed -n` chunks for large files so full reads are auditable.
- When an artifact exists in both Markdown and DOCX form, read the Markdown artifact by default. Only inspect DOCX when the user explicitly asks for layout/fidelity review or the Markdown file is missing/incomplete.
- Keep generated FastAPI OpenAPI paths aligned with `contracts/api/openapi.yaml`. If implementation and contract differ, stop and resolve the contract question explicitly.
- Preserve Phase 1-9 invariants: original bytes are immutable, canonical facts remain the default read model, evidence is required for trusted facts, model outputs and analysis notes are derivatives, exports are explicit and audited, search indexes are assistive, browser-mutating routes require CSRF, and access control is enforced before returning document-derived content.
- Do not expose raw object-store URIs to the browser, export manifests, logs, errors, job payloads, or admin views.
- Do not log raw full document text, model prompts, model responses, export contents, secrets, API tokens, passkey material, object paths, or presigned URLs.
- Treat export bundles as derived artifacts with provenance and audit, not as a second source of truth.
- Keep Phase 10 focused on exports, auth hardening, API token lifecycle, folder ACL management, backup/restore, admin jobs, service health, storage/model/extraction stats, operational QA, and the Phase 10 gate. Do not add new ingestion channels, new analysis features, multi-tenant SaaS behavior, or hard-delete workflows unless explicitly approved.

## Firecrawl Evidence Rule

When APIs, external contracts, library behavior, security conventions, OpenAPI semantics, FastAPI/Pydantic behavior, WebAuthn/passkey flows, API-token handling, session cookie behavior, CSRF behavior, PostgreSQL backup/restore, Docker Compose operations, ZFS snapshots/replication, archive formats, CSV/JSON export conventions, cryptographic hashing, browser security, React/Vite behavior, Playwright behavior, or accessibility conventions are in play, search online with Firecrawl if there is any uncertainty.

Use primary sources where possible: official framework documentation, standards documents, official package docs, project repositories, security guidance, OS/ZFS/Postgres docs, WebAuthn specs/libraries, or vendor docs. Save Firecrawl outputs under `.firecrawl/`, read them incrementally, and summarize the evidence in implementation notes or ADRs when it affects a decision. Do not use unsourced memory to settle uncertain API, schema, auth, backup, restore, database, browser, worker, or security behavior.

## Phase 10 Required Artifact Set

The full Phase 10 artifact list from `STRUCTURA_IMPLEMENTATION_PLAN.md` remains required context:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/09_Deployment_and_Runtime_Architecture.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/15_PGMQ_and_Worker_Strategy.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/folder_acl.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/create_datasets.sh
```

The duplicate DOCX entries in the root plan are intentionally omitted here under the current repo guidance.

## 10.0 Baseline Reconciliation And Contract Gap Review

Goal: confirm the Phase 10 baseline and resolve public API gaps before implementing exports, auth hardening, ACL administration, or operations.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 10 section.
- `STRUCTURA_PLAN_INDEX.md`, stop rules and source alignment.
- `STRUCTURA_PHASE_1_IMPLEMENTATION_PLAN.md`, object storage and protected assets.
- `STRUCTURA_PHASE_2_IMPLEMENTATION_PLAN.md`, folders, tags, organization, ACL, and audit commitments.
- `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md`, canonical facts, review, and evidence commitments.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, search/facet/filter commitments.
- `STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md`, analysis note separation and disabled-mode commitments.
- `agents.md`.
- `.wolf/cerebrum.md`.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`.
- `pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md`.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`.
- Active `contracts/api/openapi.yaml`.
- Active `database/020_core_tables.sql`.
- Active `database/025_baseline_identity_acl_candidate_rules.sql`.
- `compose.yaml`.
- `README.md`.

Work:

- Inventory the active baseline: `POST /api/v1/exports` placeholder, `job_type = export`, `asset_role = export_bundle`, export object root, `pipeline_jobs`, `audit_events`, `service_health_snapshots`, admin job list/retry, sessions, magic links, WebAuthn credential table, API token table, folder ACL table, and protected asset serving.
- Identify API gaps before coding:
  - WebAuthn/passkey registration and authentication routes are not currently explicit in OpenAPI.
  - API token list/create/revoke routes are not currently explicit in OpenAPI.
  - folder ACL management routes are not currently explicit beyond folder `aclMode`.
  - export download/list/status routes are not currently explicit beyond `POST /api/v1/exports` and generic job status.
  - backup/restore/admin storage/model/stat endpoints may need contract extensions.
- Decide which Phase 10 features are API contract extensions versus internal admin procedures. Update OpenAPI, DTOs, route parity tests, and implementation together for each public extension.
- Confirm that default access remains local-first and non-public-internet. Any exposure hardening should match LAN/VPN/Tailscale assumptions, not SaaS multi-tenancy.
- Confirm Phase 10 does not introduce hard-delete or redaction bundle behavior beyond the requested export types unless the user explicitly approves it.

Firecrawl Evidence:

- Use Firecrawl if OpenAPI extension strategy, WebAuthn route design, API token security, backup admin surface conventions, or ZFS/Postgres operational assumptions are uncertain.

Exit Criteria:

- Phase 10 public contract gaps are documented.
- Contract changes are planned before implementation.
- The hardening plan matches local-first private archive assumptions.

## 10.1 Export Contract, Data Model, And Job Lifecycle

Goal: define export request, job, result, manifest, storage, authorization, and download behavior before writing bundle code.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, export tasks.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, export and sharing requirements.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, canonical facts and export storage normalization.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `/api/v1/exports` and `ExportRequest`.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, `document_assets`, `pipeline_jobs`, `audit_events`, and canonical/extraction tables.
- `database/010_types_and_enums.sql`, `asset_role = export_bundle` and `job_type = export`.
- `lib/config/settings.py`, `export_objects_root`.
- `apps/api/structura_api/routes_documents.py`, current export placeholder.
- `lib/jobs/service.py`.

Work:

- Define export DTOs for `ExportRequest`, `ExportAccepted`, `ExportManifest`, `ExportFileEntry`, `ExportProvenance`, and safe job result metadata.
- Keep supported export types aligned with OpenAPI: `originals`, `originals_plus_json`, `originals_plus_csv`, and `review_report`.
- Decide whether `POST /api/v1/exports` plus `GET /api/v1/jobs/{jobId}` is sufficient, or whether a documented export download/status endpoint is required. If so, update OpenAPI and route parity tests before implementation.
- Define export storage under `/srv/structura/objects/exports/<export-id>/...` with no direct filesystem paths exposed in API responses or manifests.
- Define idempotency, retry, expiration/retention, lifecycle cleanup, and replacement behavior for export jobs.
- Decide whether export bundles are represented only as `document_assets` with `asset_role = export_bundle`, or whether a dedicated `exports` table is needed for request scope, retention, and manifest state. Add a scoped migration only if necessary.
- Add tests for request validation, unsupported type rejection, job payload safety, idempotency, manifest shape, retention metadata, and OpenAPI parity.

Firecrawl Evidence:

- Use Firecrawl if export API design, archive retention conventions, ZIP/TAR behavior, content hashing, or FastAPI streaming/download patterns are uncertain.

Exit Criteria:

- Export contracts and lifecycle behavior are explicit.
- Export jobs can be tracked without leaking content or object-store paths.
- Any contract extension is documented before implementation.

## 10.2 Export Bundle Builder

Goal: generate the required export bundle types with deterministic structure and provenance.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, export type list.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, export bundle expectations.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, export bundle QA checklist.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, canonical accepted facts as export read model.
- `database/020_core_tables.sql`, document assets, pages, extractions, document fields, line items, amounts, deadlines, relationships, review events, and analysis notes.
- `database/025_baseline_identity_acl_candidate_rules.sql`, canonical fields, canonical line items, household/ACL, contacts, evaluation, and service health.
- Active object storage service from Phase 1.

Work:

- Implement an export worker/service that claims `export` jobs and writes bundles into the export object root.
- For `originals`, include only authorized original assets plus manifest.
- For `originals_plus_json`, include originals, accepted canonical facts, selected normalized extraction JSON, evidence references, relationships, deadlines, tags/folders, and manifest.
- For `originals_plus_csv`, include originals plus CSV/JSONL projections from canonical fields, canonical line items, amounts, deadlines, contacts, folders, tags, and relationships.
- For `review_report`, include review tasks/events, canonical fact history, candidate summary, evidence references, and enough source identifiers for audit without dumping raw model output by default.
- Keep raw model output, analysis notes, hidden documents, and highly sensitive excerpts out unless a documented export type or explicit option allows them.
- Create deterministic filenames, stable IDs, hashes, MIME types, byte counts, and bundle-level manifest metadata.
- Add tests for each export type, deterministic filenames, CSV quoting, JSON schema shape, missing asset handling, retry/idempotency, large bundle behavior, and no raw object paths.

Firecrawl Evidence:

- Use Firecrawl if CSV escaping, archive format safety, zip-slip prevention, Python archive APIs, or manifest/provenance conventions are uncertain.

Exit Criteria:

- All required export types generate valid bundles.
- Bundle contents come from authorized source documents and canonical accepted data.
- Export files are deterministic enough to test and audit.

## 10.3 Export Authorization, Manifest Provenance, Download, And Audit

Goal: make export actions explicit, authorized, provenance-backed, and auditable.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, manifest/provenance and export audit tasks.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, export audit and privacy requirements.
- `pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md`, sensitivity interaction and export warnings.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, exports, jobs, and protected assets.
- `database/025_baseline_identity_acl_candidate_rules.sql`, household, folder ACL, document ACL mode, API tokens, and audit events.
- Phase 1 protected asset route implementation.
- Phase 2 ACL implementation.
- Phase 5 search ACL implementation.

Work:

- Authorize every selected document before export generation. Do not leak missing or hidden documents through counts, filenames, errors, or manifest entries.
- Apply sensitivity policy: `medical`, `financial`, `legal`, `pii`, and `highly_sensitive` documents should produce explicit export warnings or require confirmation when current product policy says so.
- Include manifest provenance: export id, type, created timestamp, actor, document ids, asset ids, hashes, canonical fact versions, schema versions, evidence refs, app version/commit where available, and tool versions.
- Store safe export bundle asset metadata and make download available through an authorized API route if contract-approved.
- Audit export requested, export completed, export failed, export downloaded, and export deleted/expired events where applicable.
- Add tests for cross-household denial, folder ACL denial, sensitivity warnings, manifest provenance, audit events, authorized download, expired/missing bundle behavior, and no object URI exposure.

Firecrawl Evidence:

- Use Firecrawl if audit event modeling, privacy export warnings, secure download patterns, or manifest provenance conventions are uncertain.

Exit Criteria:

- Exports cannot bypass document/folder ACL.
- Export actions are auditable.
- Manifest provenance is complete and safe.

## 10.4 Passkey/WebAuthn Hardening And Recovery

Goal: add strong browser authentication for non-local exposure while preserving bootstrap/admin recovery safety.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, passkey/WebAuthn hardening task.
- `pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md`, auth policy and implementation order.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, session handling and secret requirements.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, auth/session surfaces and `authMethod = webauthn`.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `webauthn_credentials`, `magic_links`, `sessions`, and password credentials.
- Active auth service, routes, settings, cookies, CSRF, bootstrap admin, and magic-link implementation.

Work:

- Select a WebAuthn/passkey library and route flow using Firecrawl evidence from primary docs before coding.
- Add contract-backed routes for passkey registration challenge, registration verification, authentication challenge, authentication verification, credential list, credential rename, and credential revoke if public API routes are needed.
- Persist credential id, public key, sign count, transports, label, last used timestamp, and user association safely.
- Ensure WebAuthn-created sessions persist `auth_method = webauthn` and set the same secure session/CSRF cookie pair as other browser sessions.
- Add settings for relying party id/name, allowed origins, challenge TTL, user verification policy, and local-development behavior.
- Preserve bootstrap password and magic-link recovery, but add surfaces to rotate/disable bootstrap password where policy allows.
- Add audit events for credential creation, use, revoke, failed verification, recovery link issuance/use, and bootstrap credential rotation.
- Add tests for challenge lifecycle, origin/rp validation, replay prevention, sign counter handling, revoked credential denial, session creation, CSRF, cookie settings, recovery flows, and route parity.

Firecrawl Evidence:

- Use Firecrawl for WebAuthn specs/library docs, browser passkey behavior, FastAPI integration patterns, secure challenge storage, and cookie/security conventions.

Exit Criteria:

- Passkey enrollment and sign-in work under documented local/VPN exposure assumptions.
- Recovery paths remain explicit and auditable.
- Password-only bootstrap can be hardened without locking out the admin.

## 10.5 Session Timeout, Rotation, Revoke-All, And Cookie Hardening

Goal: make browser sessions manageable and aligned with the intended exposure model.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, session timeout, rotation, and revoke-all task.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, session/cookie requirements.
- `pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md`, session policy.
- Active `lib/auth/service.py`.
- Active `apps/api/structura_api/routes_auth.py`.
- Active `lib/config/settings.py`.
- Active OpenAPI auth/session contract.

Work:

- Implement configurable absolute session TTL, optional idle timeout, last-used update throttling, and session rotation after sign-in or privilege/security changes.
- Add revoke-current and revoke-all behavior. If revoke-all needs a public endpoint, update OpenAPI and route parity tests.
- Ensure cookie flags match settings: HttpOnly session cookie, non-HttpOnly CSRF cookie, SameSite=Lax by default, Secure under TLS deployment, narrow path/domain, and explicit expiry.
- Add UI/settings surfaces for active sessions if within Phase 10 scope and contract-approved.
- Audit sign-in, logout, revoke-all, session expiry, rotation, and suspicious session failures where practical.
- Add tests for expiry, idle timeout, last-used updates, revoked session denial, revoke-all, cookie flags, CSRF pairing, API-token non-cookie behavior, and contract parity.

Firecrawl Evidence:

- Use Firecrawl if session rotation, SameSite/Secure cookie behavior, CSRF design, or FastAPI response-cookie behavior is uncertain.

Exit Criteria:

- Session behavior is explicit, configurable, and tested.
- Users/admins can revoke access safely.
- Cookie handling matches the intended exposure model.

## 10.6 API Token Lifecycle UI And Service

Goal: allow scoped automation tokens for CLI, watched-folder, and admin flows without exposing token secrets after creation.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, API token lifecycle UI task.
- `pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md`, API token policy.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `api_tokens`.
- Active API-token principal resolution in auth service.
- Active protected route dependencies.
- OpenAPI contract security scheme for `X-API-Token`.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`, if UI surfaces are implemented.

Work:

- Define token scopes for current automation/admin needs. Keep scope names stable, narrow, and contract-documented.
- Add contract-backed routes to list token metadata, create a token, revoke a token, and optionally rotate a token. The raw token secret should be returned only once on creation.
- Hash tokens before storage. Never log raw tokens or return token hashes.
- Track label, scopes, owner, household, created time, last used time, expiry, and revoked time.
- Add settings and UI for token expiry defaults, max lifetime, creation warnings, and revoke confirmations.
- Audit token creation, revoke, failed token auth, and token use for privileged/admin actions.
- Add tests for one-time secret display, hashing, scope enforcement, expiry, revoke, last-used update, admin-only routes, UI flows, and log redaction.

Firecrawl Evidence:

- Use Firecrawl if token format, hashing/KDF choices, one-time secret UX, scope naming, or API-token security conventions are uncertain.

Exit Criteria:

- API tokens are manageable without database access.
- Token secrets are protected.
- Scoped automation can be audited.

## 10.7 Folder ACL Management And Authorization Regression

Goal: make folder ACLs usable, enforceable, and visible enough for sensitive archives.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, folder ACL management task.
- `pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md`, folder ACL and sensitivity behavior.
- `pro-merged-master-v1.2/contracts/schemas/folder_acl.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, folder and organization schemas.
- `database/025_baseline_identity_acl_candidate_rules.sql`, folder ACL table, document household/owner/primary folder/ACL mode.
- Phase 2 folder/tag implementation.
- Phase 5 search ACL/filter implementation.
- Phase 9 analysis ACL/sensitivity implementation.

Work:

- Define folder ACL service semantics for `private`, `household`, and `custom`.
- Implement folder ACL management routes and DTOs if not already contract-covered. Update OpenAPI and route parity tests for public API changes.
- Validate `principal_type = user | household | role` and `permission = read | write | admin` against `folder_acl.v1`.
- Propagate ACL effects to document list/detail, asset serving, search, analysis, export, relationships, timelines, review queues, filing rules, and admin views.
- Define document inheritance from primary folder and sensitivity override behavior. Restricted documents should require explicit grant or owner/admin per policy.
- Audit ACL changes and failed access attempts where practical.
- Add regression tests for list/detail/assets/search/export/analysis/review across private, household, custom, owner/admin/member/viewer, primary-folder change, folder deletion, and hidden result suppression.

Firecrawl Evidence:

- Use Firecrawl if ACL API design, role-based access conventions, SQL authorization patterns, or privacy-preserving search result suppression behavior is uncertain.

Exit Criteria:

- Folder ACLs are manageable and enforced consistently.
- Sensitive routes remain protected.
- ACL regressions are covered across all document-derived surfaces.

## 10.8 Backup Procedures, Scripts, And Integrity Checks

Goal: implement documented, repeatable backups for DB, object storage, config, and repo state.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, backup procedure tasks.
- `pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md`.
- `pro-merged-master-v1.2/docs/09_Deployment_and_Runtime_Architecture.md`, upgrade strategy.
- `pro-merged-master-v1.2/infrastructure/zfs/README.md`.
- `pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv`.
- `pro-merged-master-v1.2/infrastructure/zfs/create_datasets.sh`.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, storage and backup requirements.
- Active `infrastructure/zfs/`.
- Active `compose.yaml`.
- Active `.env.example` and README.

Work:

- Add scripts or documented commands for logical Postgres backup, optional physical/snapshot strategy, object storage backup, config backup, repo checkout backup, and model cache reproducibility notes.
- Separate backup classes:
  - required: Postgres, canonical objects, derived objects, config, repo.
  - optional/policy-driven: logs, exports, observability.
  - excluded/rebuildable: cache, tmp, model cache where reproducible.
- Add object-store consistency checks that compare DB asset rows to filesystem objects and report missing/orphaned files without deleting by default.
- Add backup manifest/checksum generation for backup runs.
- Document snapshot schedules for ZFS datasets and note that `sync=disabled` is not acceptable for Postgres.
- Add dry-run mode for backup scripts and clear failure exit codes.
- Add tests for manifest generation, path safety, missing dataset handling, object consistency check, dry-run behavior, secret redaction, and backup command docs.

Firecrawl Evidence:

- Use Firecrawl if pg_dump/pg_restore behavior, ZFS snapshot/send/receive commands, checksum manifests, Docker volume backup conventions, or backup security guidance is uncertain.

Exit Criteria:

- Backup procedures cover DB, object storage, config, and repo.
- Integrity checks can identify broken DB/object references.
- Scripts are safe to dry-run and document their assumptions.

## 10.9 Restore Rehearsal And Disaster Recovery Runbook

Goal: prove backups are restorable before calling Phase 10 complete.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, restore rehearsal and Phase 10 gate.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, restore gate.
- `pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md`, snapshot policy.
- `pro-merged-master-v1.2/docs/09_Deployment_and_Runtime_Architecture.md`, upgrade and remote access strategy.
- `pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv`.
- Active migration scripts, Compose config, object storage implementation, and backup scripts.

Work:

- Write a restore runbook that starts from a clean target runtime root and restores Postgres, object roots, config, and repo state.
- Include separate paths for logical DB restore, ZFS snapshot restore/replication, and object-store copy restore if supported.
- Validate restored app behavior: migrations status, bootstrap/session behavior, document list, protected asset route, search index freshness/rebuild path, job ledger, export download, and admin health.
- Add a restore rehearsal script or checklist with operator prompts for destructive target actions.
- Record restore evidence in docs: date, backup source, target path, commands, validation outputs, known limitations, and cleanup.
- Do not run destructive restore over the active local dataset unless the user explicitly approves the target and command.

Firecrawl Evidence:

- Use Firecrawl if Postgres restore, ZFS receive/rollback, Docker Compose restore, or disaster recovery documentation conventions are uncertain.

Exit Criteria:

- Restore has been rehearsed on a non-production target.
- Rehearsal evidence is documented.
- Phase 10 gate can cite concrete restore proof.

## 10.10 Admin Jobs, Dead-Letter Retry, And Worker Operations

Goal: make job failures and retries visible and controllable for daily self-hosted operation.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, admin jobs and retry tasks.
- `pro-merged-master-v1.2/docs/15_PGMQ_and_Worker_Strategy.md`, dead-letter behavior and launch requirements.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, observability and failure handling.
- `contracts/api/openapi.yaml`, `/api/v1/jobs/{jobId}`, `/api/v1/admin/jobs`, and `/api/v1/admin/jobs/{jobId}/retry`.
- `lib/jobs/service.py`.
- `apps/api/structura_api/routes_jobs.py`.
- `workers/placeholder.py`.

Work:

- Expand admin job list fields enough for triage: job id, type, status, document link, queue, worker, attempt count, max attempts, scheduled/started/finished times, safe error class/message, retryability, next retry time, and correlation id.
- Keep queue messages and job payload summaries free of document text, raw model output, prompt bodies, and sensitive extracted fields.
- Ensure retry only applies to failed/dead-letter jobs and preserves canonical history/idempotency.
- Add suppress/dismiss behavior only if contract-approved; otherwise document it as a future extension.
- Add UI/admin surface if within current app scope, using quiet machine-health patterns from the design language.
- Add tests for list filters, retry CSRF, retry authorization, non-retryable denial, dead-letter recovery, redacted error payloads, stuck lease behavior, and PGMQ/Redis fallback semantics.

Firecrawl Evidence:

- Use Firecrawl if PGMQ behavior, job retry semantics, admin UI conventions, or worker lease recovery patterns are uncertain.

Exit Criteria:

- Admin can inspect and retry dead-letter jobs.
- Retry behavior is safe and auditable.
- Job/admin surfaces do not leak private content.

## 10.11 Service Health, Storage Usage, Model Health, And Extraction Failure Stats

Goal: provide operational visibility without turning admin surfaces into raw logs.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, admin stats tasks.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, observability requirements.
- `pro-merged-master-v1.2/docs/09_Deployment_and_Runtime_Architecture.md`, service responsibilities and GPU allocation.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `service_health_snapshots` and `evaluation_runs`.
- `apps/api/structura_api/routes_admin.py`.
- `compose.yaml`.

Work:

- Extend service health with latest status per service, queue depth by job type, oldest job age, success/failure counts, dead-letter counts, extraction validation failure counts, search/index freshness, model server latency/availability, and storage usage by artifact type.
- Add storage usage calculation for canonical objects, derived objects, export objects, backups, logs, models, cache, and Postgres where feasible.
- Add model health checks for qwen, granite, embed, and optional analysis model endpoints without sending document content.
- Add extraction failure stats by schema, document family, validator code, model route, and time window.
- Keep admin payloads summary-only and redacted. Detailed logs should remain local operator files, not default API responses.
- Add tests for service health shape, metrics aggregation, missing model endpoints, storage root missing, permission errors, redaction, and degraded status classification.

Firecrawl Evidence:

- Use Firecrawl if model health endpoints, filesystem usage APIs, Docker healthcheck behavior, Prometheus metric conventions, or privacy-safe observability design are uncertain.

Exit Criteria:

- Admin can see service, storage, model, and extraction health.
- Degraded states are visible and actionable.
- Health surfaces are safe to expose to authenticated admins.

## 10.12 Settings UI, Admin UI, And Design-Language Alignment

Goal: expose Phase 10 controls in calm workbench surfaces without making operational internals dominate document work.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 10 UI-related tasks.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`, UI workflow, Playwright, and stop rules.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, Settings/Exports/Admin navigation and design language.
- `pro-merged-master-v1.2/design-language-v1.3.html` if UI surface references are needed.
- Active web app shell and existing admin/status UI.

Work:

- Add or refine navigation for Exports, Settings, and Admin/status only if supported by Figma or artifact guidance.
- Implement export request/status/download UI, passkey settings, API token settings, folder permission management, session management, and admin health/jobs views as contract-backed surfaces.
- Use Figma MCP for any available handoff frames and stop if UI/UX ambiguity remains.
- Keep settings/admin views dense, legible, and quiet. Do not replace the workbench with a dashboard-first layout.
- Add Playwright tests for export creation, export status/download, API token create/revoke, session revoke-all, folder ACL edit, admin job retry, service health, storage usage, responsive behavior, keyboard focus, and no raw object paths in DOM/network responses.

Firecrawl Evidence:

- Use Firecrawl if accessibility patterns, WebAuthn browser UX, React/Vite behavior, Playwright testing, or settings/admin UI conventions are uncertain.

Exit Criteria:

- Phase 10 controls are usable through UI where appropriate.
- UI matches the calm evidence workbench design language.
- Workflow and accessibility checks pass.

## 10.13 Security, Privacy, And SAST Regression Pass

Goal: validate that Phase 10 hardening did not create new leaks, bypasses, or unsafe operational defaults.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 10 gate.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, security and privacy requirements.
- `pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md`, auth/ACL/audit requirements.
- Active `Makefile`, `pyproject.toml`, SAST targets, tests, and CI scripts.
- All Phase 10 changed files.

Work:

- Run formatting, lint, type checking, contract validation, event/schema validation, SAST tools, dependency/security checks if configured, tests, and web build.
- Add targeted security tests for CSRF, cookie flags, auth bypass, API token scope enforcement, passkey challenge replay, folder ACL enforcement, asset route authorization, export authorization, admin-only access, and redacted logs/errors.
- Add grep/static rules or tests that prevent raw object paths, token secrets, document text, export contents, model prompts, and model outputs from appearing in logs or API responses.
- Verify backup/restore scripts do not print secrets and protect config exports appropriately.
- Verify network/default configuration does not introduce public exposure, hidden cloud telemetry, or outbound document-content calls.

Firecrawl Evidence:

- Use Firecrawl if SAST tool configuration, WebAuthn threat handling, CSRF/cookie guidance, security-header defaults, or local network exposure conventions are uncertain.

Exit Criteria:

- Static and runtime security checks pass or blockers are documented.
- Sensitive routes remain protected.
- Phase 10 changes preserve local-first privacy.

## 10.14 Restore, Release Candidate, And Phase 10 Gate

Goal: close Phase 10 with restore proof, operational evidence, and full regression coverage.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 10 gate.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, RC/GA-like gates.
- `STRUCTURA_PHASE_10_IMPLEMENTATION_PLAN.md`, all subphase exit criteria.
- Active README, ADRs, runbooks, Makefile, Compose, scripts, tests, and validation commands.

Work:

- Run migration-from-scratch tests.
- Run backup and restore rehearsal on a non-production target and record evidence.
- Run golden corpus regression or the configured representative corpus suite.
- Run export E2E: originals, originals plus JSON, originals plus CSV, and review report.
- Run auth hardening E2E: passkey enrollment/sign-in, session timeout/rotation/revoke-all, API token create/revoke/scope, folder ACL edit/enforcement.
- Run admin E2E: service health, storage usage, model health, extraction failure stats, dead-letter retry.
- Run UI Playwright flows where UI changed.
- Update README/runbooks/ADR notes with final Phase 10 commands, limitations, exposure assumptions, backup/restore evidence, and release candidate checklist.
- Confirm the Phase 10 gate:
  - restore has been rehearsed;
  - auth hardening matches intended exposure;
  - sensitive routes remain protected;
  - admin can retry dead-letter jobs.
- Stop after Phase 10. Do not start any unplanned post-Phase-10 feature work without explicit user instruction.

Firecrawl Evidence:

- Use Firecrawl if restore validation, release candidate criteria, WebAuthn compatibility, backup tooling, or operations checklists are uncertain.

Exit Criteria:

- Phase 10 gate evidence is recorded.
- Full validation passes or blockers are clearly documented.
- Structura has a credible private-archive operations baseline.

## Stop Point

After Phase 10 is implemented and verified, stop and report:

- Files changed.
- Contracts or schema migrations added.
- Export, auth hardening, API token, folder ACL, backup, restore, and admin behavior implemented.
- Export manifest/provenance and audit behavior.
- Backup and restore rehearsal evidence.
- Security/SAST/runtime/UI validation commands and results.
- Known limitations and recommended next operational follow-up.

Do not continue into unplanned post-Phase-10 work until the user explicitly approves the next scope.
