# Product and user-experience completion

Companion to the [master completion plan](../../../STRUCTURA_PRODUCTION_COMPLETION_PLAN.md). Its milestone order and phase gates control this workstream. All packages are planned until their evidence is recorded in the [closure register](closure-register.md).


Product workstream for the root execution plan, 2026-09-07. Intended location: `docs/plans/production-completion/product.md`. This plan changes no application code or runtime. Linked repository sources use paths relative to that location. Work package IDs are stable (`UI-01` through `UI-13`); extension IDs are `EXT-01` through `EXT-08`.

## Source reconciliation and scope

Use [STRUCTURA_IMPLEMENTATION_PLAN.md](../../../STRUCTURA_IMPLEMENTATION_PLAN.md) for phase sequence and stop points, [ADR 0008](../../adr/0008-qwen38-27b-ingestion.md) for the selected ingestion model and [ADR 0009](../../adr/0009-qwen-native-document-parsing.md) for Qwen-native document parsing. The target uses the existing Qwen3.8-27B BF16 service on Oxcart for full searchable parsing, classification, semantic understanding and structured extraction through bounded task contracts. Immutable originals and their page coordinate systems anchor evidence; versioned parse provenance, validators and human review govern downstream claims and canonical facts. Docling is an optional temporary migration/comparison adapter, with no authority to veto Qwen parsing or extracted candidates. Model and parser choices are settled; integration, representative quality and shared-service capacity gates remain open. Product copy, help, screenshots and tests must identify the converter/model/profile actually invoked, without presenting older Qwen or Granite paths as active behavior or relabeling historical results.

The remaining Phase 8.5 evidence gate precedes Phase 9 analysis execution. UI repairs, contract design, deterministic fixtures and operational hardening can proceed while runtime validation is being completed. The RTX PRO 4000 Blackwell on Blackbird is proposed for retrieval embeddings used by ingestion indexing, reindexing and queries; Qwen3.8-27B generation stays on the existing Oxcart service. Embedding placement and dimensions, endpoint compatibility, sustained ingestion throughput and the effect on other users of that shared service require measured acceptance. Root owns that runtime plan; selecting an existing model does not mark its Structura integration ready.

ADR 0009 explicitly changes the provider-specific Docling requirements across app-spec §§5.3, 6.3, 8–11 and 16 while preserving the converter-neutral product outcomes of stories 3.1/3.2. Contracts must retain searchable ordinary text, page/element/table structure, reading order, concrete evidence and protected raw/normalized debug artifacts. Keep genuine historical Docling artifacts readable under their original converter/version identity; never fabricate Docling JSON or require a Docling pass to call the Qwen-native path complete. X-01–X-08 own the existing parser/claim/retrieval/runtime migration work, with UI-04/UI-06/UI-07/UI-08 integrating its user-facing outcomes; no new package or deferred extension replaces this core requirement.

Normative product inputs reviewed: full [pro-merged-master-v1.2/docs/01_App_Specification.md](../../../pro-merged-master-v1.2/docs/01_App_Specification.md); all 26 stories in [04_User_Stories_and_Acceptance_Criteria.md](../../../pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md); [STRUCTURA_UI_FIGMA_QA_PLAN.md](../../../STRUCTURA_UI_FIGMA_QA_PLAN.md); v1.3 normalization/design language; QA/release strategy; current Phase 8.5 truth/review/debug documentation; analysis note/event contracts and existing analysis-intake helpers. Figma frame `14:990` owns analysis design; frame `14:611` owns extraction review; `17:2`, `14:434`, `14:797`, and handoff frames `35:2/7/12/17` own the remaining primary UI. Current implementation screenshots are regression baselines, not proof of Figma parity.

Completion means all required v1 behaviors and all 26 stories are demonstrably usable. The full feature inventory below includes required functionality that the audit did not explicitly flag. Named later-phase functions are tracked separately at the end so they are not silently omitted or confused with the initial production gate. General SaaS, mandatory cloud inference, autonomous source destruction and expert-system claims remain non-goals.

## Implementation evidence and companion contracts

Current code references are baseline anchors, not instructions to keep growing those files. This plan expects behavior-preserving extractions into cohesive owners before adding responsibilities.

- [App shell and request state](../../../apps/web/src/App.tsx), [correction coercion](../../../apps/web/src/reviewActions.ts), [document table](../../../apps/web/src/components/DocumentTable.tsx), [folder/smart-folder controls](../../../apps/web/src/components/OrganizationRail.tsx).
- [Viewer and accepted-fact rendering](../../../apps/web/src/components/Viewer.tsx), [ReviewQueue](../../../apps/web/src/components/ReviewQueue.tsx), [review editors](../../../apps/web/src/components/ReviewDecisionPanel.tsx), [SearchResults](../../../apps/web/src/components/SearchResults.tsx), [search filter mapping](../../../apps/web/src/components/SearchFilterPanel.tsx).
- [Current shared CSS](../../../apps/web/src/styles.css), [Review CSS](../../../apps/web/src/components/ReviewQueue.css), [Sidebar](../../../apps/web/src/components/Sidebar.tsx), [TopCommand](../../../apps/web/src/components/TopCommand.tsx), [Playwright configuration](../../../playwright.config.ts), [live Phase 4 test](../../../tests/e2e/phase4-live.spec.ts).
- [Canonical detail read model](../../../lib/documents/read_model.py), [review service](../../../lib/review/service.py), [human canonical persistence](../../../lib/review/action_repository.py), [typed candidate values](../../../lib/extraction/candidate_repository.py), [contracts](../../../lib/contracts/models.py).
- [Analysis intake](../../../lib/documents/analysis_intake.py), [analysis quality/eligibility](../../../lib/documents/analysis_quality.py), [mutation guard](../../../lib/documents/analysis_mutation_policy.py), [truth/review/debug policy](../../../docs/model-runtime/phase8_5_truth_review_debug_surfaces.md).
- [Analysis note schema](../../../contracts/schemas/analysis_note.v1.schema.json), [analysis job event](../../../contracts/events/analyze_documents_job.v1.schema.json), [active API contract and ExportRequest](../../../contracts/api/openapi.yaml), [QA/release requirements](../../../pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md), [design language](../../../pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md).

## Execution boundaries and architecture

