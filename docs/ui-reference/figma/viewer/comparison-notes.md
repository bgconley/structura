# Viewer Figma Comparison

- Figma frame: `14:434` / `02 Document Viewer v2`
- Local route: `/` with Viewer state opened from an Inbox row.
- Target viewport: `1440 x 960`
- Implementation status: Phase 1 renders protected preview/page assets when available and exposes original downloads through the asset API.
- Intentional Phase 1 difference: full PDF/page rendering remains a Phase 3 hardening item; Phase 1 creates a stable protected SVG preview fallback.
- Playwright validation: `npm run test:e2e` captures `playwright-screenshot.png` at `1440 x 960` after opening Viewer from the uploaded Inbox row and verifying protected preview/original asset URLs.
