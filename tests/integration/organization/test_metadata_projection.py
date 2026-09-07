import pytest

from lib.db.connection import db_connection
from lib.fact_authority import metadata_projection

from .support import (
    assert_fact_basis_preserved,
    collections,
    established_facts,
    file_document,
    impact,
)


def test_filing_refreshes_metadata_atomically_without_touching_103_facts_or_manual_date(
    organization_document,
):
    doc = organization_document
    established_facts(doc)
    folder, tag = collections(doc)
    before = impact(doc)
    result = file_document(
        doc,
        title="Filed source",
        filingNotes="Human filing context",
        folderIds=[folder.id],
        primaryFolderId=folder.id,
        tags=[tag.name],
    )
    after = impact(doc)
    assert_fact_basis_preserved(before, after)
    assert result.title == "Filed source" and result.document_date.isoformat() == "2020-03-04"
    assert result.folder_ids == [folder.id] and result.primary_folder_id == folder.id
    assert result.tags == [tag.name]
    lexical = after["fields"]["chunks"][0]["bm25_text"]
    for value in (
        "Filed source",
        "Human filing context",
        "/Claims",
        "evidence-tag",
        "Exact accepted field",
        "Exact accepted line",
    ):
        assert value in lexical
    old, new = before["fields"]["projection"], after["fields"]["projection"]
    assert new["projection_revision"] == old["projection_revision"] + 1
    assert new["indexed_metadata_sha256"] != old["indexed_metadata_sha256"]
    assert len(after["fields"]["jobs"]) == len(before["fields"]["jobs"]) + 1
    assert len(after["filing"]["audits"]) == 1
    assert after["filing"]["audits"][0]["payload_json"]["after"]["tags"] == [tag.name]


@pytest.mark.parametrize("state", ["absent", "unestablished"])
def test_filing_does_not_establish_a_legacy_fact_projection(organization_document, state):
    doc = organization_document
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET document_date='2019-12-31' WHERE id=%s", (doc.document_id,)
        )
        if state == "unestablished":
            cur.execute(
                "INSERT INTO document_fact_projection_state(document_id,legacy_metadata_json) "
                "VALUES(%s,'{}')",
                (doc.document_id,),
            )
    before = impact(doc)
    result = file_document(doc, filingNotes="Only filing metadata changed")
    after = impact(doc)
    assert_fact_basis_preserved(before, after)
    assert result.document_date.isoformat() == "2019-12-31"
    assert "Only filing metadata changed" in after["fields"]["chunks"][0]["bm25_text"]
    assert len(after["fields"]["jobs"]) == 1


@pytest.mark.parametrize("failure", ["metadata_fingerprint", "enqueue_embed_document_job"])
def test_metadata_or_enqueue_failure_rolls_back_document_audit_projection_and_jobs(
    organization_document, monkeypatch, failure
):
    doc = organization_document
    established_facts(doc)
    before = impact(doc)
    original = getattr(metadata_projection, failure)

    def fail_after_real_step(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Injected after real filing persistence")

    monkeypatch.setattr(metadata_projection, failure, fail_after_real_step)
    with pytest.raises(RuntimeError, match="Injected after real filing persistence"):
        file_document(doc, title="Must roll back", filingNotes="Must roll back too")
    assert impact(doc) == before


def test_repeated_unchanged_filing_does_not_duplicate_audit_or_enqueue(organization_document):
    doc = organization_document
    folder, tag = collections(doc)
    changes = {"folderIds": [folder.id], "primaryFolderId": folder.id, "tags": [tag.name]}
    file_document(doc, **changes)
    before = impact(doc)
    file_document(doc, **changes)
    after = impact(doc)
    assert after["filing"]["audits"] == before["filing"]["audits"]
    assert after["fields"]["jobs"] == before["fields"]["jobs"]
    assert after["fields"]["projection"] == before["fields"]["projection"]
