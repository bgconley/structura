# Phase 8.5 GPU Model Validation

Phase 8.5 is not complete with fixture-only behavior. The canonical GPU node must
prove live model services are reachable and that private model-backed corpus evidence
passes thresholds.

```bash
ssh -i /Users/brennanconley/vibecode/infx/ubuntu24_ed25519 bgconley@10.25.0.50
cd /tank/repos/structura
git pull --ff-only
STRUCTURA_MODEL_MODE=live PYTHON=/tank/venvs/structura/bin/python bash scripts/gpu/phase8_5_model_smoke.sh
```

On the current 2x 24GB Blackwell node, `models-live` is the co-resident VLM
profile with role-weighted context budgets:

- GPU0: Qwen3-VL-8B-Instruct-FP8 Smart Parse semantic service at 32K context.
- GPU1: Granite 4.0 3B Vision at 16K context, then Qwen3-VL-Embedding 2B at 2K.
- Qwen3-Embedding-4B text embeddings remain offload/on-demand on the two-Blackwell
  node; prefer the RTX 3090 node for always-available text embeddings once
  cross-node serving is wired.

Use managed smoke mode to start the highest-context VLM on each card first, then
the lower-context companion services, then temporarily offload GPU1 VLM services
to validate text embeddings, and finally restore the co-resident VLM services:

```bash
STRUCTURA_MODEL_MODE=live \
STRUCTURA_MODEL_SMOKE_MANAGE_COMPOSE=1 \
PYTHON=/tank/venvs/structura/bin/python \
bash scripts/gpu/phase8_5_model_smoke.sh
```

The smoke gate waits for first-load health and performs minimal live inference
requests against Qwen Smart Parse, Granite, visual embeddings, and text
embeddings before evaluating the private corpus manifest.

The Blackwell runtime uses explicit Docker Compose GPU reservations rather than
only `gpus: all`. Each live model container is assigned a host GPU with
`deploy.resources.reservations.devices[*].device_ids`, then sees that device as
inside-container `CUDA_VISIBLE_DEVICES=0` with `CUDA_DEVICE_ORDER=PCI_BUS_ID`.
This avoids vLLM using the wrong card or inheriting NVIDIA runtime sentinel
values before model inspection.

The default memory/context settings are intentionally conservative:

- Qwen3-VL-8B-Instruct-FP8 Smart Parse: 32K context, image-only, low concurrency;
  highest allocation because it owns semantic inventory and routing.
- Granite 4.0 3B Vision: 16K context, image-only, low concurrency; targeted
  crops/regions should keep extraction prompts narrower than full-document Qwen.
- Visual embeddings: 2K context with native 2048-dimensional Qwen3-VL-Embedding
  output. It rejects the OpenAI `dimensions` override, so do not configure
  Structura visual embeddings as 1024-dimensional unless a different backend is
  explicitly selected.
- Text embeddings: offload/on-demand on the two-Blackwell node; prefer the RTX
  3090 node for always-available text embeddings.

If smoke output shows KV-cache preemption, increase that service's
`STRUCTURA_*_GPU_MEMORY_UTILIZATION` or reduce `STRUCTURA_*_MAX_NUM_SEQS`.
If startup OOMs, reduce `max_model_len`, `max_num_seqs`, or avoid co-residency
for that profile.

The committed example model-corpus manifest is deterministic documentation only.
Release validation must use a private `phase8_5_model_manifest.json` with
`fixtureType = "model_backed"` and `runManifest.model_mode` set to `live` or
`required`. Any run-manifest model profile fields must match the corresponding
evidence section `profile` values.

Use `make model-corpus` only as a deterministic manifest shape check. Use
`make model-corpus-release MODEL_CORPUS_RELEASE_MANIFEST=/path/to/private/phase8_5_model_manifest.json`
or `make release-readiness` for the release gate; both require model-backed
evidence and fail fast when the private manifest is missing or fixture-backed.
To assemble the private release manifest from measured artifacts, run
`make build-model-corpus-manifest` with explicit `MODEL_CORPUS_*_EVIDENCE`,
`MODEL_CORPUS_THRESHOLDS_JSON`, `MODEL_CORPUS_GOLD_METRICS_JSON`, and
`MODEL_CORPUS_GOLD_THRESHOLDS_JSON` paths. The builder validates the generated
manifest with `scripts/run_model_corpus.py --require-model-backed` before
writing it.

