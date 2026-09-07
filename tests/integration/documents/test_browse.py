from datetime import datetime
from uuid import uuid4

import pytest
from psycopg.errors import NotNullViolation
from psycopg.types.json import Jsonb

from lib.documents import list_repository
from tests.integration.documents.browse_support import (
    browse_rows,
    create_identity,
    login,
    seed_paged_documents,
)


@pytest.mark.parametrize(
    "sort,key,descending",
    [
        ("uploaded_desc", "created", True),
        ("uploaded_asc", "created", False),
        ("document_date_desc", "date", True),
        ("document_date_asc", "date", False),
        ("title_asc", "title", False),
        ("title_desc", "title", True),
    ],
)
def test_all_documents_are_browsable_with_deterministic_ties_and_null_dates(
    browse_corpus,
    sort,
    key,
    descending,
):
    documents = seed_paged_documents(browse_corpus)
    known = [row for row in documents if row[key] is not None]
    unknown = [row for row in documents if row[key] is None]
    expected = sorted(known, key=lambda row: (row[key], row["id"]), reverse=descending)
    expected += sorted(unknown, key=lambda row: row["id"], reverse=descending)
    seen = []
    for offset in range(0, len(documents), 50):
        page = browse_corpus.list(sort=sort, offset=offset, limit=50)
        assert page["total"] == page["corpusTotal"] == page["counts"]["all"] == 207
        assert (page["offset"], page["limit"]) == (offset, 50)
        assert datetime.fromisoformat(page["observedAt"].replace("Z", "+00:00")).tzinfo
        seen.extend(row["id"] for row in page["items"])
    assert seen == [str(row["id"]) for row in expected]
    assert len(seen) == len(set(seen)) == 207
    beyond = browse_corpus.list(offset=250)
    assert beyond["items"] == [] and beyond["total"] == 207 and beyond["offset"] == 250
    # Browsing is read-only: even original hashes remain unchanged.
    stored = browse_rows(
        "SELECT id,original_sha256 FROM documents WHERE household_id=%s",
        (browse_corpus.identity.household_id,),
    )
    assert {row["id"]: row["original_sha256"] for row in stored} == {
        row["id"]: row["hash"] for row in documents
    }
    # Dates can be unknown; title/received timestamp are required by both the
    # document schema and response DTO. Do not weaken those constraints to seed
    # impossible null-sort records.
    if sort == "title_desc":
        with pytest.raises(NotNullViolation):
            browse_rows("UPDATE documents SET title=NULL WHERE id=%s", (documents[0]["id"],))
    if sort == "uploaded_desc":
        with pytest.raises(NotNullViolation):
            browse_rows("UPDATE documents SET created_at=NULL WHERE id=%s", (documents[0]["id"],))


