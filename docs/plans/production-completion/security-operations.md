# Security, reliability and operations completion

Companion to the [master completion plan](../../../STRUCTURA_PRODUCTION_COMPLETION_PLAN.md). Its milestone order and phase gates control this workstream. All packages are planned until their evidence is recorded in the [closure register](closure-register.md).


Prepared 2026-09-07 for integration into the project-wide completion plan. This is an implementation and execution plan, not deployment authorization or evidence that these gates already pass. No files under `archive/` were consulted.

## Scope and sequencing

Use the root implementation plan for sequencing and the Phase 10, 11, and 12 plans for acceptance depth. The work below separates defects in existing features from later-phase features that have never been implemented. Authorization, job ownership, public error handling, and truthful health display are repairs to the current baseline and can proceed during remaining Phase 8.5 closure. Exports, account/ACL management, backup operations, and admin controls belong to Phase 10. Phase 11 validates the finished workflows; Phase 12 packages and signs off the same tested release. Do not let this operations track bypass the Phase 8.5 quality gate or introduce Phase 9 analysis early. Major Phase 10 implementation starts only after the Phase 9 gate, in the root plan order. Planning and design of that later work may occur now. An urgent baseline credential rotation or disabling an unsafe existing path is a narrow protective repair; it is not authorization to build the full Phase 10 account-management product early.

The ingestion model decision is fixed by [ADR 0008](../../adr/0008-qwen38-27b-ingestion.md), and [ADR 0009](../../adr/0009-qwen-native-document-parsing.md) sets Qwen-native parsing as the target: use the existing Qwen3.8-27B BF16 service on Oxcart with thin PDF/image handling and a versioned provider-neutral page/element/table/chunk contract. Preserve immutable originals, verified evidence, deterministic validators and human review. Native-extracted text and Qwen transcription carry different source/trust labels; copying Qwen text never establishes native-source or Docling verification. Docling is optional during migration/comparison, with historical evidence preserved; it is not a permanent parser or release prerequisite. The Blackbird RTX PRO 4000 is proposed for both ingestion/reindex and query embedding inference. Integration, quality, capacity and operational acceptance remain open. Phase 9 analysis remains optional and independently gated with a distinct job/prompt/workload profile, even if a later decision reuses that endpoint.

Dependencies:

```text
Current baseline + explicit access policy
  -> SEC-01 authorization repair
  -> JOB-01 job claim ownership -> JOB-02 worker recovery and fenced result persistence
  -> SEC-03 privacy-safe errors and truthful health

Phase 9 gate + SEC-01 -> SEC-02 account/session/token/ACL product surfaces
Phase 9 gate + SEC-01 + JOB-02 -> EXP-01 export service and UI
Phase 9 gate + storage contract + migration inventory
  -> OPS-01 backup artifact -> OPS-02 isolated full restore
Phase 9 gate + JOB-02 + SEC-03 -> OPS-03 deployment hardening + OPS-04 operations
SEC-02 + EXP-01 + OPS-02 + OPS-04 + approved model/runtime profile -> REL-01 Phase 10 gate
All product phases + REL-01 -> REL-02 Phase 11 RC -> REL-03 Phase 12 internal release
```

Independent development can run in parallel by ownership. Shared contract and migration changes receive an integration owner and explicit dependency ordering. Each package ends in a reviewable change with its own tests and evidence. There is no need to stop for permission for ordinary local edits, isolated tests, documentation, or planned reversible development. Deployments, migration of a real archive, publishing a release, destructive restore, and changing unrelated GPU services remain separate concrete operational actions; prepare the tested artifact, impact, and rollback first and use the authorization already present in the session when it covers the action.

Stable package index:

