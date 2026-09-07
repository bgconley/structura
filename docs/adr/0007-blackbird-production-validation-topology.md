# ADR 0007: Oxcart ingestion and Blackbird embedding topology

Date: 2026-09-07

## Status

Updated after the user selected Qwen3.8-27B BF16 for ingestion and Qwen-native parsing; see [ADR 0008](0008-qwen38-27b-ingestion.md) and [ADR 0009](0009-qwen-native-document-parsing.md). Those target decisions are accepted. Structura integration, provider-neutral parse migration/fidelity and the proposed Blackbird embedding placement are not yet validated. Hardware, mount inventory and the resident 27B container/configured served name were observed read-only; an earlier unauthenticated `/v1/models` probe failed and does not establish authenticated adapter behavior. Adopt measured integration/admission/embedding profiles through G0/G3; preserve unsuccessful configurations as evidence rather than accepted production capacity.

## Context

Older Structura plans assume two 24 GB Blackwell cards and a separate RTX 3090 embedding path. The accepted ingestion model is now the existing shared Qwen3.8-27B BF16 service on Oxcart. The dedicated resource available for proposed embedding services is one RTX PRO 4000 on Blackbird, while its PRO 6000 hosts unrelated Gemma serving. Oxcart also retains the established ZFS archive location. The plan must preserve existing data and clients; shared inference capacity must be budgeted independently from the dedicated 24 GB embedding card.

Observed on 2026-09-07:

| Resource | Observation |
| --- | --- |
| Blackbird | `bgconley@10.25.0.51`, Docker server 29.1.3, NVIDIA driver 590.48.01 |
| Available GPU | Index 1, `GPU-6ec4ee66-142e-34ad-e17d-a131d7153b51`, RTX PRO 4000 Blackwell, 24,467 MiB total / 23,988 MiB free / 1 MiB used |
| Excluded GPU | Index 0, RTX PRO 6000 Blackwell Max-Q, about 96,476 MiB used; `gemma4-31b-it-bf16-blackbird` resident |
| CPU resources | About 115 GiB RAM available; root filesystem about 312 GB free (time-sensitive) |
| Shared models | `/tank/ai/models` → NFS `10.25.0.50:/tank/ai/models` |
| Shared source | `/tank/work/repos/structura` on Blackbird is the same NFS checkout reached by Oxcart `/tank/repos/structura` |
| Shared experiments | `/tank/ai/experiments` is NFS-backed; not an independent backup failure domain |
| Archive | Oxcart `/srv/structura` → `/tank/apps/structura`, ZFS; existing Postgres/object directories present |
| Accepted ingestion service | Oxcart container `qwen38-27b-bf16-mtp-vl-oxcart-server`, configured served name `qwen38-27b-bf16-oxcart`, host port `18012`; authentication/integration proof still open |

## Model decision and proposed integration

1. Keep web/API/Postgres/canonical storage and CPU document workers on Oxcart for the default completion topology. Preserve its established dataset layout; any later relocation needs a separate migration/restore plan. Do not place a running Postgres data directory on NFS.
2. Integrate Structura with the existing Oxcart 27B endpoint through protected configuration and authenticated adapter tests. Do not recreate, restart, reconfigure or unload that resident service as routine integration. Use explicit concurrency/rate/context/image/output/retry budgets and measured admission to protect its existing clients; the selected model does not imply exclusive capacity.
3. Target Qwen-native parsing with thin PDF/image inspection/rendering and optional native text extraction, producing a versioned provider-neutral parse for every page, element, table and chunk. Preserve original bytes, image coordinate transforms, validators, candidate/review/canonical separation and claim/parse/extraction-generation fencing. Label native text and Qwen transcription separately; copied model text is never Docling-verified or independently source-verified by implication. Docling may remain an isolated owned migration/comparison worker, but neither its output nor its availability is a target gate. Retain historical evidence unchanged and retire its runtime only after the new parser's source fidelity, viewer/evidence, reindexing and recovery pass. Old-8B/Granite comparisons are optional diagnostics, with no hidden automatic rescue service.
4. Propose a distinct text/visual embedding project on Blackbird restricted to the PRO 4000 UUID. It serves document/chunk and selected page-image encoding during ingestion/reindex/backfill, plus compatible query encoding during search. Preserve text 1536-dimensional and visual 2048-dimensional contracts; verify exact model/backend lineage and document/query compatibility. Do not force unsupported dimensions overrides. Keep the PRO 6000/Gemma service excluded. Only explicitly owned validation containers may be stopped by tooling.
5. Measure text-plus-visual embedding co-residency on Blackbird, shared 27B parsing/transcription/continuation/extraction impact on Oxcart, and concurrent new ingest/reparse/reindex/search quality and latency. Evaluate same-model CPU embedding services only if needed and validated. Serialized checks prove individual behavior only. If capacity fails, adjust Structura admission or document a concrete alternative integration arrangement; do not silently degrade query modes, borrow another GPU or routinely change shared serving.
6. Use bounded existing image-byte/data-URI adapter calls across the private host boundary; ordinary browsers still use protected application asset routes. Model services need no raw canonical-root mount. Restrict endpoint reachability and do not log payloads.
7. Manage the shared source checkout once, from Oxcart. Use isolated local worktrees for development, immutable deployment manifests for model configuration and no simultaneous git mutations over NFS. Models/caches may be staged locally only with measured space/performance and cleanup bounds.
8. Add deployment-target and container-ownership guards to existing GPU scripts before using them with this topology. Their historical service start/offload assumptions must not act on the shared Oxcart 27B or unrelated services. Model-profile/authentication integration comes early; live ingestion runs still wait for the relevant safety and fidelity prerequisites.

