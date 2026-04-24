# Codex xhigh feedback resolution

This note records the normalization work performed after the xhigh static review of the v1.1 merged pack.

## Findings accepted as materially correct

1. Multiple incompatible defaults were still exposed as if they were equally authoritative.
2. The upload API contract was inconsistent with the implementation plan and app spec.
3. The auth model was upgraded in prose/SQL but not normalized across the contracts and phased plan.
4. The database baseline still treated the golden-master merge as a late delta even though the pack described it as baseline.
5. Finder metadata/noise should not be shipped if present.

## v1.2 resolution summary

### Default stack normalization
v1.2 now chooses one normative baseline:
- React + Vite frontend
- FastAPI backend
- content-addressed filesystem object storage on ZFS
- `pipeline_jobs` durable job ledger
- PGMQ as preferred queue transport
- Redis only as fallback profile
- household-aware schema and folder ACL in baseline
- DB-backed sessions required
- multipart upload as the normative ingest contract

### Source-of-truth normalization
New normative hierarchy:
1. ADR summary
2. `docs/19_v1.2_Normalization_and_Source_of_Truth.md`
3. database apply order
4. OpenAPI
5. JSON Schemas
6. AGENT_START_HERE

Docs 13 through 18 are now explicitly background rationale, not competing defaults.

### OpenAPI normalization
The upload contract now uses `multipart/form-data` with a binary `file` part.
The contract pack now includes auth/session endpoints.

### Database normalization
`080_gold_master_delta_schema.sql` has been retired from the normative baseline.
Its contents were promoted into `025_baseline_identity_acl_candidate_rules.sql` and the documented apply order was updated.

### Runtime normalization
Deployment and bootstrap docs no longer present Redis as a core equal default.
Redis remains documented as a fallback profile only.

## Post-normalization hardening

After the initial v1.2 normalization pass, the remaining implementation gaps were closed as follows:

- the baseline schema now includes explicit bootstrap password credential storage and persists session `auth_method`;
- the OpenAPI contract now defines explicit security schemes, stronger session request validation, and a single API port baseline;
- ingestion source identifiers were normalized across DB enums, OpenAPI, and ingest job payloads;
- the phased plan and bootstrap order now place auth/session work before protected document routes rather than in late hardening;
- the runtime service matrix now matches the normative service names and port map used elsewhere in the pack;
- Finder metadata noise remains non-normative and should be stripped from any final packaged handoff.

## Remaining intentional flex points

A few choices remain intentionally flexible, but not ambiguous:

- Redis fallback remains documented if PGMQ packaging blocks progress.
- Passkeys remain the preferred hardening path, but bootstrap password or magic-link setup is acceptable for first local admin creation.
- MinIO remains optional later, not normative for v1.2.

## v1.3 follow-up

The v1.3 pass adds product identity cleanup, stronger evidence requirements, canonical fact authority, broader OpenAPI coverage, corrected storage mount paths, and a concrete Structura workbench design language. See `docs/21_v1.3_Normalization_and_Design_Language.md` for the current normalization layer.
