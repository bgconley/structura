# Embedding and processing integrity checkpoint

Date: 2026-09-07. G1/G2/G3 remain open. Source, pushed branch and Oxcart's shared
checkout were synchronized at `7445bf1` for this checkpoint.

## Processing and session integrity

The clean Oxcart worktree at `25ca83f` passed **1,371 unit tests**. At `7445bf1`,
the fresh disposable PostgreSQL gate passed **126 integration tests** after applying
all **39 migrations through 096**. Protected logs remain under the owned temporary
validation root. No archive database or source objects were migrated.

The new tests cover immutable processing-run identities, desired-generation
supersession, claimed-worker checkpoint writes, cancellation, concurrent request
idempotency, exact source/configuration matching, immutable history, sealed
structures and document-deletion cascades. Session binding and the single-winner
magic-link race are also included. The first runs exposed fixture errors: the
bootstrap result contains no role attribute, the scope error wording changed, and
rolling back an intentional database error cleared the connection's transaction-local
search path. The fixtures were corrected; no authority or concurrency scenario was
removed. Processing-run tests now exercise real PostgreSQL locking and transactions.

This is candidate storage only. It does not yet prove current-parse/index activation,
all downstream generation bindings, asynchronous actor reauthorization or production
chaos recovery. Existing accepted facts and historical parse projections remain intact.

## Real embedding inference

The [runtime profile](../../../infrastructure/models/blackbird-embedding-validation-20260907.md)
records the two authenticated BF16 pooling services resident together on Blackbird's
PRO 4000. The existing Oxcart27B and Blackbird PRO6000 services were preserved.

The first raw image invocation returned a valid normalized 2,048-dimensional vector
in **36.814 seconds**, including first-use runtime work. The corresponding relevant
and unrelated synthetic visual query similarities were approximately **0.423** and
**0.137**. Unauthenticated inference returned 401. This is a functional smoke, not
representative corpus quality evidence.

The committed application adapter probe at `7445bf1` then exercised real document
text, text query, image-only and mixed ingestion, and visual query requests. It
validated exact response model/profile, declared artifact revision, dimensions,
finite nonzero vectors, response indexes and full input identity. Image-only and
mixed inputs with the same pixels had different fingerprints. Relevant synthetic
documents ranked above unrelated ones in every round.

| Round | Four paths | Total elapsed | Text ingestion | Text query | Image/mixed ingestion | Visual queries |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 0 | Sequential warmup | 286 ms | 42 ms | 24 ms | 161 ms | 51 ms |
| 1 | Concurrent | 29,395 ms | 29,387 ms | 29,380 ms | 128 ms | 104 ms |
| 2 | Concurrent repeat | 136 ms | 50 ms | 28 ms | 127 ms | 104 ms |

The first concurrent text latency spike is unresolved performance evidence; it is
not excluded from the report or represented as warm throughput. Startup/shape
warmup, cold/warm caching, longer requests, sustained queue behavior, cancellation,
outage recovery and user-facing latency budgets still require measurement. Three
small rounds cannot establish p95 or production capacity.

The [machine-readable result](embedding-adapter-7445bf1.json) contains the full
synthetic smoke summary without credentials, document contents or raw vectors.
Model revision values are declared deployment identity; the response's served-model
name alone does not attest checkpoint bytes. The separate cache verification record
and exact mounts establish the observed deployment artifact, with the text-cache
completeness limitation documented in the runtime profile.

No active index or query profile was switched. Complete-input persistence, source
generation rebuilds, atomic activation, representative retrieval quality and complete
application workflows remain necessary before G3 can close.
