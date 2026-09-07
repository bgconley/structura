# Production completion execution strategy

Date: 2026-09-07. Companion to the [master completion plan](../../../STRUCTURA_PRODUCTION_COMPLETION_PLAN.md). This document defines execution, not a record of deployments already performed.

## Team and integration model

Use one coordinating integrator and up to three bounded parallel workers. The integrator owns the closure register, cross-layer contracts, migration numbering, dependency order, release branch, deploy synchronization and gate evidence. Other lanes own product/UI, extraction/retrieval, and security/operations. Reassign slots as the critical path changes; do not leave an entire agent waiting for a GPU job if it can finish independent code or review.

Start a parallel package only when it has stable inputs and useful independent work. Use separate worktrees for overlapping implementation areas. Do not let multiple agents edit `lib/contracts/models.py`, OpenAPI, central settings, Compose, the same migration sequence, `App.tsx` or the shared job/extraction protocol simultaneously. Integrate contract changes before consumers. Each worker reports touched files, tests, unresolved questions and an exact completion state; another lane reviews critical auth/persistence changes.

Recommended batches:

| Batch | Coordinator | Lane A | Lane B | Lane C |
| --- | --- | --- | --- | --- |
| 0 | Source/branch/schema/runtime baseline; accepted 27B profile and authentication inventory | Permission matrix and failing regressions | Claim/run-generation design and race regressions | Numeric correction and truthful status regressions |
| 1 | Integrate provider-neutral parse contract and 27B adapter/profile; G1 | Enforce permissions/token/member validity across services | Renew/fence all workers and parse/extraction publication; stale reruns | Correct forms, expired-session UX and real-state UI |
| 2 | Corpus governance + Blackbird embedding preflight | Complete browse/file/review UX against versioned parse | Qwen-native parser, thin PDF/image handling, coverage and claims/orchestration | Evidence scorer, parse migration/reindex and retrieval/capacity harness |
| 3 | G2/G3 integration and real GPU evidence | Viewer/evidence/history and Figma/mobile/keyboard acceptance | Source-scored Qwen parse/extraction fixes with frozen holdout | Docling-free end-to-end, parse/job recovery, search and performance acceptance |
| 4 | G4, after G2/G3 | Analysis workspace + note UX | Authorized context/citations + analysis worker/profile | Analysis invariants, model-boundary tests and simultaneous ingest/search/analysis capacity |
| 5 | G5 | Account/token/ACL/admin UI | Exports and lifecycle | Real backup, restore, deployment/metrics/runbooks |
| 6 | G6/G7 release evidence | Browser/Figma/accessibility signoff | Corpus/capacity/chaos signoff | Security/restore/upgrade and operator handoff |
| 7 | G8 extension integration and regression gates | Bounded extension UX packages | Extension services/adapters/models within measured capacity | Privacy, lifecycle, compatibility and operational acceptance |

Batch order follows root phase sequencing. Phase 10 designs can be prepared here, but full Phase 10 feature implementation is not smuggled into Phase 8.5 or Phase 9 packages. Baseline safety repairs retain their original phase ownership. The target under [ADR 0009](../../adr/0009-qwen-native-document-parsing.md) is Qwen-native document parsing through the accepted 27B service, with thin PDF/image inspection, rendering and optional native-text extraction. Implement its versioned provider-neutral parse contract early. Docling is an optional temporary migration/comparison path; neither a Docling baseline run nor its continued availability is a gate for the target. Source-scored coverage, fidelity, viewer/evidence, reindexing and recovery are the gates. Preserve job, run and accepted-fact authority boundaries throughout cutover.

G3 parser cutover requires parse/job restart, interrupted migration/reindex recovery and historical evidence-read proof. The independent full-archive backup/restore product remains at G5/G6; its later Docling-free acceptance is mandatory for release, not a circular prerequisite for implementing the new parser.

## Branch and migration discipline

