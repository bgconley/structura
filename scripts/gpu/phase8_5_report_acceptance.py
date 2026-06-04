#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.model_runtime.reliability_acceptance import (  # noqa: E402
    assert_phase85_report_acceptance,
    evaluate_phase85_report_acceptance,
)


def main() -> int:
    args = _parse_args()
    reports = [_load_report(path) for path in args.report]
    summary = evaluate_phase85_report_acceptance(reports, require_gold=args.require_gold)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    try:
        assert_phase85_report_acceptance(summary)
    except SystemExit:
        return 1
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Phase 8.5 resident/smoke report acceptance gates.",
    )
    parser.add_argument("report", nargs="+", type=Path)
    parser.add_argument(
        "--require-gold",
        action="store_true",
        help=(
            "Require model-backed gold-corpus quality metrics to pass instead of allowing "
            "resident-only reports."
        ),
    )
    return parser.parse_args()


def _load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Phase 8.5 report must be a JSON object: {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
