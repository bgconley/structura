# Upload and native claim integrity checkpoint

Status: verified implementation slices of UI-02/UI-04/UI-06/UI-07, SEC-01/03,
JOB-02 and X-02/X-05. G2/G3 and native pipeline activation remain open.
This extends the [retained-evidence checkpoint](retained-evidence-checkpoint.md).

## Integrated behavior

Migration 103 adds exact canonical line-item targets, independent candidate and
human-decision revisions, immutable selected-value/evidence history, transactional
review/projection updates, and retained reads after candidates or accepting actors
disappear. The browser shows full precise values and explicit create/replace intent.
Stale decisions retain the draft and require a fresh target. Scalar facts and
manually selected totals keep their separate authority.

Migration 104 adds durable upload attempts and raw streaming through the actual API
router and web proxy. Opaque operation identities, immutable acceptance receipts,
explicit readable duplicate choices, originating credential checks, exact content
comparison, bounded active/byte reservations, transfer replacement and cancellation
are implemented. Original installation uses verified source identity and durable
same-filesystem links. Lease expiry alone cannot release reserved bytes. The legacy
upload route retains its captured credential and bounded multipart handling.

Migration 105 adds immutable claims derived from recorded native parse text. Exact
decimal strings and distinct physical rows survive sealing and replay. Historical
reads require current document access without requiring the old job, credential or
parse generation to remain current. Source/configuration hashes and explicit page
coverage are checked. Claims remain review-required; source-pixel truth, arithmetic
and extraction completeness are not inferred from successful persistence. This
branch does not import claims emitted by the combined 27B contract.

The browser repair at `b5f646f` preserves search focus when initial data arrives
late, prevents editing a correction before its candidate is ready, and supports
UUID creation on plain LAN HTTP with cryptographic random bytes. Three deterministic
regressions cover these failures.

## Exact-source verification

The integrator pushed and fast-forwarded the shared Oxcart checkout once per
candidate, then tested clean detached worktrees. No active archive database or
original object tree was migrated. Database tests used the owned loopback-only
ParadeDB 17 instance and uniquely named disposable databases.

| Candidate | Executed evidence |
| --- | --- |
| `7ecda49` | 1,765 unit and 392 database tests; static checks passed through migration 103. |
| `b5f646f` | Complete pinned Linux browser suite: 179 passed, eight live-stack skips; web lint/build passed. |
| `a714549` | 1,806 unit tests, five Node-dependent skips; Ruff, format, contracts, SAST, Pyright and Mypy passed. Public path names match OpenAPI. |
| `594bd31` | Six real HTTP/socket proxy tests passed separately under Node 20.20.2 and Python 3.12.14. |
| `b1ff7de` | All 40 upload PostgreSQL tests passed, including actual app wiring, source credentials, duplicate decisions, process/lock recovery and durable receipts. |
| `874eb4f` | 1,836 unit tests, five Node-dependent skips, and all 463 database tests passed after 48 fresh migrations through 105. All static checks passed; Mypy checked 528 production source files. |
| `47999f3` | Supervised cleanup: 1,851 unit tests, five Node-dependent skips and all static checks passed; Mypy checked 534 source files. Its database run was interrupted after 442 passes because a killed test process stranded a multiprocessing Event lock. |
| `d56c038` | Test-only pipe barriers repaired that deadlock. All 474 PostgreSQL tests passed, including 11 real cleanup process/recovery cases, after the same 48 migrations. |
| `c0476bf` | Batch client: 217 Linux browser tests passed, eight live-stack skips, one expected Phase 1 screenshot mismatch. The integrator inspected the new Inbox/Viewer images and captured both updated references in the pinned Linux image; their ordinary comparison gate remains separate. |
| `d03a77e` | Complete ordinary Linux comparison passed: 218 browser tests, eight live-stack skips, with web lint/build. No screenshot tolerance was weakened. |
| `0f2efca` | Five actual upload workflows and the disposable-stack guard passed (six tests, 11.8 seconds) against the isolated `d56c038` application images. Exact receipts and downloaded original bytes were checked. |

The five Python-host skips are not counted as socket proof. That proof ran in the
separate Node 20 image above, with six passing tests and no published host port.
Its image ID is `sha256:30a5c415f9708646812e10b23fbb4e4068219263b831760d68ef71ead0ac35f0`,
built from Node image
`sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293`.
The Linux browser image is
`sha256:b0ab6f3cb99aa7803adbc14d9027ec1785fc6e433b97e134e0f8fe61683b6b53`.
Private logs remain in the protected Oxcart validation root. Results belong to
their named candidates, not to later untested changes.

