"""Cross-member accounting checks; completeness here is a model inventory claim."""

from collections import Counter

from lib.document_parsing.page_understanding.classification import PageClassification
from lib.document_parsing.page_understanding.coverage import (
    FamilyCoverage,
    FieldCoverage,
    PageExtraction,
)
from lib.document_parsing.page_understanding.locators import (
    PhysicalRow,
    TableRow,
    row_key,
    validate_disjoint_rows,
    validate_quote,
    validate_row,
)
from lib.document_parsing.page_understanding.registry import family_rules
from lib.document_parsing.page_understanding.structure import UnderstandingElement
from lib.document_parsing.page_understanding.taxonomy import TYPED_FAMILIES


def _fields(
    elements: tuple[UnderstandingElement, ...],
    extraction: PageExtraction,
    family: str,
    fields: tuple[FieldCoverage, ...],
    row: PhysicalRow | None,
) -> tuple[list[int], bool]:
    rules = family_rules(family, "field" if row is None else "line")
    if len(fields) != len(rules) or {f.canonical_key for f in fields} != {r.key for r in rules}:
        raise ValueError("Every frozen field obligation needs one explicit page-local status.")
    rule_map = {r.key: r for r in rules}
    indices = []
    incomplete = False
    for field in fields:
        rule = rule_map[field.canonical_key]
        if field.state == "not_applicable" and rule.obligation == "required":
            raise ValueError("Required field absence cannot be called not applicable.")
        incomplete |= field.state in {"unreadable", "ambiguous", "omitted"}
        for evidence in field.evidence:
            validate_quote(elements, evidence)
        for index in field.claim_indices:
            if index >= len(extraction.claims):
                raise ValueError("Coverage references an unavailable claim.")
            claim = extraction.claims[index]
            same_row = (claim.physical_row is None and row is None) or (
                claim.physical_row is not None
                and row is not None
                and row_key(claim.physical_row) == row_key(row)
            )
            if claim.canonical_key != field.canonical_key or not same_row:
                raise ValueError(
                    "Coverage claim does not belong to its exact field and physical row."
                )
            indices.append(index)
    return indices, incomplete


def _rows(
    elements: tuple[UnderstandingElement, ...],
    extraction: PageExtraction,
    family: FamilyCoverage,
) -> tuple[list[int], bool]:
    indices = []
    incomplete = family.row_inventory in {"partial", "unreadable"}
    if not family.rows and not family.excluded_rows and family.row_inventory == "complete":
        raise ValueError("Empty line inventory requires explicit no-rows page coverage.")
    identities = []
    table_rows: dict[int, set[int]] = {}
    for row in family.rows:
        validate_row(elements, row.physical_row)
        identities.append(row_key(row.physical_row))
        refs, gaps = _fields(elements, extraction, family.family, row.fields, row.physical_row)
        if not refs:
            raise ValueError(
                "An extracted row needs a proposed value; otherwise exclude it explicitly."
            )
        indices.extend(refs)
        incomplete |= gaps
    for excluded in family.excluded_rows:
        validate_row(elements, excluded.physical_row)
        identities.append(row_key(excluded.physical_row))
        incomplete |= excluded.reason in {"unreadable", "omitted"}
    if len(set(identities)) != len(identities):
        raise ValueError("A physical row cannot be counted twice or both extracted and excluded.")
    for physical_row in (
        *[r.physical_row for r in family.rows],
        *[r.physical_row for r in family.excluded_rows],
    ):
        if isinstance(physical_row, TableRow):
            table_rows.setdefault(physical_row.element_index, set()).add(physical_row.row)
    if family.row_inventory == "complete":
        for index, rows in table_rows.items():
            table = elements[index].table
            if table is None or rows != set(range(table.row_count)):
                raise ValueError("Complete row inventory cannot skip rows in a referenced table.")
    if family.row_inventory == "no_rows_on_this_page" and (family.rows or incomplete):
        raise ValueError("No rows cannot conceal extracted or omitted lines.")
    return indices, incomplete


