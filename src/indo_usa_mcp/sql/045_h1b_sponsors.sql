-- H-1B sponsors as a searchable directory (built from the free DOL LCA disclosure file). H-1B is
-- the visa most Indians-from-India use to work in the USA, so "who sponsors / hires" is high-value.
-- Aggregated public figures only, no PII. Populated by labor.import_disclosure (CLI: h1b-import).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS h1b_sponsors (
    id            SERIAL PRIMARY KEY,
    employer      TEXT        UNIQUE NOT NULL,   -- normalized upper-case employer name
    display_name  TEXT,                          -- title-cased for display
    certified     INTEGER     NOT NULL DEFAULT 0,-- # certified H-1B labor condition applications
    median_wage   INTEGER,                        -- approx. median offered annual wage (USD)
    top_titles    TEXT[],                         -- most common job titles
    top_states    TEXT[],                         -- most common worksite states
    top_cities    TEXT[],
    fiscal_year   TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS h1b_sponsors_certified_idx ON h1b_sponsors (certified DESC);
CREATE INDEX IF NOT EXISTS h1b_sponsors_employer_trgm ON h1b_sponsors USING gin (employer gin_trgm_ops);
