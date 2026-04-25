# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-04-25

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

- For duplicate artifacts in `pro-merged-master-v1.2`, read the Markdown file by default. DOCX review is only needed when the user explicitly asks for layout/fidelity review or the Markdown file is missing/incomplete.
- For UI, implement pixel-for-pixel from the Figma mockups using Figma MCP plus Playwright validation. Stop and ask the user if UI/UX ambiguity remains after checking Figma frames, component variants, interaction specs, edge states, and redlines.
- First working Structura screen must be Inbox. UI priority order is: 1) upload + inbox + document viewer, 2) review queue + evidence inspector, 3) folder/tag filing workflow.
- After every local commit and push to GitHub, immediately SSH to the GPU node and pull/update `/tank/repos/structura`.
- Application virtualenvs for the GPU node belong under `/tank/venvs`, not inside the repo.
- Do not call Structura phase or major-milestone completion from Mac-only tests. Mac validation is preflight only; live/integration/runtime/Docker/model milestone evidence must be run on the GPU node after commit, push, SSH, and pull.
- Before creating any GPU-node directory or ZFS dataset, inspect the current node state first. Do not assume `/tank/repos`, `/tank/repos/structura`, `/tank/venvs`, `/srv/structura`, or any `tank/structura/*` dataset is missing or present without checking.
- Do not install or depend on host `node`/`npm` on the GPU node for Structura gates. Use pinned container/app images for web lint/build and Playwright so Node/npm versions are reproducible.
- Act as an architecture steward, not only a feature implementer. Preserve separation of concerns, SRP, high cohesion, low coupling, explicit layer boundaries, small understandable units, behavior-preserving refactors, meaningful abstractions, clear interfaces, and tests/type checks as guardrails.
- Before editing code, inspect target files for overloaded responsibilities. If a file is already accumulating unrelated routing, validation, persistence, orchestration, formatting, or UI logic, pause and extract or propose a focused refactor before adding more logic.
- Keep route/controller/UI code thin. Put business rules and orchestration in service/domain modules, database access in repositories/DAOs, external integrations in adapters, and reusable pure rules in precisely named modules rather than vague utilities.
- Treat file size as an architecture warning signal: review files approaching 300-500 lines; treat files over 500 lines as refactor candidates unless intentionally large; do not add logic to files over 800 lines without refactoring or explicitly justifying the exception.
- Avoid god files/classes, kitchen-sink `utils` modules, vague `manager`/`processor`/`helper` modules, business logic hidden in route handlers or UI components, random SQL spread through the codebase, circular imports, broad catch-all exception hiding, and boolean-flag explosions.
- When modifying oversized modules, prefer small behavior-preserving extraction before or alongside the requested change. Name new modules by responsibility, keep dependency direction clean, preserve public APIs where practical, and add or retain tests around moved behavior.
- Use `STRUCTURA_IMPLEMENTATION_PLAN.md` as the phase map and sequencing source of truth, but always pull in associated non-archive artifacts for implementation detail because the root plan is intentionally not comprehensive.
- When Structura artifacts exist in both Markdown and DOCX form, read the Markdown artifact by default; only inspect DOCX when the user explicitly asks for layout/fidelity review or when Markdown is missing/incomplete.
- For large artifact reviews, terminal output can truncate even when the read command succeeds. Verify length with `wc -l` and read bounded non-overlapping chunks with tools like `sed -n`, rather than broad combined `cat` calls.
- For Structura implementation work, start with the root plan, then the relevant phase-specific execution plan, then the subphase Fresh Context list. Re-read the relevant documents before coding each subphase rather than relying on old context.
- For APIs, contracts, conventions, library behavior, security, database semantics, UI testing, backup/restore, release engineering, or any uncertain implementation decision, use Firecrawl to gather current evidence from primary sources and record the rationale in implementation notes, ADRs, or release docs.
- The duplicate `docs/01_App_Specification` and `docs/02_Phased_Implementation_Plan` Markdown/DOCX pairs were spot-checked on 2026-04-24 and no material content differences were found; Markdown remains the default working source unless fidelity review or suspected drift requires opening DOCX.

## Key Learnings

