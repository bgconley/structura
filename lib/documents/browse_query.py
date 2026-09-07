"""Supported document-browse choices, independent of HTTP and persistence."""

from enum import StrEnum


class InboxState(StrEnum):
    ALL = "all"
    NEEDS_REVIEW = "needs_review"
    UNFILED = "unfiled"
    AWAITING_CLASSIFICATION = "awaiting_classification"
    DUPLICATES = "duplicates"
    LOW_CONFIDENCE = "low_confidence"
    HAS_EXTRACTION = "has_extraction"
    TEXT_SEARCHABLE = "text_searchable"


class DocumentSort(StrEnum):
    UPLOADED_DESC = "uploaded_desc"
    UPLOADED_ASC = "uploaded_asc"
    DOCUMENT_DATE_DESC = "document_date_desc"
    DOCUMENT_DATE_ASC = "document_date_asc"
    TITLE_ASC = "title_asc"
    TITLE_DESC = "title_desc"


MAX_BROWSE_OFFSET = 2**53 - 1


def validate_browse_window(limit: int, offset: int) -> None:
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Document page size must be between 1 and 200.")
    if type(offset) is not int or not 0 <= offset <= MAX_BROWSE_OFFSET:
        raise ValueError("Document offset must be a nonnegative safe integer.")
