SET search_path TO structura, public;

-- Model-service probe snapshots are now persisted through
-- service_health_snapshots; allow the probe statuses alongside the
-- original worker heartbeat statuses.
ALTER TABLE service_health_snapshots
  DROP CONSTRAINT IF EXISTS service_health_snapshots_status_check;

ALTER TABLE service_health_snapshots
  ADD CONSTRAINT service_health_snapshots_status_check
  CHECK (status IN ('ok', 'degraded', 'down', 'unknown', 'fixture', 'unavailable'));

-- Support the admin latest-per-service query and time-windowed health
-- history reads.
CREATE INDEX IF NOT EXISTS service_health_snapshots_service_checked_idx
  ON service_health_snapshots (service_name, checked_at DESC);
