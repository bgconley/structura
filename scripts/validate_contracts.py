from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.config import get_settings
from lib.contracts import ContractRegistry


def main() -> None:
    settings = get_settings()
    registry = ContractRegistry.from_settings(settings)
    registry.check_json_schemas()
    registry.check_model_output_structured_schemas()
    summary = registry.summary()
    print(
        "Validated Structura contracts: "
        f"{summary['path_count']} OpenAPI paths, "
        f"{summary['schema_count']} schemas, "
        f"{summary['event_schema_count']} event schemas, "
        f"{summary['model_output_schema_count']} model-output schemas."
    )


if __name__ == "__main__":
    main()