Do not add all the remediation to `App.tsx` (445 lines), `Viewer.tsx` (460), `ReviewQueue.tsx` (498), `SearchFilterPanel.tsx` (369) or `styles.css` (1939). Extract by stable ownership while preserving behavior: shell/navigation/session; route-level queries and mutations; document list; document viewer; canonical facts; evidence view; review selection/decisions; collections; search; analysis; exports/settings. Separate component styles and a shared measured token layer; avoid a generic helper directory.

Server controllers remain thin. Shared validation belongs in contracts/domain validation, review decisions in `lib/review`, folder/query behavior in existing organization/search services, persistence in repositories, analysis orchestration in a cohesive `lib/analysis` package, and exports in `lib/exports`. External inference and asset access remain adapters. Analysis and export workers reuse the durable job ledger; they do not run heavy work inline in API routes. Every new API operation must update OpenAPI, DTOs, persistence and authorization tests together.

Each package should land in reviewable slices: contract/service behavior; component integration; meaningful regression coverage; live acceptance evidence. Do not report a package done merely because a screen or endpoint exists. Fix integrity defects before adding batch decisions, analysis or exports that could amplify them.

## Work packages

### UI-01 — Product contract and design inventory

Dependencies: none. Can run alongside runtime inventory.

Deliver: a traceability ledger with source section/story, expected user behavior, owning package, test/evidence location and current status. Record exact supported families, review task types, relationship types, saved-query keys, upload types and permission roles from active contracts. Capture current Figma contexts, reference screenshots, interaction specs, edge states and redlines for each slice. Identify where the design lacks a state, then resolve only that concrete product decision before implementing the affected state. Existing documented drawer/collapse patterns do not need to be re-decided.

Resolve contract decisions before dependent work: source selection versus multi-document selection; selection across pages; folder delete/reparent behavior; soft-delete retention; saved-search naming/editing; analysis save/discard semantics; how uncertainty is displayed; export data inclusion; restrictive-folder inheritance. Document intentional divergences in a project decision note/ADR. Do not preserve old fixture behavior to avoid this work.

Acceptance: every v1 spec requirement and all 26 stories have a package and measurable check; every primary view has the required design references; root phase order remains unchanged.

### UI-02 — Correction integrity and asynchronous state safety

Dependencies: UI-01 contracts; start immediately for confirmed defects.

Fix `apps/web/src/reviewActions.ts:28` coercion: invalid money/numeric/integer/boolean input must remain invalid instead of becoming zero, truncated integers or false. Use typed editors with explicit currency, dates, nullable/cleared values and supported JSON shapes. Validate again server-side in the review service/contract layer; preserve legitimate zero and negative values where schema permits them. Human override may accept a disputed source value with a reason, but must not bypass type/schema validation or fabricate evidence. Retain the original user-entered value only where useful for audit, never as a substitute for the validated canonical value.

Give review/filing/search/detail/contact queries stable identity and cancellation or request-sequence guards. Clear or mark stale detail on selection changes and disable mutations until displayed task/document identity matches loaded data. Prevent double submissions and accidental duplicate rerun jobs. Keep entered corrections on failure and show a retryable error. Capture form elements before awaiting rather than accessing React `event.currentTarget` after asynchronous completion. Avoid catching and hiding errors as empty-success states.

Ownership: typed correction DTO/domain validation; `lib/review/service.py` and repositories; frontend review editor/mutation hooks; route data loaders for document and collection selection.

Acceptance: numeric garbage produces an inline validation error and no HTTP mutation; backend rejects equivalent invalid direct API payloads; valid $0 succeeds; selecting A→B with reordered responses never enables an A mutation under B; concurrent double-submit produces one auditable effect; network failures retain edits; optimistic concurrency prevents a correction silently overwriting a newer human decision. Tests must inspect persisted canonical/history values, not only success messages.

### UI-03 — Truthful, accessible application shell and route state

Dependencies: UI-01. Existing logout/expiry repairs use the current session API and do not depend on Phase 10 completion. Passkey/account-management surfaces are delivered later by UI-12/SEC-02.

Replace state-only navigation with stable URLs for Inbox, documents/pages/evidence, Review tasks, Search queries, collections, relationships/timelines, analysis runs/notes and exports. Browser back/forward, refresh and deep links must restore context with authorization rechecked. Maintain selection and return destinations when jumping to evidence. Extract session handling and query orchestration from `App.tsx`.

Implement desktop/sidebar and tablet/mobile navigation with documented collapsible or compact navigation, drawer/route details and clear return paths. Mobile CSS must not remove all navigation (`styles.css:1891`). Implement skip links, visible focus, meaningful names, keyboard row/selection interaction and the advertised Ctrl/Cmd-K behavior. Route changes move focus deliberately; drawers restore focus and trap it only while modal.

Replace hardcoded worker/backup/storage/index badges and review counts (`Sidebar.tsx:63-70`, `TopCommand.tsx:40-45`) with real authoritative read models carrying observation timestamps and unknown/stale/unavailable states. Quiet health links open operational detail, including the observed ingestion model/profile and shared-service waiting or throttling when it affects a document. Distinguish configured, reachable and task-validated capabilities. User menu uses session identity; implement sign out, session expiry/re-auth, passkey/account entry points. Wire or remove inert controls until their owning feature is available; do not display clickable success-looking affordances with no effect.

Acceptance: keyboard-only and 390 px fresh-session navigation reaches every enabled surface; deep link/back/refresh preserve authorized context; expired session returns to sign-in without leaking previous sensitive data; inaccessible documents show a safe actionable state; a worker outage/never-run backup cannot render healthy; count badges equal authorized server counts. No fake placeholder status remains outside explicit test fixtures.

### UI-04 — Ingestion, document browsing and lifecycle

Dependencies: UI-02/UI-03; backend storage/job invariants retained.

Complete single and multi-file picker, drag-and-drop, mobile-scanned PDFs and supported image ingestion. Provide upload progress, per-file acceptance/failure, duplicate choice, bounded batch concurrency, cancel-before-accept where practical and safe retry. Make Bulk Import functional through the existing ingestion/CLI path or a defined browser batch intake surface. Preserve immutable originals and received/source metadata. Worker/model availability must not block acceptance of supported files or immediate Inbox appearance.

Add server-backed pagination, stable sorting and complete list totals; do not leave the first-50-only behavior (`App.tsx:154`, `routes_documents.py:34`). Implement working Inbox state filters and metrics from the same authorized predicates. Surface lifecycle state, active job/stage, preview readiness and classified failure/abstention with refresh/polling/event updates; do not hardcode every row as Ingested. Define exact duplicates as a choice to inspect/reuse a prior record or keep a separate record, without silent merging or information about inaccessible matches. Structural duplicate suggestions remain confirmable.

