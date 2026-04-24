SET search_path TO structura, public;

-- Example 1: lexical chunk search
SELECT
  c.id,
  c.document_id,
  pdb.score(c.id) AS bm25_score,
  pdb.snippet(c.text_content) AS snippet
FROM document_chunks c
WHERE c.text_content ||| 'MRI insurance paid part'
ORDER BY bm25_score DESC
LIMIT 20;

-- Example 2: semantic search against 1536-dim text embeddings
-- Replace :query_embedding with a real vector literal or parameter.
-- SELECT
--   e.owner_id AS chunk_id,
--   e.document_id,
--   e.embedding::vector(1536) <=> :query_embedding::vector(1536) AS distance
-- FROM embeddings e
-- WHERE e.modality = 'text'
--   AND e.embedding_dimensions = 1536
-- ORDER BY e.embedding::vector(1536) <=> :query_embedding::vector(1536)
-- LIMIT 20;

-- Example 3: hybrid RRF fusion
-- Replace the commented semantic query above with a real parameterized query.
WITH bm25 AS (
  SELECT
    c.id AS chunk_id,
    c.document_id,
    RANK() OVER (ORDER BY pdb.score(c.id) DESC) AS rank_value
  FROM document_chunks c
  WHERE c.text_content ||| 'MRI insurance paid part'
  ORDER BY pdb.score(c.id) DESC
  LIMIT 20
),
semantic AS (
  SELECT
    NULL::uuid AS chunk_id,
    NULL::uuid AS document_id,
    NULL::integer AS rank_value
  WHERE false
),
rrf AS (
  SELECT document_id, rrf_score(rank_value, 60) * 1.0 AS score FROM bm25
  UNION ALL
  SELECT document_id, rrf_score(rank_value, 60) * 0.7 AS score FROM semantic
)
SELECT
  d.id,
  d.title,
  d.document_family,
  SUM(rrf.score) AS hybrid_score
FROM rrf
JOIN documents d ON d.id = rrf.document_id
GROUP BY d.id, d.title, d.document_family
ORDER BY hybrid_score DESC
LIMIT 10;

-- Example 4: document-level lexical search with metadata filter hints
SELECT
  d.id,
  d.title,
  d.document_family,
  d.document_date,
  pdb.score(d.id) AS bm25_score
FROM documents d
WHERE d.title ||| 'warranty return'
ORDER BY bm25_score DESC, d.document_date DESC NULLS LAST
LIMIT 10;

-- Example 5: review queue
SELECT * FROM open_review_queue_v LIMIT 50;

-- Example 6: upcoming deadlines
SELECT
  d.id,
  d.title,
  dd.deadline_type,
  dd.due_on
FROM document_deadlines dd
JOIN documents d ON d.id = dd.document_id
WHERE dd.due_on BETWEEN current_date AND current_date + interval '30 days'
ORDER BY dd.due_on ASC;
