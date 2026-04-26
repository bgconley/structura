SET search_path TO structura, public;

ALTER TABLE watched_folders
  ADD COLUMN IF NOT EXISTS owner_user_id uuid REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE filing_rule_runs
  ADD COLUMN IF NOT EXISTS blocked_actions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS decision_status text NOT NULL DEFAULT 'recorded',
  ADD COLUMN IF NOT EXISTS actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE filing_rule_runs
  DROP CONSTRAINT IF EXISTS filing_rule_runs_decision_status_check;

ALTER TABLE filing_rule_runs
  ADD CONSTRAINT filing_rule_runs_decision_status_check
  CHECK (
    decision_status IN (
      'recorded',
      'pending',
      'accepted',
      'rejected',
      'deferred',
      'applied',
      'not_matched'
    )
  );

CREATE INDEX IF NOT EXISTS contacts_household_normalized_idx
  ON contacts (household_id, normalized_name);

CREATE INDEX IF NOT EXISTS contact_aliases_alias_idx
  ON contact_aliases (alias);

CREATE INDEX IF NOT EXISTS filing_rule_runs_pending_suggestions_idx
  ON filing_rule_runs (rule_id, document_id, decision_status, created_at DESC)
  WHERE mode = 'suggest';

CREATE INDEX IF NOT EXISTS watched_folders_owner_idx
  ON watched_folders (owner_user_id)
  WHERE owner_user_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_filing_rule_runs_updated_at ON filing_rule_runs;
CREATE TRIGGER trg_filing_rule_runs_updated_at
BEFORE UPDATE ON filing_rule_runs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
