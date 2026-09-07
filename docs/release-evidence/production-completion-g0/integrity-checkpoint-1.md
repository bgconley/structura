# Integrity checkpoint 1

Date: 2026-09-07. Candidate: `c250427`, on `codex/production-completion`.
Local source, origin branch and Oxcart shared checkout matched this candidate.
Tests ran from a clean detached worktree with deployment settings excluded.

## Verified behavior

- Current membership, role, token scope and document/folder write permission constrain existing mutations. Real two-connection races cover relationship create/accept/reject, filing suggestion reject/defer and contact merge versus a new private link. A review-only token can decide relationships but cannot create them.
- Seven queue workers renew claim-token leases and fence the enumerated publication transactions. Reclaimed/cancelled/expired attempts cannot renew, complete, fail or commit the tested domain mutations. Independent desired-run and descendant authority remain separate work.
- Numeric/boolean corrections reject malformed, coerced, nonfinite, overprecision or mismatched-currency values. Valid zero and negative corrections preserve canonical values and history. Additional date/JSON/revision controls are the next checkpoint.
- Public API/job errors and legacy job result projection exclude raw source text, paths and arbitrary metadata. API logs use declared route templates; interrupted streams remain failed/incomplete with a safe exception. Fresh cancellation/lease-expiry events replace earlier private error metadata.
- Document rows use actual lifecycle state. Fabricated backup/storage/worker/count badges were removed; missing measurements remain explicit.

## Candidate checks

| Check | Result |
| --- | --- |
| Oxcart Python unit suite | 1,263 passed |
| Oxcart fresh PostgreSQL integration suite | 79 passed |
| Fresh migration registry | 34 scripts through 091; rerun idempotency included |
| Pinned Node 20 Linux web lint/build | Passed |
| Local preflight Ruff/format, contracts, mypy/targeted Pyright | Passed for the integrated changes |

Protected runtime logs are `integrity-unit-c250427.log`, `integrity-integration-c250427.log`, and `web-build-c250427.log` in the owned Oxcart validation root. The database uses a temporary volume, loopback-only port, explicit ownership label and no archive mounts. Web verification copied the clean source into a disposable container workspace with executable temporary storage; it did not write Linux dependencies into the shared checkout.

The initial candidate omitted migrations 090/091 from the explicit registry. The next commit registered them and changed the migration coverage check to detect omitted numbered SQL files. The resulting database run exposed an empty legacy relationship evidence object being converted into an invalid reference; it now remains an empty evidence list. A preexisting rollback test was updated to assert the new safe HTTP 500 boundary while retaining its no-mutation database assertion. The final full run above passed without excluding those regressions.

## Actual 27B connection proof

At `f641960`, `scripts/gpu/probe_ingestion_service.py` made two sequential authenticated synthetic calls through the new Structura clients to the existing Oxcart service. Both schema-constrained text and image responses matched their distinct expected reference/amount pairs. The profile is `qwen3.8-27b-bf16-oxcart-ingestion:v1`, served name `qwen38-27b-bf16-oxcart`, source engine `qwen3_8_27b`. Observed latency was 1,226 ms for text and 486 ms for image, both with `finish_reason=stop`. This is bounded adapter proof, not a document-quality or capacity benchmark.

Observed serving image ID: `sha256:fc120ece0a388cc0aa1caad4a9f1cd92113484ab7ec2fd0efadd62585be05bf8`. Model `config.json` SHA-256: `191e0af232104ed8b65258cf3fb2b842e288008baca7633c11b82a1ac7203aab`. The config hash is not a full weights/revision attestation. Observed resident configuration was BF16, automatic KV dtype, context 262144, four sequences, 8192 batched tokens and MTP with three speculative tokens. Structura's profile imposes smaller request limits without modifying those server settings. Credentials were read privately into the disposable validation secret path and were not committed or printed.

No resident model restart/reconfiguration, application deployment, archive migration or reparse occurred. Blackbird embedding deployment and quality/capacity proof remain open.

## Remaining gate scope

G1 is open: descendant/run-generation authority, session-bound CSRF/recovery races, asynchronous actor reauthorization, full correction concurrency and remaining workspace stale-state checks require their own evidence. G3 is open: neutral parse persistence/history, Qwen-native end-to-end parsing/extraction, authoritative claims, original-scored quality, real text/visual retrieval and simultaneous ingestion/query capacity. No Phase 9 or release acceptance is implied by this checkpoint.