The candidate begins at local feature head `d2820a8`, including its 30 commits ahead of `master`. Proposed integration branch: `codex/production-completion`. This name is a plan, not an already-created branch. Preserve the user's existing untracked and modified files; do not clean, reset or blanket-add the working tree. Individual packages use `codex/pc-<package>` worktrees from their required integrated base.

Review, test and integrate small changes. Only the integrator assigns the next migration number after querying the actual migration registry; `089` is the current reviewed maximum, not permission to reserve the same number in several branches. Prefer additive expand/backfill/switch/retire steps. Preserve canonical histories and old evidence until data equivalence and reference integrity are proven. Never rewrite an applied migration to avoid an upgrade problem.

Persist claim generation and run generation as different concepts: an execution lease owns a particular attempt; a parse generation identifies a structural interpretation; extraction/index generations reference the exact parse generation they consume. A write may require both claim ownership and the currently authorized generation. Backfills label historical values honestly; they cannot invent actual invocation or source evidence. Claims becoming authoritative needs a resumable migration/reconciliation plan and invariant report, not just a feature-flag change.

Migrate parsing with additive, versioned provider-neutral page/element/table/chunk records and immutable parse artifacts. Record actual parser/model/prompt/schema provenance, page coverage and image coordinate transforms. Native PDF text and Qwen-transcribed text have distinct origins and trust; copying model output is not native-source verification or Docling verification. Preserve historical Docling records and accepted evidence IDs without relabeling them. New reprocessing creates a new parse generation and explicit evidence mappings where verified; never silently retarget accepted facts. Reindexing keys off that generation, and old queued work cannot publish into its replacement. The target release must ingest, parse, extract, review, render evidence, index/search and recover with Docling unavailable. Retire the owned Docling worker/runtime dependency only after those gates and legacy-history reads pass; retained artifact readers do not require rerunning Docling.

Before each milestone, identify exact source SHA, schema state, image digests, model revisions, prompt/contract versions, flags and target services. Local source, origin branch, deployed shared checkout and built images must correspond to that candidate. After a local commit and push, follow the root sync policy from Oxcart with an inspected fast-forward pull. If branch/divergence prevents a safe pull, resolve it deliberately; never hard-reset the deployment checkout. Do not pull twice from both hosts: Blackbird's `/tank/work/repos/structura` is the same NFS checkout as Oxcart's `/tank/repos/structura`.

Final release integration into master must be reviewed and authorized under the execution session. If a merge creates a different candidate or invalidates tested behavior, rerun affected gates on that candidate. A feature-branch report is not automatically proof for a different release commit.

## Oxcart ingestion and Blackbird embedding execution

Follow [ADR 0008](../../adr/0008-qwen38-27b-ingestion.md) for the accepted ingestion model, [ADR 0009](../../adr/0009-qwen-native-document-parsing.md) for Qwen-native parsing, and [ADR 0007](../../adr/0007-blackbird-production-validation-topology.md) for topology. The ingestion model is the existing Qwen3.8-27B BF16 service on Oxcart: container `qwen38-27b-bf16-mtp-vl-oxcart-server`, configured served name `qwen38-27b-bf16-oxcart`, host port `18012`. The earlier unauthenticated `/v1/models` request failed; authenticated Structura adapter integration, parse/text/image contract behavior and shared-service capacity are still unverified. Establish credentials through protected runtime configuration and perform bounded functional validation; never put credentials in source, command output or evidence reports.

Blackbird's PRO 4000 is proposed for text and visual embedding services. Use GPU UUID `GPU-6ec4ee66-142e-34ad-e17d-a131d7153b51` or a freshly verified mapping to host index 1. Never leave default GPU 0 assignment or `gpus: all` in a Blackbird model profile. Container-visible CUDA index 0 is valid only after the container is restricted to the intended physical card. Do not deploy the ingestion Qwen service on this card as part of the default plan.

