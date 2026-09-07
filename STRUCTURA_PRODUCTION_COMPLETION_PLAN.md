# Structura production completion plan

Date: 2026-09-07

Status: Qwen3.8-27B and Qwen-native parsing target accepted; implementation gates remain open

Starting application commit: `d2820a80641e166186bfadd10ed4902340b186ed`

## Objective and authority

Deliver the polished local-first application described by the v1.3 app specification, all 26 user stories, the root implementation plan and its phase artifacts. Remediate every finding in the [September readiness review](docs/reviews/2026-09-07-production-readiness-review.md), finish the incomplete features, and prove that the resulting application preserves a real archive, presents useful evidence-backed results, survives operational failures, and meets measured quality and usability gates.

This is the execution overlay for [STRUCTURA_IMPLEMENTATION_PLAN.md](STRUCTURA_IMPLEMENTATION_PLAN.md), not a replacement phase map. The root plan still controls phase order and stop points. The associated phase plans, current contracts, database/infrastructure files, normalization artifacts and accepted ADRs supply acceptance detail. Read the relevant non-archive artifacts before each implementation package. Markdown is the default for duplicate artifacts. Never inspect `archive/`.

The user selected the existing Qwen3.8-27B BF16 service on Oxcart as the ingestion model and requested this plan update. That model choice is settled; it does not depend on winning a new comparison against the previous 8B model. Integration, quality, simplification and capacity gates remain open. This planning task changes documentation only. During execution, use the authorization then in effect; do not introduce repeated confirmations for ordinary edits, isolated tests, or already-authorized actions. Prepare concrete deployment/migration/rollback artifacts before any operational approval that is actually needed.

## Plan contents

| Document | Responsibility |
| --- | --- |
| This document | Scope, dependencies, milestones, release gates and execution order |
| [Product workstream](docs/plans/production-completion/product.md) | Browse/file/review/search/relationships, accessible UI, analysis, exports UX, and story-level acceptance |
| [Extraction and retrieval workstream](docs/plans/production-completion/extraction-retrieval.md) | Phase 8.5 defects, claims/orchestration, real-model quality, embeddings and search measurements |
| [Security and operations workstream](docs/plans/production-completion/security-operations.md) | Authorization, sessions, job ownership, exports, recovery, observability and release operations |
| [Execution strategy](docs/plans/production-completion/execution.md) | Team ownership, branch/migration discipline, Blackbird scheduling, evidence, run order and handoff |
| [Closure register](docs/plans/production-completion/closure-register.md) | Every review issue, all stories, spec requirements and deferred features mapped to work and acceptance |
| [Blackbird topology ADR](docs/adr/0007-blackbird-production-validation-topology.md) | Observed hardware, proposed topology, constraints and experiments required before adoption |
| [Qwen3.8-27B ingestion decision](docs/adr/0008-qwen38-27b-ingestion.md) | Accepted model selection, preserved evidence boundaries, profile migration and measured simplification |
| [Qwen-native parsing decision](docs/adr/0009-qwen-native-document-parsing.md) | Target parser replacement, explicit spec amendment, original evidence and Docling retirement gates |

The workstream documents define packages; the milestone order below controls when they execute. If a package combines an early defect repair and a later-phase feature, split the change at that boundary. A package is not complete simply because a screen, route, schema, or test fixture exists.

## Accepted ingestion direction

Use **Qwen3.8-27B BF16 on Oxcart** as the primary parser and sole generative ingestion backend for full document structure/text, classification, semantic understanding and structured/vision extraction. A lightweight PDF/image layer supplies immutable-source page inventory, rendering, coordinates and optional native text. Reuse the resident service through authenticated bounded adapters. Do not deploy a second ingestion model on Blackbird, quantize 27B merely to fit that card, or require the old Qwen8B/Granite arrangement as an execution dependency.

