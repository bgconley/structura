from __future__ import annotations

from lib.documents.access_policy import DocumentAccessContext, document_read_access_params

READABLE_COUNTERPART_SQL = """
AND document_is_readable(
  CASE
    WHEN dr.from_document_id = d.id THEN dr.to_document_id
    ELSE dr.from_document_id
  END,
  %s,
  %s,
  %s
)
"""


def readable_counterpart_params(access: DocumentAccessContext) -> tuple[object, ...]:
    return document_read_access_params(access)
