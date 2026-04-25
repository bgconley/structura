# Structura Agent Guidance

## Planning Source Of Truth

Use `STRUCTURA_IMPLEMENTATION_PLAN.md` as the phase map and sequencing source of truth.

The root implementation plan is not comprehensive by itself. Before implementing any phase or subphase, pull in the associated non-archive artifacts listed by the root plan and any directly related artifact-pack docs, contracts, database SQL, and infrastructure files.

Do not inspect or rely on anything under `archive/`.

## File Review Handling

When an artifact exists in both Markdown and DOCX form, read the Markdown file by default. Only inspect the DOCX version when the user explicitly asks for DOCX/layout fidelity or when the Markdown artifact is missing or appears incomplete.

For large files, avoid broad combined `cat` reads that may be truncated by terminal-output limits. Verify file length with `wc -l`, then read the file in bounded, non-overlapping chunks such as `sed -n '1,250p'` so full coverage is explicit.

## Architecture Stewardship

Treat maintainability as part of the requested work. Working code is not sufficient if it leaves the codebase more coupled, ambiguous, or difficult to test.

Before editing code, inspect the target files and decide whether the change belongs there. If a file is accumulating unrelated responsibilities, pause and refactor or propose a refactor before adding more logic.

Prefer these boundaries:

1. API routes/controllers stay thin: request parsing, auth/dependency wiring, and response construction.
2. Schemas/DTOs own input/output shapes and validation.
3. Services own business rules, orchestration, workflow behavior, and application-level decisions.
4. Repositories/DAOs own persistence, database queries, transactions, and storage details.
5. Domain modules own core business concepts and infrastructure-independent rules.
6. Adapters isolate external APIs, SDKs, filesystems, queues, model providers, and vendor behavior.
7. Utilities stay small, generic, and genuinely reusable; do not dump domain logic into vague utility modules.
8. Tests should mirror the structure of the code they validate.

Actively avoid god files, god classes, kitchen-sink utilities, circular imports, business logic hidden in route handlers or UI components, random database queries spread through the codebase, broad catch-all exception handling, vague `manager`/`processor`/`helper` modules, and boolean-flag explosions.

Use these size heuristics as warning signals, not hard limits:

1. If a file is approaching 300-500 lines and is still growing, inspect its responsibilities.
2. If a file exceeds 500 lines, treat it as a refactor candidate unless it is generated code, declarative schema, migration SQL, fixture data, or intentionally large.
3. If a file exceeds 800 lines, do not add more logic without refactoring or explicitly justifying why the file should remain large.
4. If a function exceeds roughly 50-75 lines, inspect whether it contains phases that should be extracted.
5. If a class exceeds roughly 200-300 lines, inspect whether it owns too many responsibilities.

When refactoring, preserve behavior first. Prefer small, incremental extractions with clear names and clean dependency direction. Create a new module only when the extracted code has a clear responsibility, can be understood independently, reduces future change risk, and makes tests easier to write. Do not create abstractions only to satisfy file-count or line-count aesthetics.

Naming should describe ownership. Avoid names like `misc.py`, `helpers.py`, `common.py`, `stuff.py`, `manager.py`, `processor.py`, or `logic.py` unless the surrounding package makes the responsibility precise. Prefer domain names such as `document_ingestion.py`, `organization_repository.py`, `folder_policy.py`, `auth_policy.py`, `import_manifest.py`, or `export_bundle.py`.

Layering direction matters: outer layers may depend on inner layers, but domain/business logic should not depend on web frameworks, CLI frameworks, database clients, HTTP clients, cloud SDKs, or UI frameworks. Route/UI code may call services; services may call repositories and adapters; repositories may know about the database.

Before declaring work complete, inspect every touched file and answer:

1. Does this file still have one clear responsibility?
2. Did the change land in the correct architectural layer?
3. Did the change introduce dependency direction problems or circular imports?
4. Did the change make future testing easier rather than harder?
5. Did the change avoid creating or worsening a god module?
6. Was behavior preserved, and were relevant checks run?

If any answer is concerning, fix it before calling the work complete.

## Conflict Resolution

When artifacts differ:

1. Use `STRUCTURA_IMPLEMENTATION_PLAN.md` for phase order, stop points, and gate sequencing.
2. Use v1.3 normalization and ADR artifacts, `contracts/`, `database/`, and `infrastructure/` for technical truth and acceptance detail.
3. Preserve artifact-pack semantics unless a runtime compatibility issue is proven and documented.
4. Document any intentional divergence in an ADR or equivalent project note.

## Phase 0 Orientation

The current root plan breaks Phase 0 into:

1. `0A` Repository Scaffold
2. `0B` Docker Compose And Runtime
3. `0C` Database Baseline
4. `0D` Contract Integration
5. `0E` Auth And Session Foundation
6. `0F` Job And Observability Spine

Older artifact-pack docs may group the same work differently. Treat the root plan as the active sequencing layer and the artifact pack as required implementation depth.

## GPU Node Runtime And Test Policy

