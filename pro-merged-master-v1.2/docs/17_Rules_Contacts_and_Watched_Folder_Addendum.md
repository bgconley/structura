# 17 — Rules, Contacts, and Watched-Folder Addendum

Historical note: In v1.3 this document is background rationale unless explicitly referenced by the ADR summary or the current normalization doc.

Prepared: 2026-04-23

## 1. Why this addendum exists

The golden master correctly elevates contacts, rules, and watched-folder intake from incidental ideas to real product surfaces.

These features should be integrated, but they should remain transparent and reviewable.

## 2. Contacts

Contacts normalize repeated parties across documents:
- merchants;
- medical providers;
- insurers/payers;
- law firms;
- government agencies;
- utilities;
- vendors;
- personal correspondents.

Contacts should support:
- aliases;
- identifiers;
- addresses;
- phone/email;
- relationship to documents;
- suggested merge/dedupe tasks.

Contacts are not merely a UI nicety. They improve:
- filing rules;
- search facets;
- document relationships;
- medical bill/EOB matching;
- recurring vendor tracking.

## 3. Filing rules

Rules are inspectable automations.

A rule has:
- name;
- enabled flag;
- priority;
- conditions;
- actions;
- dry-run output;
- last run summary.

Example:

```json
{
  "name": "File Aetna EOBs",
  "conditions": [
    { "field": "document_family", "op": "eq", "value": "medical_eob" },
    { "field": "counterparty", "op": "contains", "value": "Aetna" }
  ],
  "actions": [
    { "type": "add_folder", "folder_path": "Medical/Insurance/EOBs" },
    { "type": "add_tag", "tag": "insurance" }
  ]
}
```

## 4. Rule safety

Rules should be assistive by default:
- show why a rule matched;
- allow dry-run;
- allow user confirmation;
- avoid hidden destructive action;
- audit applied actions.

For high-stakes documents, rules should suggest rather than silently finalize.

## 5. Watched-folder intake

Watched-folder intake should be a separate service:
- monitors configured folders;
- accepts PDF files only in v1;
- moves/links files into staging;
- computes hash;
- enqueues ingest job;
- records source path;
- optionally moves processed files to `processed/` or leaves them in place depending policy.

## 6. Watcher safeguards

The watcher should:
- ignore partial files until stable;
- reject non-PDF files;
- avoid duplicate imports by hash;
- not recursively ingest application output directories;
- maintain an ingest log;
- support pause/resume.

## 7. CLI and import

Add a CLI for:
- bulk import;
- dry-run import;
- reprocess document;
- rebuild search projection;
- run evaluation set;
- backup/restore checks.

## 8. UI surfaces

Add:
- Contacts page;
- Rules page;
- Watch-folder settings;
- Rule dry-run modal;
- Suggested filing explanation panel;
- Import status page.

## 9. Implementation order

1. Contacts table and document contact mentions.
2. Watched-folder service with PDF-only ingest.
3. Rules schema and dry-run engine.
4. Rule suggestions in review/inbox.
5. Rule application with audit.
6. Contacts merge/dedupe tools.
