# 13 — Golden Master Review and Merge Plan

Historical note: In v1.3 this document is background rationale unless explicitly referenced by the ADR summary or the current normalization doc.

Prepared: 2026-04-23

## 1. Executive judgment

The golden master is **not better as a replacement** for this handoff bundle. It is too compact to serve as an executable implementation handoff. It lacks the machine-readable SQL, OpenAPI, event contracts, extraction schemas, detailed phase plan, and ZFS/infrastructure artifacts that an agentic coder needs.

It **is** valuable as an architectural critique. It surfaces several ideas that should be merged into this bundle:

1. Candidate-vs-canonical extraction model.
2. Explicit typed authority model for Docling, Qwen, Granite, validators, and humans.
3. Postgres-native queueing via PGMQ as a preferred v1 option if the extension stack is compatible.
4. Household/passkey/ACL direction.
5. Contacts and transparent filing rules.
6. Watch-folder intake as a real service, not merely an enum value.
7. Filter-aware vector search caveats.
8. Operational status, dead-letter, import, backup, restore, and evaluation readiness as launch criteria.

The right action is **selective integration**, not replacement.

## 2. What the golden master does better

### 2.1 Candidate-vs-canonical data model

The golden master clearly distinguishes:
- raw artifacts,
- extraction runs,
- field candidates,
- line item candidates,
- canonical fields,
- canonical line items,
- review tasks,
- review events.

This is the most important improvement. The previous bundle stores extraction outputs and normalized fields, but it does not make the candidate/canonical split explicit enough. A serious review workflow needs to preserve competing model outputs and then select accepted canonical facts.

### 2.2 Authority model

The golden master defines a useful source authority matrix:

- Docling: structure, reading order, provenance, page geometry.
- Qwen: classification, broad semantics, OCR rescue, narrative understanding.
- Granite: tables, KVPs, line items, service lines.
- Rules/validators: deterministic normalization and consistency checks.
- Human: final canonical override.

This should be adopted. It prevents accidental “winner takes all” extraction behavior.

### 2.3 PGMQ queue strategy

The golden master’s PGMQ proposal is attractive because this application is single-node, Postgres-centered, and local-first. It would remove Redis as a required operational dependency and keep job state closer to the rest of the data plane.

The caveat: this should be treated as a preferred default, not a dogma. If ParadeDB/Postgres packaging, extension compatibility, or Python worker ergonomics become painful, the existing durable `pipeline_jobs` table plus Redis queue remains a valid fallback.

### 2.4 Household auth and ACL

The previous bundle intentionally kept auth single-user-friendly. The golden master is stronger here: household records are naturally multi-person, and folder/document ACL should be designed early even if the first deployment uses one user.

Adopt:
- households
- users
- WebAuthn credentials
- sessions
- magic links for invite/recovery
- API tokens
- folder ACLs
- document ACL check through API before asset access

### 2.5 Contacts and filing rules

The previous bundle has `parties` and document party mentions, but the golden master’s “contacts” and “rules” surfaces are productively concrete. This is especially useful for vendors, providers, payers, law firms, government agencies, and recurring correspondents.

Adopt:
- contacts as normalized entities
- filing rules as inspectable dry-run-capable automation
- rule suggestions with explanations
- no hidden filing automation without reviewable reason

### 2.6 Search caveats

The golden master explicitly warns that pgvector HNSW filtering can under-return because filtering may occur after the approximate index scan. The previous bundle mentions dimension-conscious design, but should more explicitly include:
- filter-aware vector query planning
- partial vector indexes where useful
- iterative scans where available
- RRF candidate fusion before reranking
- B-tree indexes on frequent filters

### 2.7 Operational launch bar

The golden master correctly treats import, backup, restore, dead-letter handling, status, and evaluation as v1 readiness items. These should remain in the implementation plan and should not be deferred as “ops chores.”


### 2.8 Frontend workbench stack

The golden master’s React/Vite recommendation is reasonable. This app does not need server-side rendering, and a Vite SPA behind FastAPI/reverse proxy may be simpler than Next.js. The merged recommendation is not to hard-require either stack; it is to require a workbench-quality React UI with PDF viewer performance, keyboard navigation, command palette, and evidence-first review flows.

## 3. What the original bundle does better

### 3.1 Implementation completeness

