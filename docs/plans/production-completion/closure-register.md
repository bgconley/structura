# Production completion closure register

Date: 2026-09-07. Source: [readiness review](../../reviews/2026-09-07-production-readiness-review.md), [app specification](../../../pro-merged-master-v1.2/docs/01_App_Specification.md), [26 user stories](../../../pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md), [root implementation plan](../../../STRUCTURA_IMPLEMENTATION_PLAN.md) and its owning phase artifacts. Execution order: [master completion plan](../../../STRUCTURA_PRODUCTION_COMPLETION_PLAN.md).

**Every row is initially planned/open.** Assignment is to a workstream role; an execution owner is recorded when dispatched. Add implementation/verification/acceptance references as work proceeds. A prior test, draft or existing code component is not closure evidence for the gap it still has.

Execution began on `codex/production-completion` after user authorization. The [G0 execution record](../../release-evidence/production-completion-g0/README.md) records the current baseline, dispatched owners, migration assignments and validation boundary. SEC-01, JOB-01/02, UI-02 and SEC-03 are in progress; no finding is accepted closed by dispatch alone.

[Integrity checkpoint 1](../../release-evidence/production-completion-g0/integrity-checkpoint-1.md) contains fresh verified implementation evidence at `c250427` for current permission checks, claim ownership, strict numeric corrections and public error/status truth. X-01 also has an authenticated 27B text/image adapter pass. These are bounded passes within open packages; G1/G3 remain open and every remaining acceptance requirement below still applies.

Subsequent implementation evidence is retained in the [embedding checkpoint](../../release-evidence/production-completion-g0/embedding-checkpoint.md), [persisted source and authority checkpoint](../../release-evidence/production-completion-g0/persisted-source-checkpoint.md), and [browser/static-analysis checkpoint](../../release-evidence/production-completion-g0/browser-security-checkpoint.md). The native parser now has immutable generation capture and two source-scored real 27B synthetic ingests; Blackbird has verified document/query text and image embedding adapters. The latest complete integrity gate passed 1,491 unit and 193 database tests, while a later Linux browser candidate passed 70 functional tests with eight live-stack skips. These establish progress in X-01/X-02/X-06/X-08, SEC-01/03, JOB-01/02 and UI-02/03; they do not activate the native pipeline or close those packages. Exact-generation indexing, stale human-decision conflicts, durable rejection/classification/manual-date authority, actual Inbox browsing and the remaining quality/product gates are in progress.

Package definitions live in [product.md](product.md), [extraction-retrieval.md](extraction-retrieval.md), [security-operations.md](security-operations.md), and the additional extension packages below. The package dependencies there and milestone gates in the master plan are binding.

The [Inbox/review checkpoint](../../release-evidence/production-completion-g0/browse-review-checkpoint.md) adds verified backend coverage for R-22/R-24 (all filters and 207-record browsing), R-29 (exact human-decision revisions), and exact upload identity: 1,517 unit and 220 database tests passed at `04938db`. The current UI controls and broader field-decision authority remain open. [Dependency remediation](../../release-evidence/production-completion-g0/dependency-checkpoint.md) patched the six reported web-package findings and passed the Linux build/browser/audit gate; this is one bounded part of R-40, not closure of release security assurance.

The [native index and workbench checkpoint](../../release-evidence/production-completion-g0/native-index-workbench-checkpoint.md) supersedes those earlier counts with 1,598 unit and 268 database passes at `714b5fc`, plus 92 full Linux browser passes at `bed4c5b`. The Inbox controls and hidden candidate index executor are integrated; migrations 098–100 preserve exact vectors and durable human-authority records with tested retention behavior. Human-decision writer/API activation, actual persisted GPU indexing, coherent native publication, batch intake and broader product/quality gates remain in progress. These are bounded verified slices of UI-04/UI-07, SEC-01, X-02/X-05/X-07 and JOB-02, not package acceptance.

The [persisted GPU index checkpoint](../../release-evidence/production-completion-g0/persisted-index-checkpoint.md) adds actual 27B parsing, eight saved Blackbird text/image vectors, zero-call sealed replay and both query encoders at `a23d041`. Four tiny synthetic page-query rankings and offline reconstruction passed. This advances X-01/X-02/X-06/X-07/X-08 without activating application search or accepting corpus/capacity quality. The checkpoint qualifies the broad-reference versus tight-text-box geometry scores; original references and scores remain intact.

