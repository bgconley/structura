from __future__ import annotations

from lib.documents.access_policy import (
    DocumentAccessContext,
    document_read_access_params,
)

READABLE_RELATED_COUNT_SQL = """
  (
    SELECT count(*)::int
    FROM document_relationships dr
    JOIN documents related_doc
      ON related_doc.id = CASE
        WHEN dr.from_document_id = d.id THEN dr.to_document_id
        ELSE dr.from_document_id
      END
    WHERE dr.status IN ('suggested', 'confirmed')
      AND d.id IN (dr.from_document_id, dr.to_document_id)
      AND document_is_readable(related_doc.id, %s, %s, %s)
  ) AS related_count
"""


def readable_related_count_params(access: DocumentAccessContext) -> tuple[object, ...]:
    return document_read_access_params(access)
