# Inbox browsing and review concurrency checkpoint

Date: 2026-09-07. Database/unit candidate: `04938db`. Browser/static candidate: `2500c42`. G1/G2/G3 remain open; this does not activate native ingestion or complete the Inbox UI.

## Delivered behavior

`GET /api/v1/documents` now composes eight Inbox states with query, family, review status and manual/smart-folder filters. Six deterministic sorts include unique document-ID ties and put unknown dates last. Pagination retains the default 50 and maximum 200 items. A read-only repeatable-read transaction covers authorized corpus size, folder resolution, scoped overlapping counts and the selected page. Counts are computed before the selected Inbox state; totals include it. They cannot be summed. Separate requests remain ordinary offset pages, so concurrent corpus changes can move items between requests; no durable snapshot token is implied.

Duplicate counts independently authorize every counterpart. Extraction-result counts require current nonempty completed/accepted output and do not imply canonical facts. Text-searchable counts use published lexical chunks and do not imply current semantic/visual vectors. Hidden native candidate generations do not contribute. Classification uses recorded decisions rather than interpreting any reviewed document as human-classified.

Accepted uploads now return `documentId` alongside `jobId` and `status`, directly from the ingestion transaction's result. Two uploads with the same title and original bytes return distinct document identities, each matching its own ingest job and protected original download. UI consumption is separate ongoing work.

Correction, confirmation and rejection now share canonical human-authority and revision policy. An existing human source, confirmed/corrected status or retained accepting actor requires an exact current revision before replacement. A deleted reviewer does not remove the protection. Supplied revisions also guard system-origin rows; explicit null means no canonical row existed. The browser submits the exact document/path/ordinal revision, refuses inconsistent or missing explicit task references, and preserves decision text after a conflict. Decisions and task closure affect only the intended ordinal; wrong-document/path references and contradictory candidate/ordinal metadata remain unresolved.

## Verification

- **1,517 unit tests and 220 database integration tests passed at `04938db`**, with all 40 migrations through 097, on a clean Oxcart worktree and fresh disposable database.
- The browse matrix traversed **207 records under all six sorts**, checked unique ties and nullable dates, every overlapping state/count, manual/smart/query combinations, inaccessible/private/deleted duplicate counterparts, unchanged original hashes, and a separate-connection insert between response queries.
- Sixteen review-decision database cases exercised legacy/deleted actor markers, first and explicit subsequent decisions, real transactions blocked behind a concurrent correction, and scoped ordinal/history/task behavior. Rejected stale actions created no additional changes, events or jobs.
- **81 Linux browser tests passed at `2500c42`**, with eight live-stack tests intentionally skipped. This included the new exact-task/revision conflict cases and normal comparison against all reviewed Linux baselines. Web lint/build passed.
- **Full `make sast` passed at `2500c42`**: Bandit, 512 Semgrep rules on 1,108 tracked files with the previously documented size/ignore/parse limitations, Pyright and Mypy (418 source files). The narrow subsequent upload DTO/route passed targeted static, contract and unit checks and the complete database/unit gate above.

Protected logs are `unit-04938db.log`, `integration-04938db.log`, `sast-2500c42.log` and `browser-2500c42.log` beneath the owned temporary validation root. No existing archive or resident model service changed.

The first browse run correctly denied a supposed shared fixture whose primary folder was absent; the fixture now explicitly grants the intended household-folder access. The first complete combined gate then exposed two obsolete exact-response assertions and an incomplete test evidence locator. Assertions now also require zero corpus/scoped counts after denial, and the synthetic correction contains a concrete source-text locator. The 220-case rerun excluded no tests and changed no production policy to accommodate these fixture repairs.

## Remaining acceptance

Persistent rejection tombstones without canonical rows, durable classification/manual-date authority, atomic accepted-fact rollups and indexing revisions are assigned to migration 099 and its writer integration. Inbox URL/filter/page controls, exact uploaded-document navigation and complete selection recovery are in progress. Native render/index candidates under planned migration 098 remain hidden until their own publication/quality gates pass. These foundations do not close the broader UI-04/UI-07, SEC-01, X-02/X-05 or release packages.
