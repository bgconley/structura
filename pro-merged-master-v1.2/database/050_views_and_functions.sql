SET search_path TO structura, public;

CREATE OR REPLACE FUNCTION rrf_score(rank_value integer, k_value integer DEFAULT 60)
RETURNS double precision
LANGUAGE SQL
IMMUTABLE
AS $$
  SELECT 1.0 / (k_value + rank_value);
$$;

CREATE OR REPLACE VIEW current_extractions_v AS
SELECT DISTINCT ON (document_id, schema_name)
  id,
  document_id,
  schema_name,
  schema_version,
  status,
  is_current,
  source_engine,
  model_name,
  model_version,
  prompt_version,
  raw_output_asset_id,
  normalized_json,
  validation_json,
  confidence,
  review_status,
  created_at,
  updated_at
FROM document_extractions
WHERE is_current
ORDER BY document_id, schema_name, created_at DESC;

CREATE OR REPLACE VIEW document_primary_amounts_v AS
SELECT
  d.id AS document_id,
  MAX(CASE WHEN a.amount_role = 'total' THEN a.amount END) AS total_amount,
  MAX(CASE WHEN a.amount_role = 'subtotal' THEN a.amount END) AS subtotal_amount,
  MAX(CASE WHEN a.amount_role = 'tax' THEN a.amount END) AS tax_amount,
  MAX(CASE WHEN a.amount_role = 'patient_responsibility' THEN a.amount END) AS patient_responsibility_amount,
  MAX(CASE WHEN a.amount_role = 'plan_paid' THEN a.amount END) AS plan_paid_amount,
  MAX(a.currency_code) FILTER (WHERE a.currency_code IS NOT NULL) AS currency_code
FROM documents d
LEFT JOIN document_amounts a
  ON a.document_id = d.id
GROUP BY d.id;

CREATE OR REPLACE VIEW document_folder_paths_v AS
SELECT
  f.id,
  f.parent_id,
  f.name,
  CASE
    WHEN f.parent_id IS NULL THEN '/' || f.name
    ELSE COALESCE(p.path_cache, '/' || p.name) || '/' || f.name
  END AS computed_path
FROM folders f
LEFT JOIN folders p ON p.id = f.parent_id;

CREATE OR REPLACE VIEW document_summary_v AS
SELECT
  d.id,
  d.title,
  d.original_filename,
  d.document_family,
  d.document_subtype,
  d.lifecycle_state,
  d.review_status,
  d.document_date,
  d.counterparty_display,
  d.page_count,
  d.created_at,
  d.updated_at,
  a.total_amount,
  a.currency_code,
  (
    SELECT array_agg(t.name ORDER BY t.name)
    FROM document_tags dt
    JOIN tags t ON t.id = dt.tag_id
    WHERE dt.document_id = d.id
  ) AS tags,
  (
    SELECT array_agg(f.name ORDER BY f.name)
    FROM document_folder_memberships dfm
    JOIN folders f ON f.id = dfm.folder_id
    WHERE dfm.document_id = d.id
  ) AS folders
FROM documents d
LEFT JOIN document_primary_amounts_v a
  ON a.document_id = d.id
WHERE d.deleted_at IS NULL;

CREATE OR REPLACE VIEW open_review_queue_v AS
SELECT
  rt.id AS review_task_id,
  rt.document_id,
  d.title,
  d.document_family,
  rt.task_type,
  rt.status,
  rt.priority,
  rt.reason,
  rt.created_at,
  rt.due_at
FROM review_tasks rt
JOIN documents d ON d.id = rt.document_id
WHERE rt.status IN ('open', 'in_progress')
  AND d.deleted_at IS NULL
ORDER BY rt.priority DESC, rt.created_at ASC;
