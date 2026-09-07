from concurrent.futures import ThreadPoolExecutor

import pytest

from lib.automation import service
from lib.automation.errors import AutomationError
from lib.contracts import FilingRuleApplyRequest, FilingRuleWrite
from lib.db.connection import db_connection
from lib.fact_authority import metadata_projection

from ..test_completion_authorization import observe_lock_backend
from ..test_completion_session_security import wait_for_blocked
from .support import assert_fact_basis_preserved, collections, established_facts, impact


def rule_for(doc, folder, tag, *, suggested=False):
    return service.upsert_filing_rule(
        FilingRuleWrite(
            name="File generic sources",
            reviewRequired=suggested,
            conditions=[{"field": "document_family", "op": "eq", "value": "generic"}],
            actions=[
                {"type": "add_folder", "folder_id": str(folder.id)},
                {"type": "add_tag", "tag": tag.name},
            ],
        ),
        doc.principal,
    )


def apply(doc, rule):
    return service.apply_rule(
        rule_id=rule.id,
        payload=FilingRuleApplyRequest(documentId=doc.document_id),
        principal=doc.principal,
    )


@pytest.mark.parametrize("suggested", [False, True])
def test_rule_and_explicit_suggestion_share_atomic_metadata_without_replacing_facts(
    organization_document, suggested
):
    doc = organization_document
    established_facts(doc)
    folder, tag = collections(doc)
    rule = rule_for(doc, folder, tag, suggested=suggested)
    baseline = impact(doc)
    first = apply(doc, rule)
    if suggested:
        assert first.status == "suggested"
        before = impact(doc)
        result = service.accept_suggestion(run_id=first.run_id, principal=doc.principal)
        assert result.status == "accepted"
    else:
        before = baseline
        assert first.status == "applied"
    after = impact(doc)
    # A review task can change state on suggestion acceptance; accepted fact
    # rows, decisions, history, and their projection basis remain identical.
    before["fields"]["tasks"] = after["fields"]["tasks"]
    before["lines"]["tasks"] = after["lines"]["tasks"]
    assert_fact_basis_preserved(before, after)
    assert after["fields"]["document"]["document_date"] == "2020-03-04"
    assert len(after["fields"]["jobs"]) == len(before["fields"]["jobs"]) + 1
    assert tag.name in after["fields"]["chunks"][0]["bm25_text"]
    if suggested:
        with pytest.raises(AutomationError) as failure:
            service.accept_suggestion(run_id=first.run_id, principal=doc.principal)
        assert failure.value.status_code == 404
        assert impact(doc) == after
    else:
        assert apply(doc, rule).status == "applied"
        repeated = impact(doc)
        for key in ("audits", "folders", "tags"):
            assert repeated["filing"][key] == after["filing"][key]
        assert repeated["fields"]["jobs"] == after["fields"]["jobs"]
        assert repeated["fields"]["projection"] == after["fields"]["projection"]