Implement explicit selection mode and bulk filing/tagging/review-set/export/analysis entry points. Selection scope across pages is visible; do not mutate all matched records when the user selected only a page. Implement soft-delete/trash/restore in the owning document service with audit and exclusion from normal queries; originals are not physically destroyed. Hard purge remains separate from ordinary deletion.

Acceptance: a >200-document corpus can be fully browsed; counts and filters compose correctly; model-disabled upload/manual filing works; row appears within the spec's 2 seconds after upload completion; common listing meets <500 ms target on the declared moderate-corpus fixture; duplicate choice is clear and no originals are overwritten; retry does not create accidental records; partial batch failures are explicit. Verify PDF, PNG/JPEG/TIFF/WebP only to the extent active server contracts promise them, and align picker/contract rather than advertising unsupported types.

### UI-05 — Folder, tag, saved-search and smart-folder completion

Dependencies: UI-02/UI-03/UI-04; reuse existing saved-query planner parity.

Complete folder create/read/rename/reparent/archive/remove and nested tree behavior, preventing cycles and handling nonempty folders deliberately. Complete tag create/rename/merge/remove with defined effects on memberships. Support multi-folder membership, primary folder, title/date/filing notes, permission-aware available actions, dirty-state handling, and durable save feedback from Inbox, Viewer and Review. ACL editing itself is coordinated with UI-12.

Enable smart folders (`OrganizationRail.tsx:42-47`) and remove Phase 5 placeholder copy. Smart folder membership must execute the same saved-query semantics as Search/list repositories. Provide criteria builder, preview of matches, rename/edit/delete and dynamic update after review/filing changes. Complete saved-search list/reopen/edit/delete/naming with full mode, visual, relationship, deadline, date, amount, sensitivity and sorting round-trip; current `App.tsx:311` drops later filter keys. Allow creating a smart collection from a search without silently changing its query semantics.

Ownership: existing folder/tag/organization services and repositories; `lib/search/saved_query.py`; dedicated collections UI/API clients, not `App.tsx` form logic.

Acceptance: create a three-level tree, reparent safely, reject a cycle, file one record in two folders and preserve primary permission semantics; rename a tag without orphaning usage; reopen a search after reload with identical result IDs/filter meaning; smart collection membership changes after a review decision without manual refresh of its definition; permission changes do not expose excluded counts or stale content. Test removal behavior and unsaved edits as well as happy-path creation.

### UI-06 — Document Viewer, complete accepted facts and evidence

Dependencies: UI-02/UI-03; canonical document read models.

Render real protected page thumbnails rather than `rail-thumb` decorations. Provide page input/next/previous, zoom/fit, rotate-display if the design supports it, find-in-document over canonical text, lazy preview loading and large-PDF navigation. Display loading/missing/failed-original states with legitimate download/retry/manual-handling choices. Originals remain immutable; display rotation never rewrites source bytes.

Consume the versioned converter-neutral parse read model delivered by X-01–X-08. Qwen-native parsing must cover ordinary prose as well as structured facts: searchable transcription that preserves original wording separately from summaries, headings/paragraphs, page inventory, reading order, tables/rows/cells and chunk references, with explicit unreadable or deferred coverage. A reference document without invoice-style fields still needs complete useful search and find-in-document behavior. Protected debug views show actual native/model source origin, converter/model/prompt/schema/run identity, raw output and normalized structure, alongside separately labeled historical Docling artifacts. Parsed text and structures are derived source representations; their existence does not mark extracted financial or other facts accepted.

Render all accepted header fields and canonical line items, not `fields.slice(0,5)` or only candidate tables. Build schema-aware receipt/invoice/EOB views: money/currency/date formatting; receipt line quantities/tax/totals; invoice headers, due date, remittance and lines; EOB billed/allowed/plan-paid/patient-responsibility service rows. Preserve useful extra accepted observations without forcing them into an unrelated schema. Accepted, review-required and rejected material must be visibly separate. Provide expansion/paging of large tables, never silent truncation.

Create a reusable evidence view shared by Viewer/Review/Search/Analysis. Resolve bbox, element, table-row and text-span anchors through authorized structural read models, using the same deterministic richest-anchor selection. Each anchor identifies the immutable original/page, coordinate space/transform and parse/run/version lineage. Validate bounds and transforms; assess content support against the original page, since a match within the same model-generated transcript is not independent verification. Show an honest excerpt/page-locator fallback when no validated highlight can be drawn. Correctly handle page dimensions, rotations and zoom. Historical citations keep resolving to the parse version that produced them after reprocessing. A source jump must be one action and preserve the parent workflow. Separate user facts, review material and advanced diagnostics in tabs/drawers so model internals and deprecated Granite copy do not dominate the normal document experience. Expose document/review/filing history on demand.

Acceptance: an invoice with >5 fields and >20 line items is entirely readable; accepted EOB service lines show the relevant payment breakdown; each visible fact/line has a working evidence path; rotated/multipage/non-bbox evidence points to the correct source without fabricated highlights. With Docling disabled, a long ordinary-text reference document and mixed text/table scan yield durable searchable text, complete page coverage, tested reading order/table structure and useful find-in-document; unreadable/deferred portions are explicit. Annotated original pages establish parse/locator correctness independently of Docling agreement. Rerun and converter migration preserve old citation resolution and human decisions. The long reference PDF stays usable and cached first-page open meets <1 second target; no direct object storage path enters browser payloads. Snapshot real populated states, not only empty fixture previews.

### UI-07 — Complete review and correction workbench

Dependencies: UI-02/UI-03/UI-06; Phase 8.5 candidate/currentness semantics.

Implement Figma's side-by-side source, accepted values and competing candidates with stable selected task/document/page. Review list shows document title, family, priority, reason, confidence, status and enough source identity to distinguish repeated field tasks. Add filters, paginated backlog, keyboard next/previous and deliberate bulk review where actions are valid. Uncertainty appears as work to resolve, never as operational failure.

Complete accept/reject/edit for supported fields, observations and line items; rejection is candidate-specific where competition remains. Allow reclassification, mark reviewed with task-specific semantics, notes, extraction rerun and filing/link actions for an ordinary document, even when it currently has no open review task. Display before/after values, actor, timestamp, evidence and provenance history; keep rejected/current/superseded outputs distinguishable. Rerun must preserve accepted human corrections and immutable prior runs and must show queued/working/completed/failed or classified quality outcomes.

