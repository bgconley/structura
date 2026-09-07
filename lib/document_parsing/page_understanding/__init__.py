"""Pure combined-page v2 contract; runtime/version dispatch is intentionally separate."""

from lib.document_parsing.page_understanding.codec import decode_page_understanding
from lib.document_parsing.page_understanding.model import PageUnderstanding

__all__ = ["PageUnderstanding", "decode_page_understanding"]
