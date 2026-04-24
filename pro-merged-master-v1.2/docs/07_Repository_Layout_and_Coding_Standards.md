# Repository layout and coding standards

## 1. Recommended monorepo layout

```text
structura/
  apps/
    web/
    api/
  workers/
    ingest/
    previews/
    docling/
    extraction/
    embeddings/
    relationships/
    analysis/
  lib/
    config/
    db/
    storage/
    jobs/
    contracts/
    evidence/
    search/
    observability/
    models/
  contracts/
    api/
    schemas/
    events/
  database/
  infrastructure/
    docker/
    zfs/
    scripts/
  docs/
  tests/
    unit/
    integration/
    e2e/
    corpus/
```

## 2. General coding standards

- prefer explicit types;
- favor small modules with obvious ownership;
- treat contracts as first-class code artifacts;
- avoid undocumented magic constants;
- keep prompts versioned and checked in;
- use stable names for job types and schema names.

## 3. Backend standards

- FastAPI plus Pydantic for API contracts
- SQLAlchemy or SQLModel if preferred, but raw SQL is acceptable for search-heavy flows
- no business logic inside route handlers beyond orchestration
- all DB writes should go through clear service boundaries
- background-job handlers must be idempotent

## 4. Frontend standards

- use React + Vite as the normative workbench frontend
- separate page state, API client state, and local UI state
- prefer clearly named components over giant page files
- evidence jump and review correction are core interactions; design component structure accordingly
- keep debug or ops UI gated behind explicit routes or flags

## 5. DB and migration standards

- numbered SQL migration files or an equivalent migration tool
- schema changes in source control only
- add comments for non-obvious indexes
- when modifying extraction schemas, update both JSON contracts and DB expectations

## 6. Contract standards

For every JSON Schema:
- include `$schema`
- include an id or stable filename-based identifier
- version the schema in the filename
- prefer explicit required fields
- keep evidence fields structurally consistent across schemas

## 7. Worker standards

Every worker should:
- claim jobs explicitly
- update durable job state
- log start and finish with correlation ids
- record model metadata if relevant
- emit structured failure payloads

## 8. Prompt and model standards

- prompts must be versioned strings or templates in source control;
- model name and version must be recorded with every run;
- do not let prompt tweaks happen only in notebooks or shell history.

## 9. API standards

- version under `/api/v1`
- use predictable resource nouns
- keep upload, review, search, and analysis clearly separated
- analysis endpoints must not imply mutation of accepted extracted facts

## 10. Documentation standards

Update docs when:
- repository layout changes materially
- a new document family is added
- core ADRs change
- a new worker or service is introduced
- search or extraction behavior changes materially
