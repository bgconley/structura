SET search_path TO structura, public;

ALTER TABLE semantic_region_annotations
  DROP CONSTRAINT IF EXISTS semantic_region_annotations_semantic_type_check;

ALTER TABLE semantic_region_annotations
  ADD CONSTRAINT semantic_region_annotations_semantic_type_check
  CHECK (
    semantic_type IN (
      'document_header',
      'billing_summary',
      'payment_summary',
      'patient_responsibility_summary',
      'covered_services_line_item_table',
      'invoice_line_item_table',
      'receipt_line_item_table',
      'service_record_line_item_table',
      'denial_or_coverage_decision',
      'appeal_or_next_steps',
      'tax_summary',
      'legal_clause',
      'contact_block',
      'vehicle_or_asset_block',
      'signature_block',
      'boilerplate',
      'unmatched_region',
      'unknown'
    )
  );
