SET search_path TO structura, public;

ALTER TABLE document_deadlines
  DROP CONSTRAINT IF EXISTS document_deadlines_status_check;

ALTER TABLE document_deadlines
  ADD CONSTRAINT document_deadlines_status_check
  CHECK (status IN ('open', 'due_soon', 'overdue', 'snoozed', 'resolved', 'waived', 'needs_review'));