The original bundle has:
- detailed app specification
- detailed phased implementation plan
- agent execution order
- user stories and acceptance criteria
- SQL DDL
- OpenAPI contract
- event schemas
- extraction schemas
- ZFS dataset plan
- runtime service matrix
- risk register
- QA plan

The golden master is more of a strategic synthesis than a handoff pack.

### 3.2 Model routing nuance

The original bundle is more conservative and, in my view, better on model routing. The golden master says Qwen runs on every document. That is too expensive and too likely to blur deterministic parsing with semantic interpretation.

Recommended merged stance:
- Docling runs on every document.
- Qwen does **not** necessarily run deep extraction on every document.
- Qwen may run lightweight classification or rescue tasks.
- Granite runs by policy for structured business documents.
- Qwen deep pass is escalation/fallback/arbitration, not blanket default.

### 3.3 Object storage nuance

The golden master chooses MinIO. The original bundle chooses filesystem-backed content-addressed storage on ZFS with MinIO compatibility later.

Recommended merged stance:
- keep the storage abstraction;
- keep filesystem object storage as the simplest v1 default;
- provide a MinIO-compatible layout and optional deployment path;
- do not make MinIO mandatory unless S3 semantics are needed immediately.

### 3.4 Existing machine-readable contracts

The original bundle already has JSON Schemas and event contracts. The golden master has better ideas but fewer executable artifacts. The merged result should extend the original contracts, not replace them.

## 4. Recommended merged decisions

| Surface | Keep original? | Integrate golden idea? | Final recommendation |
|---|---:|---:|---|
| Overall bundle | Yes | Yes | Use original bundle as base; add golden deltas |
| Docling canonical parse | Yes | Yes | Docling always; VLM escalation |
| Qwen usage | Mostly | Partially | Qwen lightweight/semantic/escalation; not blanket heavy extraction |
| Granite usage | Yes | Yes | Adaptive specialist for tables/KVP/line items |
| Queue | Partially | Yes | Prefer PGMQ if extension stack works; keep durable job ledger and Redis fallback |
| Object storage | Yes | Partially | Filesystem-first abstraction; optional MinIO profile |
| Data model | Partially | Strongly yes | Add candidate/canonical split |
| Auth | Partially | Strongly yes | Add household/passkey/ACL design now |
| Contacts/rules | Partially | Yes | Add as v1.1 surfaces |
| Search | Yes | Yes | Add filter-aware vector planning requirement |
| Frontend | Yes | Yes | Add workbench shortcuts, command palette, status, contacts/rules |
| Contracts | Yes | Yes | Add schemas for candidates, canonical facts, rules, ACLs |
| Implementation plan | Yes | Yes | Insert new subphases for auth/ACL, candidates, rules, watcher, eval/status |

## 5. Files added in this v1.1 merged pack

- `docs/13_Golden_Master_Review_and_Merge_Plan.md`
- `docs/14_Canonicalization_Candidate_Authority_Model.md`
- `docs/15_PGMQ_and_Worker_Strategy.md`
- `docs/16_Auth_ACL_Household_Model.md`
- `docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`
- `docs/18_Filter_Aware_Vector_Search_Addendum.md`
- `database/025_baseline_identity_acl_candidate_rules.sql`
- `contracts/schemas/field_candidate.v1.schema.json`
- `contracts/schemas/canonical_field.v1.schema.json`
- `contracts/schemas/filing_rule.v1.schema.json`
- `contracts/schemas/folder_acl.v1.schema.json`

## 6. Files that should be edited during a true source-controlled implementation

This pack adds delta artifacts rather than destructively rewriting the base files. In a real repo, an implementation agent should fold the delta into:
- `database/020_core_tables.sql`
- `database/040_indexes_bm25_pgvector.sql`
- `contracts/api/openapi.yaml`
- `docs/02_Phased_Implementation_Plan.md`
- `docs/04_User_Stories_and_Acceptance_Criteria.md`
- `docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`
- `docs/09_Deployment_and_Runtime_Architecture.md`
- `docs/10_Architectural_Decision_Record_Summary.md`

## 7. Bottom line

The golden master is a good editor, not a good replacement. The best final pack is the original handoff bundle plus the candidate/canonical model, authority matrix, PGMQ option, auth/ACL model, rules/contacts/watcher surfaces, and filter-aware vector search implementation guidance.
