# Structura production-readiness review — 7 September 2026

**Verdict: substantial engineering beta; not a release candidate and not yet a polished production application.** The durable document and extraction foundations are real. However, several implemented workflows still have correctness or authorization defects, the frontend does not expose all of the backend's useful results, analysis and export remain unimplemented, and recovery plus representative quality gates are unfinished.

Completing the remaining numbered phases alone would not make the existing workflows polished. The work needs three tracks: close correctness and reliability defects, finish everyday user workflows, and establish a reproducible release with measured product quality and recovery proof. A single completion percentage would obscure these different kinds of remaining work.

## Scope and evidence

This review used the non-archive app specification, all 26 user stories, root phase map, associated phase/normalization/security/release/UI artifacts, current ADRs, and the newer extractive-first plans. It inspected the major frontend, API, persistence, auth, job, extraction, model-runtime, search, infrastructure and test boundaries. It included targeted in-memory probes and fresh automated validation. It is an architecture-wide review with targeted code-path inspection, not a claim that every source line or possible execution path has been exhaustively verified. No files under `archive/` were inspected.

The reviewed application code is commit `d2820a80641e166186bfadd10ed4902340b186ed` on `codex/extractive-first-uat-hardening`. Existing uncommitted files were preserved. The June 12 completion spec and plan are untracked draft proposals; individual recommendations in them were checked against code rather than assumed to remain open.

Current synchronization observed:

| Location | Observed revision/status |
| --- | --- |
| Local feature branch | `d2820a8` |
| Local `master` and remote `master` | `714126a`; feature branch is 30 commits ahead |
| GPU checkout `/tank/repos/structura` | `b31cbc9`, on the feature branch, one commit behind local |
| GPU application | No Structura containers present in `docker ps -a`; no Structura Compose project running; connection to `127.0.0.1:13000` refused |
| Latest feature-branch GitHub workflow found | GPU Live Smoke for `d2820a8`, cancelled; not passing deployment evidence |

This does not establish why the runtime is unavailable. It establishes that a current production deployment and a synchronized milestone cannot be validated from the present state. The review did not start model services, alter the GPU checkout, or modify its data.

The supplied April baseline is stale relative to current code. [ADR 0006](../adr/0006-extractive-first-extraction.md) and the updated [root plan](../../STRUCTURA_IMPLEMENTATION_PLAN.md) now use Docling-based extractive text lanes, deterministic planning, and Qwen exceptional vision, with Granite retained for explicit rollback/comparison. Older semantic-plan and operational guidance still describe Granite as the default structured extractor. Consolidating that guidance is necessary before another implementation or release milestone.

## Fresh checks

| Check | Result and limits |
| --- | --- |
| Python unit suite | **1,162 passed**, 23.05 seconds, local Python 3.11 |
| Fresh migrations and DB integration | **32 migration scripts applied through 089; 52 tests passed**, 25.18 seconds; disposable pinned `paradedb/paradedb:0.21.5-pg17` database, current-commit snapshot |
| Ruff lint and format | Passed; 510 files already formatted in application/script/test scope |
| Pyright and mypy | Passed; mypy checked 339 source files |
| Contract validation | Passed: 49 OpenAPI paths, 14 schemas, 6 event schemas, 13 model-output schemas |
| Bandit | Passed; existing suppression warnings emitted |
| Web lint/build | Passed in `node:20-alpine`; isolated current-commit snapshot |
| Browser regression | **18 passed**, 22.2 seconds, pinned Playwright 1.59.1 Linux container; all eight mocked phase specs |
| Compose configuration | Default and selected combined live/worker profiles validated |
| Deterministic corpus checks | Passed; these validate fixture/scoring shapes, not current model quality |
| Dependency audit | `npm audit --omit=dev` reported 6 affected packages: 4 high and 2 low; these include build tooling. Deployment exploitability was not established by the audit count |
| Fresh GPU/model end-to-end validation | Not run: target application unavailable |
| Full archive backup recovery | Not demonstrated; existing rehearsal is insufficient, as detailed below |

The isolated database/container was removed after verification. Test installation/build output stayed in a temporary snapshot, outside the user's working tree. Semgrep and a full dependency/container vulnerability assessment were not rerun. This review is not a new canonical GPU milestone.

I directly read the stored June 13 UAT reports under `/srv/structura/objects/exports/phase85-runs/uat-e8bb26b/`. Both report files are model-backed and show passing hard-correctness and operational gates, two `needs_human_review` documents, and zero `pipeline_failed` documents. Both have `goldCorpusQuality: not_evaluated`. This is useful historical pipeline evidence for two documents, not proof of broad extraction accuracy, acceptable review workload, or current runtime health. See [the validation record](../model-runtime/phase8_5_gpu_validation.md).