This includes ingestion embedding inference: workers submit document text chunks and selected page images to Blackbird for indexing, reindexing and backfill. Search submits queries to the compatible text/visual query encoders. CPU workers own scheduling and persistence; the PRO 4000 owns the proposed embedding inference for both paths. Measure bulk indexing throughput and protect interactive query latency with bounded batches/admission so an import cannot monopolize the embedding services.

Do not execute the existing managed GPU smoke/bringup scripts unchanged on either host. They encode historical host placement and can recreate or offload services. First add an explicit target-host/profile allowlist, GPU identity checks, service ownership checks, dry-run output and scoped teardown. Refuse to stop any container not created by the Structura validation project. The resident Oxcart 27B service remains shared infrastructure: restarting, reconfiguring, unloading or changing its serving profile is not routine Structura integration. Protect its existing clients through request/admission budgets. Host reboot, blanket GPU cleanup, `swapoff`, driver changes and Blackbird's unrelated Gemma/PRO 6000 service remain outside routine validation.

Use a dedicated embedding-only Compose overlay/project on Blackbird (proposed `compose.blackbird.models.yaml`, project `structura-blackbird-models`). Persist deployed Compose/manifest snapshots by commit; mount them read-only where possible. Oxcart retains the API, web, database, originals/derived objects and CPU workers for thin PDF/image handling, Qwen request orchestration and persistence, and Structura calls its existing 27B endpoint without taking ownership of that container. If retained during migration, Docling/Torch/OpenCV stay isolated in the owned Docling image; they are not dependencies of the target parser or shared API/worker images. Embedding services receive bounded request bytes through adapters; they need no direct permission to browse canonical originals.

Current adapters use bounded base64/data-URI image payloads, so the same image does not need to exist at the same absolute path on both hosts. Exercise the actual cross-host HTTP path, size/time limits, retries, privacy and concurrency, including scratch-file cleanup and simultaneous identical input. Keep direct model ports internal to the selected trusted network and authenticated/firewalled as designed; public browser asset URLs remain protected API routes.

Model weights currently have an NFS-backed home at `/tank/ai/models`; immutable, revisioned model caches may be staged on Blackbird local storage only after disk/quota/performance checks. Root had about 312 GB free at planning time. Do not use `/tank/work/repos` or shared NFS as a live DB volume or write conflicting git state. Store ephemeral model scratch locally with permissions/TTL; keep private run artifacts under protected Structura storage. `/tank/ai/experiments` is NFS too, not an independent backup device.

### Resource experiment order

