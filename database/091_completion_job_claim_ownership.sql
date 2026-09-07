-- JOB-01: attempt identity is internal; it is never part of public job DTOs.
-- Deploy with workers drained/stopped. Pre-migration tokenless running rows
-- remain untouched until their existing lease expires, then normal recovery
-- requeues/dead-letters them. Do not run old workers beside token-aware workers.
SET search_path TO structura, public;

ALTER TABLE pipeline_jobs ADD COLUMN claim_token uuid;

COMMENT ON COLUMN pipeline_jobs.claim_token IS
  'Opaque execution-attempt ownership; replaced on claim and revoked at termination/retry.';
