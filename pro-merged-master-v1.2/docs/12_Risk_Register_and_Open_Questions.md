# Risk register and open questions

## 1. Major risks

### Risk 1 - false trust from neat-looking extraction
Impact: high  
Mitigation:
- evidence-backed fields
- schema validation
- arithmetic checks
- review queue

### Risk 2 - canonical parse quality varies widely across source types
Impact: high  
Mitigation:
- store parse quality signals
- route difficult documents differently
- expose debug tooling early

### Risk 3 - model-serving memory pressure
Impact: medium to high  
Mitigation:
- split workloads across GPUs
- standardize dimensions and model choices
- avoid always-on heavyweight analysis

### Risk 4 - search quality disappointment
Impact: high  
Mitigation:
- benchmark early
- use hybrid retrieval
- tune chunking and filters with a golden corpus

### Risk 5 - storage sprawl
Impact: medium  
Mitigation:
- content-addressed artifacts
- retention rules for cache-like derivatives
- separate datasets by purpose

### Risk 6 - operational fragility from too many moving parts
Impact: medium  
Mitigation:
- Compose first
- boring worker model
- minimal service count at start

### Risk 7 - handwriting accuracy remains poor
Impact: medium  
Mitigation:
- review-required default
- selective routing
- clear uncertainty presentation

## 2. Open questions

- What exact embedding model and dimension should be locked for v1 production indexing?
- Should page-level visual embeddings be included in general search by default or only as an advanced mode?
- Which document families deserve normalized relational tables beyond the generic field and line-item model?
- Is redaction needed in v1, or can export stay original-plus-structured only?
- Does the product need a local email-ingestion path in the first serious release, or is upload enough?
- How aggressive should duplicate detection become beyond exact file hashes?
- Should analysis notes be editable by users after generation, or remain immutable artifacts?

## 3. Triggers for revisiting architecture

Revisit the baseline architecture if:
- the corpus size grows well beyond expected single-node comfort;
- multi-user support becomes near-term;
- model-serving throughput becomes a bottleneck;
- a different canonical parser clearly outperforms Docling for the dominant document mix.

## 4. Suggested review cadence

- review risks after Phase 2
- review again after Phase 4 benchmark results
- review before any decision to move to k3s