Do not treat Mac-only validation as phase or major-milestone completion evidence. Local Mac runs are allowed only as quick preflight checks. For live, integration, runtime, Docker, model, or milestone-completion validation, commit locally, push to GitHub, SSH to the GPU node, pull the pushed commit there, then build and test on the GPU node.

GPU node connection and checkout settings from `STRUCTURA_PLAN_INDEX.md`:

```text
Host: 10.25.0.50
SSH user: bgconley
SSH key: /Users/brennanconley/vibecode/infx/ubuntu24_ed25519
Remote git URL: https://github.com/bgconley/structura.git
GPU node repo path: /tank/repos/structura
GPU node virtualenv root: /tank/venvs
```

Before creating any GPU-node directory or ZFS dataset, inspect the current node state with `zfs list`, `zpool list`, `findmnt`, and `ls`. Do not assume paths are missing. As of 2026-04-25, `/tank/repos` already exists as the `tank/repos` ZFS dataset and `/tank/repos/structura` already exists as a checkout directory. Application virtualenvs on the GPU node must be created under `/tank/venvs`, not inside the repository and not under `/tank/repos`; as of 2026-04-25, `/tank/venvs` exists as a directory on the root ext4 filesystem, not as a dedicated ZFS dataset.

Persistent runtime state follows the ZFS plan in `pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md` and `pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv`. The recommended pool example is `tank/structura`, mounted at `/srv/structura`; `POOL` in the matrix is a placeholder. Runtime root for Compose bind mounts is `${STRUCTURA_RUNTIME_ROOT:-/srv/structura}`.

Key runtime paths:

```text
Runtime root: /srv/structura
Postgres data: /srv/structura/postgres
Redis fallback data: /srv/structura/redis
Canonical objects: /srv/structura/objects/canonical
Derived objects: /srv/structura/objects/derived
Exports: /srv/structura/objects/exports
Model storage: /srv/structura/models
Staging: /srv/structura/staging
Cache: /srv/structura/cache
Runtime config: /srv/structura/config
Logs: /srv/structura/logs
Backups: /srv/structura/backups
Observability: /srv/structura/observability
Temporary utilities scratch: /srv/structura/tmp
```

Docker bind mounts are the `/srv/structura` paths declared in `compose.yaml` and `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`: Postgres uses `/srv/structura/postgres`; API uses `config/api`, `objects/canonical`, `objects/derived`, `objects/exports`, `cache`, and `logs/api`; web uses `config/web` and `cache`; ingest uses `staging`, `objects/canonical`, and `logs/workers`; previews uses `staging`, `objects/derived`, `cache`, and `logs/workers`; Docling uses `staging`, `objects/derived`, and `logs/workers`; extraction, embeddings, relationships, and analysis use `objects/derived` and `logs/workers`; model services use `models` and `logs/models`; Redis fallback uses `redis`.

The artifacts do not define a Docker daemon image-store/data-root path. Do not invent or change Docker image storage without a new explicit decision or ADR; use the GPU node's existing Docker configuration until that decision is made.

Do not install or rely on host `node` or `npm` on the GPU node for Structura verification. The GPU host should provide orchestration capabilities such as `ssh`, `git`, `docker`, `docker compose`, ZFS tools, and Python venv tooling for Python-side gates. Web lint/build and browser E2E gates must run through pinned container images or app images so Node/npm versions stay tied to the runtime/test image contract. Current pinned surfaces are `node:20-alpine` for the web app image and `mcr.microsoft.com/playwright:v1.59.1-noble` for browser E2E.

Observed GPU-node ZFS state on 2026-04-25:

```text
Pool: tank, ONLINE, size 3.62T, allocated 376G, free 3.26T
Existing relevant dataset: tank/repos mounted at /tank/repos
Existing repo checkout: /tank/repos/structura
Existing venv directory: /tank/venvs, currently on root ext4 rather than a dedicated ZFS dataset
Existing Docker root: /var/lib/docker, currently on root ext4
Missing runtime mount root: /srv/structura
Missing expected runtime dataset tree: tank/structura and all tank/structura/* children from the Structura ZFS matrix
```

Expected Structura runtime datasets still to create before production-equivalent runtime validation, unless an operator intentionally maps them differently:

```text
tank/structura -> /srv/structura
tank/structura/postgres -> /srv/structura/postgres
tank/structura/redis -> /srv/structura/redis
tank/structura/objects-canonical -> /srv/structura/objects/canonical
tank/structura/objects-derived -> /srv/structura/objects/derived
tank/structura/objects-exports -> /srv/structura/objects/exports
tank/structura/models -> /srv/structura/models
tank/structura/staging -> /srv/structura/staging
tank/structura/cache -> /srv/structura/cache
tank/structura/config -> /srv/structura/config
tank/structura/logs -> /srv/structura/logs
tank/structura/backups -> /srv/structura/backups
tank/structura/observability -> /srv/structura/observability
tank/structura/tmp -> /srv/structura/tmp
```

The artifact matrix also lists optional `tank/structura/repo` and `tank/structura/venv`, but the active GPU-node policy supersedes those for source and virtualenv placement: use `/tank/repos/structura` and `/tank/venvs`.
