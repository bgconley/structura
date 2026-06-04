from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.model_runtime.model_corpus_manifest import (  # noqa: E402
    evaluate_model_corpus_manifest,
    load_manifest,
)

DEFAULT_MANIFEST = Path("tests/fixtures/model_corpus/phase8_5_model_manifest.example.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Structura Phase 8.5 model corpus gate.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--require-model-backed", action="store_true")
    args = parser.parse_args()

    payload = load_manifest(args.manifest)
    result = evaluate_model_corpus_manifest(
        payload,
        require_model_backed=args.require_model_backed,
        manifest_path=args.manifest,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
