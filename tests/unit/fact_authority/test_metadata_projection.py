from datetime import date
from decimal import Decimal
from uuid import UUID

from lib.fact_authority.metadata_projection import metadata_fingerprint
from lib.fact_authority.projection_values import snapshot_digest


def test_metadata_fingerprint_preserves_existing_projection_encoding_and_exact_values():
    metadata = {
        "title": "Café",
        "tags": ["alpha", "beta"],
        "amount": Decimal("99999999999999.9999"),
    }
    decisions = {
        "document_date": {
            "property": "document_date",
            "value_json": date(2020, 3, 4),
            "revision": UUID("00000000-0000-4000-8000-000000000001"),
        }
    }
    rollups = {"documentDate": {"ownership": "manual", "value": "2020-03-04"}}
    existing = snapshot_digest(
        {
            "schemaVersion": "indexed_metadata.v1",
            "metadata": metadata,
            "decisions": decisions,
            "rollups": rollups,
        }
    )
    assert metadata_fingerprint(metadata, decisions, rollups) == existing
    assert metadata_fingerprint({**metadata, "title": "Changed"}, decisions, rollups) != existing
    assert metadata["amount"] == Decimal("99999999999999.9999")
