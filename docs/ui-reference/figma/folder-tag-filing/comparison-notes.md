# Folder And Tag Filing Comparison

- Figma frame: filing workflow uses the Inbox workbench frame `17:2` with the handoff pages `35:2`, `35:7`, `35:12`, and `35:17` for folder/tag controls and edge states.
- Local route: `/` with the organization rail and manual filing inspector state.
- Target viewport: `1440 x 960`
- Implementation status: Phase 2 supports creating manual folders, smart-folder records, tags, filing notes, document title/date edits, multiple folder memberships, primary folder selection, and list/viewer propagation.
- Intentional Phase 2 difference: dynamic smart-folder execution remains Phase 5; Phase 2 displays saved smart-folder records and keeps manual filing usable without model workers.
- Playwright validation: `npm run test:e2e` asserts the deterministic `phase2-filing-workflow.png` visual snapshot at `1440 x 960` after creating a folder/tag, filing a document, filtering by folder, and opening the viewer.
