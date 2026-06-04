SET search_path TO structura, public;

ALTER TABLE semantic_extraction_plan_tasks
  ADD COLUMN IF NOT EXISTS visual_plan_summary jsonb;

ALTER TABLE semantic_extraction_plan_tasks
  DROP CONSTRAINT IF EXISTS semantic_extraction_plan_tasks_visual_plan_summary_object_check;

ALTER TABLE semantic_extraction_plan_tasks
  ADD CONSTRAINT semantic_extraction_plan_tasks_visual_plan_summary_object_check
  CHECK (
    visual_plan_summary IS NULL
    OR jsonb_typeof(visual_plan_summary) = 'object'
  );