The [accepted-field and retained-evidence checkpoint](../../release-evidence/production-completion-g0/retained-evidence-checkpoint.md) records the next verified slices: migration 101 field decisions/editor, complete Viewer data, truthful unknown/review states, and migration 102 protected historical pages. The gate passed 1,698 unit, 316 database and 139 Linux browser tests; static and real 27B/Blackbird retention proof passed at `2439134`. Both index and page asset publication now survive cleanup winning their content lock. A 29-second visual query JIT spike remains a runtime qualification issue despite a fast limited warm follow-up. These advance UI-06/UI-07, SEC-01, X-02/X-05/X-07/X-08 and JOB-02; line-item authority, batch intake, native publication and full G2/G3 acceptance remain open.

Accepted model/parser decisions: [ADR 0008](../../adr/0008-qwen38-27b-ingestion.md) selects the existing Oxcart Qwen3.8-27B BF16 service for ingestion; [ADR 0009](../../adr/0009-qwen-native-document-parsing.md) selects Qwen-native full searchable parsing. X-01–X-08 cover profile/parse-contract migration, source-coordinate evidence, claims, scored parse/extraction/retrieval quality and shared-service capacity; UI-04/UI-06/UI-07/UI-08 consume these outcomes. X-08 covers shared Oxcart admission and proposed Blackbird embeddings for ingestion, reindexing and queries. These decisions are accepted, but implementation/quality/capacity rows remain open. Docling is an optional temporary migration/comparison adapter, with no authority or veto; neither Docling agreement nor an 8B comparison is required to reconfirm the chosen target.

ADR 0009 records the explicit deviation from provider-specific Docling wording across app-spec §§5.3, 6.3, 8–11 and 16. The converter-neutral outcomes of stories 3.1/3.2 and required full-text, page/element/table/reading-order, evidence and protected-debug behavior remain binding. Preserve genuine historical Docling artifacts and citations under their actual identity; never fabricate Docling output. This migration is assigned to the existing packages and rows below and changes none of the finding, story or package counts.

The [upload and native claim checkpoint](../../release-evidence/production-completion-g0/upload-claims-checkpoint.md) records migrations 103–105: exact line-item decisions/editor, durable raw upload attempts, and immutable native claims with current-authority historical reads. The latest complete backend candidate `874eb4f` passed 1,836 unit and 463 database tests plus static checks. The separately identified Linux browser candidate passed 179 tests with eight live-stack skips; six Node 20 socket tests passed. These advance UI-02/UI-04/UI-06/UI-07, SEC-01/03, JOB-02 and X-02/X-05. The follow-on cleanup gate passed 474 database tests at `d56c038`; the batch client is integrated at `c0476bf` and its browser references are under ordinary comparison. Real upload browser/API acceptance, combined 27B extraction, native publication and broader G2/G3 acceptance remain open.

## Package owners and gates

| Packages | Accountable workstream | Gate |
| --- | --- | --- |
| UI-01 | Product + integrator | G0 design/contract inventory, completed per-surface before coding |
| SEC-01, SEC-03, JOB-01, JOB-02, UI-02 | Security/jobs/product, shared contract integrated once | G1 |
| UI-03–UI-10 | Product; services owned by relevant domain lane | G2, with quality/runtime acceptance at G3 |
| X-01–X-08 | Extraction/retrieval; job protocol shared with JOB-01/02 | G0/G1 prerequisites, final G3 |
| X-09 | Extraction/retrieval handoff; analysis implementation owned jointly with UI-11 | G3 interface readiness; G4 context/model/concurrent-workload acceptance |
| UI-11 | Analysis service + product | G4 after G2/G3 |
| SEC-02, EXP-01, OPS-01–OPS-04, UI-12, REL-01 | Security/operations/export + product | G5 after G4 |
| UI-13, REL-02 | Integrator + independent reviewers | G6 |
| REL-03 | Integrator + archive/operator owner | G7 |
| EXT-01–EXT-10 | Domain/product owners identified in each package | G8 after G7 |

There are 35 core package IDs and 10 explicit extension IDs. JOB-01/02, OPS-01/02 and OPS-03/04 have shared descriptions because they must coordinate; each still needs separate completion evidence. No workstream independently redesigns the shared permission, run-generation or claim-token contract.

## Every readiness-review issue

