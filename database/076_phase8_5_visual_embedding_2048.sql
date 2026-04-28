SET search_path TO structura, public;

CREATE INDEX IF NOT EXISTS embeddings_visual_2048_hnsw_idx
  ON embeddings
  USING hnsw ((embedding::vector(2048)) vector_cosine_ops)
  WHERE is_active
    AND modality = 'visual'
    AND embedding_dimensions = 2048;
