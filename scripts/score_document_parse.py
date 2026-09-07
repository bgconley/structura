"""Score supplied private annotations/captures; never run a model or declare release readiness."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.evaluation.annotations import DocumentAnnotation  # noqa: E402
from lib.evaluation.captures import DocumentCapture  # noqa: E402
from lib.evaluation.manifest import EvaluationManifest  # noqa: E402
from lib.evaluation.scorer import score_evaluation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--annotations", type=Path, nargs="+", required=True)
    parser.add_argument("--captures", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = score_evaluation(
            EvaluationManifest.model_validate_json(args.manifest.read_text()),
            [DocumentAnnotation.model_validate_json(path.read_text()) for path in args.annotations],
            [DocumentCapture.model_validate_json(path.read_text()) for path in args.captures],
            expected_manifest_sha256=args.expected_manifest_sha256,
        )
    except (OSError, ValueError):
        # Pydantic errors may contain source text; keep console diagnostics private-safe.
        print(
            "Evaluation inputs are invalid, inconsistent, unavailable or exceed scorer limits.",
            file=sys.stderr,
        )
        return 2
    try:
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    except OSError:
        print("Evaluation output must be a new writable private file.", file=sys.stderr)
        return 2
    print(
        f"Computed parse diagnostics for {report['documents_scored']} documents; "
        "release acceptance remains not evaluated."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
