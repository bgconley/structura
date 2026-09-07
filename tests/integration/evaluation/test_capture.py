from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from lib.auth import AuthService, hash_secret
from lib.db.connection import db_connection
from lib.document_processing.service import DocumentProcessingService
from lib.documents.access_policy import DocumentAccessContext
from lib.evaluation.capture_models import CaptureDeclaration, CaptureUnavailable
from lib.evaluation.persisted_capture import capture_sealed_generation
from lib.jobs import JobService


def sql(statement, params=()):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchall() if cur.description else []


def seal(processing, *, text="Immutable source transcription"):
    processing.configuration = processing.configuration.model_copy(
        update={"model_revision": "fixture:database-test-v1"}
    )
    run = processing.start()
    claimed = processing.claim()
    service = DocumentProcessingService()
    checkpoint = processing.checkpoint(run, text=text)
    with processing.scope(claimed):
        service.initialize_inventory(run.binding, processing.inventory)
        service.checkpoint(run.binding, checkpoint)
        service.seal(run.binding, processing.structure(run, [checkpoint]))
    JobService().complete_job(job_id=claimed.state.job_id, claim_token=claimed.claim_token)
    return run


def capture(processing, run, **overrides):
    return capture_sealed_generation(
        **{
            "document_id": processing.document_id,
            "processing_run_id": run.binding.processing_run_id,
            "parse_generation_id": run.binding.parse_generation_id,
            "access": processing.access,
            "declaration": CaptureDeclaration(
                item_id="sql-capture-fixture",
                commit="c" * 40,
                max_output_tokens=8192,
                temperature=0,
            ),
            **overrides,
        }
    )


def test_exact_sealed_capture_does_not_change_publication_or_claim_live_execution(processing):
    run = seal(processing)
    result = capture(processing, run)
    assert result.capture.fixture_type == "deterministic_fixture"
    assert result.capture.structure.pages[0].elements[0].text == "Immutable source transcription"
    assert result.capture.structure.processing_run_id == run.binding.processing_run_id
    assert result.original_artifact_verification == "not_evaluated"
    assert result.commit_provenance == "externally_declared"
    assert (
        sql("SELECT canonical_asset_id FROM documents WHERE id=%s", (processing.document_id,))[0][
            "canonical_asset_id"
        ]
        == processing.asset_id
    )


def test_superseded_and_cancelled_sealed_history_resolves_without_current_fallback(processing):
    old = seal(processing, text="First retained source")
    new = seal(processing, text="Second retained source")
    historical = capture(processing, old)
    assert historical.run_status == "superseded"
    assert historical.capture.structure.pages[0].elements[0].text == "First retained source"
    DocumentProcessingService().cancel(new.binding, access=processing.access)
    cancelled = capture(processing, new)
    assert cancelled.run_status == "cancelled"
    assert cancelled.capture.structure.pages[0].elements[0].text == "Second retained source"
    assert capture(processing, old).capture == historical.capture


def test_unsealed_and_mixed_or_foreign_identifiers_are_unavailable(processing):
    unsealed = processing.start()
    with pytest.raises(CaptureUnavailable):
        capture(processing, unsealed)
    old = seal(processing)
    new = seal(processing)
    for overrides in (
        {"document_id": uuid4()},
        {"processing_run_id": uuid4()},
        {"parse_generation_id": new.binding.parse_generation_id},
        {"access": replace(processing.access, household_id=uuid4())},
    ):
        with pytest.raises(CaptureUnavailable):
            capture(processing, old, **overrides)


@pytest.mark.parametrize("revocation", ["membership", "disabled", "deleted"])
def test_historical_capture_requires_live_document_access(processing, revocation):
    old = seal(processing)
    seal(processing)
    assert capture(processing, old).run_status == "superseded"
    if revocation == "membership":
        sql(
            "DELETE FROM household_memberships WHERE household_id=%s AND user_id=%s",
            (processing.access.household_id, processing.access.user_id),
        )
    elif revocation == "disabled":
        sql("UPDATE users SET is_disabled=true WHERE id=%s", (processing.access.user_id,))
    else:
        sql(
            "UPDATE documents SET deleted_at=clock_timestamp() WHERE id=%s",
            (processing.document_id,),
        )
    with pytest.raises(CaptureUnavailable):
        capture(processing, old)


@pytest.mark.parametrize("revocation", ["scopes", "revoked", "expired"])
def test_capture_rechecks_persisted_token_state_despite_stale_context(processing, revocation):
    run = seal(processing)
    token_id = sql(
        "INSERT INTO api_tokens (user_id,household_id,label,token_hash,scopes) "
        "VALUES (%s,%s,'Capture fixture',%s,%s) RETURNING id",
        (
            processing.access.user_id,
            processing.access.household_id,
            hash_secret(uuid4().hex),
            ["documents:read"],
        ),
    )[0]["id"]
    access = replace(processing.access, api_token_id=token_id, scopes=("documents:read",))
    assert capture(processing, run, access=access).run_status == "sealed"
    if revocation == "scopes":
        sql("UPDATE api_tokens SET scopes=ARRAY['jobs:admin']::text[] WHERE id=%s", (token_id,))
    elif revocation == "revoked":
        sql("UPDATE api_tokens SET revoked_at=clock_timestamp() WHERE id=%s", (token_id,))
    else:
        sql(
            "UPDATE api_tokens SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",
            (token_id,),
        )
    with pytest.raises(CaptureUnavailable):
        capture(processing, run, access=access)


def test_folder_read_grant_controls_retained_generation_access(processing):
    run = seal(processing)
    reader = AuthService().bootstrap_admin(
        email=f"capture-reader-{uuid4()}@example.com", password="minimum8", household_name="Reader"
    )
    sql(
        "INSERT INTO household_memberships (household_id,user_id,role) VALUES (%s,%s,'viewer')",
        (processing.access.household_id, reader.user_id),
    )
    folder_id = sql(
        "INSERT INTO folders (name,household_id,owner_user_id,acl_mode,folder_kind) "
        "VALUES ('Capture private',%s,%s,'custom','manual') RETURNING id",
        (processing.access.household_id, processing.access.user_id),
    )[0]["id"]
    sql(
        "UPDATE documents SET primary_folder_id=%s WHERE id=%s", (folder_id, processing.document_id)
    )
    access = DocumentAccessContext(processing.access.household_id, reader.user_id, "owner")
    with pytest.raises(CaptureUnavailable):
        capture(processing, run, access=access)
    sql(
        "INSERT INTO folder_acl (folder_id,principal_type,principal_id,permission) "
        "VALUES (%s,'user',%s,'read')",
        (folder_id, reader.user_id),
    )
    assert capture(processing, run, access=access).run_status == "sealed"
    sql(
        "DELETE FROM folder_acl WHERE folder_id=%s AND principal_id=%s", (folder_id, reader.user_id)
    )
    with pytest.raises(CaptureUnavailable):
        capture(processing, run, access=access)
