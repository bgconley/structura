# ADR 0001: Phase 1 Ingest, Storage, Preview, And Viewer Baseline

Date: 2026-04-24

## Decision

Phase 1 implements the first upload-to-viewer workflow with content-addressed filesystem storage, protected asset streaming, real document list/detail APIs, lightweight derived preview assets, and a Figma-aligned Inbox/Viewer UI.

Original uploads are staged while SHA-256 is computed, then committed under the canonical object root with `os.replace`. The DB remains the authoritative catalog through `document_assets.uri`; browser clients only receive `/api/v1/assets/{assetId}` URLs.

The upload endpoint uses FastAPI multipart `UploadFile`/`Form` handling. `python-multipart` is now an explicit runtime dependency. Asset delivery uses Starlette `FileResponse` with private no-store caching, safe filenames, and inline content disposition so PDFs/images/SVG previews can render in the browser while still requiring API authorization.

## Phase 1 Preview Scope

Phase 1 creates deterministic SVG thumbnail and first-page preview fallbacks as protected derived assets. These assets are sufficient for stable Inbox/Viewer states and retryable preview jobs without introducing a heavyweight PDF renderer before the Phase 3 preview/page-image hardening work.

Full PDF page rasterization, Docling canonical artifacts, complete page image sets, and parse-quality metadata remain Phase 3 responsibilities.

## Evidence

- FastAPI official docs state file uploads are sent as multipart form data and `UploadFile` can be used for file handling; they also call out `python-multipart` as the required package for form/file parsing: <https://fastapi.tiangolo.com/tutorial/request-files/>.
- Python official docs state `os.replace` performs an atomic rename when successful, with same-filesystem caveats: <https://docs.python.org/3.12/library/os.html#os.replace>.
- Starlette official docs state `FileResponse` asynchronously streams files, supports `filename` and `content_disposition_type`, and sets file response metadata headers: <https://starlette.dev/responses/#fileresponse>.

## Consequences

- Duplicate exact-byte uploads create separate document rows while sharing immutable content-addressed original bytes.
- Phase 2 can add folder/tag organization without changing the document list/detail response shape, because Phase 1 already returns `folderPaths` and `tags` where the active contract permits them.
- Phase 3 can replace SVG fallbacks with real page renders while preserving the same `document_assets` and `/api/v1/assets/{assetId}` access pattern.
