-- Vertical: Indian community services (money transfer/remittance, banks, immigration/visa,
-- travel agents, tax/insurance). Noisier OSM coverage — curate in admin. Idempotent.

CREATE TABLE IF NOT EXISTS service_raw (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT        NOT NULL,
    source_url  TEXT,
    source_id   TEXT,
    payload     JSONB       NOT NULL,
    scraped_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed   BOOLEAN     NOT NULL DEFAULT false,
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_service_raw_unprocessed ON service_raw (processed) WHERE NOT processed;
CREATE UNIQUE INDEX IF NOT EXISTS uq_service_raw_source ON service_raw (source_name, source_id);

CREATE TABLE IF NOT EXISTS services (
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
    service_type     TEXT,                       -- money_transfer, bank, immigration, travel, tax, insurance
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
CREATE INDEX IF NOT EXISTS idx_services_geo ON services (lat, lng) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_services_city ON services (city, state) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_services_name_trgm ON services USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_services_tags ON services USING gin (tags);

CREATE TABLE IF NOT EXISTS service_versions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id    BIGINT      NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    version       INT         NOT NULL,
    data          JSONB       NOT NULL,
    change_reason TEXT,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_service_versions ON service_versions (service_id, version);
