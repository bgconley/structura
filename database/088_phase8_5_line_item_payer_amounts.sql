-- Phase 8.5: preserve payer-side service-line amounts on line-item candidates.
-- Medical EOB service lines carry allowed and plan-paid amounts through the
-- constrained Granite contract, region envelope, and Claim projection; the
-- candidate row must not silently drop them.

ALTER TABLE line_item_candidates
  ADD COLUMN IF NOT EXISTS allowed_amount numeric(18,4),
  ADD COLUMN IF NOT EXISTS plan_paid_amount numeric(18,4);
