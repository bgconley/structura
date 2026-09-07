# Exposed three-family page-understanding probe

These are **visible synthetic development cases**, independently authored before
any model invocation. They are not a blind holdout, a production corpus, a human
adjudication study, or a calibrated acceptance gate. `source-recipe.json` records
fictional source content and its authoring time; the three PNG pages show exactly
that content. No text, value, ledger, geometry, or expectation is obtained from a
model response.

The pages cover a two-line invoice (including a negative adjustment and zero
paid), a two-line receipt (including leading-zero receipt/payment identifiers),
and a two-line medical EOB with distinct billed, allowed, plan-paid, patient,
deductible, copay, and coinsurance amounts. This small fixture does not cover all
23 families, mixed/dense/long/degraded documents, every business-field variant,
calibration, or production latency and memory contention.

`annotation.json` independently records source text, sensitive-token occurrence
counts, page/region geometry, simple table cells, and reading order. The typed
expectations in `expectations.json` cover selected explicit visible obligations
and every printed line row. Additional supported interpretations, such as an
inferred remittance payee or normalized party name, are not exhaustively labeled.
The report therefore measures annotated-obligation recall and row grouping; it
lists extra claims as unscored and never calls them all false positives or claims
overall business precision. Model-reported absence/coverage ledgers are shown
separately and cannot stand in for annotated truth. Structural geometry agreement
does not establish visual support for a proposed fact.

The original is reconstructed from the committed RGB PNGs after proving that
conversion to grayscale preserves every pixel. The deterministic Pillow raw,
three-frame grayscale TIFF is **12,960,384 bytes**. Its exact expected SHA-256 and
size are frozen in `expectations.json` and checked against the annotation before
admission. The probe privately retains those exact TIFF bytes through normal
canonical object storage. No redundant 13 MB source binary is committed and no
optional TIFF compression dependency is required. `fixture_authoring.py` is an
explicit source-authoring tool, not part of probe execution. Do not regenerate
labels from an observed response.

PNG compression backends may encode identical source pixels differently. Before
inference, the existing render-rebinding adapter verifies the original, all
reference hashes, full source inventory and exact RGB pixels; it then records an
immutable lossless encoding transform while preserving every label. The actual
capture continues to verify exact rendered bytes for its frozen renderer.

Run `scripts/gpu/probe_page_understanding.py --help` for the required controls.
The operator must provide a fresh private runtime/output directory, its exact
canonical/derived roots, a real isolated `structura_it_<16 hex>` database, a clean
committed checkout, accepted live ingestion profile, explicit deployment revision,
output token budget, temperature, seed (or `none`), and timeout. The declared
revision is not weight-checkpoint attestation. Budgets are validation bounds,
not qualified output capacity. Root performs shared-service preflight and owns
live execution; this command does not deploy, restart or select a model.

Execution permits exactly three source pages and at most three actual HTTP
attempts. There is one combined structure/classification/extraction call per page,
no automatic retry, and successful sealed replay must make zero calls. Source
renders are retained and replayed before job ACK. A failed parse or retention
operation does not ACK, attempts a nonretryable failure under the original claim,
and preserves exact partial-generation diagnostics when readable. Candidate data
is not published as the application's current parse or canonical facts.

Private artifacts (new files only, mode `0600`, output directory `0700`) contain
frozen source labels/expectations/configuration, per-call prompt/settings/image
identities, bounded HTTP response observations, complete successful raw outputs,
exact persisted checkpoints, an authorized historical capture and protected-page
API proof. Error-status bodies are drained only to the 1 MiB wire prefix bound,
under the original request transport timeout; compressed or incomplete prefixes
are labeled accordingly and never repaired into checkpoints. The production
adapter's independent 1 MiB **decoded** response limit is unchanged. Ordinary
console failures omit raw model/document text, paths, credentials and exceptions.
Pre-inference failures retain a static stage/code in `failed-stage.json` when a
new private output directory can be created; prior output directories are never
modified. Configuration failures remain distinguishable from model-contract
rejection without retaining raw exception text.

After ACK, the historical API proof creates and cancels an unclaimed successor
(zero model calls), proves the prior generation and every protected page remain
identical/readable, and checks missing and revoked-credential cases. Capture then
uses the exact historical IDs. The post-inference manifest is an output-bundle
pin, not a claim that outputs were known before inference. Structural and typed
reports are separate, thresholds stay `not_ratified`, and release acceptance,
calibration and production activation remain unevaluated/false.
