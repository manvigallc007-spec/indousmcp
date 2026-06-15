-- Vertical: Indian-American immigration & legal services (immigration attorneys, law firms with
-- an Indian-name/diaspora signal). OSM office=lawyer + Indian name-match; submission-fed too.
-- Idempotent. Carries the cross-cutting enrichment/linkcheck/lifecycle columns up front (the
-- column-loop migrations 017/024/025/026 used a fixed table list, so a new table carries them).

CREATE TABLE IF NOT EXISTS legal_raw (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT        NOT NULL,
    source_url  TEXT,
    source_id   TEXT,
    payload     JSONB       NOT NULL,
    scraped_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed   BOOLEAN     NOT NULL DEFAULT false,
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_legal_raw_unprocessed ON legal_raw (processed) WHERE NOT processed;
CREATE UNIQUE INDEX IF NOT EXISTS uq_legal_raw_source ON legal_raw (source_name, source_id);

CREATE TABLE IF NOT EXISTS legal (
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
    legal_type       TEXT,                       -- immigration, attorney, law_firm
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
CREATE INDEX IF NOT EXISTS idx_legal_geo ON legal (lat, lng) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_legal_city ON legal (city, state) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_legal_name_trgm ON legal USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_legal_tags ON legal USING gin (tags);

CREATE TABLE IF NOT EXISTS legal_versions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    legal_id      BIGINT      NOT NULL REFERENCES legal(id) ON DELETE CASCADE,
    version       INT         NOT NULL,
    data          JSONB       NOT NULL,
    change_reason TEXT,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_legal_versions ON legal_versions (legal_id, version);
