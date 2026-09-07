"""Independent synthetic persisted v2 checkpoints for real SQL authority tests."""

from copy import deepcopy
from dataclasses import replace

import pytest

from lib.db.connection import db_connection
from lib.document_processing.service import DocumentProcessingService
from lib.extraction.native_claims.model_emission.service import NativeModelEmissionService
from tests.fixtures.native_model_emission_source import checkpoint, configuration
from tests.fixtures.page_understanding_sources import invoice_page
from tests.integration.document_processing.conftest import processing  # noqa: F401


def setup_source(processing, outputs=None):  # noqa: F811
    outputs = outputs or [invoice_page()]
    if len(outputs) > 1:
        inventory = processing.inventory.model_copy(
            update={
                "mime_type": "image/tiff",
                "pages": tuple(
                    processing.inventory.pages[0].model_copy(update={"page_number": n})
                    for n in range(1, len(outputs) + 1)
                ),
            }
        )
        processing = replace(processing, inventory=inventory)
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE document_assets SET mime_type='image/tiff' WHERE id=%s",
                (processing.asset_id,),
            )
    processing = replace(processing, configuration=configuration(processing.inventory))
    run = processing.start()
    claimed = processing.claim()
    parser = DocumentProcessingService()
    checkpoints = []
    with processing.scope(claimed):
        parser.initialize_inventory(run.binding, processing.inventory)
        for number, output in enumerate(outputs, 1):
            output = {**deepcopy(output), "page_number": number}
            item = checkpoint(processing.configuration, run.binding.parse_generation_id, output)
            parser.checkpoint(run.binding, item)
            checkpoints.append(item)
        parser.seal(run.binding, processing.structure(run, checkpoints))
        binding = NativeModelEmissionService().start(run.binding)
    return processing, run, claimed, binding, tuple(checkpoints)


@pytest.fixture
def model_source(processing):  # noqa: F811
    return setup_source(processing)


def populated(source):
    harness, run, claimed, binding, checkpoints = source
    with harness.scope(claimed):
        for item in checkpoints:
            NativeModelEmissionService().checkpoint(binding, item.page.page_number)
        NativeModelEmissionService().seal(binding)
    return source
