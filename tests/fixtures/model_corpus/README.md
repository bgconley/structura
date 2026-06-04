# Phase 8.5 Model Corpus Fixtures

The committed example manifest is deterministic and sanitized. It documents the
required evidence/metric shape without containing private documents or live model
outputs.

Release candidates must provide a separate private `phase8_5_model_manifest.json`
with `fixtureType = "model_backed"` and measured Qwen, Granite, text embedding,
visual embedding, hybrid retrieval, and provenance metrics.

Each model-backed evidence section (`qwen`, `granite`, `textEmbedding`, and
`visualEmbedding`) must include non-empty `profile`, `runId`, `measuredAt`, and
`evidencePath` fields. `evidencePath` should point to the private GPU smoke,
resident, retrieval, or corpus report artifact that produced the corresponding
metric evidence. Relative `evidencePath` values resolve from the private
manifest's directory, and the runner requires the target artifact file to exist
when evaluating a model-backed manifest from disk.
