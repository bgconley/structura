SET search_path TO structura, public;

UPDATE semantic_extraction_plan_tasks task
SET page_number = COALESCE(psa.page_number, dp.page_number, dep.page_number, dtp.page_number)
FROM semantic_region_annotations region
LEFT JOIN page_semantic_annotations psa ON psa.id = region.page_annotation_id
LEFT JOIN document_pages dp ON dp.id = region.page_id
LEFT JOIN document_elements de ON de.id = region.element_id
LEFT JOIN document_pages dep ON dep.id = de.page_id
LEFT JOIN document_tables dt ON dt.id = region.table_id
LEFT JOIN document_pages dtp ON dtp.id = dt.page_id
WHERE task.semantic_region_id = region.id
  AND task.page_number IS NULL
  AND COALESCE(psa.page_number, dp.page_number, dep.page_number, dtp.page_number) IS NOT NULL;