Relationship/duplicate/quality/filing-suggestion tasks need relevant actions or a direct contextual link to their owning flow, not irrelevant field forms. Show evidence insufficiency honestly and request a concrete human anchor or retain review status according to policy. Distinguish closing a task from accepting all facts on a document.

Acceptance: reviewer enters from a selected EOB service line, inspects evidence, corrects a field, confirms another candidate, rejects an alternative, files the document and returns to the same backlog position; DB history and canonical values match decisions. Repeat with observation, line-item, duplicate and quality tasks. Persisted asynchronous candidate updates cannot switch the document being decided. Backend+browser live tests exercise actual correction and evidence/history, replacing the current heading-only live Phase 4 smoke.

### UI-08 — Retrieval completion and meaningful collections from results

Dependencies: UI-03/UI-05/UI-06; real embedding/runtime and golden-query workstream.

Coordinate X-07/X-08 so the proposed Blackbird embedding services support document/chunk/page embeddings during ingestion and reindexing, plus query embeddings at search time. Verify compatible versioned text/visual profiles and index dimensions, complete searchable-text projection from the Qwen-native parse, correction/reparse freshness, and explicit stale/unavailable states. Qwen generation does not substitute for retrieval embeddings; an indexed document alone does not prove the query-side adapter works.

Complete lexical, semantic, hybrid and selective visual modes with canonical enrichment and authoritative ACL filters. Provide query history, complete advanced filters, removable chips/reset, sort by relevance/date/amount/review status, group by family/folder, clickable facets, actual thumbnails, highlighted lexical snippets, page references and quick preview. Preserve submitted query/filter state separately from draft edits so explanations never claim a filter was applied when results are still from an earlier request.

Make quick actions and Create review set meaningful through an explicit selected-result set, reused for analysis/export/filing. Do not invent new canonical review tasks just because a user collects documents for review; distinguish a saved work selection from machine-generated review requirements. Use shared saved-query parsing for natural-language supported filters and reject unsupported criteria explicitly. Where date/amount semantics are ambiguous, show the interpreted filter rather than silently pretending a structured interpretation occurred.

Acceptance: exact identifiers, semantic paraphrases, low-text visual examples and relationship-aware queries return expected documents with useful snippets; every exposed filter and sorting/grouping mode composes and round-trips; back from Viewer restores results/scroll/filter selection; stale responses never replace the newest query; a no-results state preserves active constraints. Prove BM25 <300 ms median, semantic <500 ms median and hybrid <1 second median on the declared corpus/runtime. Quality gate must show approved hit@k/MRR and hybrid improvement over lexical/semantic, not only that all three APIs return results.

### UI-09 — Contacts, transparent rules and watched intake usability

Dependencies: UI-03/UI-04/UI-05; existing Phase 6 safety seams.

Complete contact create/read/edit/archive and aliases, identifiers, addresses and phone/email where active data contracts support them; add missing contract fields explicitly. Document links must be navigable, editable and traceable, not merely a linked-document count. Merge/dedupe flow previews effects and preserves audit/history. Required G2 entity-centric browsing covers merchants, providers, insurers, vehicles, home appliances and topics. Add basic typed identity records, manual document linking/unlinking, rename/archive and associated-document browsing through a focused entity service/repository and explicit schema/contracts; do not force non-person concepts into organization contacts. Rich automated entity resolution and graph expansion remain EXT-07.

Complete rule editing, multiple conditions/actions, priority/order, enable/pause, dry-run, proposed/blocked action explanations, run history and accept/reject/defer suggestions. Use the shared organization mutation path and preserve atomic filing+run+audit semantics. Integrate suggestion cues into Inbox/Review, not only an isolated Automation tab. Complete watcher edit/pause/resume, allowed-root help, stable-file handling, excluded formats, intake log, last scan, imported/rejected/skipped counts and reprocess/rebuild CLI entry points.

Acceptance: create and edit a multi-condition/multi-action rule, preview and accept its effect on a high-stakes document; prove no silent finalization and no partial application on failure. Contact alias correction changes relevant lookup without merging distinct parties. Watcher UI reflects real scan health and protected paths, rejects symlink/out-of-root/partial/non-PDF intake, does not recursively ingest output, and resumes without duplicate imports. Browser forms survive validation errors and asynchronous success without losing user state or throwing `currentTarget` errors.

Entity acceptance at G2: create a vehicle, appliance and topic, link more than one document to each, browse the resulting collection, rename and correct a link, and preserve its history. Verify household/document permissions on identity records, counts and results; no inferred merge is accepted silently. Existing merchant/provider/insurer browsing must use the same consistent document navigation and permission semantics.

### UI-10 — Complete relationships, entity timelines and deadline work

Dependencies: UI-03/UI-05/UI-06/UI-09; accepted-fact deadline rules.

Support every contracted relationship type, manual creation, suggestion accept/reject, correction/removal with audit, related navigation and grouped transaction/claim/case histories. Both ends and the reason/evidence are understandable. Full relationship/deadline/timeline lists need pagination/filtering rather than `.slice(0,12/10/16)`. Smart-view counts open the corresponding collection, not informational cards only.

Entity timelines use meaningful document/event dates and link to originals; disclose unknown/estimated dates. Surface open/closed/overdue deadlines and warranties with evidence, accepted source and explicit manual correction/completion actions where supported. Keep existing related-document navigation complete; deliver new missing-companion suggestions in EXT-07 after v1. Absence of a retrieved document must never be asserted as proof a bill/payment does not exist.

Acceptance: traverse invoice→receipt→warranty/service history and bill→EOB→payment case; inspect/decide a suggestion; fix a mistaken link without losing history; view >16 events and correctly ordered known/unknown dates; open every smart view into matching ACL-safe records; unaccepted extracted dates cannot silently create authoritative obligations.

### UI-11 — Phase 9 optional cited analysis

Dependencies: completed Phase 8.5 runtime/reliability gates, UI-02/UI-03/UI-06/UI-07/UI-08, then root Phase 9 authorization/sequence. No model-side analysis is enabled before these prerequisites are met.

