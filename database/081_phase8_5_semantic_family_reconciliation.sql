SET search_path TO structura, public;

ALTER TYPE document_family_enum ADD VALUE IF NOT EXISTS 'retail_order';
ALTER TYPE document_family_enum ADD VALUE IF NOT EXISTS 'service_record';
ALTER TYPE document_family_enum ADD VALUE IF NOT EXISTS 'insurance_denial';
ALTER TYPE document_family_enum ADD VALUE IF NOT EXISTS 'real_estate_title';
ALTER TYPE document_family_enum ADD VALUE IF NOT EXISTS 'mortgage_escrow_statement';
ALTER TYPE document_family_enum ADD VALUE IF NOT EXISTS 'financial_dispute_form';
