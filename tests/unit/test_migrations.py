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
    assert plan.scripts[-1].name == "088_phase8_5_line_item_payer_amounts.sql"
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


def test_phase7_relationship_migration_adds_status_deadline_and_guardrails() -> None:
    sql = Path("database/073_phase7_relationships.sql").read_text(encoding="utf-8")

    assert "document_relationships" in sql
    assert "status" in sql
    assert "document_relationships_active_pair_type_uniq" in sql
    assert "document_deadlines_document_type_due_active_uniq" in sql
    assert "deadline_type" in sql
    assert "relationship_types" in sql


def test_phase7_deadline_status_waived_migration_preserves_applied_phase7_checksum() -> None:
    phase7_sql = Path("database/073_phase7_relationships.sql").read_text(encoding="utf-8")
    waived_sql = Path("database/074_phase7_deadline_status_waived.sql").read_text(encoding="utf-8")

    assert "'waived'" not in phase7_sql
    assert "'waived'" in waived_sql
    assert "document_deadlines_status_check" in waived_sql


def test_phase8_5_semantic_annotation_migration_is_baseline_migration() -> None:
    plan = baseline_migration_plan("database")
    names = [script.name for script in plan.scripts]

    assert "075_phase8_5_semantic_annotations.sql" in names

    sql = Path("database/075_phase8_5_semantic_annotations.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS document_semantic_annotations" in sql
    assert "CREATE TABLE IF NOT EXISTS page_semantic_annotations" in sql
    assert "CREATE TABLE IF NOT EXISTS semantic_region_annotations" in sql
    assert "ALTER TYPE job_type_enum ADD VALUE IF NOT EXISTS 'semantic_annotate'" in sql
    assert "document_semantic_annotations_current_uniq" in sql


def test_phase8_5_visual_embedding_native_dimension_migration_is_baseline_migration() -> None:
    sql = Path("database/076_phase8_5_visual_embedding_2048.sql").read_text(encoding="utf-8")

    assert "embeddings_visual_2048_hnsw_idx" in sql
    assert "embedding::halfvec(2048)" in sql
    assert "halfvec_cosine_ops" in sql
    assert "embedding_dimensions = 2048" in sql


def test_phase8_5_semantic_type_constraint_migration_is_baseline_migration() -> None:
    sql = Path("database/077_phase8_5_semantic_type_constraint.sql").read_text(encoding="utf-8")

    assert "semantic_region_annotations_semantic_type_check" in sql
    assert "covered_services_line_item_table" in sql
    assert "unknown" in sql


def test_phase8_5_region_extraction_scope_migration_is_baseline_migration() -> None:
    plan = baseline_migration_plan("database")
    names = [script.name for script in plan.scripts]

    assert "078_phase8_5_region_extraction_scope.sql" in names

    sql = Path("database/078_phase8_5_region_extraction_scope.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS extraction_scope" in sql
    assert "source_semantic_region_id" in sql
    assert "semantic_annotation_id" in sql
    assert "model_output_schema_name" in sql
    assert "normalization_json" in sql
    assert "DROP INDEX IF EXISTS document_extractions_one_current_idx" in sql
    assert "document_extractions_current_document_scope_idx" in sql
    assert "document_extractions_current_region_scope_idx" in sql


def test_phase8_5_extraction_observations_migration_is_baseline_migration() -> None:
    plan = baseline_migration_plan("database")
    names = [script.name for script in plan.scripts]

    assert "079_phase8_5_extraction_observations.sql" in names

    sql = Path("database/079_phase8_5_extraction_observations.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS extraction_observations" in sql
    assert "semantic_annotation_id" in sql
    assert "source_semantic_region_id" in sql
    assert "model_output_schema_name" in sql
    assert "extraction_observations_document_family_idx" in sql


def test_phase8_5_semantic_type_expansion_migration_is_baseline_migration() -> None:
    plan = baseline_migration_plan("database")
    names = [script.name for script in plan.scripts]

    assert "080_phase8_5_semantic_type_expansion.sql" in names

    phase8_semantic_sql = Path("database/075_phase8_5_semantic_annotations.sql").read_text(
        encoding="utf-8"
    )
    sql = Path("database/080_phase8_5_semantic_type_expansion.sql").read_text(encoding="utf-8")
    assert "retail_order_line_item_table" not in phase8_semantic_sql
    assert "retail_order_line_item_table" in sql
    assert "seller_information_block" in sql
    assert "unsupported_document_region" in sql


def test_phase8_5_semantic_family_reconciliation_migration_is_baseline_migration() -> None:
    plan = baseline_migration_plan("database")
    names = [script.name for script in plan.scripts]

    assert "081_phase8_5_semantic_family_reconciliation.sql" in names

    sql = Path("database/081_phase8_5_semantic_family_reconciliation.sql").read_text(
        encoding="utf-8"
    )
    assert "ALTER TYPE document_family_enum ADD VALUE IF NOT EXISTS 'retail_order'" in sql
    assert "ALTER TYPE document_family_enum ADD VALUE IF NOT EXISTS 'service_record'" in sql
    assert "ALTER TYPE document_family_enum ADD VALUE IF NOT EXISTS 'real_estate_title'" in sql
    assert (
        "ALTER TYPE document_family_enum ADD VALUE IF NOT EXISTS 'mortgage_escrow_statement'" in sql
    )


def test_phase8_5_reliable_extraction_platform_migration_is_baseline_migration() -> None:
    plan = baseline_migration_plan("database")
    names = [script.name for script in plan.scripts]

    assert "083_phase8_5_reliable_extraction_platform.sql" in names

    sql = Path("database/083_phase8_5_reliable_extraction_platform.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS semantic_extraction_plans" in sql
    assert "CREATE TABLE IF NOT EXISTS semantic_extraction_plan_tasks" in sql
    assert "CREATE TABLE IF NOT EXISTS candidate_admission_events" in sql
    assert "plan_task_id uuid REFERENCES semantic_extraction_plan_tasks" in sql
    assert "semantic_annotation_id uuid REFERENCES document_semantic_annotations" in sql
    assert "region_envelope_version text" in sql
    assert "ADD COLUMN IF NOT EXISTS plan_id" in sql
    assert "ADD COLUMN IF NOT EXISTS plan_task_id" in sql
    assert "candidate_admission_events_plan_task_idx" in sql


def test_phase8_5_plan_task_page_numbers_migration_is_baseline_migration() -> None:
    plan = baseline_migration_plan("database")
    names = [script.name for script in plan.scripts]

    assert "084_phase8_5_plan_task_page_numbers.sql" in names

    sql = Path("database/084_phase8_5_plan_task_page_numbers.sql").read_text(encoding="utf-8")
    assert "UPDATE semantic_extraction_plan_tasks task" in sql
    assert "LEFT JOIN page_semantic_annotations psa" in sql
    assert "LEFT JOIN document_elements de" in sql
    assert "LEFT JOIN document_tables dt" in sql
    assert "task.page_number IS NULL" in sql


def test_phase8_5_plan_task_visual_summary_migration_is_baseline_migration() -> None:
    plan = baseline_migration_plan("database")
    names = [script.name for script in plan.scripts]

    assert "085_phase8_5_plan_task_visual_summary.sql" in names

    sql = Path("database/085_phase8_5_plan_task_visual_summary.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE semantic_extraction_plan_tasks" in sql
    assert "ADD COLUMN IF NOT EXISTS visual_plan_summary jsonb" in sql
    assert "jsonb_typeof(visual_plan_summary) = 'object'" in sql


def test_phase8_5_service_health_migration_is_baseline_migration() -> None:
    plan = baseline_migration_plan("database")
    names = [script.name for script in plan.scripts]

    assert "086_phase8_5_service_health.sql" in names

    sql = Path("database/086_phase8_5_service_health.sql").read_text(encoding="utf-8")
    assert "service_health_snapshots_status_check" in sql
    assert "'fixture'" in sql
    assert "'unavailable'" in sql
    assert "service_health_snapshots_service_checked_idx" in sql
    assert "(service_name, checked_at DESC)" in sql


def test_phase8_5_quality_outcome_migration_is_baseline_migration() -> None:
    plan = baseline_migration_plan("database")
    names = [script.name for script in plan.scripts]

    assert "087_phase8_5_quality_outcome.sql" in names

    sql = Path("database/087_phase8_5_quality_outcome.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE document_extractions" in sql
    assert "ADD COLUMN IF NOT EXISTS quality_outcome text" in sql
    assert "document_extractions_quality_outcome_check" in sql
    for outcome in (
        "extracted_cleanly",
        "needs_human_review",
        "insufficient_signal",
        "no_extraction_target",
        "pipeline_failed",
    ):
        assert f"'{outcome}'" in sql
    assert "quality_outcome IS NULL" in sql
    assert "extraction_observations_status_check" in sql
    assert "'accepted'" in sql