| ID | Deliverable | Phase placement |
| --- | --- | --- |
| SEC-01 | Enforced permission matrix and authorization repairs | Existing-feature repair during 8.5 |
| SEC-02 | Account, passkey, session, token, and ACL management | 10 after the 9 gate |
| SEC-03 | Safe public failures and truthful health | Existing-feature repair during 8.5 |
| JOB-01 | Claim identity, renewal, and lifecycle compare-and-set | Existing-feature repair during 8.5 |
| JOB-02 | Fenced domain publication and crash/retry recovery | Existing-feature repair during 8.5 |
| EXP-01 | Four audited export formats and user flows | 10 after the 9 gate |
| OPS-01 | Consistent backup artifacts, manifests, and retention | 10 after the 9 gate |
| OPS-02 | Isolated full-archive restore and recovery proof | 10, revalidated in 11 and 12 |
| OPS-03 | Reproducible deployment and safe runtime configuration | 10, finalized in 12 |
| OPS-04 | Metrics, admin operations, runbooks, and capacity evidence | 10, measured in 11 and 12 |
| REL-01 | Phase 10 integrated operations gate | 10 |
| REL-02 | Release candidate evidence pack | 11 |
| REL-03 | Frozen internal release, runbooks, and go/no-go | 12 |

## SEC-01 — Repair authorization across existing product surfaces

**Priority:** current-baseline release blocker. **Prerequisite:** document the permission matrix before adding more conditional checks.

Confirmed defects: organization mutations and canonical corrections authorize with document readability; owner/admin API tokens bypass their scopes; session/token resolution retains household authority after membership removal; normal job lookup checks only household rather than document access.

Implementation:

- Define a small domain policy for action names and principal capabilities, independent of FastAPI and database clients. Add persistence-owned queries for read, write, review, and administration checks. Thin route dependencies resolve identity and pass action intent; services enforce the same policies for browser, API, CLI, and rule-driven calls.
- Establish one policy matrix for owner, admin, member, and viewer; document ownership; primary-folder inheritance; private/household/custom ACL; read/write/admin grants; sensitivity; and API-token scopes. A viewer and a read-only grant must not modify metadata, refile documents, correct canonical facts, create relationships, or accept suggestions. Preserve member editing behavior only where the agreed household policy grants write capability. No role crosses household boundaries.
- API-token authority must be the intersection of live user authorization and the token's explicit scopes. An owner token limited to reading is still limited to reading. Unknown or empty scopes fail closed for actions requiring scopes. Define scope names in contracts before adding token-creation UI.
- Resolve durable credentials only when user and relevant membership remain valid. Revoking membership, disabling a user, or reducing privileges must take effect without waiting for cookie expiry. Revoke or invalidate associated sessions and tokens where appropriate.
- Apply write/review checks before any transactional mutation across organization, review corrections, candidate decisions, contacts, filing rules/suggestions, relationships, deadlines, reprocessing, uploads, and administrative jobs. Check both the source document and target folder before refiling; verify all documents in multi-document actions.
- Document-derived job reads inherit document authorization. Admin queue inspection remains explicitly administrative. Recheck access at execution/download for user-requested asynchronous exports and other sensitive jobs; store actor/scope references rather than a permanent permission snapshot.
- Resolve role-grant representation explicitly: schema accepts `principal_type=role` today while existing queries handle user/household. If a named-role representation requires a schema change, add a forward migration and update `folder_acl.v1` and DTOs together.

Suggested ownership: focused `lib/auth/authorization_policy.py`, `lib/documents/access_repository.py`, `lib/jobs/access_policy.py`, and existing service/repository call sites. Do not expand the 500-line auth service or 700-line job service into broader responsibility containers.

Acceptance:

- Parameterized integration matrix exercises list/detail/assets/search/facets/review/jobs and every write surface for multiple households, roles, sensitivities, folder grants, and token scopes.
- Regression cases: read-granted user cannot edit title/tags/primary folder or accepted facts; owner read-only token cannot cancel/retry jobs or write; removed member immediately loses session and token access; changing a primary-folder ACL changes all derived surface access consistently; private job IDs return the same not-found shape as missing jobs.
- Denied actions leave document rows, candidates/canonical facts, relationships and search projection unchanged, with no successful-action audit or child job. A bounded privacy-safe security-denial event is permitted. Allowed actions still audit and preserve previous behavior.

## SEC-02 — Complete secure account, session, token, and ACL management

**Phase:** 10.4–10.7. **Dependencies:** SEC-01 and public contract decisions.