UI-11a contracts/persistence: implement asynchronous analysis request, run/status/cancel/retry, optional saved note, list/read/archive note operations; preserve the existing seven `analysis_note_type` values (summary, explanation, comparison, timeline, obligation_scan, tax_scan, medical_explanation). Persist selected document scope, query, model/version/prompt/schema, timestamp, answer, citations, recommended actions and source-version lineage. Reconcile `save_result` with the story's explicit save choice: every run has operational lineage; a generated note enters the user's saved library only on their chosen save policy. Default generated bodies are immutable; user notes/follow-ups are separately attributed.

UI-11b service/worker: add `lib/analysis` with context, citation validation and run services/repositories; `workers/analysis/worker.py` uses the durable ledger and a measured model adapter. Analysis remains optional with a distinct job/queue, prompt and workload profile. A later explicit decision may reuse the Oxcart Qwen3.8-27B endpoint, but ingestion model selection does not enable analysis or satisfy its citation-quality and concurrent-capacity gates. Context consumes `lib.documents.analysis_intake.build_phase9_document_intake`, `phase9_document_eligibility`, existing search service and ACL-safe evidence/relationship/deadline context. It must not directly consume raw model debug outputs, planner annotations as truth, or storage paths. Accepted facts are primary; review material is opt-in/explicitly uncertain. Long legal/reference documents with no typed extraction remain eligible for clearly bounded source-text analysis where their structural evidence is sound; do not force a household invoice schema just to make analysis eligible.

UI-11c UX: implement frame `14:990`: select one/multiple documents or an explicit search-result set, choose an action or question, inspect scope/uncertainty/eligibility, start/cancel/view progress, read cited output, jump to source and return, save/discard, reopen/share by authorized app link. Show limited/review-only/failed/unavailable states in user language. Comparison identifies the evidence for both sides. Recommended actions become explicit navigation/preview through existing mutation APIs after user selection; generated text never directly changes facts, relationships, filing, deadlines or review status.

UI-11d acceptance: all seven actions work on representative documents; EOB explanation and two-document comparison have claim-supporting citations that resolve to authorized document pages/locators. Test fabricated/mismatched/stale/missing citations, prompt instructions embedded in documents, cross-household source selection, permission revocation before read, context overflow, model outage, retry idempotency and restart recovery. Hash canonical facts, relationships, tags/folders, deadlines/review state before/after an ordinary analysis run to prove non-mutation. Test no-analysis profile still completes filing/review/search. Separate citation validity from factual support: independent human scoring must reject confident unsupported synthesis even when a citation URL is technically valid.

### UI-12 — Phase 10 exports, settings and operational user surfaces

Dependencies: G4 (Phase 9 gate), UI-02/UI-03/UI-05/UI-06/UI-07, then root Phase 10 operations/security implementation. Analysis-note export depends on UI-11.

UI-12a export flow: implement originals, originals+JSON, originals+CSV/JSONL with explicit canonical data mapping, and review report. Multi-document selection shows scope, data classes and inclusion options; preview manifest before generation where practical, then queued/progress/ready/error, authorized download, history and retention cleanup. Files include original hashes, extraction/prompt/schema lineage as appropriate, accepted facts and locator-bearing provenance. Candidate/rejected/debug data are excluded from default accepted-data exports or explicitly labeled in an opted-in review report. Distinguish currency, dates, nulls and line ordinals; spreadsheet exports must not interpret untrusted text as formulas. All bundles include a manifest for production export, resolving the existing optional `includeManifest` contract explicitly.

UI-12b settings/auth: implement passkey enrollment/use/remove with last-credential protection; bootstrap password rotation/disablement; recovery/invite flows appropriate to the local household; scoped API token create/revoke/expiry (secret displayed once); active session list/revoke-all/expiry; household membership and permission controls; folder ACL and sensitivity editing. Respect primary-folder inheritance and validate permission changes before both reads and mutations. Do not present controls to roles that cannot use them, but server authorization is authoritative.

UI-12c operator UI: job queues, per-document chain, timestamps/heartbeat, error class and safe details, retry/dismiss/suppress as defined; actual model/version, task/prompt profile, mode, validated capabilities and last observation; shared Oxcart admission/concurrency limits, queue wait, latency, timeouts and token/image budgets; proposed or active Blackbird embedding profiles and index freshness/search timing; extraction validation failure trends; real storage usage; last successful backup and restore rehearsal artifact. Display configured limits separately from measured utilization and never expose another service consumer's prompts or document metadata. Link from quiet shell indicators. Unknown/degraded is a valid state. Backups and restores themselves remain the root operations workstream with documented recovery evidence, not a UI button that implies untested safety.

UI-12d access audit: with OPS-04 and SEC-03 privacy review, implement the spec's later-phase document-view/original-access audit alongside export/delete history. Define a deliberate view/download event with actor, document, time, action and request correlation; ordinary thumbnail requests must not flood the history. Store no source text or unnecessary asset paths, and restrict history to authorized readers/operators.

Acceptance: verify original byte hashes in every bundle, manifests against actual contents, canonical/candidate boundaries, CSV/JSONL numeric/date handling, safe filenames and hostile CSV text, revoked ACL before build/download, unauthorized asset access, interrupted/retried builds and cleanup. Complete session/token/ACL/password/passkey flows in production-like browser secure context. Operator can diagnose a deliberately failed job, retry it safely and see real completion; a missing backup/restore record cannot display healthy. Restored deployment must retrieve original+facts+evidence and reopen a saved search before this package is declared complete.

Audit acceptance: authorized document opens and original downloads produce the defined events once at their intended boundary; export and soft-delete events identify the actual affected scope. Denied access never produces a successful-view event, repeated thumbnails do not create unbounded entries, and neither event payloads nor history leak inaccessible content.

### UI-13 — Whole-product polish and production acceptance

Dependencies: continuous per-package checks; final run after UI-02–UI-12 and root Phase 11 requirements.

Repair the QA configuration so a project-level Desktop Chrome device does not override the intended 1440×960 reference viewport. Capture populated, empty, loading, error, permission, stale, offline-worker, duplicate, low-confidence and rerun states at documented desktop/tablet/mobile widths. Compare to Figma with recorded view/scale/viewport; preserve an intentional-difference ledger. Do not refresh expected images merely to hide a regression. ReviewQueue's current 30–54 px heading/22 px radii and empty-after-accept snapshot are not valid proof of the compact evidence-workbench target.

