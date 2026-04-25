# ADR 0002: Phase 2 Manual Organization

Date: 2026-04-25

## Status

Accepted

## Context

Phase 2 makes Structura useful as a manual filing cabinet before model workers, Docling parsing, classification, and extraction are complete. The phase requires folders, smart-folder records, tags, manual document filing, primary-folder selection, metadata edits, auditability, and visible folder/tag surfaces in Inbox and Viewer.

The artifact contract already defined organization endpoints, but the Phase 2 UI QA plan also requires tags to appear in the Inbox. The upstream v1.3 `DocumentSummary` schema included `folderPaths` but did not include list-level tags.

## Decisions

- Organization routes are thin FastAPI controllers. Business rules live in `lib/organization/manual_filing.py`, SQL in `lib/organization/repository.py`, and validation/path policy in `lib/organization/policy.py`.
- Manual folders and smart folders are first-class folder records. Phase 2 supports creating and listing smart-folder records with bounded JSON `savedQuery` validation, but dynamic smart-folder execution and the full search grammar remain Phase 5 work.
- Folder reads and writes are household scoped. Private/custom folder visibility uses the current folder ACL tables where available.
- Tags remain global to the local install in Phase 2 because the active schema has global `tags` rows with no household ownership column. Household-scoped tags require an approved schema/contract change.
- Document organization updates reject unknown tag names instead of auto-creating tags. Tag creation is an explicit user action.
- `primaryFolderId` is atomically added to folder membership if supplied outside `folderIds`. If folders are supplied without a primary, the first folder becomes primary; clearing all folders clears the primary.
- `DocumentSummary` is intentionally extended with optional `tags` so Inbox can show filed tags without an extra detail request. This is reflected in `contracts/api/openapi.yaml`, `lib/contracts/models.py`, the document read model, and tests.
- Browser QA against the production-shaped runtime uses the GPU-hosted web service. With `STRUCTURA_E2E_LIVE=1`, Playwright defaults to `http://10.25.0.50:13000`, does not start a Mac-hosted Vite server, and exercises the real proxied API/DB stack.

## Consequences

- Phase 2 manual filing works without Docling, extraction, embeddings, search ranking, or model workers.
- Phase 3 can add parse/page/canonical artifacts behind the existing document detail shape without changing organization ownership boundaries.
- Phase 5 can attach dynamic smart-folder execution to existing `savedQuery` records without redefining folder creation/listing APIs.
- A future household-scoped tag migration must preserve or migrate existing global tags deliberately.

## Deferred Work

- Contacts, filing-rule automation, watched-folder ingestion, and model-based filing suggestions remain later phases.
- Dynamic smart-folder search execution remains Phase 5.
- Review-workspace filing actions remain coupled to the future Phase 4 review surfaces, while the reusable filing panel is ready for integration.