## Where each phase stands

| Phase | Assessment |
| --- | --- |
| 0: foundation/auth/jobs | Substantial and well tested; authorization, job ownership, readiness and hardening gaps prevent production signoff |
| 1–2: upload/view/file | Useful core implemented; archive pagination, real thumbnails, nested folders, duplicate handling and truthful status remain incomplete |
| 3: canonical parse | Strong structural foundation and protected diagnostics; large-document, failure and restart behavior need release proof |
| 4: extraction/review | Extensive backend machinery; correction integrity, rerun concurrency, accepted line-item views and review ergonomics need work |
| 5: retrieval | Lexical/semantic/hybrid/visual plumbing and filters exist; reusable collection UX and measured search superiority remain unproven |
| 6–7: automation/relationships | Real contacts, watched intake, rules, relationships and timelines exist; management/navigation and scale polish remain |
| 8: difficult documents | Quality signals, uncertainty states and visual retrieval exist; representative difficult-document extraction quality is not signed off |
| 8.5: real models/extractive-first | Material progress and historical live UAT; useful coverage gaps, unfinished E5 consolidation and missing release-gold scoring keep this gate open |
| 9: analysis | Unimplemented; endpoint returns 501. Correctly remains gated on extraction/retrieval readiness |
| 10: export/security/recovery/ops | Largely unfinished product/release work, although some auth/job foundations already exist |
| 11: release candidate | Harnesses exist; representative quality, recovery, performance and complete workflow acceptance are not established |
| 12: internal GA/handoff | A derived plan beyond the root plan's Phase 11; final packaging, runbooks and signoff remain |

## Release-blocking defects in implemented behavior

**1. Read permission is being used as write permission.** Organization mutations authorize with `document_is_readable`, then change title, date, notes, tags or primary filing. Canonical corrections similarly call `assert_readable` before updating accepted data. The schema distinguishes read/write/admin grants and viewer/member roles, so a shared-folder read grant must not suffice for these mutations. Introduce one explicit write/review policy and negative integration tests across organization and review endpoints. Evidence: [organization repository](../../lib/organization/repository.py), `lock_document_for_household`, lines 208–225; [review action repository](../../lib/review/action_repository.py), lines 59–78; [ACL function](../../database/067_document_read_acl_function.sql). This is a code-path finding, not a write performed against the user's archive.

**2. Restricted API tokens can inherit unrestricted owner/admin authority.** `require_admin` and `require_admin_csrf` accept the household role before evaluating token scopes; ordinary routes also lack operation-specific scope checks. A pure function probe confirmed that an owner token with only `documents:read` passes `require_admin`. Effective permission must be the intersection of current user authority and token scope. Evidence: [dependencies.py](../../apps/api/structura_api/dependencies.py), lines 54–80. Session/token resolution also uses a membership `LEFT JOIN` without requiring membership to remain present; deleted membership does not reliably terminate household access. See [auth service](../../lib/auth/service.py), lines 323–331 and 366–374.

**3. Invalid human correction text silently becomes trusted numeric data.** Executing the actual frontend function yielded `abc` as money → `$0`, `not a number` → `0`, `12garbage` as integer → `12`, and `1e3` as money → `$13`. The backend accepts the coerced typed value in its human-canonical write path and marks it reviewed. Reject invalid or ambiguous input, show field-specific errors, and validate types again server-side. Evidence: [reviewActions.ts](../../apps/web/src/reviewActions.ts), lines 28–44; [ReviewDecisionPanel](../../apps/web/src/components/ReviewDecisionPanel.tsx), line 84; [review service](../../lib/review/service.py), lines 41–54; [canonical correction persistence](../../lib/review/action_repository.py), lines 59–109. No correction was submitted to live data.

**4. Long-running jobs have neither active lease renewal nor claim fencing.** The default lease is 300 seconds, but no worker calls `heartbeat_job`; service-health heartbeats occur between synchronous jobs. A second worker can reclaim work still executing after lease expiry. Completion/failure updates by job ID, without checking the worker's claim generation. Renew during execution, reject stale completions, and test jobs exceeding the lease with multiple workers and forced restarts. Evidence: [job service](../../lib/jobs/service.py), lines 288–381 and 641 onward; [Docling loop](../../workers/docling/worker.py), line 220. The concurrency risk is established statically, not reproduced on the GPU.

