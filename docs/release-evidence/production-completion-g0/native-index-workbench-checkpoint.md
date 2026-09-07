# Native index foundation and Inbox workbench checkpoint

Date: 2026-09-07. Latest integrity candidate: `714b5fc`. Latest complete browser
candidate: `bed4c5b`. G1/G2/G3 remain open; native ingestion/search is not activated.

## Delivered behavior

Migration 098 and `lib/search/indexing/` retain an exact parse-only candidate index:
source/configuration identities, complete page/input eligibility, exact original
renders, float32 vector checkpoints and a sealed completion record. Candidate
execution dispatches one input per request outside database transactions, preserves
actual response identity and resumes only missing saved inputs. The producer's
independently renewed claim, requested processing run and index authority fence
each saved response. Pending execution cannot acknowledge successful completion.
No current search pointer or ordinary worker is switched by this foundation.

Migration 099 adds independently revised human field decisions, rejection records
without fabricated canonical values, conservative historical path guards,
classification/manual-date decisions and accepted-fact projection revisions.
Its schema and backfills are verified here. Writer/API/client activation remains
the next separate change; the schema alone does not preserve new decisions.

Migration 100 fixes a real retention dependency found in the fresh database gate.
Six original/run/job/parse/render foreign keys now defer their checks to commit,
allowing a complete document deletion while still rejecting independent deletion
of required parents. Historical rows remain protected. Applied migrations 096/098
were not rewritten. A subsequent cleanup fixture was repaired to use distinct
document images; production cleanup still retains any referenced URI or hash.

The Inbox now consumes all eight server filters, six stable sorts, authorized
counts and pages beyond the first 50 records. Its URL preserves query, folder,
filter, sort, page and selected document across refresh/back/Viewer navigation.
Late responses cannot replace an explicit selection. Accepted upload navigation
uses the returned document ID, including duplicate titles, and upload failures
remain visible after navigation with same-file retry available.

## Verification

| Candidate | Check | Result |
| --- | --- | --- |
| `bed4c5b` | Fresh PostgreSQL integration, 43 migrations through 100 | 263 passed in 118.90 s |
| `bed4c5b` | Complete pinned Linux browser suite | 92 passed; 8 live-stack tests skipped |
| `714b5fc` | Complete unit suite | 1,598 passed in 37.20 s |
| `714b5fc` | Fresh PostgreSQL integration, 43 migrations through 100 | 268 passed in 121.57 s |
| `714b5fc` | Ruff, format, contracts, Bandit, Semgrep, Pyright, Mypy | Passed; 512 Semgrep rules, 1,167 targets, zero findings; Mypy 438 files |
| `714b5fc` | Affected Inbox browser tests, pinned Linux lint/build | 11 passed in 17.8 s; lint/build passed |

The five new executor database cases cover persisted bounded resume, sealed replay
without another adapter invocation, zero eligibility, and separate-connection job
cancellation, run supersession and index cancellation while inference is blocked.
Denied responses add neither vector checkpoints nor a completion record. Controlled
test adapters are explicitly fixture provenance; these results are not GPU proof.

Browser verification uses the pinned Playwright 1.59.1 Linux image recorded in the
[baseline](README.md). Root inspected proposed desktop/mobile controls and both
changed Phase 1 screenshots before committing the Linux Inbox/Viewer baselines.
The 92-test run then used normal comparisons; tolerance was not relaxed. The
browser installs reported zero npm audit findings. Tests requiring a full live
application stack remain distinct from mocked browser evidence.

The first static pass flagged six psycopg statements using fixed SQL fragments or
quoted test identifiers under a SQLAlchemy raw-query rule. Each was reviewed and
given a rule-specific suppression with its rationale; parameters remain bound.
Four browser assertions now compare URL components directly instead of creating
regular expressions from document IDs. No global scan rule was disabled. Existing
scan size/ignore/parse limitations remain as documented in the earlier checkpoint.

Protected logs remain under the owned temporary validation root on Oxcart:

| Log | SHA-256 |
| --- | --- |
| `integration-bed4c5b.log` | `91e2fa68589c6ece46e2c021dedf4986f6f11dcdc6299536356e445da4f7c56e` |
| `browser-bed4c5b.log` | `b137470987ce034907a286a535693b95c4f6488e5249d3216a7e7eecc81090f1` |
| `unit-714b5fc.log` | `3cf25f37017e09c86671851827c2915e347d6a931b8ff7d82e103a82bfe06533` |
| `integration-714b5fc.log` | `4177a9ba553433b6dd02d968eb935e3949220952d7d0d6b0cc30f2f504f3cbcd` |
| `static-714b5fc.log` | `be82006bd8e7b3c5c5dcbe3f23c76104a9434b75188379d51922f10a50ca3a7b` |
| `browser-714b5fc.log` | `143d19e5bc31fc75bdf0357c983e0ecc391dbb904f315f58c66825ac9132ec04` |

## Remaining acceptance

X-02/X-05/X-07 still require real persisted document/query embedding evidence,
all-page evidence assets, accepted-fact and metadata authority in index inputs,
generation-aware publication/readers, reindex/rollback and measured retrieval
quality. UI-04/UI-07 and SEC-01 still require the durable human-decision writer,
batch/drop/progress/duplicate workflow, full history/evidence and remaining product
acceptance. Corpus fidelity, capacity and all release gates remain open. No existing
archive, resident model configuration or public application deployment changed.