- Split credential persistence, session lifecycle, passkey adapter, and authorization policy into cohesive modules as required by responsibility. Keep existing Argon2id and hashed random-token primitives.
- Add bootstrap password rotation/disablement and a usable recovery procedure; the existing `must_rotate` flag must correspond to a supported action and enforced policy. Do not create a public unauthenticated bootstrap endpoint.
- Add passkey enrollment, authentication, naming, listing, revocation, and recovery with bounded single-use challenges, exact relying-party/origin validation, user-verification policy, and audited security actions. Select the maintained library from current primary documentation during implementation.
- Add absolute TTL, documented idle timeout, throttled last-used writes, rotation after security changes, active-session display, revoke-current, and revoke-all. Security changes invalidate affected tokens/sessions consistently.
- Bind CSRF validation to the authenticated session or a signed equivalent. Require the expected browser origin on unsafe cookie-authenticated requests. Cover login/session replacement and recovery endpoints appropriately; an explicitly token-authenticated call may avoid browser CSRF only after token validity and scopes succeed. Invalid token headers must not accidentally grant token-only handling to a cookie session.
- Wire Secure, SameSite, HttpOnly, names, expiry, and origin settings through Compose and startup validation. Document the local HTTP exception and require secure-cookie configuration for the intended TLS exposure profile.
- Add token create/list/revoke/rotate with secret shown once, metadata-only subsequent reads, hashed persistence, scope/expiry validation, and audit. Add folder ACL management, member-role display/management within agreed v1 household scope, and permission explanations in Settings.
- Add bounded authentication/recovery request throttling and audit-safe failed-auth events. Make magic-link consumption atomic so concurrent redemption cannot create two sessions; do not promise delivered recovery links when delivery is only a stub.

Acceptance: real browser passkey and session flows; expiry/rotation/revoke-all; TLS cookie flags; CSRF absent/mismatched/cross-session/cross-origin denial; one-use challenge/link races; token secret never reread; member downgrade/revoke propagation; no account enumeration through recovery responses. Keyboard and accessible form/error flows work. Every new API route has request/response/auth parity tests, including actual response validation rather than only the OpenAPI overlay.

## JOB-01/JOB-02 — Make job ownership, retries, and persistence safe

**Priority:** current-baseline reliability blocker before multiple consumers or sustained long-document processing. **Dependencies:** migration/contract design; coordinate with extraction owners.

The current 300-second lease is not renewed by workers, and completion/failure does not verify claim ownership. Fix the protocol across all real worker queues, including future export/analysis workers, not just a longer timeout.

- Add an opaque claim token or monotonically increasing claim generation, attempt identity, lease expiry, and safe cancellation state. Return the claim identity to the worker. Claim, renew, complete, fail, and cancel operations use compare-and-set semantics.
- Renew leases while work runs, not only between jobs. Renewal validates the current claim. Loss of ownership stops new downstream scheduling and publication; cancellation has a defined cooperative boundary and bounded model timeout.
- Fence domain result publication as well as the final job status: a stale worker must not insert/promote/supersede document parse, extraction, canonical, embedding, or relationship state before its completion update is rejected. Validate ownership in the same transaction as current-result promotion and child-job enqueue. Immutable provisional blobs may survive a failed attempt, but remain unreferenced and eligible for delayed safe cleanup.
- Maintain a publication inventory mapping every worker/queue to its mutation and enqueue boundaries, owning transaction/service, claim check, applicable run-generation check and regression evidence. Include previews/assets, parsed structure, semantic annotations, quality/review tasks, claims/canonical data, lexical/vector projections, relationships/deadlines and child jobs. Add export bundles and analysis notes when those workers land. Mark a generation check inapplicable only with a documented reason and the corresponding cancellation/invalidation rule.
- Include the Qwen parser and any temporary Docling worker in that inventory. Fence full-document/page continuation assembly, parse artifact publication, relational pages/elements/tables/chunks, quality state and downstream extraction/index scheduling against the owning parse generation. An extraction or embedding job records the exact parse generation consumed. A stale Qwen or legacy Docling job cannot overwrite a newer parse or reintroduce its downstream projections.
- Preserve idempotency keys for domain scope: document/run/schema/semantic region, embedding profile/page, export request, and downstream task. Unique constraints and transactional reconciliation prevent duplicate current rows and fanout after retries.
- Distinguish retryable runtime failures from terminal protocol failures and document-quality outcomes. Preserve the existing quality outcome vocabulary and bounded backoff/dead-letter policy. Manual retry starts a fresh claim without silently replacing original/canonical history.
- Extract claim repository, lifecycle service, and safe event/error mapping from the oversized job service as behavior-preserving modules. Keep worker business responsibilities in their respective services.

