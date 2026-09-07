# Persisted Oxcart-to-Blackbird indexing checkpoint

Date: 2026-09-07. Candidate: `a23d04102c04c7ee1efeca66b9c60df7370b07c9`.
Evidence: [public synthetic summary](native-index-a23d041.json).

## Result and scope

One source-authored two-page TIFF passed the actual 27B parse → saved native
structure → Blackbird document/page embeddings → saved PostgreSQL vectors →
compatible text/visual queries path. The probe used an isolated database and
protected object/evidence directories, with no Docling call. It did not activate
ordinary application ingestion, publication or search.

The resident Oxcart Qwen3.8-27B BF16 service made two observed adapter calls, one per
page. Parse replay made zero additional calls. Blackbird's PRO 4000 generated
six 1,536-dimensional document text vectors and two 2,048-dimensional page-image
vectors through eight observed HTTP requests. The first bounded execution saved
one vector; the second resumed it and saved the remaining seven. Sealed replay
made zero additional requests and retained identical manifest/checkpoint/vector
and completion bytes. Each saved result retained its reported model and declared
profile/artifact/input identity.

Two frozen queries ran in both vector spaces: one text batch request and two
visual query requests. All four ranked the expected source page first. Rankings
used actual rehashed pgvector values. A separate offline check reconstructed all
eight checkpoint/vector hashes and all four query bindings and complete rankings
from the protected bundle after the test database was dropped, without model calls.
This is an exposed two-page regression, not representative retrieval acceptance.

The first indexing pass took 179 ms, the resumed pass 1,139 ms and sealed replay
196 ms. The two-query text batch reported 46 ms; the two visual requests together
reported 51 ms. These are one-run measurements, not p50/p95, service capacity or
production search latency. Earlier cold-start spikes and shared-client admission
requirements remain open.

## Source scoring and interpretation

Both source pages were inventoried and scored. All 12 annotated text tokens and
all four cells in the one table matched exactly, with no scored text insertion or
omission. Source-original and reproduced-render identities were verified.

The retained region scores are 3/4 matches on page 1 and 2/2 on page 2, with mean
IoU 0.298727 and 0.074037 respectively. Page 1's same-kind matcher reports 2/3
reading-order pairs because the intended title was returned as a paragraph.
These metrics need an annotation-policy qualification: the pre-authored fixture
uses broad region boxes while Qwen returns tight text boxes. For example, the
page-2 reference for “Terms” is `(30,30,250,70)`; independent nonwhite-pixel bounds
are `(30,32,59,40)`, and Qwen returned `(28.8,32,57,41.6)`. The payment text has the
same broad-reference/tight-output mismatch. Low IoU alone therefore does not
establish inaccurate visual localization. The references and original scores
were not rewritten after seeing model output. Define and adjudicate region/glyph
annotation semantics before using geometry thresholds for release judgments.

No field-family usefulness, source-pixel grounding policy, blind holdout, hybrid
ranking comparison, review effort or load target is accepted by this probe.
The model servers returned their model IDs with an empty version field; deployed
artifact revisions are declarations, not returned weight attestations.

## Validation and isolation

The clean synchronized candidate passed **1,623 unit tests**, full Ruff/format/
contract/Bandit/Semgrep/Pyright/Mypy checks, and the five affected executor database
tests against all 43 fresh migrations through 100. The immediately preceding
executor candidate's complete database suite passed 268 tests; browser evidence
remains in the [workbench checkpoint](native-index-workbench-checkpoint.md).

Preflight found and fixed a validation-tool isolation defect before this run:
libpq can use a `dbname` query parameter instead of the URI path. Probe guards now
check the libpq-resolved name and actual connected database before bootstrap or
mutation. The integration runner removes name overrides when generating a test
database and checks the actual connection before migrations. Regression tests
exercise encoded/repeated overrides, mismatched connections and zero forbidden
bootstrap/migration side effects. Earlier canonical runs used constructed URLs
without query overrides; their disposable target evidence is unchanged.

Runtime inventory confirmed the existing Oxcart service and the two owned
Blackbird embedding services, both restricted to PRO 4000 UUID
`GPU-6ec4ee66-142e-34ad-e17d-a131d7153b51`. Blackbird's occupied PRO 6000/Gemma and
Oxcart's 27B configuration were preserved. The protected bundle is
`persisted-index-a23d041/evidence` beneath the owned Oxcart validation root;
the public summary records the private artifact hashes without raw vectors,
credentials, source paths or private corpus data.

## Next gates

Complete all-page retained evidence assets, human field/line-item/metadata authority,
generation-aware publication and read APIs, complete Viewer results, original-source
corpus scoring and concurrent ingestion/retrieval measurements. G2/G3 remain open
and precede Phase 9. This checkpoint establishes real persisted ingestion and query
embedding behavior on the approved hardware; it is not a production deployment.
