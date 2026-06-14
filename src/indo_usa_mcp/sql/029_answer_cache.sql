-- Semantic answer cache (learning layer): serve repeat general-knowledge chat answers (the
-- web-fallback path) locally instead of calling the external LLM again. General info only — we
-- never cache per-listing results that would go stale. A near-duplicate question (by embedding
-- cosine) reuses the stored reply.
CREATE TABLE IF NOT EXISTS answer_cache (
    id           BIGSERIAL PRIMARY KEY,
    query_norm   TEXT UNIQUE NOT NULL,
    query        TEXT NOT NULL,
    embedding    vector(384),
    reply        TEXT NOT NULL,
    provider     TEXT NOT NULL DEFAULT 'web',
    hits         INTEGER NOT NULL DEFAULT 1,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
