# Structura Phase 7 Implementation Plan

Phase 7 connects documents into transaction, claim, object, and case histories. It makes explicit relationships useful, creates reviewable relationship suggestions, surfaces meaningful timelines and deadlines, and adds smart views for high-value document histories without turning suggestions into unreviewed truth.

This plan expands Phase 7 from `STRUCTURA_IMPLEMENTATION_PLAN.md`. It does not replace the root plan. Use the root plan for phase boundaries and this document for Phase 7 execution detail.

## Operating Rules

- Do not inspect or rely on anything under `archive/`.
- Before coding any subphase, re-read the files listed in that subphase's **Fresh Context** section. Use `wc -l` and bounded `sed -n` chunks for large files so full reads are auditable.
- When an artifact exists in both Markdown and DOCX form, read the Markdown artifact by default. Only inspect DOCX when the user explicitly asks for layout/fidelity review or the Markdown file is missing/incomplete.
- Keep generated FastAPI OpenAPI paths aligned with `contracts/api/openapi.yaml`. If implementation and contract differ, stop and resolve the contract question explicitly.
- Relationship suggestions are not accepted relationships until a policy or user action confirms them. Ambiguous or high-stakes matches must be reviewable.
- Relationship, timeline, and deadline views must preserve source document access controls. Do not reveal hidden documents through counts, titles, snippets, timelines, or suggestion explanations.
- Preserve Phase 1-6 invariants: original bytes are immutable, accepted canonical facts remain the default read model, search indexes are assistive, filing automation is auditable, and browser-mutating routes require CSRF.
- Keep Phase 7 focused on document relationships, related-document navigation, entity/document timelines, deadlines/reminders, and relationship-aware smart views. Do not implement Phase 8 visual retrieval, Phase 9 analysis chat/comparison, or Phase 10 exports except for contract-safe placeholders already present.

## Firecrawl Evidence Rule

When APIs, external contracts, library behavior, security conventions, OpenAPI semantics, FastAPI/Pydantic behavior, PostgreSQL/SQL behavior, graph traversal, recursive SQL, date/deadline handling, timezone conventions, reminder semantics, fuzzy matching, React/Vite conventions, Playwright behavior, or UI accessibility conventions are in play, search online with Firecrawl if there is any uncertainty.

Use primary sources where possible: official framework documentation, standards documents, official package docs, project repositories, security guidance, or vendor docs. Save Firecrawl outputs under `.firecrawl/`, read them incrementally, and summarize the evidence in implementation notes or ADRs when it affects a decision. Do not use unsourced memory to settle uncertain API, schema, database, graph, date, browser, worker, or security behavior.

## Phase 7 Required Artifact Set

