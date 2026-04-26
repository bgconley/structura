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
    assert plan.scripts[-1].name == "072_phase6_automation.sql"
    assert all(script.exists() for script in plan.scripts)


def test_parties_bm25_index_preserves_artifact_search_inputs_with_citext_cast() -> None:
    sql = Path("database/040_indexes_bm25_pgvector.sql").read_text(encoding="utf-8")

    assert "((normalized_name::text)::pdb.simple)" in sql
    assert "address_json" in sql


def test_folder_uniqueness_migration_is_household_scoped() -> None:
    sql = Path("database/066_folder_household_uniqueness.sql").read_text(encoding="utf-8")

    assert "DROP INDEX IF EXISTS folders_parent_name_uniq" in sql
    assert "folders_household_parent_name_uniq" in sql
    assert "household_id IS NOT NULL" in sql
    assert "folders_system_parent_name_uniq" in sql


def test_document_read_acl_function_is_baseline_migration() -> None:
    sql = Path("database/067_document_read_acl_function.sql").read_text(encoding="utf-8")

    assert "CREATE FUNCTION document_is_readable" in sql
    assert "folder_acl" in sql
    assert "highly_sensitive" in sql


def test_phase4_extraction_review_migration_is_baseline_migration() -> None:
    sql = Path("database/068_phase4_extraction_review.sql").read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION refresh_document_chunk_projection" in sql
    assert "review_tasks_document_status_idx" in sql
    assert "canonical_fact_history_document_created_idx" in sql


def test_phase5_search_migration_is_baseline_migration() -> None:
    sql = Path("database/069_phase5_search.sql").read_text(encoding="utf-8")

    assert "document_chunks_bm25_idx" in sql
    assert "bm25_text" in sql
    assert "embeddings_active_text_owner_profile_uniq" in sql
    assert "saved_searches_household_name_uniq" in sql
    assert "CREATE OR REPLACE FUNCTION document_matches_saved_query" in sql


def test_phase5_search_guardrails_migration_replaces_saved_query_function() -> None:
    sql = Path("database/071_phase5_search_guardrails.sql").read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION document_matches_saved_query" in sql
    assert "'tags'" in sql
    assert "bool_and(query_key IN" in sql


def test_phase6_automation_migration_adds_rule_and_watcher_state() -> None:
    sql = Path("database/072_phase6_automation.sql").read_text(encoding="utf-8")

    assert "owner_user_id" in sql
    assert "blocked_actions_json" in sql
    assert "decision_status" in sql
    assert "'deferred'" in sql
    assert "filing_rule_runs_pending_suggestions_idx" in sql
