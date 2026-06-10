# Parse Debug Comparison

- Figma source: Phase 3 parse-debug uses the Viewer and Extraction Workspace source frames from `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- Primary Figma frame: `14:434` / `02 Document Viewer v2`.
- Supporting Figma frames: `14:611` / `03 Extraction Workspace v2`, `35:7` / interaction specs, and `35:12` / edge states.
- Local route: `/` with the Viewer opened and the parse-debug panel loaded.
- Target viewport: `1440 x 960`
- Implementation status: Phase 3 exposes read-only canonical Docling artifacts, page text previews, elements, tables, chunks, and worker job status in the Viewer.
- Intentional Phase 3 difference: the Figma set does not include a standalone finalized parse-debug frame. This baseline treats parse-debug as a Viewer diagnostic extension, not the later extraction review workspace.
- Playwright validation: `npm run test:e2e` asserts the deterministic `phase3-parse-debug.png` visual snapshot at `1440 x 960`.
- Stored source artifacts: `figma-context.json`, `playwright-screenshot.png`, plus the linked Viewer and Extraction Workspace Figma artifacts in sibling reference folders.

## 2026-06-10 shared-shell refresh

- Playwright screenshot regenerated after the Phase 8.5 viewer/inbox
  truthfulness pass. The Figma source is unchanged; deltas are inherited from
  the shared application shell and Viewer surface (derived status chips,
  truthful metric tiles, removed dead controls) rather than changes to this
  screen's own workflow.
