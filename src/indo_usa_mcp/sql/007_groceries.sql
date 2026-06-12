-- Phase 2 vertical: Indian grocery stores (desi groceries / supermarkets). Idempotent.

CREATE TABLE IF NOT EXISTS grocery_raw (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT        NOT NULL,
    source_url  TEXT,
    source_id   TEXT,
    payload     JSONB       NOT NULL,
    scraped_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed   BOOLEAN     NOT NULL DEFAULT false,
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_grocery_raw_unprocessed ON grocery_raw (processed) WHERE NOT processed;
CREATE UNIQUE INDEX IF NOT EXISTS uq_grocery_raw_source ON grocery_raw (source_name, source_id);

CREATE TABLE IF NOT EXISTS groceries (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    natural_key      TEXT        NOT NULL UNIQUE,
    name             TEXT        NOT NULL,
    address_full     TEXT,
    city             TEXT,
    state            TEXT,
    country          TEXT        DEFAULT 'USA',
    lat              DOUBLE PRECISION,
    lng              DOUBLE PRECISION,
    phone            TEXT,
    email            TEXT,
    website          TEXT,
    hours_json       JSONB,
    store_type       TEXT,                       -- supermarket, grocery, convenience
    region_tag       TEXT,                       -- Gujarati, Punjabi, South Indian, ...
    dietary_tags     TEXT[]      NOT NULL DEFAULT '{}',  -- halal, vegetarian
    festival_specials TEXT,
    is_active        BOOLEAN     NOT NULL DEFAULT true,
    is_featured      BOOLEAN     NOT NULL DEFAULT false,
    featured_until   TIMESTAMPTZ,
    is_claimed       BOOLEAN     NOT NULL DEFAULT false,
    source_name      TEXT,
    source_url       TEXT,
    source_id        TEXT,
    last_seen_at     TIMESTAMPTZ,
    confidence_score REAL        NOT NULL DEFAULT 0,
    version          INT         NOT NULL DEFAULT 1,
    embedding        vector(384),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_grocery_geo ON groceries (lat, lng) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_grocery_city ON groceries (city, state) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_grocery_name_trgm ON groceries USING gin (name gin_trgm_ops);

CREATE TABLE IF NOT EXISTS grocery_versions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    grocery_id    BIGINT      NOT NULL REFERENCES groceries(id) ON DELETE CASCADE,
    version       INT         NOT NULL,
    data          JSONB       NOT NULL,
    change_reason TEXT,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_grocery_versions ON grocery_versions (grocery_id, version);