## Acceptance

- Recorded physical GPU assignment for Blackbird embeddings; unchanged unrelated Gemma serving and unchanged resident Oxcart 27B configuration unless separately authorized.
- Authenticated real-adapter 27B parse/text/structured/image smokes, exact served-model provenance, complete provider-neutral page/element/table/chunk contracts and source-scored parsing/extraction fidelity. Native text and Qwen transcription remain distinguishable. The earlier unauthenticated failure is not a passing result; Docling comparisons are optional.
- Full new-document ingestion, parsing, extraction, evidence/viewer/review, indexing/search and parse/job recovery succeed with Docling unavailable after cutover. Mixed-provider migration preserves historical accepted-fact/evidence references, resumes backfills and rejects stale parser/index publication before the old owned worker is retired. Phase 10 recovery-topology planning is not a prerequisite for G3 parser implementation/cutover.
- G5/G6 separately prove offline full-archive/evidence recovery with models unavailable and restored model-backed new-ingest/reindex/search recovery; both are mandatory before release and run without Docling. OPS-02/OPS-03 must record independent model artifacts, immutable runtime configurations, recovered credentials, authenticated isolated endpoints and measured sufficient recovery compute. Production inference or NFS passthrough cannot count as source-host-loss recovery, and the 24 GB embedding card is not assumed to host BF16 27B. Recovery hardware and the full processing RTO remain explicit deliverables/risks, without an unverified hardware selection; offline recovery timing cannot substitute for processing recovery timing.
- Exact-model document-text/page-image ingestion embeddings and compatible query embeddings, with truthful lineage and 1536/2048 dimension checks; sustained indexing/backfill and interactive query capacity are measured together.
- Representative extraction/retrieval quality plus concurrent ingest/search latency, VRAM/RAM/disk, finite queueing and outage recovery evidence; measured shared Oxcart client protection under the selected Structura admission budgets.
- Explicit CPU service validation if used, including query/document embedding compatibility and latency; no assumption that CPU availability proves responsiveness.
- A versioned complete integration/runtime profile with observed resident model configuration, embedding image/model digests, flags, measured request budgets, readiness and scoped rollback. Rollback removes or redirects Structura's integration/owned services without restarting shared inference.
- Matching application/runtime candidate versions and no raw source path or private payload leakage.

## Consequences

Qwen-native parsing and extraction use the selected shared 27B service beside the Oxcart archive/control plane; proposed ingestion/query embeddings create the Blackbird service boundary. CPU workers retain thin media handling, versioned persistence and scheduling. The 24 GB limit applies to embeddings, while Oxcart inference budgets include the additional parsing load. Neither limit justifies weaker provenance, original image fidelity or search acceptance. The target direction is settled; authenticated compatibility, provider-neutral parse migration/fidelity, Docling-free recovery and concurrent release capacity remain open gates. Refresh hardware/client snapshots before runtime actions; historical availability does not prove present headroom.
