from copy import deepcopy

import pytest
from pydantic import ValidationError

from lib.document_parsing.page_understanding.model import PageUnderstanding
from tests.fixtures.page_understanding_sources import invoice_page, locator, paragraph


@pytest.mark.parametrize(
    "defect",
    [
        "foreign_element",
        "foreign_cell",
        "negative_span",
        "overrun",
        "wrong_occurrence",
        "wrong_row",
        "value_changed",
        "duplicated_physical_key",
        "invented_row_label",
        "bool_index",
    ],
)
def test_claim_binding_rejects_cross_member_or_unstable_source_identity(defect):
    page = invoice_page()
    claim = page["extraction"]["claims"][2]
    if defect == "foreign_element":
        claim["primary_source"]["element_index"] = 399
    elif defect == "foreign_cell":
        claim["primary_source"]["cell_column"] = 99
    elif defect == "negative_span":
        claim["primary_source"]["text_start"] = -1
    elif defect == "overrun":
        claim["primary_source"]["text_end"] = 99999
    elif defect == "wrong_occurrence":
        claim["primary_source"]["text_start"] = 1
    elif defect == "wrong_row":
        claim["physical_row"]["row"] = 2  # Same printed value still belongs to another row.
    elif defect == "value_changed":
        claim["raw_value"] = "USD 99.00"
    elif defect == "duplicated_physical_key":
        page["extraction"]["claims"][4]["physical_row"]["row"] = 1
        page["extraction"]["claims"][4]["primary_source"]["cell_row"] = 1
    elif defect == "invented_row_label":
        claim["physical_row"] = {"kind": "row_label", "id": "row-1"}
    else:
        claim["primary_source"]["element_index"] = True
    with pytest.raises(ValidationError):
        PageUnderstanding.model_validate(page)


@pytest.mark.parametrize(
    "defect", ["inverted_box", "future_parent", "overlapping_cells", "outside_grid"]
)
def test_structure_rejects_invalid_geometry_hierarchy_and_grid(defect):
    page = invoice_page()
    if defect == "inverted_box":
        page["elements"][0]["bbox"]["left"] = 999
    elif defect == "future_parent":
        page["elements"][0]["parent_index"] = 2
    elif defect == "overlapping_cells":
        page["elements"][1]["table"]["cells"].append(
            deepcopy(page["elements"][1]["table"]["cells"][0])
        )
    else:
        page["elements"][1]["table"]["cells"][0]["column_span"] = 3
    with pytest.raises(ValidationError):
        PageUnderstanding.model_validate(page)


def test_sparse_table_keeps_partial_evidence_without_inventing_empty_cells():
    page = invoice_page()
    # Remove one header cell, preserving every captured value and line.
    page["elements"][1]["table"]["cells"].pop(1)
    with pytest.raises(ValidationError, match="Sparse"):
        PageUnderstanding.model_validate(page)
    page["state"] = "partial"
    page["diagnostics"] = ["content_omitted"]
    page["extraction"]["disposition"] = "partial"
    page["extraction"]["reasons"] = ["content_omitted"]
    parsed = PageUnderstanding.model_validate(page)
    assert len(parsed.elements[1].table.cells) == 5


def test_empty_and_merged_cells_are_retained_but_multiline_value_cannot_be_two_rows():
    page = invoice_page()
    table = page["elements"][1]["table"]
    # One printed amount spans both equal-description rows: it is one ambiguous value.
    table["cells"][3]["row_span"] = 2
    table["cells"].pop(5)
    with pytest.raises(ValidationError, match="merged multi-row"):
        PageUnderstanding.model_validate(page)


