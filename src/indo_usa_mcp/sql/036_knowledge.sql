-- Per-vertical knowledge base for richer, free-form RAG answers (culture/festivals, immigration &
-- tax guides, temple/place details, menus, listings, and web-page text). Documents are chunked +
-- embedded into kb_chunks; retrieval is cosine over pgvector, filtered by vertical. Reuses the
-- existing 384-dim embeddings. Idempotent.

CREATE TABLE IF NOT EXISTS kb_documents (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vertical     TEXT,                       -- NULL = general / cross-vertical knowledge
    source_type  TEXT        NOT NULL,       -- listing | webpage | article | faq | ...
    source_ref   TEXT        NOT NULL,       -- 'restaurants:123' | a URL | an article slug
    title        TEXT,
    url          TEXT,
    lang         TEXT        NOT NULL DEFAULT 'en',
    content      TEXT        NOT NULL,
    content_hash TEXT        NOT NULL,        -- skip re-embed when unchanged
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_kb_documents_ref ON kb_documents (source_type, source_ref);
CREATE INDEX IF NOT EXISTS idx_kb_documents_vertical ON kb_documents (vertical);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id  BIGINT      NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    vertical     TEXT,
    chunk_index  INT         NOT NULL,
    text         TEXT        NOT NULL,
    embedding    vector(384),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_document ON kb_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_vertical ON kb_chunks (vertical) WHERE embedding IS NOT NULL;
