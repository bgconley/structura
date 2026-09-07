# Combined page understanding checkpoint

Status: verified contract, adapter and historical-reader slices of X-01–X-05 and
JOB-02. Candidate `30284d2`; G2/G3 and native publication remain open. The
[upload checkpoint](upload-claims-checkpoint.md) records the separately verified
application upload workflows.

## Implemented behavior

The frozen `structura.page_understanding.v2` contract is integrated at `312e305`.
It retains searchable structure and separately typed classification and extraction
from one response. Classification preserves the 23 existing families; the receipt,
invoice and EOB ledgers account for 109 field obligations. Exact quotes, source
occurrences and distinct physical rows are required. Missing, ambiguous, unreadable
and unsupported content remains explicit. Model-reported completeness is not
measured recall or independent source support.

`30284d2` adds explicit v2 configuration and invocation types, a combined adapter,
shared raw-output dispatch, checkpoint/resume integration and coordinated retained
evidence, indexing-preparation and evaluation readers. V1 remains the default.
Golden checks preserve historical v1 configuration, invocation, checkpoint and
capture instance bytes/hashes. The expanded outer JSON-schema artifacts change
because they now describe both versions; unknown versions fail closed.

V2 freezes the original inventory, bounded native-PDF context, actual prompt/schema/
definition and adapter implementation hashes, request settings and deployment
declaration. Native PDF hints are untrusted source context, distinct from model
transcription. Execution rechecks original context and current authority before
inference, then independently fences each checkpoint and seal. No transaction
spans inference. Completed pages replay without new calls; no second model stage
is introduced. A missing server-reported revision stays null.

Migration 105 retains its separate recorded-text normalization semantics and old
claim identities. It may consume v2 transcription without claiming that those
deterministically derived values were typed members emitted by the model.

## Canonical verification

The integrator reviewed the production changes, committed and pushed `30284d2`,
fast-forwarded the shared Oxcart checkout once, and validated a clean detached
worktree. No archive data, model service or production default changed.

| Gate | Result |
| --- | --- |
| Static | Ruff, format, contract validation, Bandit/Semgrep, Pyright and Mypy passed; Mypy checked 557 production source files. |
| Python unit | 1,960 passed, five Node-dependent skips in 60.43 seconds. The separately executed Node socket proof remains identified in the upload checkpoint. |
| PostgreSQL | 477 passed in 257.39 seconds after all 48 migrations through 105 on a fresh isolated database. |
| Pinned Linux web/browser | Lint/build and all 219 ordinary browser tests passed in 3.7 minutes; 12 explicitly live-stack tests skipped. Normal screenshot comparison stayed enabled. |
| Focused local preflight | 79 pure-contract tests and 30 versioning/execution/capture tests passed; these are subsets of the canonical unit gate. |

The new SQL cases retain v2 captures and page media through supersession or
cancellation, prepare the hidden native index, preserve 105 reconstruction without
raw-envelope interpretation, and reject an in-flight old response after an
independent connection starts a new run. Other cases cover exact request/image/raw
binding and a real HTTP adapter driven by mock transport. That transport test is
not a live 27B result. Five of the live upload workflows skipped by the ordinary
suite were executed against the separate disposable stack described in the upload
checkpoint; the remaining historical live suites are not claimed as executed here.

The model-facing schema is 23,705 compact UTF-8 bytes and the synthetic two-line
contract response is 9,076 bytes. These are not token measurements. Actual limits
remain distinct: 160 KiB prompt, 10 MiB image, 1 MiB decoded HTTP response envelope,
2,000,000 captured raw characters and 16 MiB standalone decoder ceiling. Dense-page
output capacity is unqualified; responses are never silently truncated to fit.

## Next dependencies

The integrator allocated `106_completion_native_model_emission.sql` for exact
persisted-raw member import. It is in progress and was not included in the 48-script
gate above. Its claims, classification and page coverage remain immutable derived
records; canonical/review publication requires its own subsequent integration.

A new bounded three-page synthetic probe will test actual 27B combined output and
zero-call replay. Its sources and expectations must be fixed before inference.
This checkpoint contains no live v2 quality result. Representative source-scored
quality, unseen holdout performance, native candidate/review and current-index
publication, Docling-free end-to-end behavior, and shared Oxcart/Blackbird capacity
remain required. Blackbird continues to own ingestion/reindex and query embeddings.
Phase 9 remains gated on G2/G3.