| ID | Gap or defect | Packages | Decisive evidence |
| --- | --- | --- | --- |
| R-01 | Read authorization permits metadata/refiling/canonical writes | SEC-01 | Read-granted/viewer actors denied across every mutation; allowed behavior preserved; no denied side effects |
| R-02 | Owner/admin token ignores restrictive scopes | SEC-01, SEC-02 | Token capabilities intersect current user authority; read-only owner token cannot write/admin |
| R-03 | Removed membership leaves credentials effective | SEC-01, SEC-02 | Session/token reads and queued actions lose access immediately after revoke/downgrade |
| R-04 | Invalid correction becomes zero/truncated numeric data | UI-02, SEC-01 | Browser and direct API reject malformed values; valid zero/negative/schema-permitted inputs persist correctly |
| R-05 | No job lease renewal during synchronous work | JOB-01 | Long work renews; expired owner cannot renew someone else's claim |
| R-06 | Job status completion/failure lacks claim ownership | JOB-01, JOB-02 | Competing-consumer CAS/race tests and worker kill/reclaim matrix |
| R-07 | Stale workers can publish domain results before final job rejection | JOB-02, X-02 | Per-worker/output inventory proves claim-token and applicable run-generation checks transactionally at every publication/enqueue boundary |
| R-08 | Old extraction can recreate current output after rerun | X-02, X-05 | Paused old job resumes after new publication and changes no current fact/asset/review/index record |
| R-09 | Template-clone rehearsal presented as archive recovery | OPS-01, OPS-02, REL-01 | Independent backup copy restored into clean root/DB with isolated source data/config unavailable; recovered keys/secrets, isolated endpoints, hash and product checks |
| R-10 | No working archive backup/retention/off-device recovery | OPS-01, OPS-02 | Consistent manifests, retained prior backup after failure, verified independent copy and measured recovery |
| R-11 | Public failure text exposes paths/private content | SEC-03 | Synthetic sensitive strings excluded from API/DOM/ordinary logs; protected bounded diagnostics retained |
| R-12 | Job lookup is household-only rather than document-aware | SEC-01, SEC-03 | Known private job IDs return safe denial to unauthorized household member |
| R-13 | Invoice header/payment-summary coverage suppressed | X-03 | Table-bearing/table-free invoice fixtures retain every supported present obligation; gold field recall |
| R-14 | Some Docling text suppresses all vision recovery | X-01, X-03, X-04 | Qwen-native full parsing and region extraction work with Docling disabled; no Docling-presence or agreement veto; mixed/image-only candidates have validated original-page evidence and review policy |
| R-15 | Long-document targets disappear before skip reporting | X-03, UI-06, UI-07 | Complete page/text/table inventory and ten+ table targets; tested reading order, explicit unreadable/deferred coverage/continuation and no duplicate claims |
| R-16 | E5 claims/orchestration remains partial/default-off | X-05, JOB-02 | Authoritative claim rebuild, projection parity, kill/retry/rerun proof; default path activated then obsolete path retired |
| R-17 | Two-document UAT lacks gold quality/generalization scoring | X-06 | Blind origin/template split; reviewed original-page annotations and computed full-text/page/table/reading-order/locator plus per-family extraction usefulness; honest sample uncertainty; Docling agreement is not ground truth |
| R-18 | Fixture search scoring does not prove actual hybrid superiority | X-07 | Same real query/filter/ACL set compared across lexical, semantic, visual and hybrid ranks/snippets |
| R-19 | Accepted line items not rendered; accepted fields truncated | UI-06, UI-07 | >5 accepted fields and >20 invoice/EOB rows fully accessible with evidence |
| R-20 | Backup/storage/worker/review/index badges fabricated | SEC-03, UI-03, OPS-04, X-01 | Timestamped actual values/model profiles, capacity-wait and unknown/stale/offline states; no test fixtures or 8B labels for 27B calls |
| R-21 | Rows always display Ingested; status does not refresh | UI-04, OPS-04 | Actual per-document job/quality progression and failure/retry updates |
| R-22 | Inbox filter pills change styling only | UI-04 | Server result IDs/counts reflect each filter and combinations |
| R-23 | Bulk Import and Create review set are inert | UI-04, UI-08 | Actual bounded batch intake and explicit selected-document work set |
| R-24 | First 50 documents only; no archive pagination | UI-04, UI-08 | >200-record browsing, stable pages/sort/selection and complete authorized totals |
| R-25 | Nested-folder and management UI incomplete | UI-05 | Three-level create/reparent/rename/remove, cycles denied, memberships and permission inheritance preserved |
| R-26 | Smart folders disabled; saved searches write-only/drop filters | UI-05, UI-08, X-07 | Reload/edit/delete/full-filter round-trip and dynamic membership after decisions |
| R-27 | Evidence navigation loses review task/context | UI-03, UI-06, UI-07 | Persistent side-by-side evidence, back/refresh and backlog position |
| R-28 | Review tasks lack identity/history and useful task-specific actions | UI-07 | Document-labeled tasks; correct observation/line/duplicate/relationship/quality forms and old/new audit history |
| R-29 | Stale async details remain actionable; weak error handling | UI-02, UI-03 | Reordered-response and double-submit tests; no mutation for mismatched loaded identity; errors retain edits |
| R-30 | Mobile navigation hidden; rows/selection/shortcut not keyboard usable | UI-03, UI-13 | Fresh 390px and keyboard-only entry reaches every enabled surface with visible focus |
| R-31 | Decorative thumbnails; no zoom/find/large-PDF acceptance | UI-06, UI-13 | Protected real previews, coordinate-correct zoom/rotation/find, lazy long-document navigation |
| R-32 | Logout/expiry recovery/deep links missing | UI-03, SEC-02 | Existing logout/expiry repair early; refresh/back/auth-safe deep links; final session lifecycle at G5 |
| R-33 | Figma drift, stale/empty Review screenshot, viewport mismatch | UI-01, UI-13 | Fresh 1440×960 and responsive populated/error-state references; documented visual acceptance |
| R-34 | Live review checks headings only; weak a11y/browser coverage | UI-07, UI-13, REL-02 | Actual persisted correction/evidence/history; keyboard/mobile/critical cross-browser workflows |
| R-35 | Relationship/timeline truncation and inactive smart-view cards | UI-10 | Full paginated events and actionable ACL-safe matching collections |
| R-36 | Analysis explanation/comparison and other actions missing | UI-11 | All seven types; citations support claims; save/discard/read; no canonical mutation; optional/offline behavior |
| R-37 | Export, settings, token/ACL/admin product missing | UI-12, SEC-02, EXP-01, OPS-04 | Real protected bundle/account/operator journeys plus audit and revocation checks |
| R-38 | Restart/readiness/degradation and capacity not proven | OPS-03, OPS-04, X-08, REL-02 | Scoped restart/recovery, dependency states, bounded queues, measured Oxcart shared-client impact and Blackbird document/reindex/query embedding capacity |
| R-39 | Mutable image tags, secure-cookie wiring and secret build-context hazards | SEC-02, OPS-03 | Pinned artifacts, actual TLS cookie/origin tests, no secrets/private artifacts in images |
| R-40 | Dependency audit findings and incomplete release security assurance | OPS-03, REL-02 | Updated/triaged dependencies with reachability rationale; required SAST/dependency/container checks |
| R-41 | Ordinary CI omits browser workflows; release gates incomplete | UI-13, REL-02, REL-03 | Regular browser CI plus isolated live release evidence; required failed/missing checks block promotion |
| R-42 | Version/branch/runtime drift and absent current deployment | X-01, OPS-03, REL-03 | Matching accepted source/image/schema/config state, functional deployed endpoints and scoped rollback |
| R-43 | Contradictory model guidance and excessive representations/modules | X-01, X-02, X-04, X-05, UI-01, UI-06, JOB-02 | ADRs 0008/0009 profile/parse/schema/provenance migration; genuine historical artifacts remain readable; Qwen-native target has no Docling prerequisite/veto or fabricated Docling output; cohesive owners and no obsolete active rendezvous |
| R-44 | Search freshness/metrics/backup visibility and runbooks incomplete | X-07, OPS-04, REL-03 | Correction/reindex freshness; real metrics; operator performs documented recovery tasks |

