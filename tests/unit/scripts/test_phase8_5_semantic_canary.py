from __future__ import annotations

from uuid import uuid4

from scripts.gpu import run_phase8_5_semantic_canary as semantic_canary


def test_semantic_canary_parser_supports_expected_modes_and_skip_granite() -> None:
    for mode in semantic_canary.CANARY_MODES:
        args = semantic_canary.parse_args(
            [
                "--mode",
                mode,
                "--document-id",
                str(uuid4()),
                "--skip-granite",
                "--json-output",
                "/tmp/semantic-canary.json",
            ]
        )

        assert args.mode == mode
        assert args.skip_granite is True
        assert str(args.json_output) == "/tmp/semantic-canary.json"


def test_semantic_canary_estimates_adaptive_fan_in_with_fallback() -> None:
    sequence = semantic_canary._image_fan_in_sequence(
        page_count=3,
        confidence={"fallback_reason": "multi_image_page_coverage"},
    )

    assert sequence == [3, 1, 1, 1]
