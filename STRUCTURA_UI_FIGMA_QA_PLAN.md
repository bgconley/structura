# Structura UI, Figma, And Playwright QA Plan

Last updated: 2026-04-24

This document defines the canonical UI implementation and QA process for Structura.

## User Decisions

- First working screen: Inbox.
- UI must be implemented pixel-for-pixel from Figma mockups.
- Use Figma MCP for design context, screenshots, measurements, components, interaction specs, edge states, and redlines.
- Use Playwright to validate local UI rendering and workflows.
- UI slice priority:
  1. Upload + Inbox + Document Viewer
  2. Review Queue + Evidence Inspector
  3. Folder/tag filing workflow
- If further UI/UX questions arise, stop and ask the user.

## Figma Source

Figma file:

```text
https://www.figma.com/design/5GAPHbduQLu9INBOXUPxJN/Structura-v1.3-Product-Mockups
```

File key:

```text
5GAPHbduQLu9INBOXUPxJN
```

User-supplied nodes:

```text
14:2 - 04 Mockups - Prism Refinement
35:2 - 05 Handoff - Component Variants
```

Concrete frames discovered through Figma MCP:

```text
17:2   - 01 Home - Document Operations v3
14:434 - 02 Document Viewer v2
14:611 - 03 Extraction Workspace v2
14:797 - 04 Natural Language Corpus Search v2
14:990 - 05 Analysis and Inference Request v2
35:2   - 05 Handoff - Component Variants
35:7   - 06 Handoff - Interaction Specs
35:12  - 07 Handoff - Edge States
35:17  - 08 Handoff - Dev Redlines
```

Use these frames as the visual and interaction source of truth. The local `design-language-v1.3.html` and `design-language-dashboard.PNG` remain useful background, but Figma wins for pixel implementation.

## Figma MCP Workflow

Before implementing a UI surface:

1. Call Figma MCP `get_design_context` for the concrete target screen frame, not the containing page node.
2. Call Figma MCP `get_screenshot` for the target screen frame.
3. Inspect component variants from page `35:2`.
4. Inspect interaction specs from page `35:7`.
5. Inspect edge states from page `35:12`.
6. Inspect dev redlines from page `35:17`.
7. Extract exact layout measurements, typography, colors, spacing, radii, borders, and states.
8. Save reference screenshots into the repo under a future implementation path such as:

```text
docs/ui-reference/figma/
```

Do not use `use_figma` unless JavaScript-based file inspection is needed. If using `use_figma`, first load and follow the `figma-use` skill and pass `skillNames: "figma-use"`.

Known Figma note:

- The user-provided nodes `14:2` and `35:2` are Figma pages. For design-to-code context and screenshots, use concrete child frames such as `17:2`, `14:434`, `14:611`, `14:797`, and `14:990`.
- If `get_design_context` reports no selection for a node, inspect page structure with `use_figma` following the `figma-use` skill, then retry on the concrete frame.

## Required Reference Artifacts During Implementation

For each screen, save these implementation references in the future app repo:

```text
docs/ui-reference/figma/<screen-name>/figma-context.json
docs/ui-reference/figma/<screen-name>/figma-screenshot.png
docs/ui-reference/figma/<screen-name>/playwright-screenshot.png
docs/ui-reference/figma/<screen-name>/comparison-notes.md
```

The comparison notes should record:

- Figma frame id.
- Local route and viewport.
- Known intentional differences, if any.
- Remaining pixel mismatches.
- User approval if a mismatch is accepted.

## Implementation Stack

Frontend:

- React + Vite + TypeScript.
- CSS modules, scoped CSS, or equivalent project-standard styling.
- Use stable component boundaries:
  - App shell
  - Sidebar navigation
  - Top search/upload bar
  - Status chip
  - Metric tile
  - Document data grid
  - Evidence inspector
  - Pipeline step
  - Document viewer
  - Review task row
  - Field evidence row
  - Folder tree
  - Tag editor

Use icon libraries only if they can match Figma accurately. If a Figma icon is custom, export or reproduce it as needed.

## Visual Tokens

The implementation must be extracted from Figma, but expected baseline direction is:

- Workbench density, not marketing layout.
- Light canvas, white panels, subtle borders.
- Compact typography.
- Status colors used sparingly.
- Persistent left nav on desktop.
- Persistent right inspector on desktop.
- Responsive inspector drawer or route on narrower screens.

Do not invent a new theme if the Figma tokens are available.

## UI Slice 1 - Upload + Inbox + Document Viewer

Primary Figma frames:

```text
17:2   - 01 Home - Document Operations v3
14:434 - 02 Document Viewer v2
35:2   - Component variants
35:7   - Interaction specs
35:12  - Edge states
35:17  - Dev redlines
```

Required UI:

- Sign-in redirects to Inbox after successful session creation.
- Inbox is the first working screen.
- Left navigation matches Figma.
- Top bar includes search, upload, bulk import, local-first/no-cloud/hybrid-search/worker badges, user menu.
- Inbox metrics match Figma structure.
- Document data grid matches Figma columns and states.
- Row selection updates the right inspector.
- Right inspector shows selected document identity, review state, confidence, evidence preview, canonical fields, field actions, document actions, related docs.
- Pipeline summary is quiet and contextual.
- Upload button opens a file picker.
- Successful upload inserts a visible row with processing state.
- Document Viewer opens from Inbox and matches frame `14:434`.
- Viewer includes thumbnails, main page, evidence highlight, document facts, trust state, key fields, and actions.
- All asset URLs use `/api/v1/assets/{assetId}`.

Edge states:

- Empty corpus.
- Ingestion running.
- Workers offline.
- Original temporarily unavailable.
- Duplicate suspect.

