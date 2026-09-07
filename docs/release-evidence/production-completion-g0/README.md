# Production completion execution baseline

Date: 2026-09-07. Status: execution started; G0/G1 acceptance remains open.

The user authorized execution of the [completion plan](../../../STRUCTURA_PRODUCTION_COMPLETION_PLAN.md). Work starts on `codex/production-completion` from application commit `d2820a80641e166186bfadd10ed4902340b186ed`. Existing unrelated local changes and untracked artifacts are preserved. The approved planning documents are committed separately from implementation changes. One integrator owns commits, shared contracts, migration numbering and deployment synchronization.

## Current inventory

- Local source started at `d2820a8`; the clean Oxcart checkout initially remained at `b31cbc9` on `codex/extractive-first-uat-hardening`. No hard reset or archive migration is part of baseline preparation.
- Oxcart `/tank/repos/structura` resolves to `/tank/work/repos/structura`, the same checkout exported to Blackbird through NFS. Synchronize it once from Oxcart after the integration branch is pushed.
- Oxcart `/srv/structura` resolves to the existing ZFS tree `/tank/apps/structura` (3.06 GiB used in this inventory). PostgreSQL, original/derived/export objects and other archive datasets already exist. No new archive dataset or replacement database directory is needed.
- `/tank/venvs` now resolves to `/tank/work/venvs`; the existing Structura Python 3.12.3 environment imports the test dependencies. The earlier April guidance describing an ext4 venv location and missing runtime datasets is historical.
- No Structura application containers were present. Other projects and shared database/model services are active; validation must use explicitly owned isolated services.
- Oxcart's existing `qwen38-27b-bf16-mtp-vl-oxcart-server` remains running. The RTX PRO 6000 reported 97,887 MiB total and 94,532 MiB reserved/used; this does not measure request capacity. No service restart, reconfiguration or model inference was performed during this inventory.
- Blackbird's PRO 4000 is GPU 1, UUID `GPU-6ec4ee66-142e-34ad-e17d-a131d7153b51`, with 24,467 MiB total and 23,988 MiB free. Its PRO 6000/Gemma service remains occupied and excluded. Root storage had 312 GiB available. These snapshots must be refreshed before runtime actions.
- Blackbird's models and source paths are NFS mounts from Oxcart, not independent copies or recovery storage.

## Initial ownership and ordering

| Work | Owner | Status | Next decisive evidence |
| --- | --- | --- | --- |
| G0 source/guidance/runtime inventory and isolated validation | Integrator | In progress | Matching committed source on Oxcart; isolated fresh schema and baseline tests |
| SEC-01 current authorization and credential validity | Security lane | In progress | Live-role/token/read/write negative matrix and no denied side effects |
| JOB-01/JOB-02 claim lifecycle and domain publication | Jobs lane | In progress | Stale-owner/renewal/cancel tests, complete publication inventory and independent generation fences |
| UI-02 correction integrity | Product lane | In progress | Browser/API reject malformed/coerced values; exact valid corrections persist |
| SEC-03 public error and health truth | Integrator + product lane | In progress | Synthetic sensitive values absent from public errors/logs; unobserved health is explicit |
| X-01/Qwen-native contract and topology preparation | Integrator | Planned after shared contracts | Authenticated truthful adapter and versioned neutral parse contract; no archive cutover yet |

Migration numbers are coordinated: `090_completion_document_authorization.sql` belongs to SEC-01; `091_completion_job_claim_ownership.sql` belongs to JOB-01. Existing applied migrations remain immutable. New SQL is validated on a disposable database before any archive migration.

## Validation boundary

Use an owned disposable ParadeDB PG17 container on Oxcart with no archive bind mounts and a loopback-only dynamic port. `scripts/run_integration_tests.py` creates/drops its own uniquely named test databases. Keep all test storage in a disposable runtime root. Baseline and integration evidence must record the exact committed source; local Mac tests are preflight only.

The cached validation images observed on Oxcart are:

| Image | Local image ID |
| --- | --- |
| `paradedb/paradedb:0.21.5-pg17` | `sha256:f33870c3ae3d82cae6ae58e88e128e4381e5366d27e9b35df12c2eb7abd652e6` |
| `node:20-alpine` | `sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293` |
| `mcr.microsoft.com/playwright:v1.59.1-noble` | `sha256:b0ab6f3cb99aa7803adbc14d9027ec1785fc6e433b97e134e0f8fe61683b6b53` |

The earlier readiness review's test counts and June model UAT remain historical evidence. This record does not close fresh gates, prove Qwen-native parsing, or declare a production deployment. G2/G3 remain prerequisites for Phase 9; later features follow the root sequence. ADRs 0008/0009 supersede historical Docling/8B/Granite deployment instructions while preserving original evidence, model provenance, validation and human-review policy.
