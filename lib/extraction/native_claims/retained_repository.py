"""Current reader authority for immutable history, independent of producer lifetime."""

from typing import Any, cast

from lib.auth.authorization_policy import AuthorizationError
from lib.auth.request_authority import RequestCredential
from lib.auth.request_authority_repository import assert_request_authority, lock_request_authority
from lib.extraction.native_claims.authority_repository import validate_set_source
from lib.extraction.native_claims.errors import NativeClaimError
from lib.extraction.native_claims.models import NativeClaimBinding
from lib.extraction.native_claims.source_repository import read_locked_source


def lock_retained_set(
    cur: Any, binding: NativeClaimBinding, credential: RequestCredential
) -> dict[str, Any]:
    lock_request_authority(cur, credential, "documents:read")
    cur.execute(
        "SELECT primary_folder_id FROM documents WHERE id=%s FOR SHARE",
        (binding.processing.document_id,),
    )
    document = cur.fetchone()
    if document is None:
        raise AuthorizationError("Permission denied")
    if document["primary_folder_id"] is not None:
        folder_id = document["primary_folder_id"]
        cur.execute("SELECT id FROM folders WHERE id=%s FOR SHARE", (folder_id,))
        cur.fetchone()
        cur.execute(
            "SELECT id FROM folder_acl WHERE folder_id=%s AND ((principal_type='user' "
            "AND principal_id=%s) OR (principal_type='household' AND principal_id=%s)) "
            "ORDER BY id FOR SHARE",
            (folder_id, credential.user_id, credential.household_id),
        )
        cur.fetchall()
    assert_retained_read(cur, binding, credential)
    cur.execute(
        """SELECT r.*, g.state AS parse_state, g.inventory_sha256, g.structure_sha256,
        g.inventory_json, g.structure_json FROM document_processing_runs r
        JOIN document_parse_generations g ON g.id=r.parse_generation_id
        WHERE r.id=%s AND r.document_id=%s AND r.parse_generation_id=%s
          AND g.creator_run_id=r.id AND g.document_id=r.document_id FOR SHARE OF r""",
        (
            binding.processing.processing_run_id,
            binding.processing.document_id,
            binding.processing.parse_generation_id,
        ),
    )
    run = cur.fetchone()
    if run is None:
        raise NativeClaimError("Native claim source is unavailable.")
    source = read_locked_source(cur, binding.processing, run)
    cur.execute(
        "SELECT * FROM native_claim_sets WHERE id=%s AND document_id=%s "
        "AND processing_run_id=%s AND parse_generation_id=%s FOR SHARE",
        (
            binding.claim_set_id,
            binding.processing.document_id,
            binding.processing.processing_run_id,
            binding.processing.parse_generation_id,
        ),
    )
    header = cur.fetchone()
    if header is None:
        raise NativeClaimError("Native claim set is unavailable.")
    validate_set_source(header, source)
    return cast(dict[str, Any], header)


def assert_retained_read(
    cur: Any, binding: NativeClaimBinding, credential: RequestCredential
) -> None:
    assert_request_authority(cur, credential, "documents:read")
    cur.execute(
        "SELECT document_is_readable(id,%s,%s,NULL) AS allowed FROM documents "
        "WHERE id=%s AND deleted_at IS NULL",
        (credential.household_id, credential.user_id, binding.processing.document_id),
    )
    row = cur.fetchone()
    if row is None or not row["allowed"]:
        raise AuthorizationError("Permission denied")
