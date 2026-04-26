# Phase 5 Search UI Reference

Design source: Figma frame `14:797`, `04 Natural Language Corpus Search v2`.

The implementation should preserve the Phase 5 shape: a dedicated corpus search workspace, search-active navigation, a natural-language query card, filter rail, ranked results, retrieval explanation, evidence jumps, and saved-search workflow.

Accepted implementation differences:

- The app uses live contract data rather than fixed Figma examples, so labels, scores, snippets, facets, and evidence copy vary by seeded fixture or real corpus.
- The current Phase 5 implementation supports lexical, semantic, and hybrid retrieval. Relationship chips are shown as forward-compatible search-planning language, while full relationship graph retrieval remains later-phase scope.
- Create Review Set is intentionally non-mutating in Phase 5; saved searches are implemented and persisted.
- Typography and spacing follow the existing Structura CSS system rather than generated Tailwind output.

Gate expectation:

- `tests/e2e/phase5.spec.ts` owns deterministic browser snapshot coverage for the search surface.
- `tests/e2e/phase5-live.spec.ts` validates the live GPU-hosted upload-to-search-to-viewer evidence flow.
