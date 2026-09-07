-- Retained candidate generations share source/run/job references with document
-- cascades. Check these cross-branch NO ACTION references at transaction commit,
-- after every branch of a whole-document deletion has run. Independent deletion
-- still fails: existing history triggers reject it, or these FKs reject commit.
-- This is additive; migrations 096/098 may already be applied.
SET search_path TO structura, public;

DO $$
DECLARE edge record; edge_oids oid[]; edge_pair_count integer;
BEGIN
  -- Match reviewed relation pairs, not PostgreSQL's truncated generated names.
  -- CASCADE/SET NULL edges, actor authority FKs and unrelated tables are unchanged.
  SELECT array_agg(c.oid), count(DISTINCT ROW(c.conrelid,c.confrelid))
    INTO edge_oids,edge_pair_count
    FROM pg_constraint c
    JOIN (VALUES
      ('document_processing_runs'::regclass, 'document_assets'::regclass),
      ('document_index_generations'::regclass, 'document_processing_runs'::regclass),
      ('document_index_generations'::regclass, 'pipeline_jobs'::regclass),
      ('document_generation_render_assets'::regclass, 'document_assets'::regclass),
      ('document_generation_render_assets'::regclass, 'document_parse_page_checkpoints'::regclass),
      ('document_index_inputs'::regclass, 'document_generation_render_assets'::regclass)
    ) AS expected(child_relation, parent_relation)
      ON c.conrelid=expected.child_relation AND c.confrelid=expected.parent_relation
    WHERE c.contype='f';
  IF cardinality(edge_oids) IS DISTINCT FROM 6 OR edge_pair_count<>6 OR EXISTS (
    SELECT 1 FROM pg_constraint c WHERE c.oid=ANY(edge_oids) AND c.confdeltype<>'a'
  ) THEN
    RAISE EXCEPTION 'Generation retention requires exactly six reviewed NO ACTION edges';
  END IF;
  FOR edge IN
    SELECT c.conrelid::regclass AS relation_name,c.conname
    FROM pg_constraint c WHERE c.oid=ANY(edge_oids) ORDER BY c.conrelid,c.conname
  LOOP
    EXECUTE format('ALTER TABLE %s ALTER CONSTRAINT %I DEFERRABLE INITIALLY DEFERRED',
      edge.relation_name, edge.conname);
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint c
      WHERE c.conrelid=edge.relation_name AND c.conname=edge.conname
        AND c.contype='f' AND c.confdeltype='a' AND c.condeferrable AND c.condeferred
    ) THEN
      RAISE EXCEPTION 'Generation retention edge did not acquire deferred commit validation';
    END IF;
  END LOOP;
END;
$$;
