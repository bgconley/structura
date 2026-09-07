# Source-scored parse diagnostics v1

This additive X-06 foundation scores provided source annotations and captured neutral
parse output. An optional authorized adapter captures exact sealed database generations.
Neither path invokes models, replaces the legacy corpus gate, certifies a blind
holdout, or accepts a release. Every report keeps these
later stages explicitly `not_evaluated`. Quality thresholds remain `not_ratified`.

The three JSON schemas mirror the Pydantic input contracts in `lib/evaluation/`:

- `source_annotation.v1.schema.json`: independently authored original-page labels.
- `parse_capture.v1.schema.json`: captured configuration, normalized structure,
  invocation metadata and raw page output.
- `parse_evaluation.v1.schema.json`: frozen case membership, artifact identities,
  matching policy and declared split/exposure history.

Input schemas forbid extra fields, including supplied `goldMetrics`, computed scores
or acceptance thresholds. Runtime validation also enforces cross-field invariants
that JSON Schema cannot express. Keep private originals, labels, captures and reports
in protected storage. Use opaque item/group/actor references; do not use private
filenames or content as identifiers. The CLI avoids echoing invalid input content.

## Integrity and governance

Artifact hashes use SHA-256 over UTF-8 JSON from the validated model, with sorted keys,
compact separators, explicit defaults, and non-finite numbers forbidden. They are
canonical model-content hashes, not hashes of pretty-printed files. Each case pins
the annotation, capture, original, processing run, parse generation, configuration,
profile, served model and source engine. The caller supplies the frozen manifest
hash separately; do not calculate a new trusted pin from an edited manifest at
evaluation time. Preserve the pin and freeze/exposure history in an independently
controlled evaluation record.

This manifest includes captured-output hashes, so its freeze is a post-capture
bundle freeze. It cannot by itself prove that labels and matching policy were
frozen before inference. A governed live-run adapter still needs a separately
pinned pre-run source/annotation/policy manifest and captured start/end times.
Current holdout declarations and timestamps are consistency checks only.

Validation requires exact document membership, complete original-page inventories,
matching annotated render hashes/dimensions, generation-owned page IDs, raw-output
hashes, matching invocation/configuration identity, and exact raw-to-normalized
page reconstruction. Model-origin chunks cannot relabel their source as native text.
The current capture supports one raw `structura.page_parse.v1` response per rendered
page. Deferred/failed/unsupported pages without renders remain explicit; partial
raw model-call failures need a future operational capture contract.

Hashes prove consistency against the supplied pin. They do not prove that a model
was invoked, a renderer produced the declared bytes, an author reviewed the original,
or the supplied exposure registry is complete. The DB capture adapter verifies stored
consistency and live read authority; it does not attest the runtime invocation.
Reviewed source support remains separate work. Model transcription
is never an independent reference, including when it repeats PDF-native text.

Blind holdout declarations reject synthetic fixtures, development/template overlap,
previous evaluation/tuning exposure and annotations created after the freeze.
These checks do not manufacture human review or historical independence. Freeze
labels/matching rules before evaluation, record all later exposure, and move a viewed
holdout into development before tuning against it. A new blind cycle needs new
untouched origins/templates. BMW/Anthem remain known regression material.

## Frozen matching policy: `structura.parse_matching.v1`

- Text uses Unicode NFC and whitespace tokenization. Case, punctuation, exact digits
  and signs are preserved. Python `SequenceMatcher` with `autojunk=False` aligns
  contiguous blocks in order. Each occurrence can match once; omissions and insertions
  are counted separately. Substitution therefore contributes one of each. This is
  not minimum edit distance, CER or WER. More than 5,000 tokens on either side of a
  scored page fails explicitly; no text is truncated to get a favorable score.
- Annotated table text and row/column-sorted cell text participate in full-content
  scoring. Searchable chunks are scored against the same reference independently.
  Adjacent chunks for identical element-ID tuples are concatenated before tokenizing
  to restore words split by chunk length. This does not judge search relevance.
- Exact identifier/amount/date metrics count occurrences of annotated literal values
  with word boundaries, preserving punctuation and numeric values. They do not
  classify every possible sensitive token. Arithmetic reconciliation tolerances
  are not transcription tolerances.
- Pages with unresolved reference regions are explicitly text `not_evaluated` in
  this first version. Their pages remain in inventory/state coverage; the report
  states the number excluded from text measurement. Safely scoring the remaining
  readable portions requires a future adjudicated partial-region alignment policy.
  Blank reference pages are scored normally, so invented output is counted.