Use focused mocked tests for edge cases plus live workflow tests with real API/DB/assets/worker output. Listen for page errors/unhandled rejections and unexpected failed requests. Add keyboard/focus checks, accessible names, non-color-only statuses and mobile fresh-navigation tests. Include Chromium, Firefox and WebKit for critical flows; perform Safari/mobile-device validation where image/PDF/upload behavior differs. Do not require pixel-identical cross-platform font rasterization, but require functional/legibility parity.

Final task-based UAT: (1) messy scanned receipt through review→file→find→export; (2) invoice with many lines/due date/payment relationship; (3) EOB/bill case explaining plan payment with sources; (4) warranty/service history and deadline; (5) long contract comparison; (6) handwriting with conservative review; (7) large backlog import with duplicates/partial failures; (8) permission-isolated household member and revoked access; (9) model outage/restart/retry; (10) fresh restore. Use fixed annotated examples plus unseen holdouts, not only the two June samples. Tie results to exact commit, app image, schema version, model/profile and corpus manifest.

Gate: no silent incorrect correction; no misleading operational state; every required control actionable; no hidden first-page-only collections; every visible accepted fact/line accessible with provenance; all 26 stories materially pass; extraction and retrieval thresholds approved and achieved; restart/backup/restore/export/authz checks pass; serious accessibility and data-loss defects closed. Publish known limitations with scope and evidence; a pipeline producing `needs_human_review` safely is not by itself proof of useful extraction quality.

## Complete story traceability

| Story | Owning packages | Completion evidence |
| --- | --- | --- |
| 1.1 Immediate upload | UI-03/UI-04 | Supported upload returns ID; visible row within 2 seconds after completion; actual stage updates while models disabled or slow. |
| 1.2 Immutable original | UI-04/UI-12 | Hash equality at upload/download/export/restore; duplicate/reprocess does not overwrite original. |
| 1.3 Duplicate decision | UI-04/UI-10 | Exact duplicate visibly flagged; user chooses outcome; structural suggestion reviewable; no silent merge or inaccessible-match leak. |
| 2.1 PDF viewer | UI-06/UI-13 | Real thumbnails, stable page/zoom/find and accessible navigation; large multipage PDF usable; protected source fallback. |
| 2.2 Folders/tags | UI-05/UI-12 | Nested folder management, multiple memberships/primary selection, tag CRUD and ACL-correct filing propagation. |
| 2.3 Saved/smart collections | UI-05/UI-08 | Save/reopen/edit/delete round-trip; automatic matching changes after document state changes. |
| 3.1 Canonical parse | UI-04/UI-06 + X-01–X-08 | ADR 0009 converter-neutral structure covers ordinary text, pages, reading order, tables/chunks and original-coordinate evidence; Qwen-native output persists/searches with Docling disabled; partial/failure states explicit and manual workflow survives. |
| 3.2 Canonical debug | UI-06/UI-12 + X-01/X-02 | Protected converter-neutral JSON/page/element/table/job diagnostics carry actual model/converter/run/version lineage; genuine historical Docling artifacts remain available without fabricated Docling output or path disclosure. |
| 4.1 Classification | UI-06/UI-07 + runtime | Family/confidence/source shown; any authorized document can be reclassified with history and correct rerouting. |
| 4.2 Receipt data | UI-06/UI-07 + runtime | Merchant/date/subtotal/tax/total/lines scored on holdout; arithmetic checks; accepted table and evidence usable. |
| 4.3 Invoice data | UI-06/UI-07 + runtime | Invoice number/issue/due/totals/lines captured where present; no silent first-five-field truncation. |
| 4.4 EOB data | UI-06/UI-07 + runtime | Payer/provider/patient/claim/service lines and payment responsibility presented explicitly with quality scoring. |
| 4.5 Evidence | UI-06/UI-07 | All field/line locator modes resolve to correct page/source; honest fallback; original context restored. |
| 5.1 Review queue | UI-02/UI-07 | Invalid/uncertain outputs generate task with reason/priority/document identity; backlog/task-type actions usable. |
| 5.2 Correction/history | UI-02/UI-07 | Strict input validation, actor/time/old/new/evidence history, canonical update and no lost prior candidates. |
| 6.1 Exact retrieval | UI-08 + corpus | Expected IDs/names/claim terms retrieve with useful snippets/highlights under latency target. |
| 6.2 Semantic retrieval | UI-08 + X-07/X-08 + corpus | Natural-language holdout queries retrieve expected chunk-grounded records using real document/reindex/query embeddings and compatible versioned indexes. |
| 6.3 Hybrid quality | UI-08/UI-13 + corpus | Comparative hit@k/MRR shows approved improvement versus lexical/semantic under same filters. |
| 6.4 Composable filters | UI-04/UI-05/UI-08 | Type/date/amount/folder/tag/review plus later filters combine, paginate and persist predictably. |
| 7.1 Related documents | UI-10 | All required link types visible/manual/confirmable with audit; traverse complete transaction/claim history. |
| 7.2 Timelines | UI-10 | Meaningful dates/unknown-date treatment, complete paginated events, source navigation and entity scopes. |
| 8.1 Saved EOB explanation | UI-11 | Plain-language explanation supports claims with source pages; save/discard/reopen works; no canonical mutations. |
| 8.2 Comparison | UI-11 | Multi-document scope preserved; differences cite both sources; incomplete evidence and uncertainty explicit. |
| 9.1 Jobs/failures | UI-03/UI-12 | Real listed jobs/errors, retry and completion; no hardcoded health/status; operator can diagnose failed stage. |
| 9.2 Backup/restore | UI-12/UI-13 + operations | Documented fresh restore recovers files/data/evidence/query/permissions; evidence tied to release. |
| 10.1 Export | UI-12 | Originals+structured data bundles with manifests/hashes/provenance; authorized queued generation/download. |

## Audit issue closure map

