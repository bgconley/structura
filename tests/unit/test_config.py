from lib.config import Settings


def test_settings_exposes_structura_runtime_roots() -> None:
    settings = Settings(STRUCTURA_ENV="test", runtime_root="/tmp/structura")

    assert str(settings.canonical_objects_root).endswith("/objects/canonical")
    assert str(settings.derived_objects_root).endswith("/objects/derived")
    assert str(settings.export_objects_root).endswith("/objects/exports")
