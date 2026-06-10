# Folder And Tag Filing Comparison

- Figma source: composite Phase 2 source set from `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- Primary Figma frame: `17:2` / `01 Home - Document Operations v3`.
- Supporting Figma frames: `14:434` / `02 Document Viewer v2`, `14:611` / `03 Extraction Workspace v2`, `35:7` / interaction specs, `35:12` / edge states, and `35:17` / dev redlines.
- Local route: `/` with the organization rail and manual filing inspector state.
- Target viewport: `1440 x 960`
- Implementation status: Phase 2 supports creating manual folders, smart-folder records, tags, filing notes, document title/date edits, multiple folder memberships, primary folder selection, and list/viewer propagation.
- Intentional Phase 2 difference: dynamic smart-folder execution remains Phase 5; Phase 2 displays saved smart-folder records and keeps manual filing usable without model workers.
- Intentional Figma interpretation: the Figma source does not provide a single dedicated finalized manual folder/tag filing screen. The Phase 2 baseline is the Inbox workbench plus Viewer propagation and handoff constraints. Older filing-rules/watched-folders mockups are deferred automation scope, not the Phase 2 manual filing baseline.
- Playwright validation: `npm run test:e2e` asserts the deterministic `phase2-filing-workflow.png` visual snapshot at `1440 x 960` after creating a folder/tag, filing a document, filtering by folder, and opening the viewer.
- Stored source artifacts: `figma-context.json`, `figma-screenshot.png`, `handoff-interaction-specs.png`, `handoff-edge-states.png`, `handoff-dev-redlines.png`, `extraction-workspace-reference.png`, and `playwright-screenshot.png`.

## 2026-06-10 shared-shell refresh

- Playwright screenshot regenerated after the Phase 8.5 viewer/inbox
  truthfulness pass. The Figma source is unchanged; deltas are inherited from
  the shared application shell and Viewer surface (derived status chips,
  truthful metric tiles, removed dead controls) rather than changes to this
  screen's own workflow.
