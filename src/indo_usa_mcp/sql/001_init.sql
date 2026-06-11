-- Indian-American Diaspora MCP — Phase 1 (restaurants) schema.
-- Idempotent: safe to run repeatedly via `cli init-db`.

CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector, for future embedding search
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- trigram index for text search

-- ---------------------------------------------------------------------------
-- Raw landing zone: exactly what a scraper saw, untouched. One row per source
-- observation. Cleaning reads from here and never mutates it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS restaurant_raw (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT        NOT NULL,
    source_url  TEXT,
    source_id   TEXT,                 -- external id within the source (e.g. OSM node id)
    payload     JSONB       NOT NULL, -- raw scraped fields
    scraped_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed   BOOLEAN     NOT NULL DEFAULT false,
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_raw_unprocessed ON restaurant_raw (processed) WHERE NOT processed;
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_source ON restaurant_raw (source_name, source_id);

-- ---------------------------------------------------------------------------
-- Canonical, LLM-friendly restaurant records. Soft-deleted via deleted_at.
-- natural_key is a normalized fingerprint used for deduplication.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS restaurants (
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
    website          TEXT,
    menu_url         TEXT,
    hours_json       JSONB,
    cuisine_type     TEXT,
    region_tag       TEXT,                       -- Gujarati, Punjabi, Telugu, ...
    dietary_tags     TEXT[]      NOT NULL DEFAULT '{}',  -- veg, vegan, halal, jain
    price_range      TEXT,
    delivery_partners TEXT[]     NOT NULL DEFAULT '{}',
    festival_specials TEXT,
    is_active        BOOLEAN     NOT NULL DEFAULT true,
    is_featured      BOOLEAN     NOT NULL DEFAULT false,   -- monetization: explicit & visible
    is_claimed       BOOLEAN     NOT NULL DEFAULT false,
    source_name      TEXT,
    source_url       TEXT,
    source_id        TEXT,
    last_seen_at     TIMESTAMPTZ,
    confidence_score REAL        NOT NULL DEFAULT 0,
    version          INT         NOT NULL DEFAULT 1,
    embedding        vector(384),                -- optional, populated later
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ                 -- soft delete
);
CREATE INDEX IF NOT EXISTS idx_rest_geo ON restaurants (lat, lng) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_rest_city ON restaurants (city, state) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_rest_name_trgm ON restaurants USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_rest_featured ON restaurants (is_featured) WHERE deleted_at IS NULL;

-- ---------------------------------------------------------------------------
-- Full version history. Every canonical write snapshots the new state here.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS restaurant_versions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    restaurant_id BIGINT      NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    version       INT         NOT NULL,
    data          JSONB       NOT NULL,
    change_reason TEXT,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_versions_restaurant ON restaurant_versions (restaurant_id, version);

-- ---------------------------------------------------------------------------
-- Human-in-the-loop approval queue. High-risk changes land here; a person
-- approves/rejects. Low-risk inserts may be auto-applied (see pipeline config).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS approval_queue (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    restaurant_id BIGINT      REFERENCES restaurants(id) ON DELETE CASCADE,
    raw_id        BIGINT      REFERENCES restaurant_raw(id) ON DELETE SET NULL,
    change_type   TEXT        NOT NULL CHECK (change_type IN ('insert', 'update')),
    natural_key   TEXT        NOT NULL,
    proposed      JSONB       NOT NULL,    -- the candidate canonical record
    diff          JSONB,                   -- field-level diff for updates
    risk          TEXT        NOT NULL DEFAULT 'low' CHECK (risk IN ('low', 'high')),
    confidence    REAL        NOT NULL DEFAULT 0,
    status        TEXT        NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at   TIMESTAMPTZ,
    reviewed_by   TEXT
);
CREATE INDEX IF NOT EXISTS idx_approval_pending ON approval_queue (status) WHERE status = 'pending';
