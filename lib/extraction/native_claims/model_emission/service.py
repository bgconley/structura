"""Bounded immutable import orchestration; no caller payloads or model calls."""

from lib.auth.request_authority import RequestCredential
from lib.document_processing.models import ProcessingBinding
from lib.extraction.native_claims.model_emission.configuration import installed_configuration
from lib.extraction.native_claims.model_emission.page_repository import persist_page
from lib.extraction.native_claims.model_emission.projection import diagnostic_projection
from lib.extraction.native_claims.model_emission.read_repository import read_sealed, seal_set
from lib.extraction.native_claims.models import NativeClaimBinding
from lib.extraction.native_claims.set_repository import start_set
from lib.extraction.native_claims.transactions import claim_transaction


class NativeModelEmissionService:
    def start(self, processing: ProcessingBinding) -> NativeClaimBinding:
        configuration = installed_configuration()
        with claim_transaction() as cur:
            return start_set(cur, processing, configuration)

    def checkpoint(self, binding: NativeClaimBinding, page_number: int) -> str:
        implementation = installed_configuration()
        with claim_transaction() as cur:
            return persist_page(cur, binding, page_number, implementation=implementation)

    def seal(self, binding: NativeClaimBinding):
        implementation = installed_configuration()
        with claim_transaction() as cur:
            return seal_set(cur, binding, implementation=implementation)

    def rebuild(self, binding: NativeClaimBinding, *, credential: RequestCredential):
        with claim_transaction() as cur:
            claims, pages, _ = read_sealed(cur, binding, credential)
        return diagnostic_projection(claims, pages)
