# Phase 6 Automation Workbench UI Reference

## Source

- Primary implementation source: `STRUCTURA_PHASE_6_IMPLEMENTATION_PLAN.md` section 6.11.
- Visual baseline: Structura v1.3 evidence-workbench language plus the Figma handoff/review workspace references listed in `figma-context.json`.
- There is no dedicated single final Figma frame for Phase 6 rules and watched-folder automation in `STRUCTURA_UI_FIGMA_QA_PLAN.md`.

## Covered Surface

- Contacts search/detail/create.
- Filing rule create and dry-run explanation.
- Suggested filing accept/reject/defer actions.
- Watched-folder configuration.
- Import status.

## Regression Baseline

- Deterministic snapshot: `tests/e2e/phase6.spec.ts-snapshots/phase6-automation-workbench-chromium-linux.png`.
- Reference copy: `docs/ui-reference/figma/automation/playwright-screenshot.png`.
- Browser container: `mcr.microsoft.com/playwright:v1.59.1-noble`.
- Viewport: Playwright project default desktop viewport.