@pytest.mark.parametrize("defect", ["outside_hierarchy", "nested_rows"])
def test_structural_row_requires_real_ancestry_and_keeps_identical_distinct_containers(defect):
    page = invoice_page()
    page["elements"] = [page["elements"][0]]
    for _ in (1, 2):
        container = len(page["elements"])
        page["elements"].extend(
            [
                paragraph("Recorded line", kind="list_item"),
                paragraph("Service", parent=container),
                paragraph("USD 12.3400", parent=container),
            ]
        )
    family = page["extraction"]["families"][0]
    family["excluded_rows"] = []
    for position, container in enumerate((1, 4)):
        physical = {"kind": "structural_row", "container_index": container}
        family["rows"][position]["physical_row"] = deepcopy(physical)
        for offset in (0, 1):
            claim = page["extraction"]["claims"][1 + position * 2 + offset]
            claim["physical_row"] = deepcopy(physical)
            claim["primary_source"].update(
                {"element_index": container + 1 + offset, "cell_row": None, "cell_column": None}
            )
    parsed = PageUnderstanding.model_validate(page)
    assert parsed.extraction.claims[2].physical_row != parsed.extraction.claims[4].physical_row
    if defect == "outside_hierarchy":
        page["elements"][3]["parent_index"] = None
    else:
        page["elements"][4]["parent_index"] = 1
    with pytest.raises(ValidationError, match="hierarchy|cannot overlap"):
        PageUnderstanding.model_validate(page)


def test_empty_and_merged_header_cells_preserve_grid_and_printed_continuation_proposal():
    page = invoice_page()
    table = page["elements"][1]["table"]
    table["cells"][0]["column_span"] = 2
    table["cells"].pop(1)
    table["continuation_key"] = "Continued invoice lines"
    parsed = PageUnderstanding.model_validate(page)
    assert parsed.elements[1].table.cells[0].column_span == 2
    assert parsed.elements[1].table.continuation_key == "Continued invoice lines"
    page = invoice_page()
    page["elements"][1]["table"]["cells"][0]["text"] = ""
    assert PageUnderstanding.model_validate(page).elements[1].table.cells[0].text == ""


@pytest.mark.parametrize("placement", ["paragraph", "same_cell", "different_columns"])
def test_repeated_scalar_key_keeps_distinct_full_source_occurrences(placement):
    page = invoice_page()
    original = page["extraction"]["claims"][0]
    repeated = deepcopy(original)
    if placement == "paragraph":
        page["elements"][0]["text"] = "Invoice 000123 000123"
        repeated["primary_source"] = locator(0, "000123", start=15)
    else:
        cells = page["elements"][1]["table"]["cells"]
        cells[0]["text"] = "000123 000123" if placement == "same_cell" else "000123"
        original["primary_source"] = locator(1, "000123", row=0, column=0)
        if placement == "same_cell":
            repeated["primary_source"] = locator(1, "000123", row=0, column=0, start=7)
        else:
            cells[1]["text"] = "000123"
            repeated["primary_source"] = locator(1, "000123", row=0, column=1)
    page["extraction"]["claims"].append(repeated)
    field = next(
        f
        for f in page["extraction"]["families"][0]["fields"]
        if f["canonical_key"] == "invoice.invoice_number"
    )
    field["claim_indices"].append(5)
    parsed = PageUnderstanding.model_validate(page)
    assert parsed.extraction.claims[0].typed_value == parsed.extraction.claims[5].typed_value
    assert parsed.extraction.claims[0].primary_source != parsed.extraction.claims[5].primary_source
    repeated["primary_source"] = deepcopy(original["primary_source"])
    with pytest.raises(ValidationError, match="physical field cannot emit two claims"):
        PageUnderstanding.model_validate(page)


def test_line_key_identity_stays_one_per_physical_row_even_with_distinct_occurrences():
    page = invoice_page()
    page["elements"][1]["table"]["cells"][3]["text"] = "USD 12.3400 USD 12.3400"
    duplicate = deepcopy(page["extraction"]["claims"][2])
    duplicate["primary_source"] = locator(1, "USD 12.3400", row=1, column=1, start=12)
    page["extraction"]["claims"].append(duplicate)
    with pytest.raises(ValidationError, match="physical field cannot emit two claims"):
        PageUnderstanding.model_validate(page)
