# Native parser and integrity checkpoint

Date: 2026-09-07. Evaluated application commit: `77d9f1d` on `codex/production-completion`. This is a foundation checkpoint; G1/G2/G3 and production activation remain open.

## Observed results

Clean detached worktrees on Oxcart passed **1,308 unit tests** and **99 database integration tests**, using the owned disposable ParadeDB PG17 container described in [the baseline](README.md). All **37 registered migrations through 094** applied to a fresh isolated database. No existing archive database or objects were changed.

The authenticated [native parser probe](../../../scripts/gpu/probe_native_parse.py) invoked the existing Oxcart 27B service for two synthetic source pages: a letter and an invoice. Both pages were accounted for as `processed`; expected wording, identifiers and amounts survived into the structured artifact and searchable chunks. The result contained nine elements, one table and nine chunks. Both actual invocations were recorded as `qwen3_8_27b`; Docling was not imported. Request latencies were 9,572 ms and 21,230 ms. The [captured report](native-parse-77d9f1d.json) includes source and artifact hashes.

The resident model configuration and unrelated services were preserved. This probe used the real configured alias `qwen38-27b-bf16-oxcart` through Structura's authenticated adapter. It establishes a working source/render/model/normalization/checkpoint path, not representative extraction accuracy, locator correctness, concurrent capacity or retrieval quality. Its declared `quality_gate` is `not_evaluated`, and `production_activated` is false.

## Corrections made during validation

The preceding candidate exposed an environment packaging omission: the thin source adapter needs PDFium in the shared CPU runtime, but it had not been declared there. Commit `77d9f1d` declares and pins `pypdfium2==5.11.0` in the API/development lockfiles; the isolated validation environment was updated to that version before this successful run. Docling and Torch remain isolated from this dependency. No failing test was excluded.

The earlier 532cf1b integration run passed 98 cases and failed a correction-revision test that tried to force a timestamp through a table whose trigger assigns the actual update timestamp. Commit `00c31d3` corrects the test to compare the exact database timestamp, including microseconds, against the API revision and still verifies the competing reviewer's conflict. The complete 99-case suite now passes.

## Remaining acceptance

The parser currently produces a validated candidate artifact; it does not replace the active legacy structural tables or publish canonical facts. Durable document-run ownership, sealed generations, historical evidence resolution, atomic publication, generation-aware reindexing and preservation of human corrections must be integrated before activation. Page continuation, long-document context, independent source annotations, blind quality scoring and shared-service admission/capacity remain required. The separate session/authentication slice is not included in these counts. Linux browser validation of the next integrated candidate remains pending.
