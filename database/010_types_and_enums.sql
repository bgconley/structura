CREATE SCHEMA IF NOT EXISTS structura;
SET search_path TO structura, public;

CREATE TYPE document_family_enum AS ENUM (
  'generic',
  'receipt',
  'invoice',
  'medical_eob',
  'medical_bill',
  'insurance_document',
  'legal_contract',
  'legal_notice',
  'tax_document',
  'warranty',
  'identity_document',
  'bank_statement',
  'financial_statement',
  'handwritten_note',
  'typed_note',
  'whitepaper',
  'reference_document'
);

CREATE TYPE ingestion_source_enum AS ENUM (
  'web_upload',
  'api_upload',
  'watched_folder',
  'email_import',
  'mobile_scan',
  'bulk_import'
);

CREATE TYPE lifecycle_state_enum AS ENUM (
  'inbox',
  'filed',
  'archived',
  'deleted'
);

CREATE TYPE review_status_enum AS ENUM (
  'unreviewed',
  'auto_accepted',
  'needs_review',
  'user_confirmed',
  'user_corrected',
  'rejected'
);

CREATE TYPE asset_role_enum AS ENUM (
  'original',
  'normalized_pdf',
  'page_image',
  'thumbnail',
  'docling_json',
  'docling_md',
  'docling_html',
  'raw_model_output',
  'normalized_extraction_json',
  'export_bundle'
);

CREATE TYPE storage_backend_enum AS ENUM (
  'filesystem',
  's3'
);

CREATE TYPE element_type_enum AS ENUM (
  'paragraph',
  'heading',
  'table',
  'figure',
  'form_field',
  'checkbox',
  'signature',
  'header',
  'footer',
  'caption',
  'list_item',
  'key_value_pair',
  'code_block',
  'other'
);

CREATE TYPE model_source_enum AS ENUM (
  'docling',
  'qwen3_vl_4b',
  'qwen3_vl_8b',
  'granite_vision_3b',
  'validator',
  'human',
  'system'
);

CREATE TYPE extraction_status_enum AS ENUM (
  'pending',
  'completed',
  'failed',
  'superseded',
  'accepted',
  'rejected'
);

CREATE TYPE field_value_type_enum AS ENUM (
  'string',
  'integer',
  'number',
  'boolean',
  'date',
  'datetime',
  'json',
  'money'
);

CREATE TYPE line_item_type_enum AS ENUM (
  'generic',
  'receipt_item',
  'invoice_item',
  'service_line',
  'payment',
  'tax',
  'adjustment',
  'fee'
);

CREATE TYPE relationship_type_enum AS ENUM (
  'duplicate_of',
  'related_to',
  'invoice_for',
  'receipt_for',
  'eob_for',
  'bill_for',
  'amendment_to',
  'renewal_of',
  'attachment_to',
  'warranty_for',
  'proof_of_payment_for'
);

CREATE TYPE modality_enum AS ENUM (
  'text',
  'visual',
  'mixed'
);

CREATE TYPE sensitivity_enum AS ENUM (
  'normal',
  'pii',
  'financial',
  'medical',
  'legal',
  'highly_sensitive'
);

CREATE TYPE auth_method_enum AS ENUM (
  'password',
  'magic_link',
  'webauthn'
);

CREATE TYPE job_type_enum AS ENUM (
  'ingest',
  'preview',
  'docling_convert',
  'classify',
  'extract',
  'embed',
  'rerank',
  'relate',
  'analyze',
  'export'
);

CREATE TYPE job_status_enum AS ENUM (
  'queued',
  'leased',
  'running',
  'succeeded',
  'failed',
  'cancelled',
  'dead_letter'
);

CREATE TYPE deadline_type_enum AS ENUM (
  'due_date',
  'renewal_date',
  'warranty_expiration',
  'response_deadline',
  'filing_deadline',
  'appointment_date'
);

CREATE TYPE analysis_note_type_enum AS ENUM (
  'summary',
  'explanation',
  'comparison',
  'timeline',
  'obligation_scan',
  'tax_scan',
  'medical_explanation'
);

CREATE TYPE party_type_enum AS ENUM (
  'person',
  'organization',
  'provider',
  'payer',
  'merchant',
  'government',
  'law_firm',
  'insurer'
);

CREATE TYPE folder_kind_enum AS ENUM (
  'manual',
  'smart'
);

CREATE TYPE review_task_status_enum AS ENUM (
  'open',
  'in_progress',
  'resolved',
  'waived'
);

CREATE TYPE embedding_owner_type_enum AS ENUM (
  'document',
  'page',
  'chunk',
  'element',
  'asset'
);
