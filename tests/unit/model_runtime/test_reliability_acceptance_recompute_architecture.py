from __future__ import annotations

import inspect
import subprocess
import sys

import lib.model_runtime.reliability_acceptance_recompute as core_recompute

SUMMARY_RECOMPUTERS = (
    "recomputed_candidate_admission_summary",
    "recomputed_planner_summary",
    "recomputed_envelope_summary",
    "recomputed_visual_input_plan_summary",
    "recomputed_retry_summary",
    "recomputed_extraction_pressure",
    "recomputed_safe_outcome_summary",
    "recomputed_quality_summary",
)


def test_summary_recomputers_live_in_focused_module() -> None:
    import lib.model_runtime.reliability_summary_recompute as summary_recompute

    for name in SUMMARY_RECOMPUTERS:
        assert getattr(summary_recompute, name) is getattr(core_recompute, name)
        assert f"def {name}" not in inspect.getsource(core_recompute)


def test_summary_recompute_import_does_not_load_runtime_settings() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import lib.model_runtime.reliability_summary_recompute; "
                "raise SystemExit('lib.config.settings' in sys.modules)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