Earlier upload integration failures exposed a router/contract path mismatch and
test-fixture content collisions; both were repaired. The final durability test
compares the previously recorded writer-stop timestamp and independently verifies
that failed cleanup leaves its confirmation absent.

## Supervised cleanup and isolated runtime

The cleanup worker now uses an existing storage namespace, with exact directory
identity checks before claims and after source-lock acquisition. Missing/replaced
storage retains reservations. Failed items rotate fairly; expected storage failures
do not block the remaining batch. Database operations have finite waits, and health
distinguishes starting, degraded, stalled and stopping states. The worker keeps
active filesystem ownership through shutdown instead of abandoning IO.

The `d56c038` API, web and cleanup images were built from clean committed source
with the pinned Python/Node repository digests. A separate internal Docker network,
fresh disposable database, new synthetic user and independent object root host this
validation stack. No host port is published, no inference worker is running, and
the archive database/storage and resident model services are untouched. Homepage
HTTP 200, proxied unauthenticated session HTTP 401 and actual cleanup health HTTP 200
were observed. Cleanup health remained HTTP 200 with zero consecutive failures
after browser acceptance.

The actual browser gate at `0f2efca` exercised PDF registration and Viewer download,
same-name/different-byte batches without losing selection, exact duplicate reuse
and separate copies, mobile keyboard PNG upload, refresh followed by an explicit
GET without another PUT, and unsupported-signature rejection followed by a valid
upload. Every accepted/reused original was compared byte-for-byte with its synthetic
source and its receipt SHA256. Reuse preserved the existing document's metadata and
facts. No inference or extraction quality is implied by upload acceptance.

The first run at `a9ed8b1` had five false test failures: Chromium reported successful
PUT responses but evicted their bodies from its inspector cache. A diagnostic run
captured the exact `Network.getResponseBody` eviction error. The repaired helper
observes the unchanged native XHR JSON alongside inspector responses and errors;
it issues no recovery request, changes no transport or application behavior, and
binds observations to the registered operation/batch and exact upload ID. The
receipt, original-download and no-extra-PUT assertions remain intact.

Test source and image source are deliberately recorded separately. The application
images are `d56c038` API
`sha256:af74ea68fa0c3cde4b2d0d6a189492b79a2783251ecd8fe3272a47c8c3dfaeeb`
and web
`sha256:23a77a1220dd2b94336790f74c62b83f43eaa192b10327e40a145af86e4501c7`.
The browser dependency image is
`sha256:38e19a8dd16b31ddb9325cc9b5696707fe5bbb59a9f51bb5303be4dc9543da33`,
built on the pinned browser base with lockfile SHA256
`0d2f97b41377fb4fb09bf9f62ee4b0a76113fd31606cff34b78e75c8068c5a26`.
The runner used a clean `0f2efca` worktree on the internal network without egress.
Protected traces, logs and the reviewed 390-pixel mobile capture remain under
`upload-live-d56c038/browser-0f2efca` in the private validation root. This capture
proves that tested responsive state, not final mobile product acceptance.

The batch client uses exact operation/receipt identity, a bounded queue-wide capacity
pause, explicit duplicate choices, raw File transport and fresh outcome checks.
Only opaque actor-scoped recovery references and a metadata digest persist across
refresh; private filenames, files and receipts do not. Accepted uploads preserve
current navigation and expose an explicit Open document action. The visual change
removes the old global acceptance banner and adds functional upload queue controls.

## Remaining acceptance

Ordinary browser comparison and the bounded real browser/API/proxy upload gate
passed at the separately identified candidates above. The isolated stack is not a
production cutover. Process kills and fsync ordering do not establish host power-loss
recovery; broader access, workflow and capacity acceptance remains open.

The combined page-understanding v2 pure contract is integrated at `312e305` with
79 focused synthetic tests. Its versioned runtime/reader integration, raw-member-bound
claim import, candidate/review integration, coherent native parse/claim/index publication
and Docling-free end-to-end operation remain unfinished. These persistence tests are
not extraction-quality measurements. Representative original-scored coverage,
unseen holdout evaluation, search usefulness, shared Oxcart admission and Blackbird
ingestion/query embedding capacity remain open. No model service was restarted or
reconfigured for this checkpoint. Phase 9 remains gated on G2/G3.
