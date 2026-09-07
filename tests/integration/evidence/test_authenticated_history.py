from __future__ import annotations

import json

from lib.config import get_settings
from lib.storage import ObjectStorage
from scripts.gpu.probe_persisted_parse import ProbeSource
from scripts.gpu.probe_retained_evidence import verify_historical_api
from tests.integration.evidence.conftest import populate


def test_protected_asgi_history_uses_real_credentials_and_preserves_exact_page_bytes(
    evidence, monkeypatch, tmp_path
):
    """Real SQL/auth/routes/storage; parser fixture is not live model quality evidence."""
    processing, run, _, writer, _, _, _ = evidence
    populate(evidence)
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / "api-runtime"))
    get_settings.cache_clear()
    storage = ObjectStorage()
    source_page = evidence[6]
    page = storage.store_bytes(source_page.path.read_bytes(), kind="derived", role="source-page")
    assert page.uri == source_page.uri
    original = storage.store_bytes(
        b"controlled source identity for database tests", kind="canonical", role="original"
    )
    assert original.sha256 == processing.original_sha256
    source = ProbeSource(
        processing.document_id,
        processing.asset_id,
        processing.principal,
        storage,
        original,
    )
    result = verify_historical_api(run, source, tmp_path)
    assert result["page_count"] == 1
    assert result["historical_page_and_render_replay_equal"]
    evidence_file = tmp_path / "retained-evidence-api.json"
    capture = json.loads(evidence_file.read_text())
    assert capture["before"]["manifests"][0]["processingRunState"] == "sealed"
    assert capture["after"]["manifests"][0]["processingRunState"] == "superseded"
    assert evidence_file.stat().st_mode & 0o777 == 0o600
