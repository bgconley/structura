# Phase 8.5 Model Corpus Fixtures

The committed example manifest is deterministic and sanitized. It documents the
required evidence/metric shape without containing private documents or live model
outputs.

Release candidates must provide a separate private `phase8_5_model_manifest.json`
with `fixtureType = "model_backed"` and measured Qwen, Granite, text embedding,
visual embedding, hybrid retrieval, and provenance metrics.

The private `phase8_5_model_manifest.json` must include `runManifest.model_mode`
set to `live` or `required`; release validation must not infer live model mode
from the runner process environment.

Each model-backed evidence section (`qwen`, `granite`, `textEmbedding`, and
`visualEmbedding`) must include non-empty `profile`, `runId`, `measuredAt`, and
`evidencePath` fields. `measuredAt` must be an ISO-8601 timestamp with timezone.
`evidencePath` should point to the private GPU smoke,
resident, retrieval, or corpus report artifact that produced the corresponding
metric evidence. Relative `evidencePath` values resolve from the private
manifest's directory, and the runner requires the target artifact file to exist
when evaluating a model-backed manifest from disk. The target artifact must be a
JSON object with `fixtureType = "model_backed"` and `runId`, `run_id`, or an
equivalent `runManifest.run_id` matching the evidence section `runId`, plus
`measuredAt`, `measured_at`, or an equivalent run-manifest timestamp matching the
evidence section `measuredAt`. It must also include a Phase 8.5 `runManifest`
with the active `pipeline_version`, `model_mode` set to
`live` or `required`, and report evidence such as `acceptanceGates`, `metrics`,
`checks`, or `documents`; deterministic fixture artifacts are not valid release
evidence. The artifact must include model profile metadata matching the evidence
section `profile`, either as a top-level profile field or as the section-specific
profile field in `runManifest`, such as `semantic_profile`, `granite_profile`,
`text_embedding_profile`, or `visual_embedding_profile`. The artifact `metrics`
object must include the section-specific metric values claimed by the manifest,
such as Qwen route/review rates, Granite table/KVP scores, or text/visual
retrieval hit rates. Aggregate claims such as `hybrid_hit_rate_at_k` and
`provenance_truth_rate` must appear in at least one evidence artifact, and any
artifact that reports a claimed metric must match the manifest value.
