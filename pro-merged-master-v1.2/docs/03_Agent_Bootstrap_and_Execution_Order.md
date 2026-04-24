# Agent bootstrap and execution order

This document complements `AGENT_START_HERE.md` and the phased implementation plan. Its purpose is to translate the architectural intent into a concrete implementation sequence for a coding agent.

## 1. Recommended repo initialization order

1. Create the monorepo layout from `docs/07_Repository_Layout_and_Coding_Standards.md`.
2. Commit tooling first:
   - formatter
   - linter
   - test runner
   - migration runner
   - makefile or task runner
3. Commit Compose services next:
   - postgres
   - api placeholder
   - web placeholder
   - workers placeholders
   - optional redis fallback profile only if PGMQ is unavailable
4. Apply the SQL baseline.
5. Implement bootstrap auth/session routes and protected-route conventions.
6. Add the object storage abstraction and a local filesystem backend.
7. Add upload and inbox.
8. Add canonical parse worker.
9. Add extraction worker.
10. Add search.
11. Add review queue.
12. Add relationship and analysis features.

This order forces the system to acquire a durable spine before it acquires “intelligence.” The normative baseline assumes `pipeline_jobs` plus PGMQ; do not wire Redis as an equal default.
It also assumes auth/session plumbing exists before document APIs are treated as real product surfaces.

## 2. Concrete first week execution sequence

### Day / block 1
- scaffold repo
- add Compose
- boot services
- verify DB extensions
- apply schema
- implement bootstrap admin creation
- implement login, current-session, and logout routes
- protect document routes by default
- commit

### Day / block 2
- implement storage abstraction
- implement upload endpoint
- create document and asset rows
- show inbox entries
- commit

### Day / block 3
- implement preview generation
- implement document viewer page
- add folder and tag CRUD
- commit

### Day / block 4
- integrate Docling worker
- store canonical artifacts
- create page / chunk / element rows
- add debug panel
- commit

### Day / block 5
- add classification and extraction contracts
- implement receipt extraction path
- add validators and review tasks
- commit

After this point, expand to invoice and EOB, then search, then hybrid retrieval, then relationships, then analysis.

## 3. Shared libraries to create early

Create these shared internal packages early to avoid duplication:

- `lib/config` - typed env loading
- `lib/storage` - object store abstraction
- `lib/db` - DB session and models
- `lib/jobs` - queue payloads and durable job helpers
- `lib/contracts` - JSON Schema and Pydantic helpers
- `lib/evidence` - evidence object builders and validation
- `lib/search` - query normalization and filter parsing
- `lib/observability` - logging, metrics, tracing helpers

## 4. Guardrails for schema evolution

- Do not let frontend-only assumptions become the real data model.
- Add a migration for every structural schema change.
- When adding a new document family, add:
  - JSON Schema
  - validator
  - extraction tests
  - sample fixtures
  - search expectations if relevant
- Prefer additive schema evolution over destructive edits.

## 5. Worker implementation order

1. ingest worker
2. preview worker
3. Docling worker
4. classifier worker
5. extraction worker
6. embedding worker
7. relationship suggestion worker
8. analysis worker

Each worker should share a common job contract shape:

- `job_id`
- `job_type`
- `document_id` or target ids
- `scheduled_at`
- `attempt_count`
- `payload`
- `trace_context`

## 6. Core API implementation order

1. health and version routes
2. auth session create/current/delete
3. upload documents
4. list inbox documents
5. get document detail
6. folder and tag CRUD
7. review task listing and actions
8. search endpoint
9. analysis endpoints
10. admin and retry endpoints

## 7. UI implementation order

1. shell layout and navigation
2. inbox
3. document detail with viewer
4. folder tree and tag management
5. review queue
6. search page
7. relationship pane
8. analysis workspace
9. admin surface

## 8. Minimum manual QA loop after each major feature

After each subphase, manually verify:

- UI behavior
- DB rows created as expected
- artifacts stored where expected
- retries are safe
- logs are readable
- failure states are visible

## 9. Files an implementation agent should treat as normative

- `docs/01_App_Specification.md`
- `docs/02_Phased_Implementation_Plan.md`
- `docs/10_Architectural_Decision_Record_Summary.md`
- `docs/21_v1.3_Normalization_and_Design_Language.md`
- `docs/11_Model_Routing_and_Output_Contracts.md`
- `database/*.sql`
- `contracts/api/openapi.yaml`
- `contracts/schemas/*.json`
- `contracts/events/*.json`

## 10. Files an implementation agent may adapt

- UI copy and visual polish details
- exact framework-specific wiring
- queue library choice
- model-serving wrappers
- background job runner details

## 11. When to stop and revise the plan

Pause and update the pack if any of the following become true:

- the chosen embedding model cannot emit index-friendly dimensions through the serving path;
- Docling output shape differs enough to invalidate stored assumptions;
- ParadeDB version changes require materially different DDL;
- review workflows reveal the normalized data model is too rigid or too loose;
- the single-node assumption no longer holds.

The point is not blind obedience to the plan. The point is disciplined divergence.
