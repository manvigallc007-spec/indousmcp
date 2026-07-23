-- Aggregated India/NRI news headlines shown on the homepage portal + /news. We store only the
-- headline, source, link and timestamp (never the article body) and always link out to the source —
-- standard news-aggregator behaviour. Rows are pulled from the free Google News RSS feeds by NewsAgent
-- and de-duplicated on the canonical URL. Old rows are pruned by the agent so the table stays small.
CREATE TABLE IF NOT EXISTS news_articles (
    id           BIGSERIAL PRIMARY KEY,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL UNIQUE,
    source       TEXT,
    category     TEXT NOT NULL DEFAULT 'general',   -- which curated query surfaced it
    published_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_articles (published_at DESC NULLS LAST, created_at DESC);
