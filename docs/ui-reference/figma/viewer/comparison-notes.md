# Viewer Figma Comparison

- Figma frame: `14:434` / `02 Document Viewer v2`
- Local route: `/` with Viewer state opened from an Inbox row.
- Target viewport: `1440 x 960`
- Implementation status: Phase 1 renders protected preview/page assets when available and exposes original downloads through the asset API.
- Intentional Phase 1 difference: full PDF/page rendering remains a Phase 3 hardening item; Phase 1 creates a stable protected SVG preview fallback.
- Playwright validation: `npm run test:e2e` asserts the deterministic `phase1-viewer.png` visual snapshot at `1440 x 960` after opening Viewer from the uploaded Inbox row and verifying protected preview/original asset URLs.

## 2026-06-10 viewer truthfulness refresh

- Playwright screenshot regenerated from `phase1-viewer-chromium-linux.png`
  after the Phase 8.5 review-workflow surfacing pass. The Figma source frame
  (`14:434`) is unchanged; the deltas below are intentional implementation
  evolution beyond the Phase 1 frame.
- Page rail now navigates real document pages; evidence renders on its actual
  evidence page and highlights draw only when a bbox exists (no fabricated
  highlight on page 1).
- The constant "Extraction pending" chip is replaced by a chip derived from
  extraction/quality-outcome state; the constant "86% confidence" chip is
  replaced by real candidate confidence (hidden when absent).
- The quality banner reads "Document quality signals" (formerly "Phase 8
  quality signals"); "Open review" navigates to the Review Queue; dead
  controls without handlers were removed.
- New panels render semantic region extractions (semantic type, Granite task,
  status, quality outcome), observation candidates with evidence jumps, and
  claim resolution decisions with reason codes.