def test_every_inbox_state_uses_the_same_complete_count_and_membership(browse_corpus):
    names = [
        "pending",
        "model",
        "human",
        "unknown-confidence",
        "semantic",
        "reviewed-other-field",
        "filed",
        "smart-member",
        "extracted",
        "indexed",
    ]
    docs = {name: browse_corpus.document(name) for name in names}
    for name in ("model", "human", "unknown-confidence"):
        browse_corpus.model_classification(
            docs[name],
            confidence=None if name == "unknown-confidence" else 0.4,
        )
    browse_rows(
        """INSERT INTO review_events (document_id,field_path,action,new_value_json,actor_label)
        VALUES (%s,'classification.document_family','reclassify_document',%s,%s)""",
        (docs["human"], Jsonb({"family": "generic"}), str(browse_corpus.identity.user_id)),
    )
    browse_rows(
        "UPDATE documents SET review_status='user_corrected' WHERE id=%s",
        (docs["reviewed-other-field"],),
    )
    browse_rows("UPDATE documents SET review_status='needs_review' WHERE id=%s", (docs["model"],))
    browse_rows(
        "INSERT INTO review_tasks (document_id,task_type,status) VALUES (%s,'quality','open')",
        (docs["pending"],),
    )
    semantic = {
        "phase8_5": {
            "semantic_classification": {
                "version": "phase8_5_semantic_family_reconciliation_v1",
                "family": "generic",
                "should_update": True,
                "confidence": 0.8,
            }
        }
    }
    browse_rows(
        "UPDATE documents SET metadata_json=%s,family_confidence=0.8 WHERE id=%s",
        (Jsonb(semantic), docs["semantic"]),
    )
    for name, kind in (("filed", "manual"), ("smart-member", "smart")):
        folder = browse_corpus.folder(kind=kind)
        browse_rows(
            "INSERT INTO document_folder_memberships (document_id,folder_id) VALUES (%s,%s)",
            (docs[name], folder),
        )
    browse_rows(
        """INSERT INTO document_extractions
        (document_id,schema_name,schema_version,status,source_engine,normalized_json)
        VALUES (%s,'invoice','v1','completed','system',%s)""",
        (docs["extracted"], Jsonb({"total_amount": 14})),
    )
    browse_rows(
        """INSERT INTO document_extractions
        (document_id,schema_name,schema_version,status,source_engine,normalized_json,is_current)
        VALUES (%s,'invoice','v1','superseded','system',%s,false)""",
        (docs["pending"], Jsonb({"total_amount": 999})),
    )
    browse_rows(
        "INSERT INTO document_chunks (document_id,chunk_index,text_content,bm25_text) "
        "VALUES (%s,1,'Indexed original text','Indexed original text')",
        (docs["indexed"],),
    )
    browse_rows(
        "INSERT INTO document_assets (document_id,asset_role,uri) "
        "VALUES (%s,'thumbnail','filesystem://fixture/thumbnail.png')",
        (docs["indexed"],),
    )
    browse_rows(
        "UPDATE documents SET duplicate_of_document_id=%s WHERE id=%s",
        (docs["extracted"], docs["indexed"]),
    )
    expected = {
        "all": ("all", set(names)),
        "needs_review": ("needsReview", {"pending", "model"}),
        "unfiled": ("unfiled", set(names) - {"filed"}),
        "awaiting_classification": (
            "awaitingClassification",
            set(names)
            - {
                "model",
                "human",
                "unknown-confidence",
                "semantic",
            },
        ),
        "duplicates": ("duplicates", {"extracted", "indexed"}),
        "low_confidence": ("lowConfidence", {"model"}),
        "has_extraction": ("hasExtraction", {"extracted"}),
        "text_searchable": ("textSearchable", {"indexed"}),
    }
    baseline_counts = browse_corpus.list()["counts"]
    assert baseline_counts["previewReady"] == baseline_counts["humanReviewed"] == 1
    for state, (count_name, matched_names) in expected.items():
        page = browse_corpus.list(inboxState=state, limit=200)
        assert page["counts"] == baseline_counts
        assert page["total"] == baseline_counts[count_name] == len(matched_names)
        assert {row["id"] for row in page["items"]} == {str(docs[name]) for name in matched_names}
    assert all(row["amountTotal"] is None for row in browse_corpus.list()["items"])


