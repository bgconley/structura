SET search_path TO structura, public;

DROP INDEX IF EXISTS folders_parent_name_uniq;

CREATE UNIQUE INDEX IF NOT EXISTS folders_household_parent_name_uniq
  ON folders (
    household_id,
    COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid),
    lower(name)
  )
  WHERE household_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS folders_system_parent_name_uniq
  ON folders (
    COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid),
    lower(name)
  )
  WHERE household_id IS NULL;
