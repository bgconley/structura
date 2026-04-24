# Nonfunctional requirements, security, privacy, and observability

## 1. Performance targets

These are initial targets for a single-node deployment on the specified workstation and should be refined with real measurement.

### 1.1 API responsiveness
- health endpoints: under 100 ms
- inbox list: under 500 ms median
- document detail metadata: under 500 ms median
- search endpoint lexical-only: under 300 ms median
- hybrid search endpoint: under 1 second median
- review action submit: under 500 ms median

### 1.2 Background processing
- upload acknowledgment should not wait for heavy extraction;
- page preview generation should begin immediately after ingest;
- long extraction tasks must expose progress and status;
- background task retries must use bounded exponential backoff.

### 1.3 UI behavior
- no blocking spinner for long processing without status updates;
- clear “pending”, “running”, “failed”, and “review required” states.

## 2. Reliability requirements

- original asset writes must be atomic from the application’s point of view;
- the DB must remain the authoritative catalog of all objects and runs;
- workers must be safe to retry;
- the system must survive host restart without logical corruption;
- object storage and DB references must be reconcilable through integrity checks.

## 3. Data integrity requirements

- no accepted extraction without schema validation;
- one current canonical parse per document, with history retained;
- one current extraction per document plus schema name, with history retained;
- all correction events must be append-only;
- deletion must not silently break relationship graph integrity.

## 4. Security requirements

### 4.1 Local-first posture
- the default deployment must not depend on remote inference services;
- outbound network calls for document content should be disabled or clearly controlled.

### 4.2 Authentication and session handling
- authenticated routes for document content;
- DB-backed session records and secure session cookies;
- session cookies must be HttpOnly, Secure in TLS deployments, SameSite=Lax by default, and narrowly scoped;
- browser mutating routes must use CSRF protection unless the route is explicitly token-only;
- session timeout and logout support;
- bootstrap password or magic-link flow for first local admin creation;
- passkeys/WebAuthn recommended before any non-local exposure.

### 4.3 Access boundaries
- single-household friendly in v1.3;
- household-aware ownership and folder ACL in the baseline schema;
- app architecture should not block future role separation for admin vs reviewer vs standard user.

### 4.4 Secret handling
- secrets must not be committed;
- environment variables or secret files must be typed and validated;
- logs must not print secret values.

## 5. Privacy requirements

- do not log raw full document text unless explicitly in debug mode;
- redact or suppress especially sensitive fields in logs and error payloads;
- support sensitivity labeling on documents;
- remote access should be constrained to trusted network paths.

## 6. Storage and backup requirements

- Postgres must live on its own ZFS dataset with DB-appropriate settings;
- object artifacts must live on a large-recordsize compressed dataset;
- snapshots must be documented and schedulable;
- backup strategy must distinguish:
  - DB logical / physical backup
  - object storage copy
  - model cache and reproducible downloads
  - configuration backup

## 7. Observability requirements

The system should expose at least the following metrics or equivalent status views:

- queue depth by job type
- job success and failure counts
- job age
- extraction validation failure counts
- search latency
- model server latency
- storage usage by artifact type
- document counts by status
- review queue size

The system should also log:

- document ingest events
- extraction start / finish
- validation failures
- review corrections
- export events
- admin retries

## 8. Audit requirements

The following actions should be auditable:

- upload
- delete / archive
- field correction
- reclassification
- export
- analysis note save
- relationship creation or deletion

## 9. Quality requirements for AI outputs

- every extraction schema must have fixtures and validation tests;
- arithmetic checks are mandatory for financial-style documents;
- low-confidence fields should default toward review-required behavior;
- analysis outputs must cite sources and remain separate from extracted fact tables.

## 10. Compliance-like operational expectations

This project may contain medical, legal, and financial material. Even if no formal compliance certification is pursued, the operational posture should resemble a serious private archive:

- encrypted disks or encrypted datasets where feasible;
- careful access control;
- minimal data egress;
- tested backups;
- auditable changes.

## 11. Failure handling requirements

- user-facing status must distinguish “processing”, “needs review”, and “failed”;
- failed jobs must be retryable;
- repeated failure should lead to dead-letter or paused state with operator visibility;
- the app should remain browseable and searchable even if one model server is offline.

## 12. Release requirements

A release candidate is not acceptable unless:

- migrations succeed from scratch;
- restore testing has been performed;
- at least one golden-corpus regression run has passed;
- known-severity issues are documented.