The full Phase 7 artifact list from `STRUCTURA_IMPLEMENTATION_PLAN.md` remains required context:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/14_Canonicalization_Candidate_Authority_Model.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/010_types_and_enums.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/050_views_and_functions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/review_action.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/design-language-v1.3.html
```

The duplicate DOCX entries in the root plan are intentionally omitted here under the current repo guidance.

## 7.0 Baseline Reconciliation

Goal: confirm Phase 6 contacts/rules and Phase 5 search are stable enough to support relationship and timeline workflows.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 7 section.
- `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md`, canonical fact and review-action commitments.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, related-document search/filter commitments.
- `STRUCTURA_PHASE_6_IMPLEMENTATION_PLAN.md`, contacts, filing rules, watched folders, and rule suggestions.
- `agents.md`.
- `.wolf/cerebrum.md`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, related documents and timelines.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, organization intelligence and related documents.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Epic 7.
- `contracts/api/openapi.yaml`.
- `database/010_types_and_enums.sql`.
- `database/020_core_tables.sql`.
- `apps/api/structura_api/routes_documents.py`.
- `compose.yaml`.

Work:

- Confirm Phase 6 contact links and filing rules are available for relationship suggestions.
- Confirm Phase 4 canonical facts include invoice, receipt, EOB, warranty, due date, renewal date, claim number, payer/provider, patient, amount, and counterparty values where applicable.
- Confirm Phase 5 search can find exact identifiers, contact names, dates, folders, tags, and related context.
- Reconcile OpenAPI with Phase 7 needs. Current contract covers `GET/POST /api/v1/relationships` but does not explicitly cover relationship update/delete, suggestion listing, timeline endpoints, or deadline endpoints.
- Decide which Phase 7 surfaces are contract extensions versus API responses embedded in existing document detail/review/search surfaces. Update `contracts/api/openapi.yaml` and implementation together for any extension.
- Identify implementation modules for relationship service, suggestion worker, timeline service, deadline service, review action handling, smart-folder updates, and UI components.
- Confirm worker ownership: relationship suggestion work should use `job_type = relate` and the `worker-relationships` runtime service.

Firecrawl Evidence:

- Use Firecrawl if OpenAPI extension strategy, graph API design, SQL recursive query behavior, or date/deadline semantics are uncertain.

Exit Criteria:

- Phase 7 implementation boundaries are known.
- Contract gaps are resolved or explicitly deferred.
- Relationship work will not bypass review, ACL, or canonical fact authority.

## 7.1 Relationship Contract, Types, And DTOs

Goal: make relationship API shapes, relationship types, and validation rules explicit before writing graph logic.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 7 relationship tasks.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, relationship types.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `/api/v1/relationships`, `DocumentRelationship`, and `RelationshipWrite`.
- `pro-merged-master-v1.2/database/010_types_and_enums.sql`, `relationship_type_enum`.
- `pro-merged-master-v1.2/contracts/schemas/review_action.v1.schema.json`, `accept_relationship` and `reject_relationship`.
- `lib/contracts/registry.py`.
- `apps/api/structura_api/routes_documents.py`.

Work:

- Define typed DTOs for relationship list and create responses that match OpenAPI casing.
- Validate allowed relationship types: `duplicate_of`, `related_to`, `invoice_for`, `receipt_for`, `eob_for`, `bill_for`, `amendment_to`, `renewal_of`, `attachment_to`, `warranty_for`, and `proof_of_payment_for`.
- Define direction semantics for API results: `from`, `to`, and reciprocal display labels.
- Decide relationship uniqueness rules: one directed row, reciprocal virtual view, or paired inverse rows. Prefer one directed row plus normalized bidirectional query behavior unless a contract says otherwise.
- Define confidence, evidence, comment, source engine, and accepted/suggested status representation. If status cannot fit the current `document_relationships` schema, add a migration or documented extension.
- Add tests for DTO validation, enum validation, self-link rejection, direction semantics, duplicate row handling, contract parity, and malformed request behavior.

Firecrawl Evidence:

- Use Firecrawl if OpenAPI/Pydantic enum handling, graph edge representation, or REST semantics for relationship confirmation/update/delete are uncertain.

Exit Criteria:

- Relationship API shapes are typed and contract-aligned.
- Invalid relationship types and self-links are rejected.
- Direction and uniqueness behavior are explicit.

## 7.2 Relationship Persistence And Manual API

Goal: implement manual creation, listing, and confirmation of document relationships with authorization and audit.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, relationship API task.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, `document_relationships`.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, relationship endpoints.
- `pro-merged-master-v1.2/contracts/schemas/review_action.v1.schema.json`.
- `apps/api/structura_api/routes_documents.py`, relationship skeletons.
- Phase 2 auth/ACL and document access services.

Work:

- Implement `GET /api/v1/relationships` with optional `documentId` filter, household/ACL filtering, direction labeling, related document summary, confidence, evidence, and comments.
- Implement `POST /api/v1/relationships` as create-or-confirm using CSRF for browser sessions.
- Enforce both document visibility and write/confirm permissions before relationship mutation.
- Persist source engine as `human` for manual actions and `system` or model-specific source for suggestions later.
- Write review events or audit events for create/confirm/reject actions.
- Add idempotency for repeated manual create/confirm.
- Add tests for list all visible relationships, document-scoped list, create, confirm existing suggestion, self-link rejection, invalid type, cross-household denial, hidden related document suppression, CSRF, and audit rows.

Firecrawl Evidence:

- Use Firecrawl if SQL upsert/idempotency, authorization patterns, audit-event design, or FastAPI dependency behavior is uncertain.

Exit Criteria:

- Users can create and confirm relationships manually.
- Relationship list does not leak hidden documents.
- Relationship mutations are auditable.

## 7.3 Relationship Evidence And Review Actions

Goal: connect relationship suggestions and confirmations to review actions and evidence.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, relationship suggestion and confirmation tasks.
- `pro-merged-master-v1.2/contracts/schemas/review_action.v1.schema.json`.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, reviewable machine uncertainty.
- `database/020_core_tables.sql`, `review_tasks`, `review_events`, and `document_relationships`.
- Phase 4 review task/action implementation.
- Phase 6 suggestion workflow implementation.

Work:

- Implement `accept_relationship` and `reject_relationship` review actions if not already covered by Phase 4/6.
- Store relationship evidence in `document_relationships.evidence_json` using concrete source facts: matching claim number, invoice number, date, amount, contact, folder, tag, or search evidence.
- Create review tasks for suggested relationships that need human confirmation.
- On accept, confirm or create the relationship and record audit/review history.
- On reject, record rejection without losing the suggestion provenance.
- Add tests for accept, reject, evidence persistence, review task resolution, audit rows, duplicate accept idempotency, rejected suggestion not reappearing immediately, and hidden-document denial.

Firecrawl Evidence:

- Use Firecrawl if review-action REST design, evidence schema representation, or audit-state modeling is uncertain.

Exit Criteria:

- Relationship review actions work.
- Accepted/rejected relationship decisions are auditable.
- Evidence explains why a relationship was suggested.

## 7.4 Relationship Suggestion Worker

Goal: propose useful document links without pretending uncertain matches are final.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, relationship suggestion worker task.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, relationship types and confirmation rule.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, relationship suggestion engine.
- `pro-merged-master-v1.2/docs/14_Canonicalization_Candidate_Authority_Model.md`, canonical facts and evidence authority.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`, contacts and medical bill/EOB matching.
- `database/020_core_tables.sql`, `document_relationships`, `document_deadlines`, `document_amounts`, `document_contacts`, and canonical facts.
- `lib/jobs/service.py`.
- `workers/relationships/`.
- `compose.yaml`, `worker-relationships`.