1. **Inventory:** record Oxcart's 27B endpoint/authentication requirements, configured artifact/profile, existing client demand and safe probe budget; record Blackbird's UUID, VRAM, driver, RAM/disk, active containers, embedding model hashes, ports, mounts and network path. Recheck immediately before work. Inventory does not authorize changing resident serving.
2. **Early 27B integration proof:** register the actual served model and protected endpoint configuration; exercise authenticated parse, text, structured-response and image requests through Structura's real adapter with bounded synthetic/sanitized inputs. Verify full page inventory, versioned output shapes, token/image/context limits, retry/error behavior and actual Qwen invocation provenance. A model listing alone is insufficient; the prior unauthenticated failure is not integration proof.
3. **Qwen-native parse and extraction fidelity:** evaluate the target directly against frozen human-reviewed originals/annotations, including digital PDFs, scans, image uploads, tables, mixed pages and long documents. Require provider-neutral pages/elements/tables/chunks, reading order, bounded continuation, explicit partial/abstained coverage and verifiable page/image locators. Measure transcription/structure and downstream field/row fidelity separately; native source text and model transcription must remain distinguishable. Optional Docling comparison can diagnose regressions but is not a prerequisite. Prove a fresh full pipeline without Docling and preserve historical evidence during migration before retiring its owned worker. Do not spend this stage on further 8B-specific work.
4. **Embedding functional and residency proof:** validate the selected text embedding model at 1536 dimensions and visual image/text-query embeddings at native 2048 dimensions. Measure individual startup/runtime peaks and text-plus-visual co-residency on Blackbird's 24 GB PRO 4000, sustained query/indexing latency, queueing, failures and cleanup. If needed, evaluate same-model CPU serving with explicit compatibility and quality proof. Do not reduce dimensions or substitute a smaller model without an index/profile migration and quality comparison.
5. **Shared-service admission:** impose bounded Structura concurrency, request rate, prompt/image/output budgets, finite waits and retry budgets on Oxcart's 27B endpoint. Include parsing/transcription/page continuation as well as extraction in the budget; moving parsing to Qwen cannot hide its additional request load. Measure existing-client latency/error behavior against a baseline and apply backpressure to ingest before it harms those clients. Protect Blackbird interactive retrieval from ingestion/reparse/reindex backlog with bounded queues and measured scheduling. Do not unload or restart the shared 27B to satisfy an experiment. Sequential embedding load/run/unload may establish correctness, but does not prove interactive capacity. Queue wait is distinct from `pipeline_failed` and consumes a documented request/job budget.
6. **Concurrent product gate:** ingest a backlog through Oxcart 27B while repeatedly browsing, opening evidence, reviewing and running lexical/semantic/hybrid/visual queries against Blackbird embeddings; measure median/p95, timeouts, review latency, index freshness, recovery and impact on existing Oxcart clients. Add optional analysis only after Phase 9 eligibility and budget it separately; the ingestion model decision does not establish an analysis profile. No silent fixture or lexical-only replacement may make a requested semantic/hybrid query appear successful.
7. **Release capacity decision:** accept only measured request and embedding profiles meeting the documented workload/quality targets and shared-client protection budget. If they fail, lower bounded Structura admission or evaluate an explicitly measured alternative deployment arrangement. Do not reopen the selected model choice by default, borrow Blackbird's occupied PRO 6000, modify resident 27B serving as a routine fix, or declare capacity solved from serialized tests.

Qwen3.8-27B BF16 and Qwen-native parsing are the accepted target direction. Authenticated adapter integration, provider-neutral parse migration and fidelity, Docling-free end-to-end behavior, shared Oxcart admission limits, Blackbird embedding co-residency, CPU alternatives and any analysis profile remain measured implementation/release gates. A versioned Structura profile records the observed endpoint/artifact configuration and budgets without claiming ownership of or silently changing the shared serving configuration.

## Validation strategy

Use the smallest meaningful check for the package, then broaden at the integration gate. Preserve failing-regression-before-fix evidence for safety defects. Tests must verify effects and denied side effects, not mirror implementation or merely validate configuration text.

| Boundary | Required proof |
| --- | --- |
| Permission/correction | Real service/route integration matrix; invalid input does not produce any trusted value; denied operations cause no mutation, audit success or child job |
| Claim/run ownership | Per-worker publication inventory, two competing workers, shortened lease, real transaction/fencing checks, independent lost-claim and superseded-run cases at every applicable boundary, plus cancellation/crash |
| Storage/migrations | Fresh schema and mixed-provider upgrade; versioned parse/evidence mappings, object hash/reference reconciliation, resumed backfill/reindex, preserved histories and stale-generation rejection |
| Parse/model paths | Qwen-native full-page/element/table/chunk contracts, native-vs-transcribed trust labels, actual image locators and source-scored fidelity; real adapter provenance, outage/invalid/partial outcomes |
| Evaluation | Recomputed scores from captured run records and annotations; forged/stale/fixture/mismatched profile reports fail; holdout history retained |
| Search | Actual endpoints for lexical/semantic/hybrid/visual; exact identifiers, paraphrases, combined filters, ACL facets, accepted corrections and index freshness |
| UI | Real populated/error/loading/empty states, refresh/back/deep-link, keyboard and mobile entry, current backend integration, pixel/reference comparison |
| Analysis/export | Access rechecked at execution and read/download; citations/bytes match authorized source; no canonical mutation; cancellation/retry correct |
| Recovery | Independent backup copy restored into a clean isolated root/DB, source data/config unavailable, keys/secrets recovered, isolated endpoints, hashes/facts/history/search/user flows verified |
| Release | Same candidate/profile passes full corpus, browser, security, outage/restart and capacity criteria with Docling unavailable after cutover; legacy evidence and recovery work; operator can use runbooks |