Acceptance:

- An isolated DB test with two consumers, a shortened lease, and controlled clock/blocked work proves one active publication owner. The stale worker cannot renew, complete, fail, publish canonical/current data, or enqueue child tasks after reclaim.
- For each applicable publication boundary in the inventory, independently exercise loss of claim and supersession of run; a representative extraction race cannot stand in for all other workers. Future export/analysis gates include their new inventory rows and denied side effects before acceptance.
- Mixed-provider migration tests pause an old Docling attempt, publish a newer Qwen parse, then resume the old attempt; current structure, facts, review/evidence and indexes do not regress. Also test interrupted Qwen page batches and resumed reindexing: every page remains accounted for, no false complete parse is published, and continuation/retries produce no duplicate children or current records.
- Long-running work renews successfully; kill/restart recovers a job; stopped renewal permits bounded recovery; cancel-before-start and cancel-during-model-call do not publish disallowed outputs.
- Crash injection before blob write, after blob write, before DB commit, after commit, and before acknowledgement proves no original loss, duplicate current rows, or orphaned child-job storm. Reconciliation remains idempotent.
- Retry/dead-letter queues stay inspectable. Operational status distinguishes waiting, running, retry scheduled, cancelled, failed, and human review outcomes.

## SEC-03 — Privacy-safe errors and truthful status

**Priority:** current-baseline trust repair. **Dependencies:** SEC-01 for job authorization; can develop in parallel with JOB-01.

- Define allowlisted public error codes/messages and correlation IDs. Replace raw exception interpolation in extraction and other workers; never return filesystem paths, prompts, response payloads, secrets, or private excerpts through job errors.
- Keep protected operator diagnostic details with bounded size and explicit redaction, retention, and access policy. Redaction must cover string values as well as known JSON key names. Failures in logging must not fail the document pipeline.
- Remove hardcoded “Backup healthy / Last backup: 2h ago” and other invented health claims immediately. Until implemented, show unknown/not configured; afterwards show observed status, last success, freshness, and useful recovery guidance from the backend.
- Model status and result provenance identify the actual invoked model/version and task/prompt profile. Keep configured, reachable and task-validated states separate; an existing Oxcart endpoint or successful model listing does not establish Structura ingestion readiness. Shared-service budget diagnostics expose bounded utilization and waiting states without another consumer's prompts, document metadata or credentials.
- Parser status identifies Qwen, optional historical Docling or native PDF text provenance accurately. Review/debug/export surfaces distinguish model-transcribed text from native-extracted text and verified image evidence. Do not label Qwen-derived coordinates or copied model text as physically verified unless an independent locator/source check actually passed. Missing page/locator coverage stays explicit partial/review state rather than a healthy complete parse.
- Validate public asset, parse-debug, job, review, health, and export responses against their disclosure policy. Ordinary document UI remains a calm evidence workbench; internal implementation details belong in protected diagnostics.

Acceptance: synthetic private paths, tokens, document text, and model outputs injected into errors never appear in API messages, DOM, ordinary logs, or report manifests; stale/unavailable/unconfigured services never render healthy. Job status obeys SEC-01 document permissions.

## EXP-01 — Implement audited export workflows

**Phase:** 10.1–10.3 and 10.12. **Dependencies:** SEC-01, fenced job lifecycle, immutable storage contracts.

- Resolve export request/result/status/download/list contracts and persistence before UI. Implement `originals`, `originals_plus_json`, `originals_plus_csv`, and `review_report` using a focused export service, repository, format builders, storage adapter, and real worker. The normalized-data family must also support the spec's JSONL option with explicit contract negotiation; every production bundle has a manifest even if the older API treated it as optional.
- Authorize every selected document on request, execution, and download. A grant revocation while the export waits must not produce a downloadable unauthorized bundle. Counts, filenames, and error messages must not reveal hidden selections.
- Canonical accepted facts are the default JSON/CSV source. Review reports label candidates and decisions clearly; unreviewed model values must not become trusted export facts. Include evidence identifiers, schema/version lineage, asset hashes, byte counts, original names, bundle manifest, and app/run versions without raw storage URIs.
- Export parse/candidate provenance with the actual provider and parse generation, native-text/transcription origin and verified locator references. Historical Docling evidence remains resolvable; parser migration must not rewrite its IDs or imply that a Qwen transcription is an accepted fact. Document the selected parse version when a bundle includes derived text/structure.
- Define deterministic safe filenames, collision handling, archive size limits, streaming/spooling, cancellation, retries, bundle expiry, retention, and cleanup. Retention never deletes original source documents. Make sensitivity warnings follow explicit product policy and avoid adding unplanned redaction features.
- Audit request, completion, failure, download, expiry/deletion as applicable. Add user-facing selection, progress, warnings, retry, and download views plus admin diagnostics.

