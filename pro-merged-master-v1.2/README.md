# Structura agentic coder pack

This planning pack is a complete handoff bundle for building a local-first, AI-augmented document filing cabinet application on the target workstation described in the project brief: Ubuntu 24.04 on a Lenovo P620, ZFS storage, Docker-based deployment, local Postgres plus ParadeDB plus pgvector, and locally served document and multimodal models.

The pack is intentionally split into human-readable design documents, machine-readable contracts, and database / infrastructure artifacts. An agentic coder should be able to start at `AGENT_START_HERE.md`, work in sequence, and implement the system without needing to reverse-engineer the architecture from conversational prose.

## What is in this pack

Markdown files are authoritative in this normalized v1.3 pack. The DOCX files are convenience exports regenerated from the Markdown sources.


- `AGENT_START_HERE.md`  
  Strict reading order, implementation order, hard rules, and stop/go gates.
- `docs/01_App_Specification.docx` and `docs/01_App_Specification.md`  
  Full product and system specification.
- `docs/02_Phased_Implementation_Plan.docx` and `docs/02_Phased_Implementation_Plan.md`  
  A detailed implementation roadmap broken into phases and subphases.
- `docs/03_Agent_Bootstrap_and_Execution_Order.md`  
  The exact way an implementation agent should sequence work.
- `docs/04_User_Stories_and_Acceptance_Criteria.md`  
  Product backlog with acceptance criteria.
- `docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`  
  Latency, correctness, security, privacy, resilience, and audit requirements.
- `docs/06_Testing_QA_and_Release_Strategy.md`  
  Golden corpus, evaluation strategy, regression gates, and release procedure.
- `docs/07_Repository_Layout_and_Coding_Standards.md`  
  Suggested monorepo structure and engineering standards.
- `docs/08_ZFS_Datasets_and_Storage_Plan.md`  
  Full dataset plan and storage policy.
- `docs/09_Deployment_and_Runtime_Architecture.md`  
  Service topology, ports, mounts, GPU usage, and runtime behavior.
- `docs/10_Architectural_Decision_Record_Summary.md`  
  Key decisions the implementation should treat as default unless explicitly superseded.
- `docs/11_Model_Routing_and_Output_Contracts.md`  
  How Docling, Granite, Qwen, structured outputs, and evidence linkage are expected to work.
- `docs/19_v1.2_Normalization_and_Source_of_Truth.md`  
  The historical v1.2 decision table that resolves earlier merged-pack contradictions.
- `docs/20_Codex_xhigh_Feedback_Resolution.md`  
  A concise record of what was changed in response to the xhigh review.
- `docs/21_v1.3_Normalization_and_Design_Language.md`  
  The v1.3 normalization layer, source hierarchy, and Structura workbench design language.
- `docs/12_Risk_Register_and_Open_Questions.md`  
  Risks, mitigations, and open design questions.
- `database/*.sql`  
  Schema, enums, indexes, helper views, seed taxonomy, and example queries.
- `contracts/api/openapi.yaml`  
  Core HTTP API contract.
- `contracts/schemas/*.json`  
  JSON Schemas for extraction outputs and review actions.
- `contracts/events/*.json`  
  Queue payload contracts for ingestion, extraction, embedding, and analysis jobs.
- `infrastructure/zfs/create_datasets.sh` and related files  
  ZFS creation script and dataset matrix.

## Recommended reading order

1. `AGENT_START_HERE.md`
2. `docs/01_App_Specification.md`
3. `docs/02_Phased_Implementation_Plan.md`
4. `docs/10_Architectural_Decision_Record_Summary.md`
5. `docs/21_v1.3_Normalization_and_Design_Language.md`
6. `docs/19_v1.2_Normalization_and_Source_of_Truth.md`
7. `docs/11_Model_Routing_and_Output_Contracts.md`
8. `docs/07_Repository_Layout_and_Coding_Standards.md`
9. `database/README.md`
10. `contracts/api/openapi.yaml`
11. `contracts/schemas/*.json`
12. `docs/04_User_Stories_and_Acceptance_Criteria.md`
13. `docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`
14. `docs/06_Testing_QA_and_Release_Strategy.md`
15. `docs/08_ZFS_Datasets_and_Storage_Plan.md`
16. `docs/09_Deployment_and_Runtime_Architecture.md`
17. `docs/20_Codex_xhigh_Feedback_Resolution.md`

## Default implementation assumptions

- Database: PostgreSQL 17 with `pg_search` and `pgvector`
- Search pattern: BM25 on ParadeDB plus pgvector semantic retrieval plus app-side RRF plus optional reranking
- Canonical document representation: Docling JSON as the lossless structural artifact
- Typed extractions: JSON validated with Pydantic / JSON Schema
- Object storage: content-addressed filesystem store on ZFS, with a clean abstraction that allows MinIO later
- Model serving: local inference only by default, using vLLM where practical
- Frontend: React + Vite / TypeScript as the normative v1.3 default; Next.js only by explicit ADR change
- API: FastAPI / Python / Pydantic
- Queue / async execution: `pipeline_jobs` as the durable job ledger plus PGMQ as the preferred transport; Redis/RQ/Dramatiq only as a documented fallback profile
- Deployment: Docker Compose first; k3s is a later operational option, not a v1 requirement
- Authentication: household-aware schema from day one, DB-backed sessions required, bootstrap password stored via a dedicated strong-hash credential table, session `auth_method` persisted, magic-link acceptable for initial setup, passkeys recommended before any non-local exposure
- Privacy posture: local-first, no external model calls by default, original bytes preserved immutably

