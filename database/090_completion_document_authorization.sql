SET search_path TO structura, public;

-- Keep the caller signature for existing read projections. Authority comes from
-- current membership, never from p_household_role supplied by a caller.
CREATE OR REPLACE FUNCTION document_is_readable(
  p_document_id uuid, p_household_id uuid, p_user_id uuid, p_household_role text
)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1
    FROM documents d
    JOIN household_memberships hm
      ON hm.household_id = d.household_id AND hm.user_id = p_user_id
    JOIN users u ON u.id = hm.user_id AND NOT u.is_disabled
    WHERE d.id = p_document_id
      AND d.deleted_at IS NULL
      AND d.household_id = p_household_id
      AND (
        d.owner_user_id = p_user_id OR hm.role IN ('owner', 'admin')
        OR (
          d.acl_mode = 'household' AND d.sensitivity::text <> 'highly_sensitive'
          AND EXISTS (
            SELECT 1 FROM folders f
            WHERE f.id = d.primary_folder_id
              AND (f.household_id = p_household_id OR (f.household_id IS NULL AND f.is_system))
              AND (
                f.acl_mode = 'household' OR f.owner_user_id = p_user_id
                OR EXISTS (
                  SELECT 1 FROM folder_acl fa
                  WHERE fa.folder_id = f.id AND fa.permission IN ('read', 'write', 'admin')
                    AND (
                      (fa.principal_type = 'user' AND fa.principal_id = p_user_id)
                      OR (fa.principal_type = 'household' AND fa.principal_id = p_household_id)
                    )
                )
              )
          )
        )
      )
  );
$$;

CREATE OR REPLACE FUNCTION document_is_writable(
  p_document_id uuid, p_household_id uuid, p_user_id uuid, p_household_role text
)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1
    FROM documents d
    JOIN household_memberships hm
      ON hm.household_id = d.household_id AND hm.user_id = p_user_id
    JOIN users u ON u.id = hm.user_id AND NOT u.is_disabled
    WHERE d.id = p_document_id
      AND d.deleted_at IS NULL
      AND d.household_id = p_household_id
      AND hm.role IN ('owner', 'admin', 'member')
      AND (
        d.owner_user_id = p_user_id OR hm.role IN ('owner', 'admin')
        OR (
          d.acl_mode = 'household' AND d.sensitivity::text <> 'highly_sensitive'
          AND EXISTS (
            SELECT 1 FROM folders f
            WHERE f.id = d.primary_folder_id
              AND (f.household_id = p_household_id OR (f.household_id IS NULL AND f.is_system))
              AND (
                f.acl_mode = 'household' OR f.owner_user_id = p_user_id
                OR EXISTS (
                  SELECT 1 FROM folder_acl fa
                  WHERE fa.folder_id = f.id AND fa.permission IN ('write', 'admin')
                    AND (
                      (fa.principal_type = 'user' AND fa.principal_id = p_user_id)
                      OR (fa.principal_type = 'household' AND fa.principal_id = p_household_id)
                    )
                )
              )
          )
        )
      )
  );
$$;