| Audited issue | Owning package and decisive check |
| --- | --- |
| Invalid correction becomes $0 or truncated number | UI-02; browser+direct API malformed-input tests plus valid-zero persistence. |
| Canonical lines absent; fields truncated | UI-06; accepted >20-line invoice/EOB and >5 header fields fully accessible. |
| Fake backup/storage/workers/review badge/pipeline | UI-03/UI-04/UI-12; unavailable/never-run services shown truthfully from timestamped API data. |
| Inert Inbox filters/Bulk Import/Create review set | UI-04/UI-08; result-ID and actual-action tests. |
| Only first 50 documents | UI-04; browse >200 records with stable counts/pagination. |
| Flat folder creation and incomplete CRUD | UI-05; three-level/reparent/rename/remove behavior with cycle and permission tests. |
| Disabled smart folders/saved searches write-only/lost filters | UI-05/UI-08; reload round-trip and dynamic collection membership tests. |
| Review jumps lose selected task; no side-by-side source | UI-03/UI-06/UI-07; source-return and persistent task selection UAT. |
| Review/details race and missing async errors | UI-02/UI-03/UI-07; reordered responses, double submit and network error tests. |
| Hidden mobile navigation/non-keyboard rows/fake shortcut | UI-03/UI-13; fresh mobile and keyboard-only full task completion. |
| Decorative page thumbnails/no large-PDF workflow | UI-06/UI-13; real thumbnails, lazy pages, zoom/find and large-PDF acceptance. |
| No logout/session recovery/deep links | UI-03/UI-12; signout/expiry/back/refresh/permission-revoke acceptance. |
| Unfocused model diagnostics/obsolete Granite copy in main UI | UI-06/UI-12; truth/review/debug surface review and current runtime-copy audit. |
| Figma drift/stale snapshots/wrong viewport/empty Review screenshot | UI-01/UI-13; current populated/error-state manual design comparison and corrected test viewport. |
| Heading-only live Review QA and weak keyboard/mobile checks | UI-07/UI-13; actual persisted live correction/history/evidence and accessible fresh-mobile journeys. |
| Relationship smart cards unclickable and lists truncated | UI-10; actionable filtered collections and >16 event traversal. |
| Phase 9 missing | UI-11; all seven analysis types plus two explicit stories, gated by Phase 8.5 evidence. |
| Phase 10 exports/settings/ops missing | UI-12; manifest/permissions/session/backup/restore/operator task gates. |

## Required feature inventory beyond the audit

The packages also cover spec obligations easily missed by fixing only reported bugs: drag-and-drop/images/mobile scans; batch backlog cleanup and soft-delete lifecycle; nested folders and meaningful primary-folder inheritance; global/query-history/sort/group/facet search; natural-language interpretation transparency; complete receipt/invoice/EOB fields and tables; document notes/history; unrestricted authorized reclassification/rerun; structured candidate comparison and rejected state; all ten core relationship types; entity-centric browsing; contact aliases/identifiers; multi-action rules and watcher safety; all seven analysis actions; optional saved notes; all four export formats; passkeys/session/API-token/folder-ACL management; real job/index/storage/model/backup health; representative golden corpus and actual restore.

## Full specification extension sequence

These extensions are part of the complete-specification roadmap requested by the user. They follow the production v1 gate and have their own completion evidence; they are not silently dropped because the original spec called them later-phase candidates. Explicitly deferred functionality must never appear enabled in the shipping UI before its acceptance passes. The sequence separates product readiness from the later completion of every named enhancement.

### EXT-01 — Email attachment intake and ZIP bulk import

Dependencies: UI-04 intake/batch dedupe; UI-12 credential/audit/retention policy; baseline release UI-13.

Email: add an opt-in mailbox or local mail adapter with credential management, mailbox/folder scope, attachment MIME/size validation, idempotent message/attachment IDs, private source metadata, retry/quarantine and previewable intake log. Reuse immutable intake; do not treat all message text as required import data. Users can pause/disconnect and revoke credentials. No external inference is introduced by reading an explicitly configured mailbox.

ZIP: stage/stream archive members with limits on expanded bytes, file count and depth; reject traversal/symlinks/archive-bomb payloads; show per-member accepted/rejected/duplicate outcomes and source metadata; reuse upload validation and cleanup. Document whether nested archives are rejected or supported with a fixed depth limit.

Ownership: isolated mail/archive adapters and ingestion services, narrow workers and intake settings UI. Acceptance: duplicate deliveries/retries do not duplicate records; unsupported attachments and hostile archive fixtures fail safely; cancellation/revoke stops intake; valid archive members arrive with original hashes/source lineage; partial batch failures remain inspectable; ordinary local archive workflows work without a mail connection.

### EXT-02 — Redacted sharing and records-request bundles

Dependencies: UI-06 viewer/evidence; UI-12 export; UI-13 baseline.

Add manual text/region redaction on derived copies, sensitive-field suggestions that require review, redaction/share-preparation tasks, preview of every output page and a bundle manifest describing transformations and provenance. Output must remove underlying text/layers/metadata, not only place opaque boxes over a readable PDF. Preserve immutable originals. Provide selective inclusion of documents, pages and fact fields for records/tax/reimbursement/legal packets while retaining accurate omissions/provenance metadata.

Ownership: redaction domain policy, file-format adapter, export worker, dedicated review UI. Acceptance: extraction, search, metadata inspection and page rendering of generated PDFs cannot recover redacted content; all visible redactions align after rotation/zoom; image/text PDF fixtures pass; inaccessible documents cannot enter bundles; output preview matches download; manifest clearly distinguishes originals from redacted derivatives.

### EXT-03 — OCR tuning, deskew and difficult-document quality improvement

Dependencies: UI-06/07 evidence/review, representative Phase 8.5 corpus and UI-13 baseline.

Add explicit parse-quality profiles and document-specific reprocessing for scanned/rotated/low-contrast/mixed PDFs beyond the required Qwen-native baseline. Keep optional OCR/deskew or Docling comparison dependencies isolated in their dedicated adapters/workers and configured cache roots; they are not mandatory authorities or vetoes for Qwen parsing. Use bounded measured preprocessing on derived working copies; preserve original page images, structural IDs/version lineage and coordinate transforms so evidence remains traceable. Retain classified insufficient-signal/review outcomes instead of repeated model rescue loops.

Ownership: parse adapters/pipeline configuration and quality policy; extraction runtime agent owns model measurements. Acceptance: paired before/after holdout evaluation improves targeted OCR/table/readability metrics without degrading digital PDFs or corrupting coordinates; no OCR downloads to site-packages; original hashes unchanged; retry/reprocess history and human accepted facts preserved; latency/resource limits measured.

### EXT-04 — Deadline/warranty reminders

Dependencies: UI-10 accepted-source deadlines and UI-12 account/permissions; UI-13 baseline.

Add explicit opt-in reminders for accepted obligations, response deadlines, return windows and warranty expiry. Expose schedule/channel/time-zone preferences, snooze/dismiss/complete, quiet hours and delivery history. A reminder uses a cited accepted or user-created date and never promotes an unreviewed extracted date merely to schedule it. Time-sensitive eligibility handles date changes and missing dates. In-app notification is the default first channel; other channels use isolated opt-in adapters.

