-- Richer Census ACS facts about Indians-from-India in the USA: languages spoken at home (B16001,
-- keyless) + the Selected Population Profile for "Asian Indian alone" (S0201, POPGROUP 013 — income,
-- education, occupation; needs a free Census API key). Long/narrow so new metrics need no migration.
-- All public, aggregated Census estimates — no PII. Powers /insights and feeds Dost's knowledge base.
CREATE TABLE IF NOT EXISTS demographics_facts (
    geoid       TEXT NOT NULL,              -- 'us' | 'state:48' (matches demographics.geoid for states)
    level       TEXT NOT NULL,              -- 'us' | 'state'
    name        TEXT,                       -- e.g. 'United States', 'Texas'
    metric      TEXT NOT NULL,              -- 'median_household_income' | 'lang:hindi' | ...
    value       DOUBLE PRECISION,
    unit        TEXT,                       -- 'usd' | 'percent' | 'years' | 'speakers'
    label       TEXT,                       -- display label, e.g. 'Hindi', 'Median household income'
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (geoid, metric)
);
CREATE INDEX IF NOT EXISTS idx_demographics_facts_metric ON demographics_facts (metric, value DESC);
