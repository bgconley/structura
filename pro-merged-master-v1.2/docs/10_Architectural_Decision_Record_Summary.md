# Architectural decision record summary

This file summarizes the default decisions for v1. If implementation diverges, update this file and explain why.

## ADR-001: local-first, original-asset-immutable
Decision: original uploaded artifacts are immutable and remain the source of truth.

## ADR-002: Docling is the canonical structural layer
Decision: Docling JSON is the durable canonical parse artifact. Model-specific outputs are derivatives.

## ADR-003: Postgres plus ParadeDB plus pgvector is the core data platform
Decision: use one primary Postgres database with `pg_search` for BM25 and `pgvector` for semantic retrieval.

## ADR-004: filesystem object store first
Decision: use a content-addressed filesystem object store on ZFS first, with abstraction for future MinIO compatibility.

## ADR-005: Docker Compose before k3s
Decision: a single-host Compose deployment is the starting point; k3s is later if scale or operations justify it.

## ADR-006: schema-validated extraction
Decision: document-family extractions must validate against explicit JSON Schemas or equivalent Pydantic models.

## ADR-007: evidence is mandatory for trusted extracted fields
Decision: user-visible trusted extracted values must carry page-linked provenance with a concrete locator.

## ADR-008: hybrid retrieval by RRF
Decision: combine lexical and semantic candidates with RRF or weighted RRF; do not normalize unlike score scales directly.

## ADR-009: analysis is optional and separate
Decision: analysis notes are persisted separately and never silently overwrite accepted extracted data.

## ADR-010: single-household baseline, future multi-household possible
Decision: v1.3 is optimized for a single-household local deployment, but the architecture should already include household-aware ownership and ACL structures.

## ADR-011: review workflow is first-class
Decision: uncertainty results in review tasks, not silent confidence theater.

## ADR-012: model outputs are versioned
Decision: persist model name, model version, prompt version, and extraction schema version for every meaningful run.

## ADR-013: dimension-conscious vector design
Decision: standardize embedding dimensions in ways that index cleanly in pgvector; do not let model defaults quietly dictate poor storage choices.

## ADR-014: content-addressed storage and DB catalog separation
Decision: blobs live in object storage; the DB stores metadata, provenance, relationships, and search state.

## ADR-015: boring operational reliability over cleverness
Decision: prefer inspectable workers, explicit jobs, and deterministic pipelines over opaque “smart” orchestration.


## v1.1 ADR additions from golden-master review

## ADR-016: candidate-vs-canonical facts
Decision: preserve field and line-item candidates separately from canonical accepted facts. Canonical values are promoted by validation, authority weighting, or human review.

## ADR-017: PGMQ default transport, durable job ledger retained
Decision: use `pipeline_jobs` as the durable application job ledger and PGMQ as the normative queue transport profile. Redis/RQ/Dramatiq is a fallback profile only if PGMQ packaging blocks progress.

## ADR-018: household/auth/ACL model is baseline
Decision: include household, user, password-credential, session, API token, and folder ACL structures in the baseline schema. DB-backed sessions are required for v1.3, and sessions persist `auth_method` so the API contract does not depend on hidden application-only state. Passkeys are recommended hardening, but bootstrap password or magic-link setup is acceptable for the first local deployment.

## ADR-019: contacts and rules are product surfaces
Decision: model contacts and transparent filing rules as first-class v1.1 surfaces, with dry-run and audit behavior.

## ADR-020: filter-aware vector search
Decision: vector retrieval must account for SQL filters, ACL, and approximate index behavior. Use chunk projection columns, B-tree filters, RRF fusion, and optional iterative scans/tuned `hnsw.ef_search`.


## ADR-021: React + Vite workbench frontend
Decision: for v1.3, use React + Vite for the frontend workbench. Server-side rendering is not a product requirement. If a team wants Next.js later, that requires an explicit ADR update and runtime contract review.


## ADR-022: multipart upload is normative
Decision: browser and local API ingestion of original files uses `multipart/form-data` with a binary `file` part. Base64 document upload is not the primary contract.

## ADR-023: auth/session API surface is required
Decision: the contract pack must define login/session/logout and session introspection surfaces, plus explicit security-scheme expectations for session cookies and automation tokens, so auth is not left implicit.


## v1.3 ADR additions

## ADR-024: Structura namespace is canonical
Decision: Structura is the only product and runtime namespace in the pack. Legacy pre-Structura names must not appear in service names, cookies, queues, example hosts, object paths, or generated artifacts.

## ADR-025: trusted evidence requires concrete locators
Decision: page number alone is insufficient for trusted extracted fields. Evidence must include at least one concrete source locator such as a bounding box, element id, table row reference, text span, or source text excerpt.

## ADR-026: canonical facts are the default read model
Decision: `canonical_fields` and `canonical_line_items` are the default read path for UI, filtering, filing, search enrichment, and export. Candidate tables remain review inputs and extraction provenance; older projection tables are not the final authority for accepted facts.

## ADR-027: Structura uses a calm evidence workbench design language
Decision: the UI should prioritize inbox, review, evidence inspection, filing, and search workflows over dashboard theater. Operational health and pipeline state remain visible but subordinate to document work.
