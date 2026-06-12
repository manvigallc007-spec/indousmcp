-- Phase 2 vertical: Temples (Hindu/Sikh/Jain places of worship). Idempotent.
-- Independent table, shares the same pipeline/agent/MCP architecture as restaurants.

CREATE TABLE IF NOT EXISTS temple_raw (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT        NOT NULL,
    source_url  TEXT,
    source_id   TEXT,
    payload     JSONB       NOT NULL,
    scraped_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed   BOOLEAN     NOT NULL DEFAULT false,
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_temple_raw_unprocessed ON temple_raw (processed) WHERE NOT processed;
CREATE UNIQUE INDEX IF NOT EXISTS uq_temple_raw_source ON temple_raw (source_name, source_id);

CREATE TABLE IF NOT EXISTS temples (
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
    religion         TEXT,                       -- hindu, sikh, jain
    denomination     TEXT,                       -- e.g. swaminarayan, vaishnavite
    deity            TEXT,                       -- primary deity, when inferable
    region_tag       TEXT,                       -- Punjabi (Sikh), Gujarati (Swaminarayan), ...
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
CREATE INDEX IF NOT EXISTS idx_temple_geo ON temples (lat, lng) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_temple_city ON temples (city, state) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_temple_religion ON temples (religion) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_temple_name_trgm ON temples USING gin (name gin_trgm_ops);

CREATE TABLE IF NOT EXISTS temple_versions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    temple_id     BIGINT      NOT NULL REFERENCES temples(id) ON DELETE CASCADE,
    version       INT         NOT NULL,
    data          JSONB       NOT NULL,
    change_reason TEXT,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_temple_versions ON temple_versions (temple_id, version);