Acceptance: all four bundle types unpack correctly; original bytes/hashes match; CSV handles quoting/newlines and spreadsheet-formula safety; provenance/evidence resolves; large bundles respect memory/disk budgets; filename collisions and traversal strings are safe; retry creates one current result; interrupted export recovers; revocation and cross-household/folder denials hold; downloads use protected routes.

## OPS-01/OPS-02 — Real backups and full archive recovery

**Phase:** 10.8–10.9, 11.9, 12.8. **Dependencies:** storage/migration inventory; integrate export retention when EXP-01 lands.

- Rename the current template-clone check to describe what it actually verifies; remove it as sufficient evidence for the backup/restore gate. Keep it only if it remains useful as a fast database smoke.
- Define required backup classes: Postgres, canonical objects, necessary derived artifacts, configuration/secret recovery material, and release/repository manifest. Document treatment of exports, logs, observability, caches, temporary media, and reproducible model downloads.
- Implement real backup artifacts with manifest, checksums, schema/release/model versions, creation/finish time, counts, and consistent DB/object cutoff. Choose and document a consistency method suitable for the single-host system—bounded write quiescence or a database snapshot with immutable object retention—not independent copies that can silently disagree.
- Implement dry-run, locks, bounded disk checks, atomic manifest completion, nonzero failure exits, permissions/encryption for sensitive backup material, retention, and an off-host/off-device copy. Local ZFS snapshots aid recovery but do not establish host-loss recovery.
- Implement non-destructive DB/object integrity reporting for missing, corrupt, orphaned, and unexpectedly referenced objects. Cleanup is a separate explicit policy and never silently deletes originals.
- Prove two separate recovery gates at G5/G6, both mandatory before release. **Offline archive/evidence recovery:** restore into an isolated runtime root/database with model services unavailable; validate migrations, account recovery, original hashes, document/asset linkage, parse/current extraction references, canonical facts, review/audit history, protected browse/download, retained exports and lexical search/rebuild from persisted text. This does not prove new model-backed ingestion or semantic/visual search recovery. Record exact versions, duration, steps and limitations.
- Back up provider-neutral parse artifacts/relational structure, parser/model/schema versions, page render/coordinate metadata, retained legacy artifacts and evidence mappings. Restore mixed-provider history without rerunning either parser merely to read accepted facts/evidence. **Model-backed operational recovery (joint OPS-02/OPS-03):** independently recover the selected Qwen and compatible embedding artifacts/runtime configurations, authenticated isolated endpoints and measured sufficient recovery compute; then prove new intake, parse, extraction, reindex, lexical/semantic/visual search and viewer/review with Docling unavailable. Record immutable model revisions, image/config digests, credential recovery and capacity evidence. A proxy to production inference or its NFS artifacts cannot prove source-host-loss recovery; the Blackbird 24 GB embedding card is not assumed to run BF16 27B. Recovery hardware is an open OPS-03 deliverable/risk, not a selected or verified resource. Neither target recovery recipe may require the old Docling worker or its heavy dependency stack.
- Perform at least one complete recovery directly from the independent off-host/off-device backup copy, including recovery of encryption keys/secrets through the documented procedure. Use an isolated source replica for host-loss testing, then make its original data/config mounts unavailable. Remap recovered configuration to isolated storage and endpoints before starting workers; production services and the lost source must not be reachable dependencies of the rehearsal.
- Add daily backup scheduling and failure/staleness notification as deployed operational configuration; define a documented rehearsal cadence. Proposed planning targets are RPO at most 24 hours and offline archive/evidence RTO at most 4 hours for the initial private archive. OPS-02/OPS-03 must separately propose and measure the full model-backed recovery RTO once recovery compute is identified. Confirm both objectives against the user's archive needs before final release signoff; report achieved values rather than assuming success. G3 parser implementation/cutover is not blocked by this Phase 10 recovery-topology planning.

