-- Vertical: Indian apparel & jewelry (sarees, lehengas, ethnic wear, gold jewelers). Idempotent.

CREATE TABLE IF NOT EXISTS apparel_raw (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT        NOT NULL,
    source_url  TEXT,
    source_id   TEXT,
    payload     JSONB       NOT NULL,
    scraped_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed   BOOLEAN     NOT NULL DEFAULT false,
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_apparel_raw_unprocessed ON apparel_raw (processed) WHERE NOT processed;
CREATE UNIQUE INDEX IF NOT EXISTS uq_apparel_raw_source ON apparel_raw (source_name, source_id);

CREATE TABLE IF NOT EXISTS apparel (
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
    store_type       TEXT,                       -- clothing, jewelry, textiles, tailor
    region_tag       TEXT,
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
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_apparel_geo ON apparel (lat, lng) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_apparel_city ON apparel (city, state) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_apparel_name_trgm ON apparel USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_apparel_tags ON apparel USING gin (tags);

CREATE TABLE IF NOT EXISTS apparel_versions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    apparel_id    BIGINT      NOT NULL REFERENCES apparel(id) ON DELETE CASCADE,
    version       INT         NOT NULL,
    data          JSONB       NOT NULL,
    change_reason TEXT,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_apparel_versions ON apparel_versions (apparel_id, version);