Work:

- Consume `relate` jobs after classification/extraction/contact-link/search projection updates.
- Generate relationship candidates from deterministic features first: exact file hash duplicate, duplicate_of; invoice number, receipt totals/date/contact, proof of payment; EOB claim number, provider/payer/patient/date/amount, bill/EOB; warranty purchase date/item/merchant, receipt/warranty; amendment/renewal contract identifiers; attachment filename/source batch.
- Score candidates with transparent feature weights and store explanation/evidence.
- Prefer creating review tasks or suggested relationship rows for non-obvious matches; only auto-confirm exact duplicates if policy allows.
- Suppress repeated suggestions already accepted/rejected unless new evidence appears.
- Add tests for duplicate, invoice-to-receipt, bill-to-EOB, EOB-to-payment, warranty-to-receipt, amendment-to-contract, attachment-to-parent, low-confidence review, rejected suggestion suppression, and job retry/dead-letter behavior.

Firecrawl Evidence:

- Use Firecrawl if matching heuristics, graph suggestion patterns, entity resolution methods, or job scheduling conventions are uncertain.

Exit Criteria:

- Relationship suggestions are useful and explainable.
- Ambiguous suggestions require confirmation.
- Worker behavior is idempotent and retry-safe.

## 7.5 Related-Document Panel And Link Flow

