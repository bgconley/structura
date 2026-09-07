SET search_path TO structura, public;

ALTER TABLE tags ADD COLUMN IF NOT EXISTS household_id uuid
  REFERENCES households(id) ON DELETE RESTRICT;
ALTER TABLE tags DROP CONSTRAINT IF EXISTS tags_name_key;

CREATE UNIQUE INDEX IF NOT EXISTS tags_household_name_uidx
  ON tags (household_id, lower(name::text)) WHERE household_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS tags_system_name_uidx
  ON tags (lower(name::text)) WHERE is_system;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'structura.tags'::regclass AND conname = 'tags_system_scope_check'
  ) THEN
    ALTER TABLE tags ADD CONSTRAINT tags_system_scope_check
      CHECK (NOT is_system OR household_id IS NULL);
  END IF;
END $$;

-- Keep old IDs and the migration mapping for historical references. A custom
-- NULL-household row is legacy, never a globally visible user tag.
CREATE TABLE IF NOT EXISTS tag_household_migrations (
  legacy_tag_id uuid NOT NULL REFERENCES tags(id) ON DELETE RESTRICT,
  household_id uuid NOT NULL REFERENCES households(id) ON DELETE RESTRICT,
  scoped_tag_id uuid NOT NULL REFERENCES tags(id) ON DELETE RESTRICT,
  legacy_name text NOT NULL,
  migrated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (legacy_tag_id, household_id),
  UNIQUE (scoped_tag_id)
);

DO $$
DECLARE
  legacy_tag record;
  linked_households uuid[];
  target_household uuid;
  target_tag uuid;
BEGIN
  -- Include soft-deleted documents: a restore must retain their filing history.
  FOR legacy_tag IN
    SELECT * FROM tags WHERE household_id IS NULL AND NOT is_system ORDER BY id
  LOOP
    SELECT array_agg(DISTINCT d.household_id ORDER BY d.household_id)
      INTO linked_households
    FROM document_tags dt JOIN documents d ON d.id = dt.document_id
    WHERE dt.tag_id = legacy_tag.id AND d.household_id IS NOT NULL;

    IF cardinality(linked_households) = 1 THEN
      -- A single observed household can retain the existing tag ID.
      target_household := linked_households[1];
      UPDATE tags SET household_id = target_household WHERE id = legacy_tag.id;
      INSERT INTO tag_household_migrations
        (legacy_tag_id, household_id, scoped_tag_id, legacy_name)
      VALUES (legacy_tag.id, target_household, legacy_tag.id, legacy_tag.name)
      ON CONFLICT (legacy_tag_id, household_id) DO NOTHING;
    ELSIF cardinality(linked_households) > 1 THEN
      FOREACH target_household IN ARRAY linked_households LOOP
        INSERT INTO tags
          (name, color_hex, description, is_system, household_id, created_at, updated_at)
        VALUES
          (legacy_tag.name, legacy_tag.color_hex, legacy_tag.description, false,
           target_household, legacy_tag.created_at, legacy_tag.updated_at)
        RETURNING id INTO target_tag;
        INSERT INTO tag_household_migrations
          (legacy_tag_id, household_id, scoped_tag_id, legacy_name)
        VALUES (legacy_tag.id, target_household, target_tag, legacy_tag.name);
        UPDATE document_tags dt SET tag_id = target_tag
        FROM documents d
        WHERE dt.document_id = d.id AND dt.tag_id = legacy_tag.id
          AND d.household_id = target_household;
      END LOOP;
    END IF;
    -- No observed household: retain the legacy row privately. Do not infer an
    -- owner from the current administrator or expose it to every household.
  END LOOP;
END $$;