Ownership: deadline domain policies, scheduled reminder worker/repository, notification adapters/settings UI. Acceptance: time-zone/DST/overdue cases; idempotent delivery/retry; edited/removed/rejected dates cancel obsolete reminders; revoked users receive no private notification; app restarts do not fan out duplicate messages; reminder opens the correct authorized source and can be disabled.

### EXT-05 — Mobile companion and share extension

Dependencies: UI-03 responsive shell/session, UI-04 mobile-supported intake, UI-06 evidence, UI-12 strong auth; UI-13 baseline.

First ship the complete responsive web flow. Then implement a bounded mobile intake companion/share-extension experience for the selected supported platforms, with iOS scanning-app/share-sheet intake as the specification's first named context. Capture platform decision and distribution/signing ownership before native implementation. Support sharing PDF/image documents into Structura, destination/server selection, authentication, upload queue/retry/cancel, duplicate outcomes and an explicit handoff into the web document/review screen. A share extension should not become a second extraction/business-rules stack. Offline queuing must disclose pending transfer and protect local temporary files.

Ownership: platform adapter/client plus shared authenticated upload contract. Acceptance: share from Files/scanning app into a real server; correct MIME/original hash/source; authenticated/revoked/offline/large-file cases; retry does not duplicate; temporary files removed per policy; screen-reader/navigation checks on actual target device; no hidden cloud upload or analytics containing document content.

### EXT-06 — Richer household collaboration

Dependencies: UI-05/12 membership/folder ACL and auditing; UI-07 review concurrency; UI-13 baseline.

Add richer single-household collaboration: invite/join/revoke with roles, review assignments/ownership, shared and private collections, attributable notes/activity and concurrent-edit/conflict handling. If multi-household UX is included, explicitly switch context and segregate queries, counts, caches, notifications and jobs; do not accidentally turn this into public multi-tenant SaaS. Respect the default primary-folder inheritance plus custom grants policy. Preserve sufficient audit history after membership removal.

Ownership: identity/ACL domain and repositories, collaboration services, assignment/activity UI. Acceptance: two-person concurrent filing/correction; unauthorized household/folder/role matrix; access revocation invalidates cached views and future job/export/analysis access; assignments and mentions reveal no hidden document titles; user can distinguish personal from shared scope throughout.

### EXT-07 — Richer entity resolution and graph exploration

Dependencies: UI-09 contacts/rules and UI-10 relationships/timelines; UI-13 baseline.

Build on UI-09's required vehicle/appliance/topic and merchant/provider/insurer identity, linking and browsing. Add property/case identity extensions where useful, evidence-backed alias matching, user confirmation of merge/split/link suggestions and repair/undo through history. Build navigable graph/case views with filters, bounded expansion, clear edge meaning, source evidence and timelines. Missing-companion suggestions must disclose that they reflect the current archive/search evidence, not definitive real-world absence.

Ownership: entity domain/repositories and resolution adapters/services; graph UI consumes the same ACL-safe relationship API. Acceptance: false-positive merge/split adversarial examples, similar-name distinct entities, correct transaction/case traversal, large bounded graph responsiveness, inaccessible-node/edge/count leakage tests and recovery of prior links after correction.

### EXT-08 — Corrected examples, active learning and optional LoRA fine-tuning

Dependencies: UI-07 auditable corrections, UI-12 private dataset export, Phase 8.5 versioned adapters/evaluation and independent held-out corpus; UI-13 baseline. Depends on EXT-03 for OCR-derived examples when applicable.

First create a private corrected-example dataset with source/evidence/version/permission lineage and an explicit data-use selection flow. Keep held-out evaluation documents separate from training and prompt-tuning material. Add active-learning prioritization that proposes high-value uncertain examples for human review without changing accepted facts or creating repetitive review storms. Build repeatable prompt/model comparison and rollback reports. Only then add optional local LoRA fine-tuning jobs for a measured compatible model, with resource quotas, pinned dataset/model/training configuration, checkpoints and independent promotion gates. User approval of a training dataset does not automatically approve deployment of the trained model; make model promotion a concrete reviewed release action.

Ownership: evaluation/dataset domain and private storage adapters; training workers/adapters isolated from production ingestion; review prioritization service and experiment UI. Acceptance: reproducible dataset provenance, no held-out contamination, exclusion/revocation policy, active-learning suggestions demonstrably improve correction yield, matched before/after quality/latency/abstention tests on unseen documents, no regression in evidence/canonical safety, interruption/resume and disk cleanup, explicit rollback to prior model. A successful training process is not evidence of a better production model.

Review reports and unmatched-document smart views remain required v1 work in UI-12 and UI-10. New missing-companion recommendations beyond smart views belong to EXT-07, consistent with the Phase 7 plan's explicit deferral. EXT-02 expands sharing beyond the baseline review report. Email, native/share-extension intake, reminders, collaboration, graph exploration and training remain unavailable until their own gates pass. Optional reranking and hard purge have additional packages EXT-09 and EXT-10 in the closure register.

## Suggested integration order and parallelism

Wave A: UI-01 plus runtime/backup inventory; UI-02 correction/state defects; UI-03 shell/routing/health contracts. Runtime and UI work can proceed independently with deterministic contract fixtures.

Wave B: parallel UI-04 intake/browse, UI-05 collections, and UI-06 viewer/facts, each in owned modules with shared contract review. Avoid simultaneous edits to the same shell/root stylesheet. UI-07 review follows the evidence component and correction service. UI-08 retrieval follows shared collection/query semantics.

Wave C: UI-09 automation and UI-10 relationships; core filing/review/search UAT and accessibility checks. Phase 8.5 representative quality and repeatability gates finish here; analysis is not the vehicle for hiding extraction gaps.

Wave D: UI-11 Phase 9; then UI-12 Phase 10 according to root phase sequence. Security/storage scaffolding and required remediation can have been prepared earlier, but milestone claims still require full gates. The complete-specification extensions EXT-01–08 receive their own tracked milestones after the v1 production gate; independent extensions may run in parallel within their prerequisites.

Wave E: UI-13/Phase 11 release qualification, fresh restore and full user-story ledger closure. Record exact blockers and scope; do not replace objective acceptance with a percentage-complete estimate.
