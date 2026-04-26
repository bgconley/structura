SET search_path TO structura, public;

CREATE OR REPLACE FUNCTION document_matches_saved_query(
  target_document_id uuid,
  saved_query jsonb
)
RETURNS boolean
LANGUAGE SQL
STABLE
AS $$
  SELECT COALESCE(
    (
      SELECT bool_and(query_key IN (
        'amountMax',
        'amountMin',
        'dateFrom',
        'dateTo',
        'document_family',
        'families',
        'folderIds',
        'folder_ids',
        'open_review_tasks',
        'primaryFolderOnly',
        'primary_folder_only',
        'reviewStatuses',
        'review_status',
        'reviewedOnly',
        'reviewed_only',
        'sensitivity',
        'tag_names',
        'tags'
      ))
      FROM jsonb_object_keys(COALESCE(saved_query, '{}'::jsonb)) AS keys(query_key)
    ),
    true
  )
  AND EXISTS (
    SELECT 1
    FROM documents d
    LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
    WHERE d.id = target_document_id
      AND (
        NOT (saved_query ? 'review_status')
        OR d.review_status::text IN (
          SELECT jsonb_array_elements_text(saved_query -> 'review_status')
        )
      )
      AND (
        NOT (saved_query ? 'reviewStatuses')
        OR d.review_status::text IN (
          SELECT jsonb_array_elements_text(saved_query -> 'reviewStatuses')
        )
      )
      AND (
        NOT (saved_query ? 'reviewedOnly')
        OR (
          (saved_query ->> 'reviewedOnly')::boolean IS TRUE
          AND d.review_status::text IN ('auto_accepted', 'user_confirmed', 'user_corrected')
        )
        OR (
          (saved_query ->> 'reviewedOnly')::boolean IS FALSE
          AND d.review_status::text NOT IN ('user_confirmed', 'user_corrected')
        )
      )
      AND (
        NOT (saved_query ? 'reviewed_only')
        OR (
          (saved_query ->> 'reviewed_only')::boolean IS TRUE
          AND d.review_status::text IN ('auto_accepted', 'user_confirmed', 'user_corrected')
        )
        OR (
          (saved_query ->> 'reviewed_only')::boolean IS FALSE
          AND d.review_status::text NOT IN ('user_confirmed', 'user_corrected')
        )
      )
      AND (
        NOT (saved_query ? 'document_family')
        OR d.document_family::text IN (
          SELECT jsonb_array_elements_text(saved_query -> 'document_family')
        )
      )
      AND (
        NOT (saved_query ? 'families')
        OR d.document_family::text IN (
          SELECT jsonb_array_elements_text(saved_query -> 'families')
        )
      )
      AND (
        NOT (saved_query ? 'sensitivity')
        OR d.sensitivity::text IN (
          SELECT jsonb_array_elements_text(saved_query -> 'sensitivity')
        )
      )
      AND (
        NOT (saved_query ? 'tags')
        OR EXISTS (
          SELECT 1
          FROM document_tags dt
          JOIN tags t ON t.id = dt.tag_id
          WHERE dt.document_id = d.id
            AND lower(t.name::text) IN (
              SELECT lower(tag_name.value)
              FROM jsonb_array_elements_text(saved_query -> 'tags') AS tag_name(value)
            )
        )
      )
      AND (
        NOT (saved_query ? 'tag_names')
        OR EXISTS (
          SELECT 1
          FROM document_tags dt
          JOIN tags t ON t.id = dt.tag_id
          WHERE dt.document_id = d.id
            AND lower(t.name::text) IN (
              SELECT lower(tag_name.value)
              FROM jsonb_array_elements_text(saved_query -> 'tag_names') AS tag_name(value)
            )
        )
      )
      AND (
        NOT (saved_query ? 'folderIds')
        OR EXISTS (
          SELECT 1
          FROM document_folder_memberships dfm
          WHERE dfm.document_id = d.id
            AND dfm.folder_id IN (
              SELECT value::uuid
              FROM jsonb_array_elements_text(saved_query -> 'folderIds') AS folder_id(value)
            )
        )
      )
      AND (
        NOT (saved_query ? 'folder_ids')
        OR EXISTS (
          SELECT 1
          FROM document_folder_memberships dfm
          WHERE dfm.document_id = d.id
            AND dfm.folder_id IN (
              SELECT value::uuid
              FROM jsonb_array_elements_text(saved_query -> 'folder_ids') AS folder_id(value)
            )
        )
      )
      AND (
        NOT (saved_query ? 'dateFrom')
        OR d.document_date >= (saved_query ->> 'dateFrom')::date
      )
      AND (
        NOT (saved_query ? 'dateTo')
        OR d.document_date <= (saved_query ->> 'dateTo')::date
      )
      AND (
        NOT (saved_query ? 'amountMin')
        OR a.total_amount >= (saved_query ->> 'amountMin')::numeric
      )
      AND (
        NOT (saved_query ? 'amountMax')
        OR a.total_amount <= (saved_query ->> 'amountMax')::numeric
      )
      AND (
        COALESCE((saved_query ->> 'open_review_tasks')::boolean, false) = false
        OR EXISTS (
          SELECT 1
          FROM review_tasks rt
          WHERE rt.document_id = d.id
            AND rt.status IN ('open', 'in_progress')
        )
      )
  );
$$;
