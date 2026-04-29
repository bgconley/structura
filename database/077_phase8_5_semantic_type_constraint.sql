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
      'retail_order_line_item_table',
      'service_record_line_item_table',
      'receipt_payment_summary',
      'denial_or_coverage_decision',
      'appeal_or_next_steps',
      'seller_information_block',
      'escrow_summary',
      'mortgage_payment_summary',
      'dispute_transaction_table',
      'dispute_reason_block',
      'generic_form_kvp',
      'no_extraction_target',
      'unsupported_document_region',
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
