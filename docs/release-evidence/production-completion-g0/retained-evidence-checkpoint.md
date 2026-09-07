# Accepted fields, complete Viewer data and retained evidence checkpoint

Date: 2026-09-07. Candidate: `2439134d5de312815723c16e1d1994f35afd4b39`.

This is verified implementation progress in UI-06/UI-07, SEC-01,
X-02/X-05/X-07/X-08 and JOB-02. It does not accept G2/G3, activate native
publication, or establish production extraction quality.

## Application behavior

Migration 101 and its field decision service are integrated. Confirmation,
correction and rejection retain independent decision revisions, immutable human
history and accepted-fact projection identity. Rejected candidate values do not
reappear through a later automatic projection. The first field editor uses these
explicit decisions; complete line-item decision authority remains the separate
103 implementation lane.

The Viewer displays complete recorded fields and canonical rows, with source and
acceptance details, pagination and exact decimal formatting. Unknown runtime and
document review states have neutral, explicit labels. A document-quality task no
longer presents an inapplicable canonical-field editor. Four changed Linux
screenshots were individually compared with their prior references before the
normal full browser comparison passed.

Migration 102 retains every source-page image independently of visual embedding
eligibility. Protected, explicitly generation-scoped metadata, page and PNG routes
preserve historical source identity after supersession. The reader verifies a
private bounded spool, rechecks current document/token access after file IO and
serves those same verified bytes. It does not select a new current generation.

The review found a real reference-publication race in both 098 and 102: cleanup
could delete verified but unreferenced bytes before the database reference was
committed. Both writers now stage verified bytes before SQL and establish their
exact destination under the existing content hash lock before committing the
reference. Separate-connection tests prove cleanup-first recovery, final-claim
cancellation rollback, actual recreated-object cleanup and retained replay.

## Canonical regression validation

At `7a4377f`, the clean Oxcart validation worktree passed:

- 1,698 unit tests.
- 316 real PostgreSQL integration tests after all 45 migrations on a fresh isolated
  database, including authenticated ASGI history and both cleanup races.
- Web lint/build and 139 Linux Playwright tests using normal screenshot comparison.
  Eight tests requiring a deployed application remained skipped.

The initial static run flagged the numeric report key `revoked_token_status: 401`
as a hardcoded password. `2439134` renamed only that diagnostic key to
`revoked_credential_http_status`; no application behavior changed. The full static
gate then passed Ruff, format, contracts, Bandit, Semgrep, Pyright and Mypy
(472 source files). The unit/database/browser counts above retain their actual
tested SHA rather than being relabelled as a later full release-candidate gate.

## Real model and historical API proof

The [allowlisted machine-readable evidence](retained-evidence-2439134.json)
records the exact candidate and private-artifact hashes. A fresh isolated database
received all 45 migrations. The exposed two-page synthetic TIFF required two real
27B parse calls on Oxcart; sealed parse replay made zero additional calls.

Source retention checkpointed one page at a time, resumed, sealed both pages and
replayed with zero new pages or bytes. Blackbird's PRO 4000 produced six text
vectors at 1536 dimensions and two page-image vectors at 2048 dimensions. The
index resumed after its first saved vector and sealed; replay made zero HTTP calls.
Compatible text and visual query encoders ranked the expected source page first
for all four tiny synthetic page-query checks.

Real authentication and API routes were exercised through an in-process ASGI
client, without authentication/storage dependency overrides. Both page structures
and PNG hashes remained identical after a new processing run superseded the
source run and was itself cancelled without invocation. Unauthenticated/revoked
tokens returned 401; mismatched generation/document/page identities returned 404.
This is not a deployed reverse-proxy or browser-stack test.

An independent offline calculation rehashed the parse structure, index
configuration/manifest/completion, all eight float32 vectors and their observations,
both on-disk retained PNGs and both API page structures. It reconstructed all four
cosine rankings. The isolated database was dropped; originals and detailed
diagnostic artifacts remain in the owned private validation directory.

## Performance finding and remaining work

This probe measured 44 ms for the two text queries and 29,317 ms for the two visual
queries. The visual service logged an inference-time Triton JIT compilation of
`_triton_mrope_forward`. A predeclared follow-up of eight different synthetic
queries, each run twice sequentially, made 16 successful calls at 23.13–37.28 ms.
Repeated embeddings were numerically close rather than byte-identical; the lowest
cosine to the first encoding was 0.9995284196946985. Retained index replay itself
remains byte-identical because it performs no new inference.

These warm calls do not prove cold restart behavior, arbitrary request-shape
coverage, ranking stability or concurrent production capacity. A startup warm-up
policy, cold/shape coverage and combined document-index/query load remain X-08
work. No resident Oxcart or Blackbird model was restarted or reconfigured.

Full native classification/typed extraction, authoritative claim consumption,
coherent current publication and rollback, complete source-aware Viewer behavior,
line review, durable batch intake and representative private quality gates remain
open. The tiny exposed TIFF is not a blind corpus or source-pixel-support pass.
The previously recorded annotation-geometry qualifications still apply; neither
labels nor scores were changed to improve this result.
