# Review Extraction Comparison

- Figma source: Phase 4 uses `14:611` / `03 Extraction Workspace v2` from `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- Supporting Figma frames: `14:434` / `02 Document Viewer v2`, `35:7` / interaction specs, and `35:12` / edge states.
- Local route: `/` with the Review Queue opened from the left navigation.
- Target viewport: `1440 x 960`
- Implementation status: Phase 4 exposes extraction review tasks, candidate facts, canonical facts, source evidence, candidate confirmation, task closure, and extraction rerun actions.
- Intentional Phase 4 difference: the implemented surface is a focused review queue rather than the full later extraction workspace. Phase 5 search and answer synthesis remain deferred, while accepted canonical facts are already projected for that integration path.
- Playwright validation: `npm run test:e2e` asserts the deterministic `phase4-review-queue.png` visual snapshot at `1440 x 960`.
- Stored source artifacts: `figma-context.json`, `figma-screenshot.png`, and `playwright-screenshot.png`.