Acceptance: both recovery gates pass from independent backup/artifact sources with the isolated source runtime/data/config and production inference unavailable, and keys/secrets recovered through the runbook. Offline archive/evidence checks and restored model-backed new-ingest/search checks have separate results and timings; success at one cannot close the other. Corrupt/missing backup parts fail before a false success; insufficient space and interrupted backups leave the prior complete backup recoverable. No rehearsal writes over the active archive.

## OPS-03/OPS-04 — Deployment, observability, and capacity operations

**Phase:** 10.10–10.11, 11.11, 12.3–12.4 and 12.9. **Dependencies:** JOB-02 and SEC-03; hardware placement follows a measured inventory.

- Build reproducible runtime profiles with pinned model/container digests, dependencies, feature flags, migrations, and explicit live/fixture modes. A production model profile must not silently select fixtures. Document the default complete startup profile so “web/API healthy” is not mistaken for an operating ingestion pipeline.
- Deliver the independent recovery model/artifact/configuration and compute plan required by OPS-02, including authenticated endpoint setup, measured 27B/embedding capacity, acquisition/startup time and full processing RTO. The current Oxcart/NFS/Blackbird arrangement does not establish this host-loss capability; keep that release risk open until its separate G5/G6 rehearsal passes.
- The target startup profile uses thin PDF/image handling plus the Qwen-native parser and provider-neutral parse persistence. Any Docling worker remains an explicitly owned temporary migration/comparison profile with its heavy dependencies isolated. Retire it only after Qwen parse coverage, mixed-history viewer/evidence, reindexing, job recovery and full end-to-end gates pass; the accepted target must then run with Docling unavailable. Keep stored legacy artifact readers and rollback metadata without a permanent Docling service dependency.
- Exclude `.env`, private corpora, generated private reports, development state, and secrets from container build context. Use required runtime settings/secret mounts; propagate and validate cookie/origin/limits settings. Run appropriate containers without root and narrowly scope read/write mounts.
- Add documented restart policies, graceful shutdown, migration/upgrade ordering, tested rollback, disk-pressure handling, and internal-only service exposure. Separate process liveness from dependency readiness; do not take browsing offline solely because optional model inference is unavailable.
- Use the reviewed deployment topology: Oxcart remains the CPU/API/database system of record with `/srv/structura` mapped to `/tank/apps/structura` ZFS and provides ingestion inference through its existing Qwen3.8-27B BF16 service; model artifacts use shared NFS `/tank/ai/models`. Blackbird `/tank/work/repos/structura` and Oxcart `/tank/repos/structura` are the same shared NFS checkout, so one coordinator owns Git updates and concurrent pulls are forbidden. The Blackbird RTX PRO 4000 is proposed for retrieval embeddings, subject to measured fit, dimensions and retrieval acceptance. Inventory actual GPU identity/memory, running workloads, free capacity, mount/network paths, and endpoint capability to finalize integration and admission budgets for this selected topology. Do not interrupt unrelated serving or infer capacity from checkpoint size alone. Validate real text/structured-response/vision/embedding behavior appropriate to each adapter and sustained document workloads; preserve an explicit integration rollback profile.
- Provide queue depth, oldest age, throughput, retry/dead-letter counts, lease health, processing latency, review queue size, document counts/status, extraction quality vs runtime failure counts, model latency/availability, search freshness/latency, storage by class, backup freshness, and integrity failures. For the shared Oxcart service, record actual model/task profile, configured admission and concurrency limits, queue wait, in-flight requests, token/image budgets, timeouts and overload/backoff events. Prove Structura honors its allocation under competing traffic; preserve the other consumers' privacy and availability. Scope document-derived metrics and admin access correctly.
- Break out Qwen parsing/transcription/continuation load from subsequent extraction and Blackbird ingestion/query embedding work. Track page inventory/completion/abstention, parse-version migration/backfill progress, locator verification failures and index generation freshness; a completed HTTP request is not proof of complete document coverage.
- Add useful admin retry/cancel/inspection actions under SEC-01 with safe metadata and audit; present actionable degraded/unknown states. Add retention/rotation for logs and diagnostics.
- At G5, own the service/repository implementation for UI-12d document-view and original-access audit events, with SEC-03 privacy review. Define bounded actor/document/action/time/correlation records and deliberate access boundaries, excluding incidental thumbnail requests. Verify authorized access/export/delete events, absence of successful-access events on denial, protected history and content-free payloads.
- Create executable runbooks for startup, upgrade/rollback, credential recovery, backup/restore, stuck queues, model outage, index rebuild, disk pressure, and exports. Separate safe online operations from downtime procedures.

