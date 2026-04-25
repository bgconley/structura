from pathlib import Path

from lib.db.migrations import BASELINE_SQL_FILES, baseline_migration_plan


def test_baseline_migration_plan_excludes_query_examples() -> None:
    plan = baseline_migration_plan("database")
    names = [script.name for script in plan.scripts]

    assert tuple(names) == BASELINE_SQL_FILES
    assert "070_query_examples.sql" not in names


def test_baseline_migration_scripts_are_present_and_ordered() -> None:
    plan = baseline_migration_plan("database")

    assert plan.scripts[0].name == "001_extensions.sql"
    assert plan.scripts[-1].name == "060_seed_taxonomies.sql"
    assert all(script.exists() for script in plan.scripts)


def test_parties_bm25_index_preserves_artifact_search_inputs_with_citext_cast() -> None:
    sql = Path("database/040_indexes_bm25_pgvector.sql").read_text(encoding="utf-8")

    assert "((normalized_name::text)::pdb.simple)" in sql
    assert "address_json" in sql
