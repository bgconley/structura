# 16 — Auth, ACL, and Household Model

Historical note: In v1.3 this document is background rationale unless explicitly referenced by the ADR summary or the normalization doc.

Prepared: 2026-04-23

## 1. Purpose

The first deployment may be a single-household local install with one visible admin user, but the data model should not block household use. Personal records often belong to more than one trusted person, and some documents need more restricted access than others.

## 2. Recommended identity model

Add:
- `households`
- `users`
- `household_memberships`
- `user_password_credentials`
- `webauthn_credentials`
- `sessions`
- `magic_links`
- `api_tokens`

## 3. Authentication policy

Recommended v1.3 target:
- DB-backed sessions for browser access;
- bootstrap password or magic-link flow for first local admin setup;
- bootstrap passwords stored in `user_password_credentials` with a strong one-way hash such as Argon2id;
- HttpOnly session cookies with SameSite=Lax by default and CSRF protection on browser mutating routes;
- WebAuthn/passkeys as the preferred strong sign-in method once the app moves beyond purely local bootstrap use;
- scoped API tokens for CLI/import/admin automation.

Password-only bootstrap is acceptable for initial local setup, but passkeys are the preferred hardening path. Session rows should persist the authentication method used to create them.

## 4. Authorization model

Authorize every document and asset access through:
- document household;
- user membership;
- folder ACL;
- document sensitivity;
- optional explicit document grants.

Do not serve object-store URIs directly to the browser without API authorization.

## 5. Folder ACL

Folder ACL modes:
- `private`
- `household`
- `custom`

Custom ACL should allow user- or role-specific access.

## 6. Document ACL inheritance

Default:
- document inherits from primary folder;
- if no primary folder, household owner/admin can see it;
- restricted documents may require explicit grant or owner/admin.

## 7. Sensitivity interaction

Sensitivity levels should affect:
- search result visibility;
- analysis eligibility;
- export warnings;
- audit detail;
- review requirements.

## 8. Audit requirements

Audit:
- sign-in;
- export;
- delete/purge;
- ACL changes;
- token creation;
- analysis over restricted documents;
- failed access attempts where practical.

## 9. Implementation order

Do not let auth block all development. Recommended order:
1. bootstrap admin user;
2. household table and membership;
3. bootstrap password credential or magic-link issuance path;
4. DB-backed sessions and session introspection;
5. document ownership/household foreign keys;
6. folder ACL;
7. asset authorization;
8. WebAuthn/passkeys;
9. magic link recovery/invite;
10. API tokens.

## 10. UI implications

Add settings surfaces for:
- household members;
- bootstrap password rotation or disablement;
- passkeys;
- recovery links;
- API tokens;
- folder permissions;
- restricted document visibility.
