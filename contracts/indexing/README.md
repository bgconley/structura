# Native candidate indexing contracts

Status: root-approved bounded storage foundation, pending canonical migration-098
validation. No worker, HTTP endpoint, model call, default retrieval path or active
index pointer uses these contracts yet.

The JSON schemas mirror `lib/search/indexing` frozen types. Python validation
additionally checks the complete current v2 profile/protocol, ordered complete
page/input inventory, exact sealed parse projection, generation-owned render
identity and float32 vector validity. JSON schema validity alone is insufficient.

`native_parse_only_v1` preserves source chunks and origins. Facts and filing
metadata are explicitly `not_collected`. `native_visual_eligibility_v1` includes
original image pages, PDF pages with fewer than 32 stripped native-text characters,
pages with at least two tables or figures, and partial/insufficient parse pages.
Every source page has a disposition, including zero eligibility/not requested and
whitespace-only chunk IDs. This policy is not a validated recall threshold.
Only visually eligible page renders are registered in this slice; all-page Viewer
render registration remains an activation prerequisite.

Preparation verifies each content-addressed PNG outside its DB transaction,
atomically registers the bounded complete input set, and verifies bytes again
after commit. The second read catches cleanup that won before registration. A
missing object leaves a blocked/resumable candidate, never a successful vector.
Sealing snapshots the exact registered assets under authority, verifies all bytes
outside the transaction, and then applies a fresh DB seal fence. Missing or changed
bytes after vector checkpointing refuse completion. Restore only identical sealed
bytes. Future model execution must read and verify
these same bytes immediately before inference; a caller-supplied descriptor or
response is not proof of a live invocation.

The candidate uses its exact still-desired processing run and current claimed
producer job. It cannot be resumed by an unrelated job or after independent run or
index supersession. The reserved event schema is not enqueued yet; a future
candidate worker needs inherited immutable job binding and a new execution seam.
Reindexing a historical parse needs separate durable request authority, not revival
of its cancelled or superseded parse creator.

Vectors are validated against fixed text1536/visual2048 v2 spaces and canonicalized
to float32 before hashing. Repeated checkpoint content is accepted; changing a
vector, invocation identity or model declaration under the same input is rejected.
Sealing deeply recomputes projection/input parity and requires exactly every
eligible input, with explicit zero denominators. Completion records keep live
invocation attestation and retrieval quality `not_evaluated`.

The header/input/source/vector tables are hidden candidates, preserve history and
never populate legacy current tables. See the [design and remaining gates](../../docs/plans/production-completion/native-index-generations.md).