Existing baseline commands (from the repository root, using the configured Python runtime):

```bash
python -m ruff check apps lib workers scripts tests
python -m ruff format --check apps lib workers scripts tests
python scripts/validate_contracts.py
python -m pyright --pythonpath /path/to/selected/python apps lib workers scripts
python -m mypy apps/api lib workers scripts
python -m pytest -q tests/unit
python scripts/run_integration_tests.py
docker compose config -q
```

`run_integration_tests.py` needs `STRUCTURA_INTEGRATION_BASE_DATABASE_URL` pointed at a disposable test server; never run direct tests against the active archive database. Python paths above are placeholders to resolve before execution. Run web lint/build in the pinned Node 20 container and browser suites in the matching pinned Playwright container, using isolated dependency volumes/snapshots. Current phase1–phase8 `*.spec.ts` are mocked UI tests; current `*-live.spec.ts` target the live app and may create data. Use only an explicit isolated validation household/corpus for destructive/chaos tests.

Current `run_golden_corpus.py` and the example model manifest are fixture/scoring-shape checks. They do not execute representative retrieval or prove model quality. Existing resident acceptance/report scripts must be adapted to the Oxcart 27B / Blackbird embedding topology and provider-neutral/scored evidence before they become release commands. The current backup template-clone script does not count as restore proof. Proposed runners must be clearly documented as planned until implemented; do not print an invented command as a passed gate.

## Evidence, tracking and stop conditions

Add a versioned package manifest under `docs/release-evidence/<candidate-or-milestone>/` containing package IDs/status, commit, migrations, contracts/prompts/model revisions, image digests, topology/flags, commands, results, test counts, dataset hashes/split metadata, measured metrics, failures and scoped rollback. This is a proposed execution artifact path. Private PDFs, annotations with private content, model responses, screenshots of private data and raw corpus reports stay in protected runtime storage; commit only redacted summaries and digests. Audit the evidence pipeline for accidental PII.

For each item in the closure register, maintain `owner`, `status`, `dependsOn`, `implementationRef`, `verificationRef`, `acceptanceRef` and `remainingRisk`. Keep progress explicit; no percentage replaces open acceptance criteria. A screenshot proves a state; a happy-path test proves that path; neither closes error, permission or failure-recovery requirements by implication.

Do not advance the relevant gate when a critical invariant fails, quality scoring is missing, required model service is fixture-backed, the tested version differs from the candidate, live behavior depends on stealing another GPU, or a required restore/capacity result is absent. Continue independent packages while the blocked dependency is resolved. User input may be needed for a material new UI choice, actual recovery objective or measured capacity tradeoff; present concrete evidence/options and keep unrelated authorized work moving.

Use checklists and bounded reviewable changes instead of a single “finish everything” coding run. Re-estimate package effort after G0 baseline and the first measured GPU/corpus cycle; do not claim a reliable completion date before the unknowns have been resolved.

## Handoff and ongoing operation

At G7, hand over the exact release manifest, startup/upgrade/rollback, credential recovery, backup/restore, model outage, queue recovery, index rebuild, disk pressure and export runbooks. Demonstrate them against the accepted environment. Tag/package only the tested release under the user's applicable authorization.

Deploy backup schedules, failure/staleness alerts and periodic restore exercises as part of operations implementation. Run corpus comparisons after prompt/schema/model/chunking/ranking/index changes, and repeat capacity tests after meaningful archive/workload growth. This planning document does not itself create automations, notifications or external messages.