Acceptance: owned container/service restart and host-startup rehearsal recover the expected profile; current migrations/images/commit are observable; model down leaves persisted browsing, manual organization and lexical search usable while new Qwen parsing honestly waits/fails under the retry policy; retry recovers when dependencies return; no public model/DB ports or document egress appear unexpectedly; no secrets enter images or logs; operators can execute the runbooks on the isolated environment. Post-cutover acceptance runs the full new-document workflow and mixed-history evidence/recovery with Docling unavailable. Protect the shared Oxcart service and unrelated Blackbird Gemma throughout; outage tests isolate Structura's adapter/network path rather than stopping shared serving.

Capacity signoff uses the Phase 11 targets: health under 100 ms; inbox/detail/review median under 500 ms; lexical median under 300 ms; hybrid median under 1 second; upload acknowledgement within 2 seconds after upload completes. Record p95, sample count, corpus/page count, concurrency, warm/cold cache, hardware, model profile, and active workloads. Measure representative private corpus plus a larger sanitized load set; set the supported capacity from observed results rather than invented scale claims. Measure object growth, DB size, peak RAM/VRAM, model queueing, and export/restore duration. Include Oxcart ingestion under representative shared-service contention and concurrent Blackbird retrieval indexing/search; publish the enforced request/token/image limits and observed impact on existing consumers. Optional Phase 9 endpoint reuse adds a separate analysis load/citation-quality gate and cannot consume unmeasured ingestion capacity.

## REL-01/REL-02/REL-03 — Integrated verification and release execution

1. **Current-baseline repair gate:** current-head units/static/contracts plus targeted SEC-01/JOB-02/SEC-03 isolated-DB regression. Include full route-security response validation; OpenAPI overlay equality alone cannot prove runtime response parity. No regression to Phase 1–8 workflows or evidence/canonical policy.
2. **Phase 10 feature/operations gate:** SEC-02/EXP-01/OPS-02/OPS-04 complete; full browser auth/ACL/export/admin journeys; actual backup artifact restored and usable; dependency/security scans triaged; no unaddressed authorization or data-loss defects. Document the exposure profile and present truthful product status.
3. **Phase 11 release-candidate gate:** integrate extraction/retrieval owners' representative Qwen-native parse/extraction corpus and approved accuracy thresholds; run whole-app E2E, accessibility/Figma workflow acceptance, migration from scratch and mixed-provider upgrade, outage/restart/lease races, recovery, and performance measurements against one identified commit/profile. Require post-cutover Docling-free full-pipeline proof plus historical evidence reads and reindexing. Store sanitized evidence in a committed release directory; private source/evidence stays secured outside Git. Record exact commands/results and skipped checks with reasons.
4. **Phase 12 internal release gate:** freeze contract/schema/model/runtime versions; fix valid blockers; repeat only checks invalidated by changes; verify restored archive and browser smokes still pass; finalize runbooks, release notes, known issues with severity/workaround/owner/revisit trigger, deployment manifest, rollback, and go/no-go decision. Package and deploy only under the user's applicable authorization, preserving unrelated serving.
5. **Steady-state cadence:** scheduled backups and actionable failure signals; periodic full restore rehearsal; corpus regression after model/prompt/schema/index/ranking changes; dependency maintenance; revisit capacity after meaningful corpus/workload growth. This plan defines the cadence; creating external schedulers or notifications is a later concrete deployment action.

Evidence must be tied to the exact tested commit, migration set, model profile, images, and target. Tests passing on one checkout do not validate a different GPU checkout. A backend/container health response, fixture corpus pass, or database template clone never substitutes for the corresponding product, model-quality, or disaster-recovery gate.
