-- US Census ACS demographics: Asian-Indian population by state & metro (public, aggregated — no
-- PII). Powers the /insights page and tells the agents which metros to prioritize for scraping.
CREATE TABLE IF NOT EXISTS demographics (
    geoid             TEXT PRIMARY KEY,
    level             TEXT NOT NULL,           -- 'state' | 'metro'
    name              TEXT NOT NULL,
    indian_population INTEGER,
    total_population  INTEGER,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_demographics_level_pop
    ON demographics (level, indian_population DESC);
