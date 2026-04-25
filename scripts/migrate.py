from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.config import get_settings
from lib.db.migrations import apply_baseline_migrations, baseline_migration_plan


def main() -> None:
    settings = get_settings()
    plan = baseline_migration_plan(settings.database_dir)
    print("Applying Structura baseline migrations:")
    for script in plan.scripts:
        print(f"  - {script.name}")
    applied = apply_baseline_migrations(settings.database_url, settings.database_dir)
    print(f"Applied {len(applied)} migration scripts.")


if __name__ == "__main__":
    main()
