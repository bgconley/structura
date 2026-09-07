# JOB-01 / JOB-02 foundation checkpoint

Internal attempt ownership is implemented in migration091 and lib/jobs. Tokens are newly generated for every claim and revoked by complete/fail/cancel/retry/expired-lease recovery. Renew/complete/fail require job ID, token, running status, and live DB wall-clock lease; terminal transitions serialize against publication using the job-row lock. Tokens stay out of public DTOs. Workers renew independently of synchronous service calls; renewal has bounded connection/query/lock timeouts and bounded context cleanup. Lost ownership stops publication and is not itself recorded as a new job failure.

Explicit publication inventory (each fence uses the SAME connection/transaction immediately before its owning commit; locks are acquired after model/storage work):

| Worker / operation | Fenced owning boundary |
| --- | --- |
| ingest | Read-only asset acknowledgment, then owned final job transition |
| previews | workers/previews/service.py build_preview_assets asset publication |
| Docling | lib/documents/canonical_parse.py parse artifacts+relational replace and mark_parse_failed; lib/documents/quality.py quality/review task commit |
| Docling child enqueue | workers/docling/worker.py semantic and embedding enqueue independent commits |
| semantic | lib/semantic_annotations/service.py manifest/plan/children transaction; repository.py standalone manifest |
| extraction | lib/extraction/extraction_repository.py classification and extraction/claims/candidates/canonical/task-state commits; aggregate reconciliation publishes through extraction_repository |
| extraction child enqueue | workers/extraction/worker.py embedding and relationship enqueue independent commits, now before terminal job transition |
| embeddings | lib/search/embedding_service.py shared text/visual vector+projection commit |
| relationships | lib/relationships/service.py background deadline and suggestion commits |
| generic independent child creation | lib/jobs/service.py create_job owning transaction |

Cursor-only helpers inherit the owning transaction. Read-only connection contexts are not publication boundaries. Explicit context fencing intentionally does nothing for non-worker request flows; their authorization/transaction rules still apply, with a regression test proving the opt-out/reset contract. Seven claimed queue entry points establish the context before domain services. Watched-folder scanning is a separate loop, not a pipeline-job lease, and remains outside this foundation.

Cutover requirement: stop/drain old workers first; preserve running tokenless rows until their existing lease expires and normal recovery claims a fresh token. Do not run old workers alongside new token-aware workers. Migration091 does not invalidate a live tokenless row immediately. Run migration in the isolated DB and then validate before active-runtime activation.

Remaining JOB-02/X-02: independent parse/semantic/extraction run generations and current-source/version checks, parent/child cancellation invalidation (including children published before cancellation), atomic run replacement across multiple committed stages, scanner generation/ownership, and adversarial per-boundary concurrency tests. The optimistic own-job reconciliation override now happens while the lease is owned, before terminal failure revokes it; terminal ledger failure after a committed aggregate remains a cross-commit consistency case to close with run-level publication. Token ownership does not prove the run is still the desired current run. JOB-02 is not complete.

Validation checkpoint: 1252 unit tests passed; targeted mypy21 files, ruff/import/format and compileall passed. New integration tests/integration/test_job_ownership.py collect locally but need isolated migrated DB proof. They cover reclaim rejection for renew/complete/fail, real parse-failure repository rollback, same-transaction document rollback, DB clock expiry after transaction start, and cancellation. Root owns the canonical DB run and final evidence record. No deploy, runtime/model change, commit or push by this agent.
