SET search_path TO structura, public;

-- System folders
INSERT INTO folders (parent_id, folder_kind, name, description, path_cache, sort_order, is_system)
VALUES
  (NULL, 'manual', 'Inbox', 'New or unfiled documents', '/Inbox', 10, true),
  (NULL, 'manual', 'Receipts', 'Purchase receipts', '/Receipts', 20, true),
  (NULL, 'manual', 'Invoices', 'Bills and invoices', '/Invoices', 30, true),
  (NULL, 'manual', 'Medical', 'Medical and insurance records', '/Medical', 40, true),
  (NULL, 'manual', 'Legal', 'Legal notices and contracts', '/Legal', 50, true),
  (NULL, 'manual', 'Taxes', 'Tax-relevant documents', '/Taxes', 60, true),
  (NULL, 'manual', 'Warranties', 'Warranty and return documentation', '/Warranties', 70, true),
  (NULL, 'manual', 'Vehicles', 'Vehicle purchases and service', '/Vehicles', 80, true),
  (NULL, 'manual', 'Home', 'Home and property records', '/Home', 90, true),
  (NULL, 'manual', 'Archive', 'Long-term retained records', '/Archive', 100, true)
ON CONFLICT DO NOTHING;

-- Smart folders
INSERT INTO folders (parent_id, folder_kind, name, description, path_cache, saved_query_json, sort_order, is_system)
VALUES
  (NULL, 'smart', 'Needs Review', 'Documents with open review tasks or review-required status', '/Needs Review', '{"review_status":["needs_review"],"open_review_tasks":true}', 110, true),
  (NULL, 'smart', 'Tax Relevant', 'Documents tagged or typed as tax relevant', '/Tax Relevant', '{"tag_names":["tax-relevant"]}', 120, true),
  (NULL, 'smart', 'Warranties Expiring Soon', 'Warranty documents with upcoming deadline', '/Warranties Expiring Soon', '{"deadline_type":["warranty_expiration"]}', 130, true)
ON CONFLICT DO NOTHING;

INSERT INTO tags (name, color_hex, description, is_system)
VALUES
  ('tax-relevant', '#8B5CF6', 'Potentially relevant to taxes', true),
  ('urgent', '#DC2626', 'Needs timely review or action', true),
  ('medical', '#0EA5E9', 'Medical or insurance related', true),
  ('legal', '#334155', 'Legal related', true),
  ('warranty', '#F59E0B', 'Warranty or return related', true),
  ('vehicle', '#059669', 'Vehicle related', true),
  ('home', '#A16207', 'Home / property related', true),
  ('reimbursable', '#2563EB', 'Candidate for reimbursement', true)
ON CONFLICT DO NOTHING;