def test_query_folder_smart_query_and_state_counts_compose_without_changing_corpus_total(
    browse_corpus,
):
    selected = browse_corpus.document("Tax receipt")
    browse_corpus.document("Tax pending")
    browse_corpus.document("Unrelated")
    folder = browse_corpus.folder()
    browse_rows(
        "INSERT INTO document_folder_memberships (document_id,folder_id) VALUES (%s,%s)",
        (selected, folder),
    )
    browse_rows(
        "UPDATE documents SET document_family='receipt',review_status='needs_review' WHERE id=%s",
        (selected,),
    )
    smart = browse_corpus.folder(kind="smart")
    browse_rows(
        "UPDATE folders SET saved_query_json=%s WHERE id=%s",
        (Jsonb({"document_family": ["receipt"], "review_status": ["needs_review"]}), smart),
    )
    for folder_id in (folder, smart):
        result = browse_corpus.list(q="Tax", folderId=str(folder_id), inboxState="needs_review")
        assert result["corpusTotal"] == 3
        assert result["total"] == result["counts"]["all"] == 1
        assert [row["id"] for row in result["items"]] == [str(selected)]
    conflict = browse_corpus.list(folderId=str(smart), family="invoice")
    assert conflict["total"] == conflict["counts"]["all"] == 0 and conflict["corpusTotal"] == 3
    missing = browse_corpus.list(folderId=str(uuid4()))
    assert missing["items"] == [] and missing["total"] == 0 and missing["corpusTotal"] == 3


def test_private_and_other_household_duplicate_counterparts_do_not_affect_visible_counts(
    browse_corpus,
):
    member = create_identity("member")
    browse_rows(
        "INSERT INTO household_memberships (household_id,user_id,role) VALUES (%s,%s,'member')",
        (browse_corpus.identity.household_id, member.user_id),
    )
    visible = browse_corpus.document("Shared document")
    shared_folder = browse_corpus.folder(acl_mode="household")
    browse_rows(
        "UPDATE documents SET primary_folder_id=%s,acl_mode='household' WHERE id=%s",
        (shared_folder, visible),
    )
    private = browse_corpus.document("Private duplicate")
    private_folder = browse_corpus.folder(acl_mode="private")
    browse_rows("UPDATE documents SET primary_folder_id=%s WHERE id=%s", (private_folder, private))
    elsewhere = browse_corpus.document("Other household duplicate", owner=member)
    browse_rows(
        "UPDATE documents SET duplicate_of_document_id=%s WHERE id=ANY(%s::uuid[])",
        (visible, [private, elsewhere]),
    )
    browse_rows(
        "INSERT INTO document_relationships (from_document_id,to_document_id,relationship_type) "
        "VALUES (%s,%s,'duplicate_of')",
        (visible, private),
    )
    browse_corpus.client = login(member, browse_corpus.identity.household_id)
    result = browse_corpus.list(inboxState="duplicates")
    assert result["corpusTotal"] == result["counts"]["all"] == 1
    assert result["total"] == result["counts"]["duplicates"] == 0
    assert result["items"] == []
    peer = browse_corpus.document("Shared duplicate")
    browse_rows(
        "UPDATE documents SET primary_folder_id=%s,acl_mode='household' WHERE id=%s",
        (shared_folder, peer),
    )
    browse_rows("UPDATE documents SET duplicate_of_document_id=%s WHERE id=%s", (visible, peer))
    result = browse_corpus.list(inboxState="duplicates")
    assert result["total"] == 2
    assert {row["id"] for row in result["items"]} == {str(visible), str(peer)}
    browse_rows("UPDATE documents SET deleted_at=now() WHERE id=%s", (peer,))
    result = browse_corpus.list(inboxState="duplicates")
    assert result["total"] == 0 and result["corpusTotal"] == 1


def test_page_and_counts_share_a_snapshot_when_an_upload_commits_between_queries(
    browse_corpus,
    monkeypatch,
):
    original = browse_corpus.document("Before response")
    count_query = list_repository._document_list_count_sql
    inserted = False

    def concurrent_upload(where_sql):
        nonlocal inserted
        if not inserted:
            inserted = True
            browse_corpus.document("Concurrent upload")
        return count_query(where_sql)

    monkeypatch.setattr(list_repository, "_document_list_count_sql", concurrent_upload)
    response = browse_corpus.list()
    assert response["total"] == response["corpusTotal"] == response["counts"]["all"] == 1
    assert [row["id"] for row in response["items"]] == [str(original)]
    refreshed = browse_corpus.list()
    assert refreshed["total"] == refreshed["corpusTotal"] == len(refreshed["items"]) == 2
