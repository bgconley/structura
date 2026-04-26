SET search_path TO structura, public;

DROP FUNCTION IF EXISTS document_is_readable(uuid, uuid, uuid, text);

CREATE FUNCTION document_is_readable(
  p_document_id uuid,
  p_household_id uuid,
  p_user_id uuid,
  p_household_role text
)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM documents d
    WHERE d.id = p_document_id
      AND d.deleted_at IS NULL
      AND d.household_id = p_household_id
      AND (
        d.owner_user_id = p_user_id
        OR p_household_role IN ('owner', 'admin')
        OR (
          d.acl_mode = 'household'
          AND d.sensitivity::text <> 'highly_sensitive'
          AND EXISTS (
            SELECT 1
            FROM folders document_access_folder
            WHERE document_access_folder.id = d.primary_folder_id
              AND (
                document_access_folder.acl_mode = 'household'
                OR document_access_folder.owner_user_id = p_user_id
                OR EXISTS (
                  SELECT 1
                  FROM folder_acl document_access_acl
                  WHERE document_access_acl.folder_id = document_access_folder.id
                    AND document_access_acl.permission IN ('read', 'write', 'admin')
                    AND (
                      (
                        document_access_acl.principal_type = 'user'
                        AND document_access_acl.principal_id = p_user_id
                      )
                      OR (
                        document_access_acl.principal_type = 'household'
                        AND document_access_acl.principal_id = p_household_id
                      )
                    )
                )
              )
          )
        )
      )
  );
$$;