For the Phase 8.5 reliability acceptance gate, run the resident corpus twice and
compare the committed report gates/fingerprints with the current wrapper:

```bash
STRUCTURA_MODEL_MODE=live \
PYTHON=/tank/venvs/structura/bin/python \
/tank/venvs/structura/bin/python scripts/gpu/run_phase8_5_resident_acceptance.py \
  --manifest /tank/structura/private/phase8_5_resident_manifest.json \
  --report-dir /srv/structura/objects/exports/phase85-runs
```

The wrapper runs `run_phase8_5_resident_corpus.py` twice, writes one report per
pass, and fails if hard correctness, operational SLO, or repeatability gates fail.
The resident manifest uses `documents[].path` for each private PDF. For release
gold validation, the same private manifest may include corpus-level `goldMetrics`
and `goldThresholds`, or document-level overrides using the same keys. The runner
copies those values into report document rows so
`acceptanceGates.goldCorpusQuality` is recomputable from captured report
evidence. Use `--require-gold` only with a private manifest that contains those
gold annotations.

For the E4 vision-lane A/B gate, run the host-side wrapper so the app and
extraction worker containers are recreated with the correct fallback mode before
each resident acceptance run:

```bash
PYTHON=/tank/venvs/structura/bin/python \
/tank/venvs/structura/bin/python scripts/gpu/run_phase8_5_e4_vision_ab.py \
  --manifest /tank/structura/private/phase8_5_resident_manifest.json \
  --report-dir /srv/structura/objects/exports/phase85-runs/e4-vision-ab
```

The wrapper first brings up the live runtime with
`STRUCTURA_QWEN_VISION_FALLBACK=false` for the Granite fallback baseline, then
runs two-pass resident acceptance into `e4-vision-ab/granite`. It then recreates
the runtime with `STRUCTURA_QWEN_VISION_FALLBACK=true` for Qwen vision fallback
and writes the same two-pass acceptance evidence into `e4-vision-ab/qwen`.
Do not remove Granite or flip the default fallback until the Qwen reports match
or safely abstain relative to the Granite baseline with no hard invariant,
dead-letter, provenance, or hidden-second-Qwen regressions.

Report acceptance also requires `fixtureType`, `measuredAt`, and
`runManifest.model_mode` so stale fixture or pre-lineage reports cannot pass as
release evidence; the top-level `runId` must match `runManifest.run_id`; live or
required reports must include current
`semantic_profile`, `granite_profile`, `text_embedding_profile`, and
`visual_embedding_profile` lineage.
Report acceptance requires the full repeatability fingerprint set:
`documentFamily`, `semanticRegions`, `plannerTasks`, `candidateFingerprints`,
`canonicalOutput`, `reviewTasks`, and `rejectionDistribution`.
Cross-run repeatability drift compares deterministic document family, selected
semantic region, planner task, admitted candidate, canonical output, and review
task fingerprints; `rejectionDistribution` is recomputed per report as rejected
noise telemetry but is not a canonical-output drift key.
Repeatability comparisons require distinct `runId` values so the same report
cannot be submitted twice as two-pass evidence.
Two-pass repeatability evidence must include non-empty report `documents` rows
so planner and candidate fingerprints are recomputable from captured corpus
evidence.
Hard correctness acceptance requires
`acceptanceGates.hardCorrectnessInvariants.status = passed` and
`totalViolationCount = 0`.
Document-title-derived merchant or seller fields are violations whether the
title provenance appears in evidence refs or row-level source fields, unless the
document or field is explicitly allowlisted.
Operational SLO acceptance requires
`acceptanceGates.operationalSLOs.status = passed` and
`metrics.targetQueueDeadLetterCount = 0`.
Hard correctness and operational SLO counters must be numeric zero, not booleans
or string values.
Operational SLO reports must include passing subgates for
`targetQueueDeadLetters`, `classifiedOperationalFailures`, `retrySuccessRate`,
`runtimeFailureRates`, `runawayFanout`, and `retrySafeJobs`.
Gold corpus acceptance requires
`acceptanceGates.goldCorpusQuality.status = passed` with empty
`missingMetrics` and `failedMetrics` lists; gold metric summaries must have
passing statuses and no invalid values, invalid thresholds, or failing keys.
When `--require-gold` is used, the report must also be model-backed evidence:
`fixtureType = model_backed` with live or required `runManifest.model_mode`.
Use `scripts/gpu/phase8_5_report_acceptance.py` directly when re-checking already
captured report files.
