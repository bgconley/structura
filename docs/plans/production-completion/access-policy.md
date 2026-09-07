# Baseline access policy (SEC-01)

This policy repairs existing Phase 0–8.5 behavior. Account/ACL management remains in Phase 10. Resource queries require an enabled user with live membership in the selected household; a caller-supplied role cannot grant database authority. Credential resolution refreshes membership and role on every request. No grant crosses household boundaries.

| Actor/resource | Read | Write and review |
| --- | --- | --- |
| Household owner/admin | All non-deleted documents in that household | All non-deleted documents in that household |
| Member who owns the document | Yes | Yes |
| Viewer, including document owner | According to document read policy | Never |
| Member with household-mode, non-highly-sensitive document in a household primary folder | Yes | Yes |
| Member/viewer with eligible document in a custom/private primary folder | Folder ownership or user/household read/write/admin grant | Member only, with folder ownership or write/admin grant |
| Non-owner with private/custom document, highly-sensitive document, or no primary folder | Owner/admin only under the existing baseline read policy | Owner/admin only |
| Missing membership, disabled user, other household | Never | Never |

Secondary folders do not broaden document access. Refiling requires write authority on the document and every selected target folder. Folder write requires enabled membership, a non-viewer role and household/owner/write/admin authority. Document review changes canonical data, so it requires document write authority; a review token may perform review actions but cannot otherwise refile or edit metadata. Relationship decisions require write authority on both documents. Denied mutations must leave domain data, successful-action audits and child jobs unchanged.

Relationship creation/decisions and filing-suggestion decisions lock affected documents in ascending ID order, then query permissions again in a separate statement in the same transaction. The permission query must run after a competing refile's lock is released. Relationship decisions accept `documents:review` scope while creation requires `documents:write`. Contact edits/merges and contact-link writes lock contact IDs first, then document IDs, each in ascending order; the merge's linked-document inventory and fresh permission checks occur only after contact locks stabilize concurrent links.

API-token authority is the intersection of current user authorization and explicit scopes. Supported baseline scope names are `documents:read`, `documents:write`, `documents:review`, `jobs:admin`, `service:admin`, and explicit full administrative scopes `admin`/`admin:*`. Document write/review scopes include document reads; write includes review. Administrative scopes never promote a member/viewer to an administrator. `jobs:admin` does not grant service administration or document writes; `service:admin` does not grant job administration. Empty/unknown scopes grant no capability. Browser sessions use the same role/resource policy without token scope restrictions. Invalid token headers fail authentication rather than falling back to a browser cookie.

Ordinary document-derived job reads require document-read capability and the referenced document's live read policy. Jobs without a document reference are visible only to household administrators with job-administration capability. The explicitly administrative queue routes retain household-wide visibility. Missing and inaccessible job IDs return the same not-found response.

`folder_acl.principal_type = role` currently has no defined named-role representation because `principal_id` is UUID-valued. Such rows grant no access in this baseline; Phase 10 must define and migrate the representation together with its contract before exposing role-grant creation. This repair does not invent role UUIDs or broaden private/custom/highly-sensitive document visibility.

The existing global tag catalog is not household-scoped in the baseline schema; SEC-01 restricts mutation capabilities, but household isolation of shared catalog metadata requires a separate coordinated schema change. Token-creation APIs, passkeys, full session/CSRF lifecycle and asynchronous user-request authority rechecks belong to their owning completion packages.