## Notes on source material

The design choices in this pack were cross-checked against current public documentation for Docling, Granite 4.0 Vision, Qwen3-VL, Qwen3 Embedding, Qwen3-VL-Embedding, ParadeDB, pgvector, and vLLM. The goal is not to mirror those docs, but to turn them into a coherent implementation plan for this specific application.

## External references used while preparing the pack

- Docling overview: https://docling-project.github.io/docling/
- DoclingDocument concept: https://docling-project.github.io/docling/concepts/docling_document/
- Docling information extraction: https://docling-project.github.io/docling/examples/extraction/
- Docling document converter: https://docling-project.github.io/docling/reference/document_converter/
- Granite 4.0 3B Vision model card: https://huggingface.co/ibm-granite/granite-4.0-3b-vision
- Qwen3-VL-8B Instruct model card: https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct
- Qwen3-Embedding-4B model card: https://huggingface.co/Qwen/Qwen3-Embedding-4B
- Qwen3-VL-Embedding repository: https://github.com/QwenLM/Qwen3-VL-Embedding
- vLLM Qwen3-VL recipe: https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3-VL.html
- vLLM structured outputs: https://docs.vllm.ai/en/latest/features/structured_outputs/
- ParadeDB introduction: https://www.paradedb.com/blog/introducing-paradedb
- ParadeDB create index: https://docs.paradedb.com/documentation/indexing/create-index
- ParadeDB simple introduction: https://docs.paradedb.com/welcome/introduction
- ParadeDB indexing JSON: https://docs.paradedb.com/documentation/indexing/indexing-json
- ParadeDB BM25 scoring: https://docs.paradedb.com/documentation/sorting/score
- ParadeDB facets: https://docs.paradedb.com/documentation/aggregates/facets
- ParadeDB RRF explainer: https://www.paradedb.com/learn/search-concepts/reciprocal-rank-fusion
- ParadeDB self-hosted extension: https://docs.paradedb.com/deploy/self-hosted/extension
- pgvector repository: https://github.com/pgvector/pgvector


## v1.1 merged addendum

This copy includes a selective integration of the uploaded golden master. The base handoff bundle remains the implementation backbone, but the following new files add the best golden-master ideas:

- `docs/13_Golden_Master_Review_and_Merge_Plan.md`
- `docs/14_Canonicalization_Candidate_Authority_Model.md`
- `docs/15_PGMQ_and_Worker_Strategy.md`
- `docs/16_Auth_ACL_Household_Model.md`
- `docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`
- `docs/18_Filter_Aware_Vector_Search_Addendum.md`
- `contracts/schemas/field_candidate.v1.schema.json`
- `contracts/schemas/canonical_field.v1.schema.json`
- `contracts/schemas/filing_rule.v1.schema.json`
- `contracts/schemas/folder_acl.v1.schema.json`

The golden master is treated as a refinement source, not as a replacement for the fuller handoff pack.


## v1.2 normalization note

This normalized copy resolves the main contradictions in the earlier merged pack.

Historical v1.2 defaults, retained and carried into v1.3 unless superseded, are:

- React + Vite for the frontend workbench
- FastAPI for the API
- filesystem-backed content-addressed storage on ZFS
- `pipeline_jobs` as the durable application job ledger
- PGMQ as the preferred queue transport profile
- Redis only as an optional fallback profile
- household-aware auth and folder ACL in the baseline schema
- DB-backed sessions as required
- bootstrap password credentials stored explicitly in the baseline schema
- multipart upload as the normative browser/API ingest contract

The v1.1 addendum docs remain in the pack as rationale and merge history, but the normative baseline for implementation is the combination of:
- `AGENT_START_HERE.md`
- `docs/10_Architectural_Decision_Record_Summary.md`
- `docs/19_v1.2_Normalization_and_Source_of_Truth.md`
- `database/*.sql` in the documented apply order
- `contracts/api/openapi.yaml`
- `contracts/schemas/*.json`

## v1.3 normalization note

This copy completes a second normalization pass focused on product identity, contract/database alignment, evidence quality, protected asset access, and UI direction.

Normative v1.3 additions are:

- Structura is the only canonical product namespace.
- `docs/21_v1.3_Normalization_and_Design_Language.md` supersedes older source-order notes where it conflicts with them.
- accepted canonical fields and line items are the default read model for UI, filtering, filing, search, and export.
- evidence references for trusted extracted values must include a concrete locator beyond page number.
- object storage is separated into canonical, derived, and export mountpoints.
- the OpenAPI contract covers the baseline product surfaces, including candidates, canonical review actions, folders, tags, relationships, contacts, filing rules, watched folders, protected assets, exports, jobs, and admin retry.
