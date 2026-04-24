# Database baseline

This directory contains the starting SQL baseline for the application.

## Assumptions

- PostgreSQL 17
- `pg_search` installed and preloaded
- `pgvector` installed
- application schema name: `structura`

## Apply order

1. `001_extensions.sql`
2. `010_types_and_enums.sql`
3. `020_core_tables.sql`
4. `025_baseline_identity_acl_candidate_rules.sql`
5. `030_constraints_and_triggers.sql`
6. `040_indexes_bm25_pgvector.sql`
7. `050_views_and_functions.sql`
8. `060_seed_taxonomies.sql`
9. `070_query_examples.sql` (examples only; not required for boot)

## Important notes

- ParadeDB’s `pg_search` extension must be added to `shared_preload_libraries` before `CREATE EXTENSION pg_search;` will work.
- BM25 indexes are intentionally created on base tables rather than a denormalized external search engine.
- The `embeddings` table uses variable-dimension `vector` storage so different models can coexist. Indexes are created through partial expression indexes for chosen dimensions.
- Adjust vector dimensions in `040_indexes_bm25_pgvector.sql` if the serving path emits a different dimension in production.
- JSON Schemas in `contracts/schemas/` and relational persistence in these SQL files are designed to coexist. The DB stores both normalized fields and the source JSON payload.

## Source references

- ParadeDB extension install: https://docs.paradedb.com/deploy/self-hosted/extension
- ParadeDB create index: https://docs.paradedb.com/documentation/indexing/create-index
- pgvector repository: https://github.com/pgvector/pgvector


## v1.3 baseline extension

`025_baseline_identity_acl_candidate_rules.sql` is part of the normative v1.3 baseline.

It adds:

- households, users, sessions, passkeys, API tokens;
- password credentials for local bootstrap login;
- folder ACL;
- field candidates and canonical fields;
- line item candidates and canonical line items;
- contacts and filing rules;
- watched folders;
- filter-aware chunk projection columns;
- service health and evaluation runs.

Treat it as baseline schema, not as a late optional delta.
For ordinary UI, filing, filtering, search enrichment, and exports, `canonical_fields` and `canonical_line_items` are the default accepted-fact read model. Candidate tables remain review inputs and provenance.

Auth baseline note:

- `user_password_credentials` exists for first-local-admin bootstrap and should use a strong one-way hash such as Argon2id.
- `sessions.auth_method` is part of the baseline schema so the session API contract can be satisfied without hidden application-only state.
