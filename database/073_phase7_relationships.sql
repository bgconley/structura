SET search_path TO structura, public;

ALTER TABLE document_relationships
  ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'confirmed',
  ADD COLUMN IF NOT EXISTS comment text,
  ADD COLUMN IF NOT EXISTS review_task_id uuid REFERENCES review_tasks(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS created_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS decided_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS decided_at timestamptz;

ALTER TABLE document_relationships
  DROP CONSTRAINT IF EXISTS document_relationships_status_check;

ALTER TABLE document_relationships
  ADD CONSTRAINT document_relationships_status_check
  CHECK (status IN ('suggested', 'confirmed', 'rejected', 'superseded'));

ALTER TABLE document_deadlines
  DROP CONSTRAINT IF EXISTS document_deadlines_status_check;

ALTER TABLE document_deadlines
  ADD CONSTRAINT document_deadlines_status_check
  CHECK (status IN ('open', 'due_soon', 'overdue', 'snoozed', 'resolved', 'waived', 'needs_review'));

CREATE UNIQUE INDEX IF NOT EXISTS document_relationships_active_pair_type_uniq
  ON document_relationships (
    LEAST(from_document_id, to_document_id),
    GREATEST(from_document_id, to_document_id),
    relationship_type
  )
  WHERE status IN ('suggested', 'confirmed');

CREATE INDEX IF NOT EXISTS document_relationships_status_type_idx
  ON document_relationships (status, relationship_type, created_at DESC);

CREATE INDEX IF NOT EXISTS document_relationships_review_task_idx
  ON document_relationships (review_task_id)
  WHERE review_task_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS document_deadlines_document_type_due_active_uniq
  ON document_deadlines (document_id, deadline_type, due_on)
  WHERE status IN ('open', 'due_soon', 'overdue', 'needs_review');

CREATE INDEX IF NOT EXISTS document_deadlines_status_due_idx
  ON document_deadlines (status, due_on, deadline_type);

CREATE OR REPLACE FUNCTION document_matches_saved_query(
  target_document_id uuid,
  saved_query jsonb
)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
  WITH allowed_keys AS (
    SELECT unnest(ARRAY[
      'amountMax',
      'amountMin',
      'dateFrom',
      'dateTo',
      'deadlineStatuses',
      'deadlineTypes',
      'deadline_status',
      'deadline_type',
      'document_family',
      'families',
      'folderIds',
      'folder_ids',
      'hasOpenDeadlines',
      'hasRelationships',
      'open_deadlines',
      'open_review_tasks',
      'primaryFolderOnly',
      'primary_folder_only',
      'relationshipStatuses',
      'relationshipTypes',
      'relationship_status',
      'relationship_types',
      'reviewStatuses',
      'review_status',
      'reviewedOnly',
      'reviewed_only',
      'sensitivity',
      'tag_names',
      'tags'
    ]::text[]) AS key
  ),
  query_keys AS (
    SELECT jsonb_object_keys(COALESCE(saved_query, '{}'::jsonb)) AS key
  ),
  doc AS (
    SELECT d.*
    FROM documents d
    WHERE d.id = target_document_id
      AND d.deleted_at IS NULL
  )
  SELECT
    COALESCE((SELECT bool_and(query_key.key IN (SELECT key FROM allowed_keys)) FROM query_keys query_key), true)
    AND EXISTS (SELECT 1 FROM doc)
    AND (
      NOT (COALESCE(saved_query, '{}'::jsonb) ? 'document_family')
      OR (SELECT document_family::text FROM doc) = ANY (
        SELECT jsonb_array_elements_text(
          CASE
            WHEN jsonb_typeof(saved_query -> 'document_family') = 'array' THEN saved_query -> 'document_family'
            ELSE jsonb_build_array(saved_query ->> 'document_family')
          END
        )
      )
    )
    AND (
      NOT (COALESCE(saved_query, '{}'::jsonb) ? 'families')
      OR (SELECT document_family::text FROM doc) = ANY (
        SELECT jsonb_array_elements_text(saved_query -> 'families')
      )
    )
    AND (
      NOT (COALESCE(saved_query, '{}'::jsonb) ? 'review_status')
      OR (SELECT review_status::text FROM doc) = ANY (
        SELECT jsonb_array_elements_text(
          CASE
            WHEN jsonb_typeof(saved_query -> 'review_status') = 'array' THEN saved_query -> 'review_status'
            ELSE jsonb_build_array(saved_query ->> 'review_status')
          END
        )
      )
    )
    AND (
      COALESCE((saved_query ->> 'open_review_tasks')::boolean, false) = false
      OR EXISTS (
        SELECT 1
        FROM review_tasks rt
        WHERE rt.document_id = target_document_id
          AND rt.status IN ('open', 'in_progress')
      )
    )
    AND (
      NOT (
        COALESCE((saved_query ->> 'hasRelationships')::boolean, false)
        OR (COALESCE(saved_query, '{}'::jsonb) ? 'relationshipTypes')
        OR (COALESCE(saved_query, '{}'::jsonb) ? 'relationship_types')
        OR (COALESCE(saved_query, '{}'::jsonb) ? 'relationshipStatuses')
        OR (COALESCE(saved_query, '{}'::jsonb) ? 'relationship_status')
      )
      OR EXISTS (
        SELECT 1
        FROM document_relationships dr
        WHERE dr.status <> 'rejected'
          AND target_document_id IN (dr.from_document_id, dr.to_document_id)
          AND (
            NOT (COALESCE(saved_query, '{}'::jsonb) ? 'relationshipTypes')
            OR dr.relationship_type::text = ANY (
              SELECT jsonb_array_elements_text(saved_query -> 'relationshipTypes')
            )
          )
          AND (
            NOT (COALESCE(saved_query, '{}'::jsonb) ? 'relationship_types')
            OR dr.relationship_type::text = ANY (
              SELECT jsonb_array_elements_text(saved_query -> 'relationship_types')
            )
          )
          AND (
            NOT (COALESCE(saved_query, '{}'::jsonb) ? 'relationshipStatuses')
            OR dr.status = ANY (
              SELECT jsonb_array_elements_text(saved_query -> 'relationshipStatuses')
            )
          )
          AND (
            NOT (COALESCE(saved_query, '{}'::jsonb) ? 'relationship_status')
            OR dr.status = ANY (
              SELECT jsonb_array_elements_text(
                CASE
                  WHEN jsonb_typeof(saved_query -> 'relationship_status') = 'array' THEN saved_query -> 'relationship_status'
                  ELSE jsonb_build_array(saved_query ->> 'relationship_status')
                END
              )
            )
          )
      )
    )
    AND (
      NOT (
        COALESCE((saved_query ->> 'hasOpenDeadlines')::boolean, false)
        OR COALESCE((saved_query ->> 'open_deadlines')::boolean, false)
        OR (COALESCE(saved_query, '{}'::jsonb) ? 'deadlineTypes')
        OR (COALESCE(saved_query, '{}'::jsonb) ? 'deadline_type')
        OR (COALESCE(saved_query, '{}'::jsonb) ? 'deadlineStatuses')
        OR (COALESCE(saved_query, '{}'::jsonb) ? 'deadline_status')
      )
      OR EXISTS (
        SELECT 1
        FROM document_deadlines dd
        WHERE dd.document_id = target_document_id
          AND dd.status IN ('open', 'due_soon', 'overdue', 'needs_review')
          AND (
            NOT (COALESCE(saved_query, '{}'::jsonb) ? 'deadlineTypes')
            OR dd.deadline_type::text = ANY (
              SELECT jsonb_array_elements_text(saved_query -> 'deadlineTypes')
            )
          )
          AND (
            NOT (COALESCE(saved_query, '{}'::jsonb) ? 'deadline_type')
            OR dd.deadline_type::text = ANY (
              SELECT jsonb_array_elements_text(
                CASE
                  WHEN jsonb_typeof(saved_query -> 'deadline_type') = 'array' THEN saved_query -> 'deadline_type'
                  ELSE jsonb_build_array(saved_query ->> 'deadline_type')
                END
              )
            )
          )
          AND (
            NOT (COALESCE(saved_query, '{}'::jsonb) ? 'deadlineStatuses')
            OR dd.status = ANY (
              SELECT jsonb_array_elements_text(saved_query -> 'deadlineStatuses')
            )
          )
          AND (
            NOT (COALESCE(saved_query, '{}'::jsonb) ? 'deadline_status')
            OR dd.status = ANY (
              SELECT jsonb_array_elements_text(
                CASE
                  WHEN jsonb_typeof(saved_query -> 'deadline_status') = 'array' THEN saved_query -> 'deadline_status'
                  ELSE jsonb_build_array(saved_query ->> 'deadline_status')
                END
              )
            )
          )
      )
    );
$$;
