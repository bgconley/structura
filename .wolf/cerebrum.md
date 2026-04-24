# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-04-24

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

- Treat Markdown and DOCX artifacts in `pro-merged-master-v1.2` as co-equal sources. Ignore stale artifact language claiming DOCX files are only convenience exports.
- For UI, implement pixel-for-pixel from the Figma mockups using Figma MCP plus Playwright validation. Stop and ask the user if UI/UX ambiguity remains after checking Figma frames, component variants, interaction specs, edge states, and redlines.
- First working Structura screen must be Inbox. UI priority order is: 1) upload + inbox + document viewer, 2) review queue + evidence inspector, 3) folder/tag filing workflow.
- After every local commit and push to GitHub, immediately SSH to the GPU node and pull/update `/tank/repos/structura`.
- Application virtualenvs for the GPU node belong under `/tank/venvs`, not inside the repo.

## Key Learnings

- **Project:** structura
- Canonical working docs at repo root are `STRUCTURA_PLAN_INDEX.md`, `STRUCTURA_IMPLEMENTATION_PLAN.md`, and `STRUCTURA_UI_FIGMA_QA_PLAN.md`. Use these together with the original artifacts during implementation.
- Source artifact pack lives at `/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2`. Each implementation phase in `STRUCTURA_IMPLEMENTATION_PLAN.md` has required artifact paths that must be reviewed before coding that phase.
- Figma file key is `5GAPHbduQLu9INBOXUPxJN`. User-provided Figma nodes `14:2` and `35:2` are page nodes, not direct screen frames. Use concrete frames including `17:2`, `14:434`, `14:611`, `14:797`, `14:990`, plus handoff pages `35:2`, `35:7`, `35:12`, and `35:17`.
- GitHub remote is `https://github.com/bgconley/structura.git`; current branch is `master`.
- GPU node sync target is `bgconley@10.25.0.50` using SSH key `/Users/brennanconley/vibecode/infx/ubuntu24_ed25519`; repo checkout path is `/tank/repos/structura`.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

- [2026-04-24] Do not call Figma design-context tools on page nodes like `14:2` or `35:2` and assume they are screen frames. Inspect the Figma page structure first and target concrete child frames.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- [2026-04-24] Root planning docs are the canonical working implementation layer for agentic coding, but they must be used alongside the original artifact pack. Phase-specific artifact lists in `STRUCTURA_IMPLEMENTATION_PLAN.md` are mandatory required context, not optional references.
- [2026-04-24] Git repo initialized in `/Users/brennanconley/vibecode/structura`, remote set to `https://github.com/bgconley/structura.git`, and `archive/` is ignored. Everything else requested by the user was tracked and pushed.
- [2026-04-24] Deployment development workflow targets GPU node `10.25.0.50`: after each commit/push, pull or clone to `/tank/repos/structura`; put venvs under `/tank/venvs`; otherwise follow artifact ZFS plan.
