from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.search.benchmark import BenchmarkCase, evaluate_ranked_results, summarize_results

DEFAULT_MANIFEST = Path("tests/fixtures/golden_corpus/phase8_sanitized_manifest.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Structura golden corpus benchmark checks.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--require-model-backed",
        action="store_true",
        help="Require the manifest to represent a model-backed corpus run.",
    )
    args = parser.parse_args()

    payload = _load_manifest(args.manifest)
    if args.require_model_backed and payload.get("fixtureType") != "model_backed":
        raise SystemExit("Golden corpus manifest is not model-backed.")

    results = []
    for case_payload in _cases(payload):
        case = BenchmarkCase(
            name=str(case_payload["name"]),
            query=dict(case_payload["query"]),
            expected_document_ids=tuple(str(item) for item in case_payload["expectedDocumentIds"]),
            k=int(case_payload.get("k", 10)),
        )
        returned = [str(item) for item in case_payload["returnedDocumentIds"]]
        results.append(evaluate_ranked_results(case, returned))

    summary = summarize_results(results)
    thresholds = payload.get("thresholds", {})
    _assert_threshold(summary, thresholds, "hitRateAtK")
    _assert_threshold(summary, thresholds, "meanReciprocalRank")
    print(
        json.dumps(
            {
                "manifest": str(args.manifest),
                "fixtureType": payload.get("fixtureType"),
                "summary": summary,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Golden corpus manifest not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("Golden corpus manifest must be a JSON object.")
    return payload


def _cases(payload: dict[str, Any]) -> list[dict[str, Any]]:
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SystemExit("Golden corpus manifest must contain at least one case.")
    for case in cases:
        if not isinstance(case, dict):
            raise SystemExit("Golden corpus cases must be JSON objects.")
        for key in ("name", "query", "expectedDocumentIds", "returnedDocumentIds"):
            if key not in case:
                raise SystemExit(f"Golden corpus case is missing {key}.")
    return cases


def _assert_threshold(
    summary: dict[str, float | int],
    thresholds: object,
    metric: str,
) -> None:
    if not isinstance(thresholds, dict) or metric not in thresholds:
        raise SystemExit(f"Golden corpus threshold missing: {metric}")
    actual = float(summary[metric])
    expected = float(thresholds[metric])
    if actual < expected:
        raise SystemExit(f"Golden corpus {metric} {actual:.4f} is below {expected:.4f}.")


if __name__ == "__main__":
    raise SystemExit(main())
