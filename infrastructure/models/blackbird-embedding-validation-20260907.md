# Blackbird embedding validation profile

Status: measured validation candidate on 2026-09-07; production activation and the
sustained-capacity gate remain open. This implements the approved placement for
document/page ingestion, reindexing and query embeddings together.

The [captured arguments](blackbird-embedding-validation-20260907.json) contain
exact image/model revisions, resource limits, read-only model mounts and invocation
arguments. They contain references to private credential files, never their contents.
They are a record of this owned validation deployment, not a script that may replace
an existing service. Snapshot paths and GPU availability must be rechecked before reuse.

| Property | Text | Visual |
| --- | --- | --- |
| Profile | `qwen3-embedding-4b-1536-blackbird:v2` | `qwen3-vl-embedding-2b-2048-blackbird:v2` |
| Model | `Qwen/Qwen3-Embedding-4B` | `Qwen/Qwen3-VL-Embedding-2B` |
| Revision | `5cf2132abc99cad020ac570b19d031efec650f2b` | `9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda` |
| Output | Requested 1,536 dimensions | Native 2,048 dimensions; no dimensions override |
| Context / sequence limits | 8,192 / 4 | 8,192 / 2 |
| GPU utilization reservation | 0.50 | 0.35 |
| Private address | `10.25.0.51:18102` | `10.25.0.51:18103` |
| Container | `structura-completion-text-embed-20260907` | `structura-completion-visual-embed-20260907` |

Both containers are restricted to PRO 4000 UUID
`GPU-6ec4ee66-142e-34ad-e17d-a131d7153b51`. Blackbird's occupied PRO 6000 and
Oxcart's resident 27B service were not restarted or reconfigured. After concurrent
inference, the PRO 4000 reported 21,317 MiB used and 2,672 MiB free. This is an
observed allocation snapshot, not proof that arbitrary concurrent workloads fit.

The cached image is
`sha256:fc120ece0a388cc0aa1caad4a9f1cd92113484ab7ec2fd0efadd62585be05bf8`.
Observed packages: vLLM `0.1.dev20073+g8e685d198`, Torch `2.13.0+cu130`,
Transformers `5.15.1`. Both services use BF16 pooling with LAST-token pooling,
normalization enabled, eager execution and 8,192 maximum batched tokens. Prefix
caching remains the observed runtime default; its cold/warm effects are part of
the remaining workload test. The text deployment explicitly enables the model's
Matryoshka dimensions `[1536,2560]`. The visual deployment permits one image and
no video, disables the processor cache, and bounds its input raster size through
`shortest_edge=65536`, `longest_edge=1048576`. These settings affect embedding
inputs only; original evidence and 27B parser inputs are preserved.

Text ingestion uses raw document text; text queries use the frozen instruction
format in the v2 profile. Visual images, mixed image/text inputs and visual text
queries all use the same declared messages format and system instruction. Changes
to model revision, instruction, preprocessing or vector dimensions require a new
space identity and compatible document/query rebuild before activation.

`hf cache verify` matched all 12 locally present text files and all 18 visual files.
The text cache omits `.gitattributes` and `generation_config.json` from that exact
remote revision; a strict full-repository completeness check therefore fails.
The recorded proof covers the files used by this pooling deployment, not a complete
repository mirror. No shared cache was modified to hide that distinction.

Both inference endpoints rejected requests without authentication with HTTP 401.
The owned private root and API-key files use modes 0700/0600. Credential loading in
Structura rejects non-private, nonregular and symlinked key files. The validation
services use authenticated HTTP on the private LAN; final transport, key rotation,
health/readiness and production deployment hardening remain separate gates.

Run `scripts/gpu/probe_embedding_profiles.py --help` for the reproducible adapter
smoke. It checks real text ingestion, image/mixed ingestion, both query paths,
response identity, full-input fingerprints, vector validity and simple synthetic
ranking before repeating the four paths concurrently. The
[measured evidence](../../docs/release-evidence/production-completion-g0/embedding-checkpoint.md)
includes the first concurrent latency spike; the smoke does not estimate sustained
throughput or a representative p95.

Production cutover still requires complete-source reindexing, per-generation
progress, matching active query/document profiles, atomic activation/rollback,
representative retrieval quality and sustained simultaneous ingestion/search tests.
The current application/index defaults were not switched by this validation.

For cleanup or rollback, verify each exact container name/ID and its
`structura.validation=production-completion-g0` label before stopping only those
owned services. Preserve the private evidence until its required records are copied;
do not remove shared model caches or stop other resident models.