Goal: expose relationships in the document workbench where users naturally inspect source documents.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, relationship API and UI tasks.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`, Review UI and related later frame notes.
- `pro-merged-master-v1.2/design-language-v1.3.html`, related documents panel.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, right inspector and related count.
- `contracts/api/openapi.yaml`, relationship schemas.
- `apps/web/src/App.tsx`.
- `apps/web/src/styles.css`.

Work:

- Add related-document count to document list rows and right inspector.
- Add related-document panel with relationship type, related title, date, amount/counterparty where available, direction, confidence, and review state.
- Add manual link flow from the inspector: search/select target document, choose relationship type, add comment/evidence, and confirm.
- Add accept/reject controls for suggested relationships.
- Ensure clicking a related document opens it while preserving a clear return path to the source document.
- Add Playwright tests for related count, related panel, manual link, suggested accept/reject, click-through navigation, hidden related document suppression, keyboard flow, and responsive drawer behavior.

Firecrawl Evidence:

- Use Firecrawl if React state/routing, WAI-ARIA dialog/listbox patterns, keyboard navigation, or Playwright locator conventions are uncertain.

Exit Criteria:

- Relationships are visible on the document page.
- Users can create or confirm links manually.
- Navigation between related documents is clear.

## 7.6 Entity-Centric Timeline Inputs

Goal: prepare entity and document metadata needed for useful timelines without building Phase 9 analysis.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, entity-centric timeline tasks.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, entities and document-centric timelines.
- `pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md`, contacts improve relationships.
- `database/020_core_tables.sql`, `documents`, `document_contacts`, `document_amounts`, `document_deadlines`, and `document_relationships`.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `contacts`.
- Phase 6 contact services.

Work:

- Define timeline event sources: document date, received date, filed date, canonical invoice issue/due dates, receipt transaction date, EOB processed/service dates, warranty purchase/expiration, renewal dates, deadlines, and relationship creation events.
- Normalize timeline event shape with document ID, event date, event type, display label, amount/contact/folder context, source field, evidence, confidence, and review state.
- Use contacts as the primary entity grouping layer for merchants, providers, insurers, law firms, utilities, vendors, and personal correspondents.
- Avoid generating narrative explanations; keep this phase to structured event lists and navigation.
- Add tests for event extraction from document metadata, canonical facts, deadlines, relationships, contact grouping, missing dates, conflicting dates, ACL filtering, and stable ordering.

Firecrawl Evidence:

- Use Firecrawl if date normalization, timezone/local-date semantics, event schema patterns, or timeline accessibility conventions are uncertain.

Exit Criteria:

- Timeline event data is structured and testable.
- Entity grouping uses contacts where available.
- Timeline inputs do not leak hidden documents.

## 7.7 Timeline And Entity Views

Goal: let users understand sequence and context across related documents and contacts.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, timeline view task.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, timeline and grouped transaction/case view.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Story 7.2.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, secondary surfaces and interaction principles.
- `contracts/api/openapi.yaml`, current relationship/document schemas.
- `apps/web/src/App.tsx`.
- `apps/web/src/styles.css`.

Work:

- Reconcile API contract for timeline data. If adding `/api/v1/timeline` or `/api/v1/contacts/{contactId}/timeline`, update OpenAPI and implementation together.
- Implement document-centric timeline for one selected document and its reachable relationships.
- Implement entity-centric document listing/timeline for a selected contact where Phase 6 contacts exist.
- Include event date, type, title, document family, relationship context, amount/contact context, review state, and link back to original document.
- Support filters for event type, document family, contact, date range, open deadlines, and review status where data exists.
- Add Playwright tests for document timeline, entity timeline, ordering, filters, open document from event, empty state, keyboard navigation, and responsive layout.

Firecrawl Evidence:

- Use Firecrawl if REST shape for timeline data, virtualized list accessibility, date sorting conventions, or React routing patterns are uncertain.

Exit Criteria:

- Timeline ordering uses meaningful dates.
- Timeline events link back to original documents.
- Relationship history feels useful, not decorative.

## 7.8 Deadline Extraction, Surfacing, And Review

Goal: surface due dates, renewals, expirations, response deadlines, filing deadlines, and appointments from accepted facts and document metadata.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, extract and surface deadlines.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, deadlines and reminders.
- `pro-merged-master-v1.2/docs/14_Canonicalization_Candidate_Authority_Model.md`, high-confidence key fields and `contract.renewal_date`.
- `pro-merged-master-v1.2/database/010_types_and_enums.sql`, `deadline_type_enum`.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, `document_deadlines`.
- Phase 4 extraction validators and canonical fact services.
- Phase 6 review/rule suggestion services.

Work:

- Populate `document_deadlines` from accepted canonical facts and explicit document metadata: invoice due dates, warranty expiration, renewal dates, response deadlines, filing deadlines, appointment dates, and EOB/bill dates where relevant.
- Store evidence, confidence, extraction ID, metadata, status, and reminder start date.
- Mark low-confidence or weak-evidence deadlines as review-required instead of final.
- Implement update/resolve/snooze behavior only if the contract is extended; otherwise surface open deadlines read-only and use review actions for correction.
- Add tests for due date, warranty expiration, renewal date, response deadline, filing deadline, appointment date, weak evidence review, correction audit, duplicate deadline suppression, and stale deadline superseding on re-extraction.

Firecrawl Evidence:

- Use Firecrawl if date parsing, local-date vs timezone handling, reminder semantics, recurring deadlines, or OpenAPI endpoint design is uncertain.

Exit Criteria:

- Deadlines are surfaced from trusted sources.
- Weak deadline evidence triggers review.
- Deadline rows preserve evidence and extraction provenance.

## 7.9 Open Deadlines, Reminder Heuristics, And Smart Views

Goal: provide high-value smart views without overbuilding a notification system too early.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, smart folders and reminders.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, open deadlines and smart folders.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, saved searches and smart folders.
- `database/020_core_tables.sql`, `saved_searches`, `folders`, and `document_deadlines`.
- `database/050_views_and_functions.sql`, document summary views.
- Phase 5 saved search/smart folder implementation.

Work:

- Add smart views for open deadlines, warranties expiring soon, renewals coming up, needs review, tax relevant, unmatched medical documents, and relationship suggestions needing confirmation.
- Define reminder heuristics as visible status and filters first, not external notifications unless explicitly contracted.
- Calculate deadline status: open, due soon, overdue, resolved, waived, or needs review.
- Keep smart views backed by saved searches or deterministic SQL helpers so behavior is inspectable.
- Add tests for each smart view, date boundary behavior, resolved/waived filtering, ACL filtering, hidden-count suppression, and search/filter integration.

Firecrawl Evidence:

- Use Firecrawl if date boundary semantics, reminder UX conventions, SQL date arithmetic, or saved-search filter design is uncertain.

Exit Criteria:

- Users can find open deadlines and expiring warranties.
- Smart views are explainable and ACL-safe.
- Reminder behavior is visible without noisy automation.

## 7.10 Relationship-Aware Search And Filing Integration

Goal: make relationships improve existing search, filing, and review workflows without creating a second source of truth.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 7 objective.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, search enrichment and related context.
- `STRUCTURA_PHASE_6_IMPLEMENTATION_PLAN.md`, filing rules and contacts.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, relationship traversal across linked documents.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, search across related-document context.
- `database/020_core_tables.sql`, relationships/deadlines/folders/tags.

Work:

- Refresh search projection or related-context fields after relationship create/confirm/reject.
- Allow search filters for relationship presence and deadline presence where Phase 5 filter grammar supports them.
- Add relationship context to result explanations without leaking hidden documents.
- Let filing rules use relationship presence, deadline presence, and contact/entity context as conditions if Phase 6 rules support those fields.
- Add tests for search result related context, relationship filter, deadline filter, filing rule condition using related context, ACL suppression, and projection refresh idempotency.

Firecrawl Evidence:

- Use Firecrawl if SQL projection refresh, graph filter design, search explanation design, or rule-engine integration is uncertain.

Exit Criteria:

- Related-document context improves search and filing.
- Search/filter behavior remains ACL-safe.
- Relationship state stays synchronized with projections.

## 7.11 Relationship And Deadline Quality Fixtures

Goal: make relationship usefulness measurable before analysis and exports depend on it.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 7 gate.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Epic 7.
- `pro-merged-master-v1.2/docs/14_Canonicalization_Candidate_Authority_Model.md`, trusted canonical facts.
- Phase 5 golden search benchmark fixtures.
- `tests/`.

Work:

- Add sanitized fixture sets for invoice plus receipt/payment, bill plus EOB plus payment receipt, warranty plus purchase receipt, contract plus amendment/renewal, and duplicate document pairs.
- Define expected relationships, rejected relationships, timeline ordering, deadline rows, and smart view membership.
- Add metrics for suggestion precision, accepted top-k inclusion, false positive rate on unrelated documents, timeline date correctness, and deadline status correctness.
- Ensure fixtures do not include private documents or raw sensitive content.
- Add regression tests for fixture loading, relationship suggestion quality, timeline ordering, deadline status, and ACL visibility.

Firecrawl Evidence:

- Use Firecrawl if relationship evaluation metrics, graph-quality benchmark conventions, or synthetic fixture generation is uncertain.

Exit Criteria:

- Relationship quality can be tested repeatably.
- Timeline/deadline regressions are visible.
- Phase 7 gate is grounded in fixtures, not just screenshots.

## 7.12 Integration, Security, Runtime, And UI Coverage

Goal: prove relationships, timelines, deadlines, and smart views work end to end.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 7 gate.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `pro-merged-master-v1.2/design-language-v1.3.html`.
- `contracts/api/openapi.yaml`.
- `database/020_core_tables.sql`.
- `lib/jobs/service.py`.
- `workers/relationships/`.
- `compose.yaml`.
- `tests/`.

Work:

- Add integration tests from upload/parse/extract/contact link/search to relationship suggestion, review accept, timeline display, deadline display, and smart view membership.
- Add security tests for relationship list/create/review actions, timeline endpoints if added, deadline endpoints if added, hidden related documents, cross-household denial, CSRF on mutation, and API-token/service-worker access.
- Add runtime tests for `worker-relationships` health, relate job claim/complete/fail/retry, idempotent suggestion runs, and stale suggestion suppression.
- Add UI tests for related panel, manual link flow, suggestion accept/reject, document timeline, entity timeline, open deadlines, smart views, and related-document navigation.
- Add logging checks to ensure titles/counts/snippets from hidden documents are not logged or returned in debug traces.
- Add no-regression tests for Phase 4 review actions, Phase 5 search filters, and Phase 6 filing rules after relationship state changes.

Firecrawl Evidence:

- Use Firecrawl if API-token worker auth, graph traversal security, Compose health behavior, Playwright patterns, or SQL recursion behavior is uncertain.

Exit Criteria:

- Relationship, timeline, deadline, and smart-view workflows work end to end.
- Security boundaries remain intact.
- Prior search, review, and filing behavior does not regress.

## 7.13 Contract, Static Analysis, Runtime, UI, And Phase 7 Gate

Goal: prove relationships are useful and stable before difficult-document retrieval work begins.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 7 gate.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `Makefile`.
- `pyproject.toml`.
- `package.json`.
- `apps/web/package.json`.
- `tests/`.
- `compose.yaml`.

Work:

- Run formatting and lint checks.
- Run mypy/pyright/SAST checks using the repo targets.
- Run OpenAPI/schema contract validation, including any timeline/deadline/suggestion contract extensions and `review_action.v1.schema.json`.
- Run backend unit and integration tests.
- Run relationship service tests, suggestion worker tests, deadline service tests, timeline service tests, review action tests, ACL tests, search/filer integration tests, and fixture quality tests.
- Run web build.
- Run Playwright UI workflow and screenshot validation for related-document panel, manual link flow, relationship suggestions, timeline view, deadline views, smart views, and responsive states.
- Run local Compose smoke where practical: API health, worker health, upload/list/detail, filing, parse, extraction/review, search, contacts/rules, relationship suggestion worker, relationship list/create, accept/reject relationship, timeline view, open deadlines, and smart views.
- Confirm Phase 7 gate from `STRUCTURA_IMPLEMENTATION_PLAN.md`: relationships are useful and not merely decorative.
- Document intentional deferrals: missing companion document recommendations beyond smart views, external notifications, broad obligation analysis, visual retrieval, analysis chat, export bundles, and production-grade graph scoring.

Firecrawl Evidence:

- If a gate fails due to tool behavior, dependency behavior, browser/API semantics, SQL behavior, JSON Schema behavior, graph traversal behavior, date/deadline behavior, or security convention that is not locally obvious, use Firecrawl to find primary-source evidence before changing code.

Exit Criteria:

- User can traverse from invoice to receipt, bill to EOB, warranty to purchase/service history, and contract to amendment/renewal.
- Relationship suggestions are reviewable and explainable.
- Timeline ordering uses meaningful dates and links back to original documents.
- Deadlines and smart views are useful and ACL-safe.
- Phase 7 gate passes.

## Stop Point

Stop after Phase 7 gate validation and report:

- Files changed.
- Tests and checks run.
- Contract extensions or deferrals.
- Relationship suggestion quality summary.
- Timeline/deadline smart views added.
- Any deferred work and the phase it belongs to.
- Any Firecrawl-sourced evidence that materially shaped implementation decisions.

Do not continue into Phase 8 without explicit user instruction.