Playwright checks:

- Login/session happy path.
- Upload PDF.
- New document appears in Inbox.
- Select row updates inspector.
- Open document viewer.
- Protected asset route is used.
- Screenshot comparison for Inbox desktop viewport.
- Screenshot comparison for Document Viewer desktop viewport.

Phase gate:

- Pixel match is acceptable against Figma references.
- Workflow works with backend API.
- No raw object storage path appears in DOM or network-visible API payloads.

## UI Slice 2 - Review Queue + Evidence Inspector

Primary Figma frames:

```text
14:611 - 03 Extraction Workspace v2
35:2   - Component variants
35:7   - Interaction specs
35:12  - Edge states
35:17  - Dev redlines
```

Required UI:

- Review queue list by priority, reason, family, confidence, and status.
- Evidence inspector persists selected document context.
- Field rows show canonical value, confidence, review state, and evidence jump.
- Candidate comparison is available for contested fields.
- Actions:
  - accept field
  - edit field
  - reject candidate
  - mark reviewed
  - re-run extraction
  - link related document
  - file document
- Evidence jump highlights page source using concrete locator.
- Field edits create audit history and canonical fact history.

Edge states:

- Low-confidence extraction.
- Insufficient evidence.
- Failed extraction.
- No review items.
- Re-run queued.

Playwright checks:

- Review task list loads.
- Selecting task updates inspector.
- Evidence jump moves/highlights viewer source.
- Accept field updates canonical read model.
- Edit field persists correction and history.
- Mark reviewed removes or resolves task.
- Screenshot comparison for extraction/review workspace.

Phase gate:

- Review loop is auditable.
- Canonical values are sourced from canonical tables.
- Candidate details remain visible for review.

## UI Slice 3 - Folder/Tag Filing Workflow

Primary Figma sources:

```text
14:434 - Viewer filing actions
14:611 - Review filing actions
35:7   - Interaction specs
35:12  - Edge states
35:17  - Dev redlines
```

Related later frame:

```text
14:797 - Search and relationship/folder context
```

Required UI:

- Folder tree.
- Smart folders.
- Tag list/editor.
- Document organization panel.
- Primary folder selection.
- Multi-folder membership.
- Apply/remove tags.
- Filing actions from Inbox, Viewer, and Review inspector.

Edge states:

- Unfiled document.
- Missing folder permissions.
- Folder deleted or unavailable.
- Smart folder has no results.

Playwright checks:

- Create folder.
- Assign document to folder.
- Set primary folder.
- Create tag.
- Apply/remove tag.
- Folder and tag appear in Inbox and detail.

Phase gate:

- Manual filing is usable before model extraction exists.

## Later UI Surfaces

Search:

- Use Figma frame `14:797`.
- Validate lexical, semantic, hybrid, filters, snippets, evidence, and result explanations.

Analysis:

- Use Figma frame `14:990`.
- Keep analysis separate from accepted canonical facts.
- Require citations.

Rules and watched folders:

- Use handoff pages and any relevant Figma surfaces.
- Dry-run and explanation must be visible.
- High-stakes documents should suggest rather than silently finalize.

Admin/status:

- Use quiet machine health and pipeline patterns from Figma.
- Detailed job logs live in admin drill-in.

## Playwright QA Procedure

For each UI slice:

1. Start local dev services.
2. Seed or upload deterministic test data.
3. Capture Figma reference screenshot with Figma MCP.
4. Open local route in Playwright at matching viewport.
5. Capture screenshot.
6. Compare visually and, where possible, with image diff thresholds.
7. Run workflow assertions.
8. Check accessibility basics:
   - focus order
   - keyboard navigation
   - accessible names for chips/actions
   - no color-only status indication
9. Check network calls:
   - no raw object-store URIs
   - no external model/cloud calls in default flow
10. Fix layout drift before moving to the next UI surface.

The first desktop viewport is `1440 x 960` because the main Figma screen frames use that size. If browser chrome or device scale affects screenshots, record the exact Playwright viewport, device scale factor, and screenshot options in the comparison notes.

Recommended desktop viewport for first pass:

```text
1440 x 960
```

Also validate responsive behavior later:

```text
1180 px width
760 px width
mobile-width narrow flow
```

## Pixel-Match Rules

- Match Figma dimensions, spacing, borders, radii, colors, typography, and layout hierarchy.
- Use Figma component variants where available.
- Do not replace dense document tables with card layouts on desktop.
- Do not promote machine-health metrics above document work.
- Keep evidence jump more visually important than confidence percentage.
- Do not invent new copy for feature explanations unless Figma or artifact docs leave a blank.
- Do not add marketing empty states.
- If text or UI state is missing from backend, use realistic deterministic fixtures until backend integration lands, then replace with API data.
- Do not accept a large visual mismatch without either fixing it or documenting explicit user approval.
- Use image diff tooling where practical, but manual visual review against Figma remains required because some differences, such as clipped text or wrong hierarchy, can pass numeric thresholds.

## Workflow QA Rules

- UI screenshot matching is not sufficient by itself.
- Each screen must also pass the workflow assertions listed for its slice.
- Network assertions must verify that default flows do not call external inference APIs.
- Asset assertions must verify browser-facing URLs use authorized API routes, not filesystem or object-store paths.
- Keyboard and focus checks are required for Inbox row navigation, Review actions, search, and modal/drawer flows.

## UI Stop Rule

Stop and ask the user if:

- Two Figma frames conflict.
- Figma and artifact docs conflict on user-visible behavior.
- A required state is not represented in Figma or edge-state docs.
- A component cannot be matched accurately with available frontend primitives.
- Responsive behavior needs a product decision beyond the documented drawer/collapse patterns.
