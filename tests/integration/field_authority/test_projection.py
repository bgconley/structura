from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from queue import Queue
from threading import Event

import pytest

from lib.db.connection import db_connection
from lib.fact_authority import projection_repository
from lib.fact_authority.projection_values import snapshot_digest

from .support import candidate, confirm, envelope, preconditions, reject, seed_chunk, snapshot


def typed_candidate(document_id, path, kind, value):
    item = candidate(document_id, str(value))
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE field_candidates SET field_path=%s,value_type=%s,
          text_value=%s,date_value=%s,numeric_value=%s,currency_code=%s WHERE id=%s RETURNING *""",
            (
                path,
                kind,
                value if kind == "string" else None,
                value if kind == "date" else None,
                value if kind in {"money", "number"} else None,
                "USD" if kind == "money" else None,
                item["id"],
            ),
        )
        return cur.fetchone()


@pytest.mark.parametrize(
    "path,kind,value",
    [
        ("invoice.seller.display_name", "string", "Owned merchant from accepted fact"),
        ("invoice.issue_date", "date", date(2025, 4, 15)),
        ("invoice.total_amount", "money", Decimal("123.45")),
    ],
)
def test_rejection_clears_last_owned_scalar_or_total_and_lexical_fact(
    promotion_document, path, kind, value
):
    document_id, access = promotion_document
    item = typed_candidate(document_id, path, kind, value)
    seed_chunk(document_id)
    confirm(document_id, access, item)
    before = snapshot(document_id)
    if kind == "string":
        assert before["document"]["counterparty_display"] == value
    elif kind == "date":
        assert before["document"]["document_date"] == value.isoformat()
    else:
        assert [(row["amount"], row["currency_code"]) for row in before["amounts"]] == [
            (float(value), "USD")
        ]
    reject(document_id, access, path, **preconditions(envelope(document_id, access), path))
    after = snapshot(document_id)
    assert after["document"]["counterparty_display"] is None
    assert after["document"]["document_date"] is None
    assert after["amounts"] is None
    assert path not in after["chunks"][0]["bm25_text"]
    assert after["canonical"][0]["review_status"] == "rejected"
    assert after["projection"]["accepted_fact_revision"] == 2
    assert after["projection"]["projection_revision"] == 2


@pytest.mark.parametrize("manual_clear", [False, True])
def test_unestablished_legacy_date_and_explicit_manual_null_survive_projection(
    promotion_document, manual_clear
):
    document_id, access = promotion_document
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET document_date='2020-01-02',"
            "counterparty_display='Legacy label' WHERE id=%s",
            (document_id,),
        )
        if manual_clear:
            cur.execute(
                """INSERT INTO document_metadata_decisions
              (document_id,property,value_json,origin,actor_user_id,decided_at)
              VALUES (%s,'document_date','null'::jsonb,'live_review',%s,clock_timestamp())""",
                (document_id, access.user_id),
            )
    item = typed_candidate(document_id, "invoice.issue_date", "date", date(2025, 4, 15))
    confirm(document_id, access, item)
    current = snapshot(document_id)
    assert current["document"]["document_date"] == (None if manual_clear else "2020-01-02")
    assert current["document"]["counterparty_display"] == "Legacy label"
    assert current["projection"]["rollup_json"]["documentDate"]["ownership"] == (
        "manual" if manual_clear else "unestablished"
    )
    reject(
        document_id,
        access,
        item["field_path"],
        **preconditions(envelope(document_id, access), item["field_path"]),
    )
    assert snapshot(document_id)["document"]["document_date"] == (
        None if manual_clear else "2020-01-02"
    )


def test_only_owned_total_is_replaced_and_removed(promotion_document):
    document_id, access = promotion_document
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO document_amounts
              (document_id,amount_role,amount,currency_code,metadata_json)
          VALUES (%s,'total',7,'EUR','{"source":"manual_import"}') RETURNING id""",
            (document_id,),
        )
        manual_id = str(cur.fetchone()["id"])
        cur.execute(
            """INSERT INTO document_amounts
              (document_id,amount_role,amount,currency_code,metadata_json)
          VALUES (%s,'total',999,'USD','{"phase":"phase4","source":"canonical_fields"}')""",
            (document_id,),
        )
    item = typed_candidate(document_id, "invoice.total_amount", "money", Decimal("50.25"))
    confirm(document_id, access, item)
    amounts = snapshot(document_id)["amounts"]
    assert len(amounts) == 2
    assert any(
        row["id"] == manual_id and row["amount"] == 7 and row["currency_code"] == "EUR"
        for row in amounts
    )
    assert any(row["amount"] == 50.25 and row["currency_code"] == "USD" for row in amounts)
    reject(
        document_id,
        access,
        item["field_path"],
        **preconditions(envelope(document_id, access), item["field_path"]),
    )
    amounts = snapshot(document_id)["amounts"]
    assert len(amounts) == 1 and amounts[0]["id"] == manual_id


def test_indexed_metadata_hash_uses_exact_lexical_statement_snapshot(
    promotion_document, monkeypatch
):
    document_id, access = promotion_document
    seed_chunk(document_id)
    item = candidate(document_id, "Accepted field with metadata")
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tags(name,household_id) "
            "VALUES ('Before concurrent rename',%s) RETURNING id",
            (access.household_id,),
        )
        tag_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO document_tags(document_id,tag_id) VALUES (%s,%s)", (document_id, tag_id)
        )
    observed, release = Queue(), Event()
    original = projection_repository.snapshot_digest

    def pause_fingerprint(value):
        observed.put(value)
        if not release.wait(timeout=10):
            raise AssertionError("Test did not release fingerprint persistence")
        return original(value)

    monkeypatch.setattr(projection_repository, "snapshot_digest", pause_fingerprint)
    with ThreadPoolExecutor(max_workers=1) as pool:
        reviewing = pool.submit(confirm, document_id, access, item)
        metadata = observed.get(timeout=5)
        try:
            # Label writers are a later slice. This direct SQL proves that the
            # stored fingerprint uses the already-indexed statement snapshot.
            with db_connection() as conn, conn.cursor() as cur:
                cur.execute("UPDATE tags SET name='After concurrent rename' WHERE id=%s", (tag_id,))
        finally:
            release.set()
        result = reviewing.result(timeout=5)
    assert metadata["metadata"]["tags"][0]["name"] == "Before concurrent rename"
    assert result.projection.indexed_metadata_sha256 == snapshot_digest(metadata)
    lexical = snapshot(document_id)["chunks"][0]["bm25_text"]
    assert "Before concurrent rename" in lexical and "After concurrent rename" not in lexical


@pytest.mark.parametrize("kind", ["money", "number"])
def test_confirmation_response_and_audit_preserve_large_four_place_decimal(
    promotion_document, kind
):
    document_id, access = promotion_document
    value = Decimal("99999999999999.9999")
    item = typed_candidate(document_id, "invoice.exact_quantity", kind, value)
    result = confirm(document_id, access, item)
    expected = {"amount": str(value), "currency": "USD"} if kind == "money" else str(value)
    assert result.canonical.value == expected
    assert envelope(document_id, access).items[0].value == expected
    current = snapshot(document_id)
    assert current["history"][0]["new_value_json"]["value"] == expected
    assert current["events"][0]["new_value_json"]["value"] == expected
