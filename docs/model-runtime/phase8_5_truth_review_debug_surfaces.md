# Phase 8.5 Truth, Review, Debug, And Analysis Readiness

Phase 8.5 model output is not a general-purpose truth source. Future Phase 9 analysis must
consume the bounded intake projection from `lib.documents.analysis_intake`, not raw document
detail payloads or model debug artifacts.

## Truth Surface

Truth is limited to accepted user/product facts:

- accepted canonical fields
- accepted canonical line items
- promoted or accepted canonical observations
- user-confirmed or user-corrected facts

These may be used directly by product UI and Phase 9 context builders.

## Review Surface

Review material is assistive and must carry uncertainty labels:

- review-required field candidates
- review-required line-item candidates
- review-required observation candidates
- rejected candidate summaries
- uncertain observations
- evidence refs
- planner explanations
- quality signals

Phase 9 may cite this material only as uncertain or review-required context.

## Debug Surface

Debug material is never truth and must not be standalone factual context:

- raw model output
- prompt versions
- visual plan internals
- region envelopes
- normalization repairs
- model-output payloads
- adapter traces

The analysis intake reports debug surfaces as excluded from truth and exposes only bounded
references needed for diagnostics.

## Eligibility And Mutation Policy

`phase9_document_eligibility()` gates document analysis using operational status, accepted fact
coverage, candidate coverage, evidence locator coverage, and admitted-artifact regressions.

Phase 9 outputs are read-only unless an explicit user action routes through the existing review,
relationship, filing, deadline, or canonical-fact mutation APIs. Analysis output must not directly
mutate canonical facts, relationships, folders, tags, deadlines, review tasks, or review status.
