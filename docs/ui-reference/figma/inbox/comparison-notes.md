# Inbox Figma Comparison

- Figma frame: `17:2` / `01 Home - Document Operations v3`
- Local route: `/`
- Target viewport: `1440 x 960`
- Implementation status: Phase 1 uses real document rows, upload state, row selection, detail fetch, and protected asset URLs.
- Intentional Phase 1 difference: Figma sample extraction values are not fabricated; fields show pending states until Phase 3 extraction exists.
- Playwright validation: `npm run test:e2e` captures `playwright-screenshot.png` at `1440 x 960` after authenticated Inbox load, upload, row selection, and inspector update.