Keep immutable originals, source-page coordinates, a versioned provider-neutral structural artifact, deterministic typing/reconciliation, evidence verification, Claim IR, and human review. Qwen-generated structure/transcription retains model origin; copying it later is not independent verification. Dedicated compatible embedding models serve both sides of retrieval: during ingestion/backfill they encode document text chunks and selected page images; during search they encode queries in the corresponding vector spaces. Blackbird's PRO 4000 is proposed for all of this embedding inference, subject to measured co-residency, indexing throughput and query latency. “Retrieval embeddings” describes their purpose, not a query-only workload.

**Docling is temporary migration/comparison infrastructure, not a mandatory stage or an authority that must agree with Qwen.** ADR 0009 explicitly amends the spec's Docling-specific structural/debug requirements while preserving their user outcomes. The Qwen-native target must provide all searchable text, pages/elements/tables, reading order, concrete original-source evidence, run metadata and explicit omissions—not just typed invoice JSON. Implement profile/provenance and converter-neutral contracts, then the bounded Qwen-native parser/extractor, atomic parse/index migration and source-aware UI. G3 includes an end-to-end run with Docling conversion unavailable. Retire legacy queue/worker dependencies after cutover and recovery proof. Existing artifacts and human corrections remain readable. Optional old-model/Docling comparisons are diagnostics, not selection gates.

## Scope and completion points

**Required application completion:** all root phases through 11, the derived Phase 12 internal-GA handoff, all 26 stories, and required spec functionality that lacks a story. This includes image/PDF and batch upload, complete classification/typed results, nested organization and reusable collections, evidence/history/review, search/relationships, optional cited analysis, export, soft deletion, account/ACL management, and operator/recovery features.

**Explicitly deferred catalog:** email/ZIP ingestion, safe-share redaction, missing companion suggestions, reminders, optional reranking, mobile companion/share extension, OCR tuning, active learning/fine-tuning, richer multi-household collaboration and entity/graph features. They remain planned work with their own dependencies and acceptance criteria in the closure register. They are not silently declared done or required to pass the original v1 gate. The full roadmap has a v1 release milestone and a subsequent extension-completion milestone.

Non-goals remain public multi-tenant SaaS, mandatory cloud inference, automatic source destruction, arbitrary photo-library OCR, autonomous high-sensitivity finalization and medical/legal expert-system claims. A new document family may be classified and searchable without claiming a typed extractor exists for it; the required typed families remain receipt, invoice and medical EOB, with other structured/observation contracts treated according to their explicit registry support.

## Baseline that must be preserved

- Immutable original bytes, hashes and protected asset routes.
- Original-source evidence, complete versioned structure and truthful native/model origins; historical Docling artifacts remain readable.
- Candidate/review/accepted-fact separation; accepted facts remain the ordinary read model.
- Live/fixture separation and truthful actual-adapter provenance.
- Quality outcomes distinct from system failures; no hidden second Qwen semantic pass.
- Existing manual filing, auth/ACL, retry, proxy, worker, search, relationship and late-response regression coverage.
- Thin routes, cohesive services/repositories/adapters and domain rules independent of frameworks.

The review freshly passed 1,162 unit tests, 52 isolated database tests, 32 fresh migrations, 18 mocked browser tests, static/contracts checks and the pinned web build. These are regression baselines, not final acceptance. Existing June UAT covers two documents and has no gold-quality evaluation. All planning-package statuses start open unless this plan explicitly identifies an already-observed fact.

## Current hardware and deployment facts

Blackbird `10.25.0.51` has an idle RTX PRO 4000 Blackwell at GPU index 1, UUID `GPU-6ec4ee66-142e-34ad-e17d-a131d7153b51`; the current snapshot reported 24,467 MiB total, 23,988 MiB free and 1 MiB used, driver 590.48.01. About 115 GiB system RAM was available. These measurements must be refreshed before a GPU operation.

Its RTX PRO 6000 is occupied by `gemma4-31b-it-bf16-blackbird` and is excluded from this project's capacity. Do not stop, reconfigure, unload or borrow that resident service. Blackbird's one 24 GB card handles proposed ingestion/indexing/backfill and query embedding inference; generative document understanding/extraction uses the existing shared Oxcart service. CPU workers retain job orchestration and database/vector persistence.

