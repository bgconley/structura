# Deployment and runtime architecture

## 1. Deployment posture

The recommended first deployment model is Docker Compose on the single P620 host. k3s is explicitly deferred until the application has proven itself functionally and operationally on one node.

## 2. Suggested services

### Core
- web
- api
- postgres

### Workers
- worker-ingest
- worker-previews
- worker-docling
- worker-extraction
- worker-embeddings
- worker-analysis

### Model servers
- model-qwen
- model-granite
- model-embed

### Optional
- reverse-proxy
- observability stack
- redis fallback queue profile only if PGMQ is unavailable

## 3. Service responsibilities

### web
User-facing UI only. No heavy business logic.

### api
Authentication, request validation, DB orchestration, search orchestration, upload handling, authorized asset serving, review actions, export actions.

### worker-docling
Canonical conversion and relational population of pages, elements, chunks, and tables.

### worker-extraction
Classification and schema-specific extraction orchestration.

### worker-embeddings
Embedding generation, index refresh bookkeeping, reranking helpers.

### worker-analysis
Optional user-invoked analysis runs only.

## 4. GPU allocation suggestion

Treat the two GPUs as separate worker pools.

### GPU 0
- Qwen3-VL extraction serving
- Granite extraction serving

### GPU 1
- embedding model serving
- optional reranker
- optional analysis model

This is a default, not a law. Measure and adjust based on actual throughput and memory.

## 5. Port and network suggestion

- web: 3000
- api: 8000
- model-qwen: 8100
- model-granite: 8101
- model-embed: 8102
- postgres: 5432
- reverse-proxy: 80 / 443 if used

Prefer an internal Docker network with only the web and reverse proxy exposed externally.

## 6. Environment variable families

- database connection
- queue transport settings (PGMQ default; Redis fallback profile)
- object store roots for canonical originals, derived artifacts, and exports
- model endpoint urls
- upload limits
- feature flags
- security settings
- observability settings

## 7. Operational recommendations

- pin image tags
- use health checks
- restart workers on failure
- do not colocate random experimentation code in production containers
- keep model cache and DB data on separate datasets

## 8. Upgrade strategy

- back up DB
- snapshot datasets
- apply migrations
- start new workers
- verify health
- run a small smoke set on real documents

## 9. Remote access strategy

Do not publish the app directly to the public internet. Preferred remote access patterns:
- Tailscale
- WireGuard
- private LAN only
- reverse proxy with auth inside a VPN

## 10. Runtime service matrix

See `infrastructure/runtime_service_matrix.csv` for a machine-readable deployment summary.