Additional implementation findings surfaced while creating the plan are covered rather than silently folded into a completed review item: obsolete provider-specific mandatory Granite release evidence (X-01); source-derived score computation instead of supplied favorable metrics (X-06); CSRF/session binding and recovery-link concurrency (SEC-02, with confirmed exploitable baseline defects handled under SEC-01 if reproduced); current OpenAPI overlay versus actual response parity (all route packages); model scratch concurrency and cross-host payload limits (X-08/SEC-03).

## All 26 stories

The [product workstream](product.md#complete-story-traceability) contains the detailed acceptance for every individual story. This register fixes the whole-program owners and gate so backend, model and UI evidence cannot be substituted for one another.

| Story | Required result | Packages | Gate |
| --- | --- | --- | --- |
| 1.1 | Immediate accepted upload with real processing state | UI-03, UI-04, JOB-02 | G2 |
| 1.2 | Immutable, hash-verifiable retrievable original | UI-04, EXP-01, OPS-02 | G2/G5 |
| 1.3 | Duplicate detection with user choice | UI-04, UI-10, SEC-01 | G2 |
| 2.1 | Usable thumbnail/page viewer, including large PDFs | UI-06, UI-13 | G2 |
| 2.2 | Nested folders, tags and multi-folder membership | UI-05, SEC-01 | G2 |
| 2.3 | Durable saved searches and live smart collections | UI-05, UI-08, X-07 | G2/G3 |
| 3.1 | ADR 0009 converter-neutral full text/pages/reading order/tables/chunks with original-coordinate evidence; Qwen-native parse works without Docling and exposes partial/failure states | JOB-02, X-01–X-08, UI-04, UI-06 | G2/G3 |
| 3.2 | Protected raw/normalized page/element/table diagnostics with actual converter/run/version; historical Docling artifacts retained, no fabricated Docling output | X-01, X-02, UI-06, SEC-03 | G2/G3 |
| 4.1 | Family/confidence and safe user override | X-03, UI-06, UI-07 | G2/G3 |
| 4.2 | Receipt fields/lines with arithmetic and useful quality | X-03, X-04, X-06, UI-06 | G3 |
| 4.3 | Invoice headers/dates/totals/lines where present | X-03, X-04, X-06, UI-06 | G3 |
| 4.4 | EOB claim/service/payment responsibility | X-03, X-04, X-06, UI-06 | G3 |
| 4.5 | Correct concrete evidence jumps for extracted fields | X-04, UI-06, UI-07 | G2/G3 |
| 5.1 | Actionable reasoned review queue | UI-07, X-03, X-05 | G2/G3 |
| 5.2 | Validated correction with preserved old/new actor/time history | UI-02, UI-07, SEC-01, X-02 | G1/G2 |
| 6.1 | Useful precise lexical results/snippets | X-07, UI-08 | G3 |
| 6.2 | Real semantic retrieval over source chunks using compatible document/reindex/query embeddings | X-07, X-08, UI-08 | G3 |
| 6.3 | Measured hybrid improvement | X-06, X-07, UI-08 | G3 |
| 6.4 | Composable filters with predictable persisted state | UI-04, UI-05, UI-08, X-07 | G2/G3 |
| 7.1 | Visible confirmable/manual document relationships | UI-10, SEC-01 | G2 |
| 7.2 | Meaningful complete timeline with source navigation | UI-10 | G2 |
| 8.1 | Cited EOB explanation with explicit save choice | UI-11, X-09 | G4 |
| 8.2 | Multi-document comparison with supporting citations | UI-11, X-09 | G4 |
| 9.1 | Real job visibility and safe retry | JOB-01, JOB-02, SEC-03, OPS-04, UI-12 | G1/G5 |
| 9.2 | Documented tested archive recovery | OPS-01, OPS-02, REL-02, REL-03 | G5/G6/G7 |
| 10.1 | Originals and structured-data bundles with manifests | EXP-01, UI-12 | G5 |

## Required spec features beyond story titles

| Source area | Explicit coverage | Packages |
| --- | --- | --- |
| App §6.1, §2.2 | Browser/drag-drop PDFs and supported images, mobile scans, bounded batch backlog, source metadata, preserved bytes and duplicate choices | UI-04, JOB-02 |
| App §6.2 | Full initial classification taxonomy (receipt/invoice/EOB/bill/insurance/legal/tax/warranty/identity/statement/handwritten/typed/reference/generic), subtype/confidence/rationale/version, ordinary-document reclassification | X-03, X-06, UI-06, UI-07 |
| App §§5.3, 6.3, 8–11 and 16 | ADR 0009 explicit provider change: converter-neutral Qwen-native full searchable transcription/Markdown, hierarchy/reading order, pages/elements/tables and validated original-coordinate evidence, versioned raw/normalized artifacts and graceful partial/unparsed states; genuine historical Docling artifacts retained | X-01–X-08, UI-04, UI-06 |
| App §6.4 | Receipt address/time/payment/quantities; invoice buyer/PO/remittance/due date; EOB modifiers/billed/allowed/paid/responsibility/deductible/copay/coinsurance where present | X-03, X-04, X-06, UI-06 |
| App §6.5 and §13 | Folder tree/tag CRUD, multi-membership/primary permissions, notes, basic merchant/provider/insurer/vehicle/appliance/topic identity-link-browse at G2, smart collections | UI-05, UI-09, UI-10, SEC-01 |
| App §6.6, §12 and §13.4 | Query history, exact/semantic/visual/hybrid, sort/group/facets/snippets/quick actions, relationship traversal, interpreted filters, optional reranker interface | UI-08, X-07; optional reranking EXT-09 |
| App §6.7 | Candidate comparison, field/line/observation decisions, ordinary reclassification/rerun/mark-reviewed/notes, source context and audit history | UI-02, UI-06, UI-07, X-02 |
| App §6.8 and Phase 7 | Ten relationship types, meaningful entity/case timelines, deadlines, unmatched/expiring smart views; explicit suggestion review | UI-10, UI-05; extended missing-companion hints EXT-07 |
| App §6.9 / Phase 9 | Seven analysis types, separate bounded worker/profile/context, immutable generated bodies, save choice, scoped citations/recommended actions, opt-in uncertainty, optional/offline behavior | UI-11, X-09 |
| App §6.10 / Phase 10 | Originals, accepted JSON, CSV/JSONL, review report, manifest/provenance/hashes, private authorized streaming download and retention | EXP-01, UI-12 |
| App §7 / NFR §§1–3 | Performance, async progress, integrity/restarts, atomic original writes, durable reference catalog and migration/version history | JOB-01/02, X-02/05/08, OPS-03/04, REL-02 |
| App §7.4/14 / NFR §§4–5 | Local-first default, no unapproved inference egress, auth/CSRF/secure cookies/passkeys/tokens/ACL, minimal sensitive logs, trusted-network access | SEC-01–SEC-03, OPS-03 |
| App §7.5/14 / NFR §§6–8 | Queue/model/search/index/storage/review metrics, protected diagnostics, real backups, audit upload/view/original-access/delete/correction/reclass/export/analysis-save/relationships; bounded private view events at G5 | SEC-03, OPS-01–OPS-04, EXP-01, UI-12 |
| App §15 | Immutable originals/derived history; coherent current run; soft-delete/trash/restore and export/backup awareness; graph/reference integrity | UI-04, X-02/05, OPS-02; optional hard purge EXT-10 |
| UI QA plan | Figma-specific dense workbench, all primary views/states, responsive drawers, true evidence focus, current references and actual workflow/keyboard/network checks | UI-01, UI-03, UI-06/07, UI-11–UI-13 |
| Phase 6 | Contacts/aliases/links/merge decisions; all six filing-rule actions, dry-run/audit/transactional acceptance, watcher roots/symlinks/stable-file protection and maintenance CLI | UI-09, SEC-01, JOB-02, OPS-04 |
| Phases 8/8.5 | ADR 0009 Qwen-native searchable parse and versioned original-page evidence; quality signals/source modalities, selective real visual retrieval, review-first claims, no hidden semantic rescue or Docling veto, truthful scored evidence | X-01–X-09, UI-06/07 |
| Phases 10–12 | Complete operations/settings/security/export, actual backup recovery, production-like CI/quality/capacity, release manifests/notes/runbooks/known issues/tag/sync | SEC-02, EXP-01, OPS-01–OPS-04, UI-12/13, REL-01–REL-03 |

The complete original phase plans remain required acceptance depth, not optional rationale. Every exposed contract route must have real semantics or an explicitly disabled later-stage capability; the release route inventory cannot retain unexplained placeholders. Preserve optional reranking and addenda compatibility decisions rather than forcing a new provider just to fill a checklist.

## Explicit extension roadmap

EXT-01–EXT-08 are defined in [product.md](product.md#full-specification-extension-sequence). Their owner must add backend, worker/model and operational reviewers where applicable. All start after G7; training/capacity and outbound notification/mail integrations require their own explicit configuration and measured policy.

| ID | Scope | Dependencies | Acceptance focus |
| --- | --- | --- | --- |
| EXT-01 | Email attachments and ZIP bulk intake | UI-04, UI-12, G7 | Idempotent mail/member intake, safe archive limits, credentials/revoke, per-item outcomes |
| EXT-02 | Redacted sharing/records packets | UI-06, EXP-01, G7 | Redacted content unrecoverable from text/layers/metadata; explicit preview and immutable originals |
| EXT-03 | OCR/deskew and parse-quality tuning | X-06, UI-06/07, G7 | Improvement beyond required Qwen-native parse, coordinate transforms/provenance, isolated optional adapter dependencies; no mandatory Docling authority |
| EXT-04 | Deadline/warranty reminders | UI-10, SEC-02, G7 | Accepted dates only, opt-in channels/time zone, idempotence, revocation/privacy |
| EXT-05 | Mobile companion/share extension | UI-03/04/06, SEC-02, G7 | Real-device intake, offline/auth/retry/cleanup, no duplicate business logic or hidden cloud data flow |
| EXT-06 | Richer household collaboration | SEC-01/02, UI-05/07, G7 | Concurrent edits/assignments, context switching, no cross-household caches/counts/jobs leakage |
| EXT-07 | Rich entity resolution, graph/case expansion and missing-companion hints | UI-09/10, G7 | Confirmable merge/split, bounded graphs, evidence/ACL, absence treated as an archive observation |
| EXT-08 | Corrected datasets, active learning and optional local LoRA | X-06, UI-07/12, G7 | Provenance/no holdout contamination, measured learning utility, independent model promotion/rollback |
| EXT-09 | Optional text/multimodal reranking | X-07/08, UI-08, G7 | Paired relevance improvement and bounded latency/VRAM with explicit outage behavior |
| EXT-10 | Explicit hard-purge lifecycle | UI-04, OPS-01/02, SEC-01/02, G7 | Exact scope/retention/reference checks, explicit destructive authorization, no unintended loss |

### EXT-09 — Optional reranking

Owner: retrieval/model adapters, with Search UI and runtime operations. Leave the core RRF planner unchanged by default. Select a maintained local text and, if useful, multimodal reranker only after a primary-source compatibility review and matched real-query baseline. Use a narrow adapter with explicit model/index/profile/version and bounded top-k/token/image budgets. The request and response expose when reranking was applied or unavailable; no hidden cloud calls.

Acceptance: paired blinded relevance scoring improves predeclared strata without unacceptable regression; all candidates and facets remain ACL-safe; added median/p95 and resource costs meet the separately published rerank budget; concurrent ingest/search still meets the selected capacity contract; failure leaves an honestly labeled base ranking. Deploy only a measured feature-flagged profile with rollback. The existence of a hook satisfies the baseline architecture requirement, but does not mark this enhancement complete.

### EXT-10 — Explicit hard-purge lifecycle

Owner: document/storage lifecycle and security/operations. Implement only after soft-delete and real restore have shipped. Define retention, legal/user holds where configured, deduplicated-blob reference checks, affected derived artifacts/claims/relationships/notes/export manifests and what can or cannot be removed from immutable backup history. Show an exact dry-run scope before requesting explicit destructive authorization. Do not promise instant erasure from offline backups; provide documented expiry/cryptographic-erasure policy only if actually supported.

Acceptance: another document's shared original blob cannot be deleted; all dependent live references remain valid or become explicit authorized tombstones; ordinary restore cannot silently resurrect a purged record contrary to documented policy; interrupted purge is resumable and auditable; unauthorized or incorrectly scoped purge produces no changes. Automatic destruction on extraction success remains prohibited. This is separate from v1 trash/restore.

## Tracking and acceptance record

Use this row shape per issue/package during implementation:

```text
ID:
Owner:
Status: planned | ready | in_progress | blocked | implemented | verified | accepted
Depends on:
Source requirements:
Implementation commit / migration / contract version:
Verification commands and result references:
Live profile / corpus / image / config identity, when required:
Acceptance evidence:
Remaining risk / blocker / next action:
```

The integrator checks that every R-* finding, every story and every required spec row has accepted evidence before G7. Extension rows remain open until G8 individual acceptance. An explicit user-approved scope change is recorded by reference; it is never silently treated as implemented. New findings discovered in execution receive new IDs rather than overwriting the meaning of an existing issue.