The 2026-09-07 read-only inventory confirmed Oxcart container `qwen38-27b-bf16-mtp-vl-oxcart-server` running with `--dtype bfloat16`, served model name `qwen38-27b-bf16-oxcart`, and port `18012`. The user also confirmed this is the intended existing model. An unauthenticated metadata request did not succeed; authenticated Structura adapter, schema, vision and corpus validation are still required. This is no claim of an integrated ingestion deployment. Preserve the resident service and measure the impact of ingestion on its other clients; memory reservation is not a measurement of active request capacity.

Oxcart `10.25.0.50` retains the archive/control-plane location: `/srv/structura` resolves to `/tank/apps/structura` on ZFS. Its `/tank/repos/structura` resolves to `/tank/work/repos/structura`. Blackbird mounts the same `/tank/work/repos` directory over NFS, along with `/tank/ai/models` and `/tank/ai/experiments`. Those paths are not independent checkouts or off-host backups. One integration owner updates the shared checkout from Oxcart. Never put PostgreSQL live data on the Blackbird NFS mount.

Observed revisions differ: local feature branch `d2820a8`, shared deployment checkout `b31cbc9`, and `master`/`origin/master` `714126a` (30 feature commits behind). Structura's application was not running on Oxcart during review. The 27B model choice is accepted; the application integration and embedding deployment profile are not yet validated.

## Milestones and dependency gates

| Milestone | Phase ownership | Work | Exit gate |
| --- | --- | --- | --- |
| M0 — Establish the executable baseline | Current baseline | Reconcile guidance/branch, record contracts/migrations/config, inventory archive data without modifying it, prepare isolated validation, resident Oxcart 27B adapter migration and Blackbird embedding preflight | G0: reproducible baseline and explicit model/hardware/corpus/branch assumptions; no accidental shared-service or archive changes |
| M1 — Repair integrity and permissions | Defects in 0–8.5 | Read/write/review policy, token scopes/membership, correction parsing, job claim ownership, stale-run fencing, safe public errors, truthful status | G1: negative/race/kill/retry regressions and existing core tests pass; stale/unauthorized work cannot publish |
| M2 — Finish the everyday workbench | Completion of 1–8 | Navigation, upload/progress, pagination, duplicates, thumbnails, complete accepted data/history, stable review, nested folders, saved searches, smart folders, relationship/automation management | G2: realistic browse/file/review/search tasks pass on desktop/mobile/keyboard and match Figma |
| M3 — Close model and retrieval readiness | Remaining 8.5 | Integrate Qwen-native structure/extraction, migrate source provenance and current parse/index generations, complete E5 claims, full-content quality scoring and Blackbird ingestion/query embeddings; retire mandatory Docling dependencies | G3: Docling-free full ingestion/search/evidence passes on unseen originals; coverage, shared-client impact, retries and rollback/recovery proven |
| M4 — Implement optional cited analysis | Phase 9 | All seven analysis types, bounded authorized context, separate worker/profile, citation validation, note save/read/history and complete UI | G4: cited workflows and simultaneous ingest/search/analysis capacity pass on the final profile; analysis disabled/offline leaves core functions intact and never mutates accepted facts |
| M5 — Complete operations and export | Phase 10 | Export formats, passkey/session/token/ACL management, real backup/restore, operator dashboards/actions, deployment hardening | G5: protected export/account/admin journeys and actual clean-target archive recovery pass |
| M6 — Qualify the release candidate | Phase 11 | Fresh/upgrade migration, full browser/quality/security/chaos/performance matrix against one release candidate | G6: versioned evidence pack with all required checks passing and no unresolved integrity/security blockers |
| M7 — Package internal GA | Derived Phase 12 | Final Figma/accessibility acceptance, runbooks, backup/restore and resource signoff, version tag/config freeze, deployment sync and handoff | G7: deployable and recoverable release; meaningful known-issue ledger and operator signoff |
| M8 — Complete the deferred catalog | Explicit extension roadmap | Individually scoped enhancement packages in the closure register | G8: each listed extension meets its feature, privacy, performance and regression gates; no extension silently changes v1 authority rules |