- **Project:** structura
- Canonical working docs at repo root are `STRUCTURA_PLAN_INDEX.md`, `STRUCTURA_IMPLEMENTATION_PLAN.md`, and `STRUCTURA_UI_FIGMA_QA_PLAN.md`. Use these together with the original artifacts during implementation.
- Source artifact pack lives at `/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2`. Each implementation phase in `STRUCTURA_IMPLEMENTATION_PLAN.md` has required artifact paths that must be reviewed before coding that phase.
- For implementation depth, use related non-archive artifact-pack docs, contracts, database SQL, and infrastructure files alongside the root implementation plan. Do not inspect or rely on `archive/`.
- Figma file key is `5GAPHbduQLu9INBOXUPxJN`. User-provided Figma nodes `14:2` and `35:2` are page nodes, not direct screen frames. Use concrete frames including `17:2`, `14:434`, `14:611`, `14:797`, `14:990`, plus handoff pages `35:2`, `35:7`, `35:12`, and `35:17`.
- GitHub remote is `https://github.com/bgconley/structura.git`; current branch is `master`.
- GPU node sync target is `bgconley@10.25.0.50` using SSH key `/Users/brennanconley/vibecode/infx/ubuntu24_ed25519`; repo checkout path is `/tank/repos/structura`.
- GPU node source/venv paths are node-specific: clone or pull the repo at `/tank/repos/structura`, and create application virtualenvs under `/tank/venvs`.
- On 2026-04-25, direct GPU-node inspection showed `tank/repos` exists and is mounted at `/tank/repos`; `/tank/repos/structura` exists as a checkout directory; `/tank/venvs` exists but is on the root ext4 filesystem, not a dedicated ZFS dataset; `/srv/structura` does not exist; Docker root is `/var/lib/docker` on root ext4.
- On 2026-04-25, none of the expected `tank/structura` runtime datasets existed: parent `tank/structura`, `postgres`, `redis`, `objects-canonical`, `objects-derived`, `objects-exports`, `models`, `staging`, `cache`, `repo`, `venv`, `config`, `logs`, `backups`, `observability`, or `tmp`.
- Structura runtime data and Compose bind mounts use the ZFS runtime root `/srv/structura`, not the `/tank/repos` checkout. Key mounts are `/srv/structura/postgres`, `/srv/structura/redis`, `/srv/structura/objects/canonical`, `/srv/structura/objects/derived`, `/srv/structura/objects/exports`, `/srv/structura/models`, `/srv/structura/staging`, `/srv/structura/cache`, `/srv/structura/config`, `/srv/structura/logs`, `/srv/structura/backups`, `/srv/structura/observability`, and `/srv/structura/tmp`.
- Model storage belongs at `/srv/structura/models`; model service logs belong at `/srv/structura/logs/models`.
- The artifact set does not specify a Docker daemon image-store/data-root. Do not move Docker image storage or invent a path without an explicit decision/ADR; use the GPU node's existing Docker configuration until then.
- GPU-node host tooling should stay minimal: orchestration tools, Docker/Compose, ZFS, Git/SSH, and Python venvs for Python gates. Web build tooling is containerized; current pinned images are `node:20-alpine` for the app web image and `mcr.microsoft.com/playwright:v1.59.1-noble` for browser E2E.
- Phase 0A-0F is implemented locally. The next build slice should start at Phase 1 in `STRUCTURA_IMPLEMENTATION_PLAN.md`: upload, Inbox, and protected viewer.
- Dedicated execution plans now exist for Phase 1, Phase 2, Phase 3, Phase 4, Phase 5, Phase 6, Phase 7, Phase 8, Phase 9, Phase 10, Phase 11, and the final derived Phase 12 at `STRUCTURA_PHASE_1_IMPLEMENTATION_PLAN.md`, `STRUCTURA_PHASE_2_IMPLEMENTATION_PLAN.md`, `STRUCTURA_PHASE_3_IMPLEMENTATION_PLAN.md`, `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md`, `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, `STRUCTURA_PHASE_6_IMPLEMENTATION_PLAN.md`, `STRUCTURA_PHASE_7_IMPLEMENTATION_PLAN.md`, `STRUCTURA_PHASE_8_IMPLEMENTATION_PLAN.md`, `STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md`, `STRUCTURA_PHASE_10_IMPLEMENTATION_PLAN.md`, `STRUCTURA_PHASE_11_IMPLEMENTATION_PLAN.md`, and `STRUCTURA_PHASE_12_IMPLEMENTATION_PLAN.md`; use them as phase-specific implementation guides after the root plan. The root implementation plan stops at Phase 11; Phase 12 is the final internal-GA/operator-handoff phase derived from the release-candidate and definition-of-done artifacts.
- Phase plan usage order for implementation:
  1. Read `STRUCTURA_PLAN_INDEX.md` for source alignment, UI/Figma rules, GPU sync, and stop rules.
  2. Read `STRUCTURA_IMPLEMENTATION_PLAN.md` for sequencing, phase gate, and required artifact list.
  3. Read the matching `STRUCTURA_PHASE_N_IMPLEMENTATION_PLAN.md` for subphase execution detail.
  4. Re-read the subphase's Fresh Context files immediately before coding that subphase.
  5. Pull in the associated non-archive artifact-pack docs, contracts, database SQL, infrastructure files, and UI references named by the plan.
  6. If implementation touches UI, inspect the concrete Figma frame and run/record Playwright validation.
  7. If implementation touches API/schema/database/events, keep OpenAPI, JSON Schemas, DTOs, route parity, migrations, tests, and docs synchronized in the same change set.
  8. Verify with the phase gate commands and targeted tests before moving on.
- Phase 11 is release-candidate measurement and regression: golden corpus, expected answers, deterministic evaluation, extraction/search scoring, Playwright smoke, migration-from-scratch, restore rehearsal, SAST/data-flow, performance, and evidence pack. It should not be used as a broad feature expansion phase.
- Phase 12 is the final derived internal-GA/operator-handoff phase: consume Phase 11 evidence, close valid blockers, freeze contracts/schema/runtime assumptions, finalize runbooks and release notes, prepare tag/deployment sync if requested, write go/no-go, and stop. Do not create Phase 13 or continue into new feature work without explicit user direction.
- When findings arise in review or validation, map each finding back to the owning phase plan and artifacts before fixing it. Do not resolve it from memory alone.
- Phase-specific plans are execution guides, not replacements for the artifact pack. If the root plan, phase plan, Figma, contracts, database SQL, or artifacts disagree, follow the source alignment policy in `STRUCTURA_PLAN_INDEX.md` and stop for user clarification when the conflict is material.
- The root planning docs were aligned on 2026-04-24 to match the phase-specific plans: Markdown-first for duplicate artifact pairs, with DOCX reserved for fidelity review, suspected incompleteness, or suspected material mismatch.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

- [2026-04-24] Do not call Figma design-context tools on page nodes like `14:2` or `35:2` and assume they are screen frames. Inspect the Figma page structure first and target concrete child frames.
- [2026-04-24] Do not assume a large `cat` output was fully delivered into agent context. Use file length checks and explicit chunked reads so full artifact coverage is auditable.
- [2026-04-24] Do not treat the phase-specific plans as permission to skip artifact rereads. Each subphase explicitly requires fresh context, especially around API contracts, schema, database, UI, security, backup/restore, and release gates.
- [2026-04-24] Do not invent phases after Phase 12. The root implementation plan stops at Phase 11, and Phase 12 is the final derived internal-GA/operator-handoff plan unless the user explicitly asks for new planning.
- [2026-04-24] Do not force duplicate DOCX review when the corresponding Markdown file has already been parity-checked and no material difference is known. Use DOCX only for fidelity review, missing/incomplete Markdown, or suspected drift.
- [2026-04-25] Do not run live/integration/runtime milestone gates only on the Mac and report them as complete. Commit, push, pull to `bgconley@10.25.0.50:/tank/repos/structura`, then build and test on the GPU node for completion evidence.
- [2026-04-25] Do not say or imply `/tank/repos` needs to be created without inspecting the GPU node first. It already exists as `tank/repos`; future creation decisions must follow current `zfs list`/`findmnt` evidence.
- [2026-04-25] Do not install host Node/npm on the GPU node as a workaround for web gates. Containerize Node-dependent verification with pinned images instead.
- [2026-04-25] Do not keep appending feature logic to oversized Structura modules. `apps/api/structura_api/routes_documents.py` grew past 800 lines during Phase 2 kickoff and must be decomposed before more organization behavior is added there.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- [2026-04-24] Root planning docs are the canonical working implementation layer for agentic coding, but they must be used alongside the original artifact pack. Phase-specific artifact lists in `STRUCTURA_IMPLEMENTATION_PLAN.md` are mandatory required context, not optional references.
- [2026-04-24] Implementation sequencing follows `STRUCTURA_IMPLEMENTATION_PLAN.md`; technical acceptance details come from the related non-archive artifacts, especially v1.3 ADR/normalization docs, contracts, database SQL, and infrastructure matrices. If the root plan is thin, expand from those artifacts rather than improvising.
- [2026-04-24] Git repo initialized in `/Users/brennanconley/vibecode/structura`, remote set to `https://github.com/bgconley/structura.git`, and `archive/` is ignored. Everything else requested by the user was tracked and pushed.
- [2026-04-24] Deployment development workflow targets GPU node `10.25.0.50`: after each commit/push, pull or clone to `/tank/repos/structura`; put venvs under `/tank/venvs`; otherwise follow artifact ZFS plan.
- [2026-04-25] Runtime placement is split by concern: source checkout is `/tank/repos/structura`, virtualenvs are `/tank/venvs`, durable app data is under `/srv/structura`, and model weights are under `/srv/structura/models`. Docker bind mounts come from `${STRUCTURA_RUNTIME_ROOT:-/srv/structura}`. Docker daemon image storage is unspecified in current artifacts and requires an explicit decision before changing.
- [2026-04-25] GPU-node ZFS preflight found existing pool `tank` online with `tank/repos` mounted at `/tank/repos`, but no `tank/structura` runtime dataset tree. Before production-equivalent Structura validation, create or map the missing `/srv/structura` runtime datasets intentionally; do not use Mac or root ext4 runtime state as completion evidence.
- [2026-04-25] Structura web verification should not depend on host Node/npm. Runtime and test Node versions are controlled by pinned container images: app web image `node:20-alpine`, browser E2E image `mcr.microsoft.com/playwright:v1.59.1-noble`.
- [2026-04-25] Architecture stewardship is a standing implementation requirement. New work should leave the codebase more modular, cohesive, testable, and less likely to collapse into god files. Complete features should be delivered through thin outer layers, cohesive services/repositories/adapters, and targeted tests rather than convenience-driven accumulation.
- [2026-04-24] Phase 0 auth baseline uses Argon2id password credentials, durable `sessions`, non-HttpOnly CSRF cookie paired with HttpOnly session cookie, API-token principal resolution, and route dependencies that protect document, asset, job, and admin health surfaces.
- [2026-04-24] Phase 0 job baseline uses the `pipeline_jobs` table as the concrete queue state because the pinned ParadeDB PostgreSQL 17 image does not package PGMQ. Default workers expose internal health endpoints and record `service_health_snapshots`.
- [2026-04-24] Baseline migrations are tracked in `structura.schema_migrations`; legacy Phase 0 databases without that table are adopted by detecting representative schema objects, then future migration runs are no-ops.
- [2026-04-24] Phase 0 auth endpoints should let FastAPI/Pydantic handle session request validation so malformed bodies return 422, not unhandled 500s.
- [2026-04-24] Session and CSRF cookie names are configurable; all cookie reads must use `Settings.session_cookie_name` and `Settings.csrf_cookie_name`, not hardcoded aliases.
- [2026-04-24] Phase 0 keeps `pipeline_jobs` as the active queue ledger while recording an explicit fallback reason when the requested transport is PGMQ or Redis. Retryable failures use bounded exponential backoff before workers can claim them again.
- [2026-04-24] Phase 0 should expose protected skeletons for the active OpenAPI path set even when the owning feature phase is later. Generated FastAPI OpenAPI paths must match `contracts/api/openapi.yaml`; keep internal probes such as `/healthz` out of the public schema.
- [2026-04-24] Static analysis is part of the Phase 0 baseline: `make sast` runs Bandit, Semgrep, Pyright, and mypy, while Docker images run as non-root users.
- [2026-04-24] Structura's phase-specific execution plans are to be used as living implementation checklists. They deliberately include Fresh Context rereads and Firecrawl evidence instructions so future agents keep context current and support uncertain decisions with current primary-source evidence.
- [2026-04-24] Phase 11 and Phase 12 have different purposes: Phase 11 measures and produces release-candidate evidence; Phase 12 consumes that evidence to close blockers, freeze the release, hand off operations, and write the final go/no-go. Treat Phase 12 as the final planned phase.
- [2026-04-24] `STRUCTURA_PLAN_INDEX.md` and `STRUCTURA_IMPLEMENTATION_PLAN.md` now explicitly support Markdown-first artifact review with a parity note for the duplicate `01` and `02` DOCX pairs, so the root planning layer is consistent with the phase-specific plans and the user's clarified workflow.
