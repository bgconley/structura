# User stories and acceptance criteria

## Epic 1 - ingest and preserve

### Story 1.1
As a user, I want to upload a PDF and see it appear immediately in an inbox so that I know the system has accepted the file.

Acceptance criteria:
- upload returns success and a document id;
- the inbox shows the new row without waiting for extraction;
- the row displays processing state.

### Story 1.2
As a user, I want the original file preserved exactly so that I can trust the archive.

Acceptance criteria:
- the original asset hash is stored;
- the original bytes are not overwritten;
- the original can be downloaded later.

### Story 1.3
As a user, I want duplicate files detected so that I do not file the same document repeatedly.

Acceptance criteria:
- exact byte duplicates are flagged;
- the system does not silently merge documents;
- the user can decide what to do.

## Epic 2 - browse and file

### Story 2.1
As a user, I want a clean PDF viewer with page thumbnails so that I can inspect documents quickly.

Acceptance criteria:
- thumbnails render correctly;
- page navigation is stable;
- large PDFs remain usable.

### Story 2.2
As a user, I want to place documents into folders and tags so that I can organize them in the way that makes sense to me.

Acceptance criteria:
- nested folders are supported;
- tags can be created and applied;
- one document can belong to multiple folders if desired.

### Story 2.3
As a user, I want saved searches and smart folders so that I can maintain dynamic collections like “tax relevant” or “needs review.”

Acceptance criteria:
- saved searches persist;
- smart folders update automatically as document state changes.

## Epic 3 - canonical understanding

### Story 3.1
As a user, I want the system to parse a document into pages and text so that search and extraction can work even if I never run an LLM analysis.

Acceptance criteria:
- canonical parse artifacts are stored;
- page text and chunks are queryable;
- parse failures are surfaced visibly.

### Story 3.2
As an engineer, I want to inspect canonical artifacts so that I can debug extraction issues.

Acceptance criteria:
- raw canonical JSON is accessible in debug views;
- page and element data can be inspected.

## Epic 4 - classification and extraction

### Story 4.1
As a user, I want the app to classify a receipt, invoice, or EOB automatically so that I do not need to label every file by hand.

Acceptance criteria:
- a family and confidence are shown;
- the user can override the family.

### Story 4.2
As a user, I want receipt totals and line items extracted so that I can search and review spending.

Acceptance criteria:
- merchant, date, subtotal, tax, total, and line items are captured where present;
- arithmetic validation runs.

### Story 4.3
As a user, I want invoice header fields and line items extracted so that I can track obligations and payment history.

Acceptance criteria:
- invoice number, issue date, due date, totals, and line items are captured where present.

### Story 4.4
As a user, I want medical EOB service lines extracted so that I can understand what insurance paid and what I owe.

Acceptance criteria:
- payer, provider, patient, claim info, and service lines are captured where visible;
- plan paid and patient responsibility are represented explicitly.

### Story 4.5
As a user, I want every extracted field tied back to evidence so that I can verify the system’s interpretation.

Acceptance criteria:
- clicking a field highlights or jumps to the source location;
- the evidence includes page number and at least one concrete locator.

## Epic 5 - review and correction

### Story 5.1
As a user, I want uncertain documents routed to a review queue so that I can resolve ambiguous results deliberately.

Acceptance criteria:
- low-confidence or invalid outputs create review tasks;
- review tasks show reason and priority.

### Story 5.2
As a user, I want to correct a field and keep that correction in history so that the system remains auditable.

Acceptance criteria:
- old and new values are recorded;
- actor and timestamp are recorded;
- accepted data updates without destroying history.

## Epic 6 - retrieval

### Story 6.1
As a user, I want keyword search to find precise matches quickly so that exact invoices, names, claim ids, or terms are easy to locate.

Acceptance criteria:
- BM25 search returns relevant results;
- snippets or highlights are available when relevant.

### Story 6.2
As a user, I want semantic search so that I can find documents even when I do not remember exact wording.

Acceptance criteria:
- natural-language queries return conceptually relevant results;
- semantic search works over chunked document content.

### Story 6.3
As a user, I want hybrid search so that the system uses both exact terms and semantic similarity.

Acceptance criteria:
- hybrid search produces better results than lexical-only on the benchmark queries.

### Story 6.4
As a user, I want filters for type, date, amount, folder, tags, and review status so that I can narrow large result sets.

Acceptance criteria:
- filters compose correctly;
- results update predictably.

## Epic 7 - document relationships

### Story 7.1
As a user, I want related documents linked together so that I can see full transaction or claim history.

Acceptance criteria:
- relationships are visible on the document page;
- users can confirm or create links manually.

### Story 7.2
As a user, I want a timeline view for related documents so that I can understand sequence and context.

Acceptance criteria:
- timeline ordering uses meaningful dates;
- the view links back to each original document.

## Epic 8 - analysis workspace

### Story 8.1
As a user, I want to ask the system to explain a medical EOB in plain language so that I can understand what happened.

Acceptance criteria:
- the answer cites the source pages;
- the answer is stored as an analysis note if I choose to save it.

### Story 8.2
As a user, I want to compare documents, such as two contracts or two bills, so that I can see changes or discrepancies.

Acceptance criteria:
- analysis can operate on multiple selected documents;
- citations show where each finding came from.

## Epic 9 - operations and trust

### Story 9.1
As an operator, I want background jobs and failures visible so that I can manage the system without guessing.

Acceptance criteria:
- job status can be listed;
- failed jobs can be retried.

### Story 9.2
As an operator, I want backup and restore procedures so that the archive is resilient.

Acceptance criteria:
- restore has been tested;
- documentation exists.

## Epic 10 - export

### Story 10.1
As a user, I want to export originals plus extracted data so that I can share, archive, or analyze records elsewhere.

Acceptance criteria:
- export bundles can include originals and structured data;
- bundle manifests describe contents.

## Product-level acceptance summary

The user stories are considered materially satisfied for v1 when:

- ingest, browse, file, and search are already useful without any analysis;
- extracted data is evidence-backed and reviewable;
- the system performs well enough on a representative document set;
- failures are explicit rather than hidden.