@pytest.mark.parametrize("suggested", [False, True])
@pytest.mark.parametrize("failure", ["metadata_fingerprint", "enqueue_embed_document_job"])
def test_rule_and_suggestion_failures_roll_back_filing_audit_task_projection_and_jobs(
    organization_document, monkeypatch, suggested, failure
):
    doc = organization_document
    established_facts(doc)
    folder, tag = collections(doc)
    rule = rule_for(doc, folder, tag, suggested=suggested)
    run = apply(doc, rule) if suggested else None
    before = impact(doc)
    original = getattr(metadata_projection, failure)

    def fail_after_real_step(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Injected after real rule persistence")

    monkeypatch.setattr(metadata_projection, failure, fail_after_real_step)
    with pytest.raises(RuntimeError, match="Injected after real rule persistence"):
        if run:
            service.accept_suggestion(run_id=run.run_id, principal=doc.principal)
        else:
            apply(doc, rule)
    assert impact(doc) == before


def test_rule_evaluation_uses_document_context_after_document_lock_wait(
    organization_document, monkeypatch
):
    doc = organization_document
    folder, tag = collections(doc)
    rule = rule_for(doc, folder, tag)
    backends = observe_lock_backend(monkeypatch, service, "lock_writable_document")
    with ThreadPoolExecutor(max_workers=1) as pool, db_connection() as blocker:
        with blocker.cursor() as cur:
            cur.execute(
                "UPDATE documents SET document_family='invoice' WHERE id=%s", (doc.document_id,)
            )
            pending = pool.submit(apply, doc, rule)
            try:
                wait_for_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
            result = pending.result(timeout=5)
    assert result.status == "not_matched" and result.applied_actions == []
    after = impact(doc)
    assert after["filing"]["folders"] is None and after["filing"]["tags"] is None
    assert after["filing"]["audits"] is None and after["fields"]["jobs"] is None
    assert after["filing"]["rules"][0]["matched"] is False


def test_suggestion_cannot_switch_document_after_preliminary_identity_lookup(
    organization_document, monkeypatch
):
    doc = organization_document
    folder, tag = collections(doc)
    rule = rule_for(doc, folder, tag, suggested=True)
    run = apply(doc, rule)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO documents(title,ingestion_source,household_id,owner_user_id) "
            "VALUES('Other source','web_upload',%s,%s) RETURNING id",
            (doc.credential.household_id, doc.credential.user_id),
        )
        other_id = cur.fetchone()["id"]
    backends = observe_lock_backend(monkeypatch, service, "lock_writable_document")
    with ThreadPoolExecutor(max_workers=1) as pool, db_connection() as blocker:
        with blocker.cursor() as cur:
            cur.execute("SELECT id FROM documents WHERE id=%s FOR UPDATE", (doc.document_id,))
            pending = pool.submit(
                service.accept_suggestion, run_id=run.run_id, principal=doc.principal
            )
            try:
                wait_for_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
                with db_connection() as changed, changed.cursor() as other:
                    other.execute(
                        "UPDATE filing_rule_runs SET document_id=%s WHERE id=%s",
                        (other_id, run.run_id),
                    )
                before = impact(doc)
            finally:
                blocker.commit()
            with pytest.raises(AutomationError) as failure:
                pending.result(timeout=5)
    assert (
        failure.value.status_code == 404 and failure.value.detail == "Filing suggestion not found"
    )
    assert impact(doc) == before
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT (SELECT count(*) FROM document_folder_memberships "
            "WHERE document_id=%s) AS folders,"
            "(SELECT count(*) FROM document_tags WHERE document_id=%s) AS tags",
            (other_id, other_id),
        )
        assert cur.fetchone() == {"folders": 0, "tags": 0}


@pytest.mark.parametrize("mode", ["apply", "dry_run"])
def test_rule_evaluation_refreshes_target_grants_after_document_wait(
    organization_document, monkeypatch, mode
):
    from lib.contracts import FilingRuleDryRunRequest, TagWrite
    from lib.organization.manual_filing import create_tag

    from .test_document_authority import member_with_granted_folder

    doc, target, _ = member_with_granted_folder(organization_document)
    # Keep the document writable through ownership, independently from its target grant.
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET owner_user_id=%s,primary_folder_id=NULL WHERE id=%s",
            (doc.credential.user_id, doc.document_id),
        )
        cur.execute(
            "DELETE FROM document_folder_memberships WHERE document_id=%s", (doc.document_id,)
        )
    tag = create_tag(TagWrite(name="Rule evidence"), doc.principal)
    rule = rule_for(doc, target, tag, suggested=True)
    backends = observe_lock_backend(monkeypatch, service, "lock_writable_document")
    with ThreadPoolExecutor(max_workers=1) as pool, db_connection() as blocker:
        with blocker.cursor() as cur:
            cur.execute("SELECT id FROM documents WHERE id=%s FOR UPDATE", (doc.document_id,))
            if mode == "apply":
                pending = pool.submit(apply, doc, rule)
            else:
                pending = pool.submit(
                    service.dry_run_rule,
                    rule_id=rule.id,
                    payload=FilingRuleDryRunRequest(documentIds=[doc.document_id]),
                    principal=doc.principal,
                )
            try:
                wait_for_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
                with db_connection() as revoked, revoked.cursor() as other:
                    other.execute(
                        "UPDATE folder_acl SET permission='read' WHERE folder_id=%s", (target.id,)
                    )
            finally:
                blocker.commit()
            response = pending.result(timeout=5)
    evaluation = response if mode == "apply" else response.items[0]
    assert not any(action["type"] == "add_folder" for action in evaluation.proposed_actions)
    assert len(evaluation.blocked_actions) == 1
    assert evaluation.blocked_actions[0]["folder_id"] == str(target.id)
    state = impact(doc)
    assert not any(
        action["type"] == "add_folder"
        for action in state["filing"]["rules"][0]["proposed_actions_json"]
    )
    assert state["filing"]["folders"] is None
