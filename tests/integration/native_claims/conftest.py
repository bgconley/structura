"""Controlled source setup for PostgreSQL currency/authority tests."""

from dataclasses import replace

import pytest

from lib.db.connection import db_connection
from lib.document_processing.service import DocumentProcessingService
from lib.extraction.native_claims.models import NativePageRequest
from lib.extraction.native_claims.service import NativeClaimService
from tests.fixtures.native_claim_source import page_output, replace_output
from tests.integration.document_processing.conftest import processing  # noqa: F401


def setup_source(processing, *, pages=1, state="processed"):  # noqa: F811
    if pages != 1:
        inventory = processing.inventory.model_copy(
            update={
                "mime_type": "image/tiff",
                "pages": tuple(
                    processing.inventory.pages[0].model_copy(update={"page_number": n})
                    for n in range(1, pages + 1)
                ),
            }
        )
        processing = replace(processing, inventory=inventory)
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE document_assets SET mime_type='image/tiff' WHERE id=%s",
                (processing.asset_id,),
            )
    run, parser = processing.start(), DocumentProcessingService()
    claimed = processing.claim()
    checkpoints = []
    with processing.scope(claimed):
        parser.initialize_inventory(run.binding, processing.inventory)
        for number in range(1, pages + 1):
            checkpoint = replace_output(
                processing.checkpoint(run, page_number=number),
                run.binding.parse_generation_id,
                page_output(page_number=number, state=state, table=True),
            )
            parser.checkpoint(run.binding, checkpoint)
            checkpoints.append(checkpoint)
        parser.seal(run.binding, processing.structure(run, checkpoints))
        binding = NativeClaimService().start(run.binding)
    return processing, run, claimed, binding, tuple(checkpoints)


def page_request(checkpoint, *, disposition="complete"):
    table = checkpoint.page.tables[0]
    claims = tuple(
        {
            "canonical_key": "invoice.line_item.amount",
            "value_type": "money",
            "anchor": {
                "element_id": table.element_id,
                "table_id": table.id,
                "cell_id": c.id,
                "text_start": 0,
                "text_end": len(c.text),
            },
        }
        for c in table.cells
    )
    return NativePageRequest(
        page_number=checkpoint.page.page_number,
        disposition=disposition,
        reasons=() if disposition == "complete" else ("source_incomplete",),
        claims=claims,
    )


@pytest.fixture
def native_source(processing):  # noqa: F811
    return setup_source(processing)
