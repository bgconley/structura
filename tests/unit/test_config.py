from lib.config import Settings


def test_settings_exposes_structura_runtime_roots() -> None:
    settings = Settings(STRUCTURA_ENV="test", runtime_root="/tmp/structura")

    assert str(settings.canonical_objects_root).endswith("/objects/canonical")
    assert str(settings.derived_objects_root).endswith("/objects/derived")
    assert str(settings.export_objects_root).endswith("/objects/exports")


def test_settings_exposes_phase8_5_model_runtime_defaults() -> None:
    settings = Settings(STRUCTURA_ENV="test", runtime_root="/tmp/structura")

    assert settings.model_mode == "fixture"
    assert settings.model_qwen_url == "http://127.0.0.1:8100"
    assert settings.model_granite_url == "http://127.0.0.1:8101"
    assert settings.model_text_embed_url == "http://127.0.0.1:8102"
    assert settings.model_visual_embed_url == "http://127.0.0.1:8103"
    assert settings.model_input_scratch_root.as_posix().endswith("/tmp/model-inputs")
    assert settings.model_qwen_semantic_timeout_seconds == 300
    assert settings.model_qwen_hq_timeout_seconds == 180
    assert settings.model_http_timeout_seconds == 60
    assert settings.model_max_image_bytes == 10 * 1024 * 1024
