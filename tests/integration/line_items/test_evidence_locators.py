import pytest

from lib.db.connection import db_connection
from lib.review.line_items.errors import LineEvidenceError

from .support import candidate, create_request, decide, source


@pytest.mark.parametrize(
    "case",
    [
        "page_overrun",
        "page_whitespace",
        "element_missing",
        "element_overrun",
        "table_row_overrun",
        "table_column_overrun",
        "table_unknown_count",
        "raw_span",
        "chunk_span",
        "unknown_span",
        "source_text_missing",
        "source_text_ambiguous",
    ],
)
def test_recorded_locator_must_exist_and_be_addressable(line_document, case):
    doc = line_document
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE document_pages SET text_content='Known source text. Repeat Repeat.   ' "
            "WHERE document_id=%s RETURNING id",
            (doc.document_id,),
        )
        page_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO document_elements(document_id,page_id,text_content) "
            "VALUES(%s,%s,'Clinical service') RETURNING id",
            (doc.document_id, page_id),
        )
        element = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO document_tables(document_id,page_id,table_index,row_count,column_count) "
            "VALUES(%s,%s,1,%s,2) RETURNING id",
            (doc.document_id, page_id, None if case == "table_unknown_count" else 1),
        )
        table = cur.fetchone()["id"]
    ref = {"pageNumber": 1, "sourceEngine": "validator"}
    if case.startswith("table_"):
        ref.update(
            tableId=str(table),
            rowIndex=1 if case == "table_row_overrun" else 0,
            columnIndex=2 if case == "table_column_overrun" else 0,
        )
    elif case.startswith("element_"):
        if case != "element_missing":
            ref["elementId"] = str(element)
        ref["textSpan"] = {"basis": "element_text", "start": 0, "end": 999}
    elif case == "page_overrun":
        ref["textSpan"] = {"basis": "page_text", "start": 0, "end": 9999}
    elif case == "page_whitespace":
        ref["textSpan"] = {"basis": "page_text", "start": 33, "end": 34}
    elif case in {"raw_span", "chunk_span", "unknown_span"}:
        ref["textSpan"] = {
            "basis": {
                "raw_span": "raw_model_output",
                "chunk_span": "chunk_text",
                "unknown_span": None,
            }[case],
            "start": 0,
            "end": 5,
        }
    else:
        ref["sourceText"] = (
            "Repeat" if case == "source_text_ambiguous" else "Invented model transcription"
        )
    item = candidate(doc, evidence=[ref])
    assert source(doc, item)["publicationEligibility"]["reason"] == "evidence_incomplete"
    with pytest.raises(LineEvidenceError):
        decide(doc, create_request(doc, item))


@pytest.mark.parametrize(
    "locator", ["page_span", "element_span", "table_cell", "box_with_assistive_raw_span"]
)
def test_concrete_consistent_source_locators_remain_publishable(line_document, locator):
    doc = line_document
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE document_pages SET text_content='Known source text' "
            "WHERE document_id=%s RETURNING id",
            (doc.document_id,),
        )
        page = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO document_elements(document_id,page_id,text_content) "
            "VALUES(%s,%s,'Clinical service') RETURNING id",
            (doc.document_id, page),
        )
        element = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO document_tables(document_id,page_id,table_index,row_count,column_count) "
            "VALUES(%s,%s,1,1,2) RETURNING id",
            (doc.document_id, page),
        )
        table = cur.fetchone()["id"]
    ref = {"pageNumber": 1, "sourceEngine": "validator"}
    if locator == "page_span":
        ref["textSpan"] = {"basis": "page_text", "start": 0, "end": 5}
    elif locator == "element_span":
        ref.update(elementId=str(element), textSpan={"basis": "element_text", "start": 0, "end": 8})
    elif locator == "table_cell":
        ref.update(tableId=str(table), rowIndex=0, columnIndex=1)
    else:
        ref.update(
            bbox=[0, 0, 0.5, 0.5], textSpan={"basis": "raw_model_output", "start": 0, "end": 5}
        )
    item = candidate(doc, evidence=[ref])
    assert source(doc, item)["publicationEligibility"]["eligible"]
    assert decide(doc, create_request(doc, item)).canonical_item.selected