**5. A rerun can be overwritten by older in-flight extraction work.** Current rerun handling supersedes existing rows, but loading a semantic task still accepts superseded annotations. Persistence lacks a current-annotation generation check, and aggregate replacement is scoped to document/schema rather than the winning run. Older work completing after a new annotation can recreate current stale regions and potentially replace a newer aggregate. Fence persistence and reconciliation transactionally against the active generation; test rerun during active work. Evidence: [semantic repository](../../lib/semantic_annotations/repository.py), lines 239–242; [extraction persistence](../../lib/extraction/extraction_repository.py), lines 605–631; [reconciliation reads](../../lib/extraction/reconciliation_repository.py), lines 468–494. This is a verified code-path race, not an observed incident.

**6. Backup recovery is not implemented to the standard the app promises.** The current rehearsal creates a newly migrated database, inserts one audit sentinel, and clones it with `CREATE DATABASE ... WITH TEMPLATE`. It exercises no backup artifact and restores no original files or configuration. It cannot establish archive recovery after disk/host loss. Yet `make release-readiness` includes it, and the UI hardcodes a healthy recent backup. Implement backup creation, retention and a restore into a clean target; verify document hashes, relationships, accepted facts, auth and application usability. Evidence: [rehearsal](../../scripts/rehearse_backup_restore.py), lines 31–37 and 99–135; [Makefile](../../Makefile), line 73; [Sidebar](../../apps/web/src/components/Sidebar.tsx), lines 68–71.

## Extraction and retrieval usefulness

Passing safety checks is necessary, but a system that consistently omits useful fields can still pass them. These coverage findings need explicit expected-output tests:

- **Invoice headers and summaries can disappear from the plan.** An in-memory invoice probe produced a line-item-table baseline; a valid grounded Qwen payment-summary region requesting invoice number, date and total was suppressed because it did not match a baseline target. The deterministic KVP target registry lacks an invoice header/payment-summary case. Fix baseline obligations and constrained augmentation together. Evidence: [deterministic plan](../../lib/semantic_annotations/deterministic_plan.py), lines 195–215; [target registry](../../lib/semantic_annotations/docling_targets.py), lines 135–193.
- **Text-present vision fallback cannot currently recover values.** After expected-field and quote checks, all observations are rejected when Docling text is present. A quote-matching probe returned zero observations. This preserves conservative model authority but leaves weak tables, sparse OCR and mixed pages without the promised recovery. Provide a bounded source-preserving recovery path or expose a precise partial/abstention outcome; do not simply weaken admission rules. Image-only fallback also produces limited flat observations rather than a full structured invoice/EOB line-item replacement. Evidence: [Qwen vision adapter](../../lib/extraction/gateways/qwen_vision.py), lines 225–251.
- **Long-document omissions are not fully accounted for.** Ten physical tables produced eight baseline targets because the builder truncates before the planner can record the omitted obligations. Inventory all targets, then explicitly defer or classify those outside execution budgets. Evidence: [target builder](../../lib/semantic_annotations/docling_targets.py), lines 262–263 and 292–293.
- **E5 is partially implemented.** Persisted claims and per-document orchestration commits exist. Orchestration defaults off, while reconciliation still reconstructs claims from envelopes and retains the older region-job coordination path. Finish consolidation and prove retry/kill/resume behavior before calling the new architecture complete. Evidence: [settings](../../lib/config/settings.py), lines 67–70; [reconciliation repository](../../lib/extraction/reconciliation_repository.py), line 183; [ADR 0006](../adr/0006-extractive-first-extraction.md).
- **Search superiority is unproven.** The deterministic golden runner scores `returnedDocumentIds` supplied in a manifest; it does not execute search. Its two passing cases cannot establish that hybrid search beats lexical search, particularly with real embeddings, ACL filters, and large archives. Measure lexical, semantic and hybrid retrieval against the same annotated query set. Evidence: [golden runner](../../scripts/run_golden_corpus.py), lines 29–39; [Story 6.3](../../pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md).

Representative release-gold validation should include digital and scanned receipts/invoices/EOBs, weak/missing table grids, handwriting, mixed pages, long tables/continuations, unsupported families and unreadable material. Measure field/row accuracy, missing required information, evidence completeness, repeatability, false promotion, review burden and retrieval quality. Safe abstention is acceptable when explicit; silent missing work is not equivalent to satisfying a user story.

## Product polish and workflow completion

**Expose the accepted results.** The API returns canonical `lineItems`, but ordinary app components do not render them. Review shows candidate rows; Viewer shows only the first five accepted fields with no expansion. Build complete receipt/invoice/EOB fact and line-item views with evidence, history and clear accepted-versus-proposed state. Evidence: [document detail](../../lib/documents/read_model.py), line 227; [Viewer](../../apps/web/src/components/Viewer.tsx), line 185; [ReviewQueue](../../apps/web/src/components/ReviewQueue.tsx), line 377.

