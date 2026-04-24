# Structura Canonical Planning Index

Last updated: 2026-04-24

This workspace contains the original artifact pack at `pro-merged-master-v1.2/` plus the implementation planning documents below. Treat these root-level plans as the working implementation layer derived from the artifact pack and the user's clarified UI direction.

## Canonical Planning Docs

1. `STRUCTURA_IMPLEMENTATION_PLAN.md`
   - End-to-end phased build plan.
   - Includes backend, database, workers, UI slices, search, analysis, exports, hardening, and release gates.
   - References the artifact pack as source material.

2. `STRUCTURA_UI_FIGMA_QA_PLAN.md`
   - Pixel-for-pixel UI implementation and QA process.
   - Uses the Figma mockups as the UI visual source of truth.
   - Defines Playwright screenshot and workflow validation expectations.

## Source Artifact Pack

Primary artifact directory:

```text
pro-merged-master-v1.2/
```

Important source files:

```text
pro-merged-master-v1.2/AGENT_START_HERE.md
pro-merged-master-v1.2/docs/01_App_Specification.md
pro-merged-master-v1.2/docs/01_App_Specification.docx
pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.docx
pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md
pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
pro-merged-master-v1.2/database/
pro-merged-master-v1.2/contracts/
pro-merged-master-v1.2/infrastructure/
```

The `.md` and `.docx` files must be treated as co-equal source artifacts. Do not rely on the stale note that the DOCX files are only convenience exports.

## Source Alignment Policy

Use the root-level planning docs as the working implementation layer, but keep them subordinate to explicit source facts from the artifact pack and the user's later clarifications.

When non-UI artifacts disagree, use this order unless the user has explicitly overridden it:

1. User clarification in the active implementation thread.
2. Co-equal DOCX and Markdown artifact content.
3. `docs/10_Architectural_Decision_Record_Summary.md`.
4. `docs/21_v1.3_Normalization_and_Design_Language.md`.
5. `database/*.sql` in documented apply order.
6. `contracts/api/openapi.yaml`.
7. `contracts/schemas/*.json` and `contracts/events/*.json`.
8. Remaining artifact docs as explanatory context.

If a DOCX and Markdown source conflict materially, stop and ask the user. Do not silently choose one.

When UI artifacts disagree, use this order:

1. User clarification.
2. Figma frame, component, interaction, edge-state, and redline pages.
3. `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
4. `docs/21_v1.3_Normalization_and_Design_Language.md`.
5. Local static `design-language-v1.3.html` and screenshot.

If the Figma sources conflict in a way that affects visible workflow or layout, stop and ask the user.

## UI Source Of Truth

Use Figma MCP and Playwright for UI implementation and verification.

Figma file:

```text
https://www.figma.com/design/5GAPHbduQLu9INBOXUPxJN/Structura-v1.3-Product-Mockups
```

User-supplied Figma nodes:

```text
14:2 - 04 Mockups - Prism Refinement
35:2 - 05 Handoff - Component Variants
```

Important frames found under those pages:

```text
17:2   - 01 Home - Document Operations v3
14:434 - 02 Document Viewer v2
14:611 - 03 Extraction Workspace v2
14:797 - 04 Natural Language Corpus Search v2
14:990 - 05 Analysis and Inference Request v2
35:2   - Component variants page
35:7   - Interaction specs page
35:12  - Edge states page
35:17  - Dev redlines page
```

## UI Priority Order

1. Upload + Inbox + Document Viewer
2. Review Queue + Evidence Inspector
3. Folder/tag filing workflow

First working screen: Inbox.

## Stop Rule

If implementation reaches an ambiguous UI/UX decision not settled by the Figma mockups, dev redlines, interaction specs, or this planning layer, stop and ask the user before proceeding.
