-- Vertical: Indian-American real-estate (desi realtors, brokers & agencies with an Indian-name
-- signal). OSM office=estate_agent + Indian name-match; submission-fed too. Idempotent. Carries
-- the cross-cutting enrichment/linkcheck/lifecycle columns up front.

CREATE TABLE IF NOT EXISTS realestate_raw (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT        NOT NULL,
    source_url  TEXT,
    source_id   TEXT,
    payload     JSONB       NOT NULL,
    scraped_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed   BOOLEAN     NOT NULL DEFAULT false,
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_realestate_raw_unprocessed ON realestate_raw (processed) WHERE NOT processed;
CREATE UNIQUE INDEX IF NOT EXISTS uq_realestate_raw_source ON realestate_raw (source_name, source_id);

CREATE TABLE IF NOT EXISTS realestate (
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
    realestate_type  TEXT,                       -- agent, agency, broker, mortgage
    region_tag       TEXT,                       -- Telugu, Gujarati, Tamil, ...
    festival_specials TEXT,
    description      TEXT,
    tags             TEXT[]      NOT NULL DEFAULT '{}',
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
    rating           REAL,
    rating_count     INT,
    photo_url        TEXT,
    socials          JSONB,
    web_enriched_at  TIMESTAMPTZ,
    link_strikes     INT         NOT NULL DEFAULT 0,
    link_checked_at  TIMESTAMPTZ,
    auto_archived    BOOLEAN     NOT NULL DEFAULT false,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_realestate_geo ON realestate (lat, lng) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_realestate_city ON realestate (city, state) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_realestate_name_trgm ON realestate USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_realestate_tags ON realestate USING gin (tags);

CREATE TABLE IF NOT EXISTS realestate_versions (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    realestate_id   BIGINT      NOT NULL REFERENCES realestate(id) ON DELETE CASCADE,
    version         INT         NOT NULL,
    data            JSONB       NOT NULL,
    change_reason   TEXT,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_realestate_versions ON realestate_versions (realestate_id, version);