- Region alignment is a deterministic greedy one-to-one same-kind match, prioritizing
  exact normalized text, then IoU, then annotation/output order. A pair is eligible
  with exact nonempty text or IoU >= 0.1. That value is a matching heuristic, not an
  approved quality threshold. Segmentation differences can hurt layout diagnostics
  while full-page text remains correct. Missing regions contribute zero to mean
  IoU; extra regions remain in occurrence counts. Valid overlap does not prove
  source-pixel support or text truth.
- Reading-order accuracy uses explicitly annotated unambiguous pairs, with missing
  endpoints counted separately from reversed pairs. Both remain in the denominator.
- Tables match through their region. Grid dimensions, cell row/column coordinates,
  spans and exact normalized text are measured separately. Unknown cells have no
  text correctness label. Unannotated grid positions are not inferred to be absent
  cells. Continuation scores compare group relationships rather than provider names;
  missing links and false joins are separate counts. Row-shift matching and complex
  segmentation remain future work.
- Zero denominators produce `null`, with counts retained. Deferred pages stay in
  readable-source recall denominators. A fully inventoried document does not imply
  every page was processed. Results remain per document/page; this initial scorer
  does not claim macro/stratified statistics, confidence intervals or generalization.

## Exact-generation database capture

`lib.evaluation.persisted_capture.capture_sealed_generation` takes explicit
`document_id`, `processing_run_id`, `parse_generation_id`, `DocumentAccessContext`
and `CaptureDeclaration(item_id, commit, max_output_tokens, temperature)`. It reads
only that sealed generation. Superseded/cancelled sealed history remains available
subject to current household membership, user status, document/folder ACLs and,
when present, persisted token lifetime and read-capable scopes. Missing, unsealed,
cross-document and unauthorized identities all return the same unavailable error;
there is no lookup of the newest parse as a substitute.

One SQL statement captures immutable structure, inventory, frozen configuration,
original-asset metadata and every checkpoint under the same read snapshot. It does
not acquire publication locks or wait on a worker claim. Current token scope
decisions use the shared authorization policy. As with ordinary reads, revocation
after an authorized snapshot cannot retrieve bytes already disclosed.

After closing the transaction, validation verifies recorded hashes, source metadata,
exact run/generation/page IDs, raw/checkpoint/normalized equality, complete sealed
pages and searchable projection. Fixture/live mode derives exclusively from frozen
`model_revision` prefixes: `fixture:` or `declared-live:` with a nonempty revision.
Unknown legacy/unmarked revisions fail closed. These declarations describe provenance;
they do not attest weight bytes or a real endpoint call.

The returned `PersistedGenerationCapture.capture` is the scorer's `DocumentCapture`.
The wrapper retains run status, sealed timestamp and storage hashes. Its
`commit_provenance` and `generation_settings_provenance` remain `externally_declared`:
migration 096 did not persist source commit, token limit or temperature. Do not
report these caller-supplied values as independently database-verified. Capture
errors avoid echoing private stored text. No original URI/path is returned.

`lib.evaluation.artifact_verification.verify_capture_source` is optional and separate.
It takes the wrapper, explicit `original_asset_id` and a local `original_path`.
It never resolves stored/model URLs, makes network calls, invokes a model, or opens
a DB transaction. Bounded reads enforce the 100 MiB original limit; byte hash, size,
actual MIME signature, asset identity and the complete stored page inventory must
match. `DocumentSource` opens its own hash-checked snapshot (at most 500 pages), then
reproduces each page's exact render identity at the frozen scale and its normal
pixel budget. A historical renderer mismatch fails explicitly instead of silently
substituting newer render output. MIME signature checking is deliberately conservative;
unsupported signatures such as BigTIFF are not silently accepted as ordinary TIFF.

Successful artifact verification means original bytes and the deterministic page
renders match. It still does not prove the captured transcription is supported by
those pixels, that a human reviewed the labels, or that a live model ran. The
verifier returns this separate result without retroactively changing capture claims.

## File-scoring CLI

`scripts/score_document_parse.py` accepts `--manifest`, a separately recorded
`--expected-manifest-sha256`, one or more `--annotations` and `--captures` paths,
and `--output`. It only scores supplied files. A successful exit means diagnostic
computation completed; it does not mean model quality or a release gate passed.
The output must be a new file and is created with owner-only read/write permissions
(`0600`). Existing files and symlinks are rejected, including input/output collisions.

The committed fixture in `tests/fixtures/evaluation/` is explicitly synthetic, with
two reference images, a TIFF original, separately authored annotations and fake
model output. `build_fixture.py` regenerates only those synthetic fixtures. Do not
use that generator to create private labels or a blind holdout.
