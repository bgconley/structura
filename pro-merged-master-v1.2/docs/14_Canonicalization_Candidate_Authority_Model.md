# 14 — Canonicalization, Candidate, and Authority Model

Historical note: In v1.3 this document is background rationale unless explicitly referenced by the ADR summary or the current normalization doc.

Prepared: 2026-04-23

## 1. Purpose

This addendum strengthens the data model and extraction workflow by making a hard distinction between:

- raw extraction outputs,
- candidate facts,
- canonical accepted facts,
- review decisions,
- analysis notes.

The distinction matters because multiple engines may extract different values from the same document. The system must preserve those differences instead of collapsing them too early.

## 2. Definitions

### Raw output

A raw output is an untrusted artifact produced by a parser, model, planner, validator, or extractor.

Examples:
- Docling JSON
- Qwen raw response
- Granite table output
- validator trace
- normalization trace

### Candidate

A candidate is a typed value proposed by a specific run.

Examples:
- `invoice.total_amount = 1042.15` from Granite
- `invoice.total_amount = 1042.13` from Qwen
- `receipt.transaction_date = 2026-04-03` from Docling text extraction

Candidates are not canonical facts.

### Canonical fact

A canonical fact is the value the application uses for ordinary UI display, filtering, filing, search context, and downstream logic.

A canonical fact is selected by:
- deterministic reconciliation,
- authority weighting,
- validation,
- confidence threshold,
- or human review.

### Review decision

A review decision records why a candidate was accepted, edited, rejected, deferred, or superseded.

### Analysis note

An analysis note is non-canonical. It may explain or compare documents, but it does not silently rewrite canonical facts.

## 3. Authority matrix

| Source | Strong for | Weak for | Notes |
|---|---|---|---|
| Docling | structure, reading order, page grounding, layout, tables where deterministic parse is clean | broad semantic inference | Should remain canonical structural layer |
| Granite Vision | KVP, tables, charts, invoice/receipt/EOB line items | free-form narrative interpretation | Use as structured specialist |
| Qwen3-VL | classification, OCR rescue, handwriting, broad semantics, ambiguous layouts, arbitration | final table arithmetic authority without validation | Use as fallback/arbiter, not blanket final source |
| Validators | totals, dates, required fields, consistency, deterministic transforms | semantic inference | Validators can promote/reject candidates only within explicit rules |
| Human reviewer | final accepted facts and overrides | none | Human override should be auditable |

## 4. Canonicalization order

Apply this order:

1. Collect raw outputs.
2. Normalize candidate values into typed candidate tables.
3. Attach evidence to each candidate.
4. Run deterministic normalizers.
5. Run validation rules.
6. Compare candidates by field path.
7. Apply typed authority weighting.
8. Promote clean values automatically only when the policy permits.
9. Create review tasks for unresolved values.
10. Persist canonical facts only after automatic promotion or review decision.

## 5. Automatic promotion criteria

A candidate may be promoted automatically when all of the following are true:

- the document family allows auto-promotion for this field;
- required evidence exists;
- JSON Schema validation passes;
- deterministic validation passes;
- no higher-authority candidate conflicts materially;
- confidence is above the configured threshold;
- the sensitivity/review policy permits automatic acceptance.

## 6. Review triggers

Create a review task if:

- required field missing;
- two high-authority candidates disagree;
- line item totals do not reconcile;
- date normalization is suspicious;
- evidence locator is weak or missing;
- OCR confidence is low;
- the document family is high-stakes and policy requires review;
- the user explicitly requests review.

## 7. Canonical facts and UI behavior

The UI should display canonical facts by default, with a visible provenance affordance.

In v1.3, `canonical_fields` and `canonical_line_items` are the default read path for ordinary document detail, filtering, filing suggestions, search context, and exports. `field_candidates` and `line_item_candidates` are review/adjudication inputs. The older generic `document_fields` and `document_line_items` tables remain compatible normalized extraction-run projections, but they are not the final authority for accepted user-facing facts.

For every canonical fact, the UI should answer:
- value;
- source candidate or human edit;
- extraction run;
- evidence locator;
- validation state;
- review state.

## 8. Candidate review UX

For a contested field, show:

```text
Field: invoice.total_amount

Canonical value:
  $1042.15

Candidates:
  Granite Vision 3B: $1042.15, evidence page 1 table row total, confidence 0.91
  Qwen3-VL 8B:      $1042.13, evidence page 1 bottom text, confidence 0.77
  Docling text:     $1042.15, evidence page 1 text span, confidence 0.84

Validation:
  subtotal + tax = $1042.15
  line items reconcile: yes

Suggested action:
  accept Granite/Docling value
```

## 9. Field path convention

Use stable dotted field paths:

```text
document.title
classification.document_family
invoice.invoice_number
invoice.issue_date
invoice.due_date
invoice.total_amount
receipt.transaction_date
receipt.total_amount
medical_eob.claim_number
medical_eob.service_lines[].patient_responsibility
contract.parties[].name
contract.renewal_date
```

Field paths are contracts. Changing field paths should require schema and migration updates.

## 10. Line item candidate policy

Line items are harder than scalar fields. Preserve whole line-item candidate sets, not only individual cells.

Recommended pattern:
- one `line_item_candidates` row per candidate line item;
- link line-item candidates to a run and optional table/row evidence;
- canonical line items are selected or constructed after validation.

## 11. Human edits

When a user edits a canonical value:
- create or update a canonical fact;
- mark source as `human`;
- retain prior canonical value in review/audit events;
- do not delete underlying candidates.

## 12. Implementation impact

Required database additions:
- `field_candidates`
- `line_item_candidates`
- `canonical_fields`
- `canonical_line_items`
- stronger review event linkage
- optional `canonical_fact_history`

Required API additions:
- list candidates for a field;
- accept candidate;
- edit canonical value;
- reject candidate;
- create review event.

Required UI additions:
- candidate comparison panel;
- evidence preview for each candidate;
- canonical fact history drawer.