def _classification_coverage(
    extraction: PageExtraction, classification: PageClassification
) -> bool:
    classified = {a.family for a in classification.alternatives}
    covered = {f.family for f in extraction.families}
    if not (covered | set(extraction.unsupported_families)) <= classified:
        raise ValueError("Extraction family must have a recorded classification alternative.")
    required = (
        {classification.primary_family} if classification.outcome == "known" else classified
    ) & set(TYPED_FAMILIES)
    if not required <= covered:
        raise ValueError(
            "Classified typed families require their full page-local obligation ledger."
        )
    ambiguous = classification.outcome == "ambiguous"
    if ambiguous and (
        extraction.disposition != "partial" or "ambiguous_interpretation" not in extraction.reasons
    ):
        raise ValueError("Ambiguous classification requires explicit partial extraction coverage.")
    return ambiguous


def validate_coverage(
    elements: tuple[UnderstandingElement, ...],
    extraction: PageExtraction,
    classification: PageClassification,
) -> None:
    ambiguous_classification = _classification_coverage(extraction, classification)
    family_names = [f.family for f in extraction.families]
    unsupported = extraction.unsupported_families
    if len(set(family_names)) != len(family_names) or len(set(unsupported)) != len(unsupported):
        raise ValueError("Family coverage must be unique.")
    if set(unsupported) & set(TYPED_FAMILIES):
        raise ValueError("Implemented typed families cannot be relabeled unsupported.")
    if unsupported and "unsupported_family" not in extraction.reasons:
        raise ValueError("Unsupported family coverage requires its explicit reason.")
    if extraction.unsupported_fields and "unsupported_field" not in extraction.reasons:
        raise ValueError("Unsupported field coverage requires its explicit reason.")
    indices = []
    physical_rows: list[tuple[str, int, int | None]] = []
    incomplete = bool(unsupported or extraction.unsupported_fields or ambiguous_classification)
    for family in extraction.families:
        refs, gaps = _fields(elements, extraction, family.family, family.fields, None)
        row_refs, row_gaps = _rows(elements, extraction, family)
        indices.extend(refs + row_refs)
        incomplete |= gaps or row_gaps
        physical_rows.extend(row_key(r.physical_row) for r in family.rows)
    if len(set(physical_rows)) != len(physical_rows):
        raise ValueError("One physical row cannot be published as two extraction families.")
    validate_disjoint_rows(
        elements,
        tuple(
            row
            for family in extraction.families
            for row in (
                *[r.physical_row for r in family.rows],
                *[r.physical_row for r in family.excluded_rows],
            )
        ),
    )
    if Counter(indices) != Counter(range(len(extraction.claims))):
        raise ValueError("Every proposed claim must be accounted for exactly once.")
    for field in extraction.unsupported_fields:
        validate_quote(elements, field.source)
    if len(set(extraction.reasons)) != len(extraction.reasons):
        raise ValueError("Extraction reasons must be distinct.")
    state, reasons = extraction.disposition, extraction.reasons
    if state == "complete":
        if not extraction.claims or incomplete or reasons:
            raise ValueError(
                "Complete extraction cannot conceal absent values or unresolved coverage."
            )
        expected_rows = {
            (index, row)
            for index, element in enumerate(elements)
            if element.table is not None
            for row in range(element.table.row_count)
        }
        recorded_rows = {
            (row.element_index, row.row)
            for family in extraction.families
            for row in (
                *[r.physical_row for r in family.rows],
                *[r.physical_row for r in family.excluded_rows],
            )
            if isinstance(row, TableRow)
        }
        if expected_rows != recorded_rows:
            raise ValueError("Complete inventory must account for every recorded table row.")
    elif not reasons:
        raise ValueError("Non-complete extraction requires an explicit reason.")
    elif state == "partial":
        if not incomplete and not set(reasons) & {"content_omitted", "output_budget"}:
            raise ValueError("Partial extraction must identify its incomplete content.")
    elif extraction.claims:
        raise ValueError("Abstention outcomes cannot conceal extracted claims.")
    elif state == "unsupported_family":
        if not unsupported or extraction.families or "unsupported_family" not in reasons:
            raise ValueError("Unsupported typed family must remain explicitly classified.")
    elif state == "insufficient_signal":
        if "unreadable_content" not in reasons or unsupported:
            raise ValueError("Unsupported family is distinct from unreadable content.")
    elif state == "no_extraction_target":
        if incomplete or reasons != ("no_typed_target",):
            raise ValueError("No target cannot conceal unreadable, unsupported or omitted content.")