M2 and M3 may develop in parallel after their M1 prerequisites. Corpus labeling, UI reference preparation and infrastructure inventory can begin during M0/M1. M3 code depending on job/run fencing must wait for that shared contract. G2 and G3 both precede Phase 9 implementation/enablement; planning analysis contracts here does not bypass the Phase 8.5 gate. Phase 10 feature work remains after Phase 9 per the root sequencing layer. Early credential/authorization/health repairs are baseline fixes, not a hidden Phase 10 expansion.

Critical path: **G0 → ownership/authorization contracts → G1 → G2 + G3 → G4 → G5 → G6 → G7**. The likely variable work is corpus labeling, 27B integration and extraction simplification, shared Oxcart request capacity, Blackbird embedding latency and full archive recovery. Do not hide those uncertainties behind a calendar promise.

## First execution batch

1. Read this plan, the closure register and the relevant source artifacts; record current git status and preserve unrelated/untracked work. Review and integrate the 30 existing feature commits as the starting candidate rather than branching from stale `master`.
2. Establish the proposed integration branch `codex/production-completion` from the reviewed current feature head; capture the actual base SHA. Create isolated task worktrees only when execution starts. Designate one owner for shared contract and migration ordering.
3. Record environment, schema, source/object paths, private-report locations and public-safe evidence paths. Verify the existing archive is recoverable/safely snapshotted before any future data migration; this preparatory protection does not claim Phase 10 recovery completion.
4. Run four bounded lanes: coordinator/baseline + authorization repairs + job/run ownership + correction/health UI repairs. Reproduce each review finding in isolated tests before fixing it. Do not start speculative model tuning while these ownership boundaries are unstable.
5. In parallel where resources permit, freeze corpus selection/annotation rules, prepare the explicit 27B adapter/profile/provenance changes in X-01, and inventory the existing Oxcart endpoint/authentication and client load. Prepare Blackbird text/visual embedding experiments without displacing resident services. Capture endpoint/allocator state before any future service changes.
6. Integrate the shared permission and claim-generation contracts first; follow with all call-site/worker/publication changes, then run G1. A test that only rejects `complete_job` after stale data was already published does not pass.
7. Open M2 and M3 implementation packages once their dependencies are satisfied. Verify authenticated 27B text/image/structured-output calls and truthful new lineage before full ingest. Implement the source layer and Qwen-native parse contract before candidate/index consumers; use original-source quality and Docling-free end-to-end gates to qualify the target. Preserve historical evidence through an explicit current-version cutover, and retire redundant stages after rollback/recovery proof. Keep each change reviewable.

## Common definition of done

Every required package must provide:

- Closure-register IDs and source requirements, a concise before/after behavior, owner, dependencies and final status.
- Implementation at the right layer, reviewed touched-file responsibilities, no circular dependency or new broad utility/god module.
- Contract/DTO/API/database/event/UI alignment in the same change; migrations forward-only and tested on a representative upgrade as well as a clean database.
- Meaningful regression tests for the original defect plus the actual user/worker behavior. Do not count tests that merely assert configuration text or fixture values as product proof.
- ACL/privacy/canonical/provenance invariants for every new surface and async read/write/download stage.
- Fresh end-to-end proof where external services, model adapters, storage or browser interactions are material. A health response, model list, screenshot, or fixture score is never a substitute for the corresponding functional gate.
- Updated source guidance, runbook and evidence manifest; limitations and rollback stated. Original/history retention and any cleanup policy reviewed explicitly.

Allowed statuses are `planned`, `ready`, `in_progress`, `blocked`, `implemented`, `verified`, and `accepted`. “Implemented” is not closed. Only `accepted` closes an item; it requires evidence for its criteria. A blocker names the missing input or external dependency and the next action. Planning drafts and historical test records cannot close fresh release gates.

## Quality and performance acceptance