**Remove fabricated health and inactive controls.** The sidebar hardcodes backup age, storage usage, worker count and review count. The top bar hardcodes hybrid readiness. Document rows always show “Ingested.” Inbox status pills change appearance without filtering data; Bulk Import and Create review set have no actions. Every status needs a real source, an honest unavailable state, or removal. Evidence: [Sidebar](../../apps/web/src/components/Sidebar.tsx), [TopCommand](../../apps/web/src/components/TopCommand.tsx), [DocumentTable](../../apps/web/src/components/DocumentTable.tsx), [InboxMetrics](../../apps/web/src/components/InboxMetrics.tsx), [Inbox](../../apps/web/src/components/Inbox.tsx), [SearchResults](../../apps/web/src/components/SearchResults.tsx).

**Finish archive navigation and collections.** Document listing defaults to 50 rows and the frontend supplies no paging. Nested-folder creation is absent from the UI. Smart folders remain disabled with “Dynamic results in Phase 5”; the Phase 2 test still expects this. Saved searches can be created but have no list/reopen/manage experience, and saving omits some newer filters. These are visible gaps in already implemented phases. Evidence: [documents route](../../apps/api/structura_api/routes_documents.py), line 34; [App](../../apps/web/src/App.tsx), lines 154–169, 229 and 311; [OrganizationRail](../../apps/web/src/components/OrganizationRail.tsx), lines 42–47 and 90–96; [search API client](../../apps/web/src/searchApi.ts).

**Make review a coherent work session.** Source evidence opens another surface instead of staying beside the correction form; returning loses selected review context. Task labels lack helpful document identity. Detail requests do not guard against stale responses, and old candidates remain visible while another task loads. Keep task identity, evidence and candidate selection together, clear or disable stale actions while loading, preserve context, and expose correction history. Evidence: [ReviewQueue](../../apps/web/src/components/ReviewQueue.tsx), lines 47–88 and 293 onward; [App](../../apps/web/src/App.tsx), line 370.

**Complete responsive and accessible navigation.** At mobile width the primary sidebar is hidden with no replacement. Rows are mouse-click-only and selection boxes are decorative. The displayed command shortcut has no handler. Viewer page thumbnails are decorative spans; image zoom/find and demonstrated large-PDF usability are missing. There is no logout UI or robust session-expiry recovery. Evidence: [styles](../../apps/web/src/styles.css), line 1891; [DocumentTable](../../apps/web/src/components/DocumentTable.tsx), lines 55–61; [TopCommand](../../apps/web/src/components/TopCommand.tsx), line 31; [Viewer](../../apps/web/src/components/Viewer.tsx), lines 100–109.

**Prove the intended design, not merely stable screenshots.** Existing screenshot tests are useful regression checks, but they do not establish fidelity to the compact Figma workbench. Review has diverged from its source/evidence layout, and its screenshot is captured after accepting the sole task, leaving the critical populated state untested. Browser coverage is Chromium-only and lacks keyboard/focus acceptance. The project-level Desktop Chrome device settings also override the intended top-level viewport. The live Phase 4 smoke checks containers, not an actual correction/history/evidence workflow. Evidence: [UI QA plan](../../STRUCTURA_UI_FIGMA_QA_PLAN.md), [Review styles](../../apps/web/src/components/ReviewQueue.css), [Phase 4 mocked test](../../tests/e2e/phase4.spec.ts), [Phase 4 live test](../../tests/e2e/phase4-live.spec.ts), [Playwright config](../../playwright.config.ts).

## All 26 user stories

“Implemented foundation” means meaningful code and test coverage exist. It does not substitute for production acceptance or fresh model validation.

