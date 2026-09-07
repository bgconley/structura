from uuid import UUID

from tests.integration.documents.browse_support import browse_rows


def test_accepted_upload_returns_its_exact_document_even_for_identical_titles_and_hashes(
    browse_corpus,
):
    client = browse_corpus.client
    content = b"%PDF-1.7\n% Exact upload identity fixture\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    returned_ids = []
    for _ in range(2):
        accepted = client.post(
            "/api/v1/documents",
            headers={"X-CSRF-Token": client.cookies["structura_csrf"]},
            data={"source": "web_upload", "suppliedTitle": "Identical uploaded title"},
            files={"file": ("same.pdf", content, "application/pdf")},
        )
        assert accepted.status_code == 202, accepted.text
        payload = accepted.json()
        document_id = UUID(payload["documentId"])
        returned_ids.append(document_id)
        job = browse_rows("SELECT document_id FROM pipeline_jobs WHERE id=%s", (payload["jobId"],))[
            0
        ]
        assert job["document_id"] == document_id
        detail = client.get(f"/api/v1/documents/{document_id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == str(document_id)
        assert detail.json()["title"] == "Identical uploaded title"
        original = next(
            asset for asset in detail.json()["assets"] if asset["assetRole"] == "original"
        )
        assert client.get(original["assetUrl"]).content == content
    assert len(set(returned_ids)) == 2