Hard invariants have zero tolerance in the release corpus and regressions: unauthorized read/write, original-byte corruption, stale-worker publication, duplicate current outputs, fabricated trusted required fields, false model provenance, accepted facts without the required evidence, model-backed auto-promotion contrary to policy, private data leakage, and uncontrolled fanout. Quality uncertainty is not a system failure; it remains explicit review/partial/abstention state.

Use the app-spec targets as the initial operating baseline: upload row visible within 2 seconds after upload completion; inbox/detail/review median below 500 ms; cached first-page display within 1 second; lexical median below 300 ms; semantic median below 500 ms; hybrid median below 1 second excluding optional heavy reranking; health below 100 ms. Record actual p50/p95, concurrency, corpus/page counts, warm/cold state and active ingestion. Hardware changes do not silently waive these targets; measured exceptions require a concrete exposure/capacity decision before release.

Plan for at least the spec's suggested 50-document starter mix (10 receipts, 10 invoices, 10 EOBs/medical bills, five each warranties, legal documents, handwriting and long reference PDFs), plus a separately held-out/adversarial slice sufficient to exercise the identified gaps. The count is a planning target, not evidence of generalization. Record which examples were seen during tuning; never relabel known tuning inputs as unseen holdouts.

Field/row quality, required-field presence, numeric accuracy, evidence completeness, false promotion, review burden, calibration, repeatability, Hit@k/MRR and lexical-vs-semantic-vs-hybrid comparisons must be computed from captured outputs and versioned human-reviewed expected annotations. Define minimum useful output and maximum avoidable abstention/review burden per family so “everything needs review” cannot satisfy the goal. The workstream contains proposed threshold calibration; no new numeric quality threshold is represented as already approved.

## Decisions handled by evidence, not assumptions

| Decision | Default planning direction | How it closes |
| --- | --- | --- |
| Release baseline | Current feature implementation, not stale master | Integrator records accepted base and final matching source/image/config SHAs |
| Ingestion model | **Accepted: existing Qwen3.8-27B BF16 on Oxcart** | ADR 0008 records the choice; X-01/G3 verify integration and quality, not model selection |
| GPU topology | Existing Oxcart 27B + CPU/archive; Blackbird PRO 4000 for retrieval embeddings | G0 inventory and G3 concurrent workload evidence; adopt the measured embedding profile under ADR 0007 |
| Model residency | Reuse Oxcart 27B; measure text/visual embedding co-residency on Blackbird | Authenticated exact-model/dimension smokes, bounded ingestion admission and measured impact on existing Oxcart clients; preserve Blackbird Gemma |
| Parser architecture | **Accepted target: Qwen-native parse + thin PDF/image source handling** | ADR 0009 migration, full-content/evidence gates, Docling-free ingestion/recovery and controlled legacy retirement |
| Extraction call structure | Bounded 27B parse/extraction tasks; combine when useful | Full page/field/row coverage, source fidelity, review and latency gates; no mandatory Docling agreement |
| Analysis model | Separate bounded profile selected at Phase 9 | Local quality/citation/capacity trial; Smart Parse is not silently reclassified as an analysis service |
| Quality thresholds | Use existing approved thresholds; otherwise calibrate and propose per family | Frozen annotation/threshold manifest before the final holdout run, reviewed alongside precision/recall/review tradeoffs |
| Recovery objectives | Proposed RPO ≤24 h and offline archive/evidence RTO ≤4 h; full model-backed recovery RTO to be defined with independent recovery compute | OPS-02/OPS-03 separately prove archive reads and restored model-backed new intake/search; both require measured recovery and archive-owner acceptance at release |
| UI unspecified states | Existing Figma handoff and compact design language | Concrete reference/state implementation; unresolved user-visible choices are presented with a reviewable proposal |
| Optional/deferred features | Preserve explicit later-stage scope | Closure register extension packages; no claiming the v1 gate implements them |

The plan itself is complete when all review findings and requirements have a work owner, dependency, acceptance criterion and gate. Application completion remains the execution of those packages and acceptance of their evidence.