| Stories | Current product-level assessment |
| --- | --- |
| 1.1 upload; 1.2 preserve original | Strong implemented foundation; processing UX still needs truthful refresh/status |
| 1.3 duplicates | Detection exists; user decision/handling workflow incomplete |
| 2.1 viewer | Partial: rendering/navigation work; real rail thumbnails and large-PDF usability incomplete |
| 2.2 folders/tags | Basic multi-folder/tag filing works; nested management incomplete |
| 2.3 saved searches/smart folders | Persistence/planner foundations exist; reusable end-user collection workflow incomplete |
| 3.1 parse; 3.2 debug | Strong implemented foundation; operational failure/restart acceptance remains |
| 4.1 classification | Core implemented; normal-document override/confidence experience incomplete |
| 4.2 receipt; 4.3 invoice; 4.4 EOB | Substantial backend; useful field coverage, representative quality and accepted line-item presentation incomplete |
| 4.5 evidence | Real page/bbox jumps; incomplete field coverage and broken review continuity |
| 5.1 review queue | Implemented; task identity, loading races and source context need work |
| 5.2 correction/history | Persistence exists; numeric coercion defect and missing history presentation block full acceptance |
| 6.1 keyword; 6.2 semantic | Implemented plumbing and search UI; representative relevance/performance proof incomplete |
| 6.3 hybrid improvement | Not established by comparative live benchmarks |
| 6.4 filters | Search filters work; Inbox filtering and collection-state persistence incomplete |
| 7.1 relationships; 7.2 timeline | Basic flows implemented; navigation/list scale and smart-view polish remain |
| 8.1 cited explanation; 8.2 comparison | Not implemented: Phase 9 |
| 9.1 jobs/failures | API foundation exists; complete operator UI and truthful health incomplete |
| 9.2 backup/restore | Not satisfied by the existing clone/sentinel rehearsal |
| 10.1 export bundles | Not implemented: Phase 10 |

Analysis and export endpoints explicitly return `501` in [routes_placeholders.py](../../apps/api/structura_api/routes_placeholders.py). Those are known unimplemented features, rather than regressions. Analysis is optional for core filing, but its two stories remain unsatisfied for the full specification.

## Remaining production engineering

- Implement real exports with originals, structured data, manifests, provenance and audit events.
- Complete appropriate session/token/ACL management and exposure hardening: expiry recovery, revoke-all, password rotation, secure cookies/TLS configuration and the planned passkey work.
- Add document-aware job authorization and public-safe error messages. Current job access checks household only, and exception text can expose private storage paths. Evidence: [jobs route](../../apps/api/structura_api/routes_jobs.py), line 22; [extraction failure mapping](../../workers/extraction/worker.py), line 304.
- Establish restart policies, dependency readiness, queue depth/age, model/storage/backup health, bounded overload behavior and practical operator recovery. Compose currently has no restart policies. Static process health is not dependency readiness.
- Pin release images by digest and triage/update dependency findings. Exclude secrets from image build context: the API copies the repository and `.dockerignore` does not exclude `.env`. No local `.env` was found, so this is a configuration hazard rather than a confirmed leak.
- Put browser workflow coverage into ordinary CI, retain stronger live release tests, and measure capacity/latency on a realistic archive. Release criteria need measured upload-to-visible, preview/parse completion, document opening, search and review latency under concurrent ingestion.
- Keep architectural boundaries strong. Thin routes and focused repositories are strengths, but extraction still carries overlapping model output, normalization, envelope, claim, decision, projection, candidate and canonical representations. Several extraction/planning modules exceed 800 lines. E5 should remove duplicate authority and stale coordination paths rather than add another compatibility layer.

## Recommended sequence and acceptance gates

1. **Restore a trustworthy implementation baseline.** Reconcile current planning/ADR guidance and choose the release branch. Fix read-versus-write authorization, token scope/membership enforcement, numeric correction validation, job claim ownership and rerun fencing. Each fix needs a regression that demonstrates the previously unsafe behavior. Synchronize the chosen commit before a deployment gate.
2. **Close Phase 8.5 on useful output.** Fix invoice, mixed-page and long-document coverage/accounting; finish the selected E5 path with kill/retry/resume tests. Run an unseen gold-annotated corpus with explicit quality and review-burden thresholds, including live text/visual/hybrid retrieval. Keep Phase 9 gated until this passes or blockers are explicitly accepted.
3. **Finish the everyday workbench.** Real status, pagination, duplicate handling, nested folders, working smart folders and saved-search management, complete accepted facts/line items, a stable source-linked review session, history, mobile navigation and keyboard access. Validate user tasks with realistic archives and populated/error/loading states.
4. **Complete the remaining specification phases in plan order.** Add optional cited analysis after its prerequisites; implement exports, auth/ACL management, backup/restore and operator surfaces. Do not treat a working API endpoint as completion of a user workflow.
5. **Qualify a release candidate and internal GA.** From a clean, synchronized build: fresh migrations, full workflows, approved quality/search metrics, realistic latency/capacity, model outage and worker restart recovery, a restored archive with verified originals and facts, Figma/accessibility acceptance, versioned release configuration, runbooks and a known-issue ledger.

A limited internal beta can precede the complete analysis feature set once core integrity, daily workflows and recovery are dependable and its scope is explicit. The full spec requires the remaining analysis/export stories as well. At present, the product has enough substance to harden and finish; it does not need a wholesale rewrite, and it is not one cosmetic pass away from production.
