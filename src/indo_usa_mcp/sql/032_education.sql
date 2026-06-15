-- Vertical: Indian-American education & tutoring (heritage/language schools, Bal Vihar, coaching
-- centers, classical-arts & academic tutoring with an Indian signal). OSM schools/educational
-- institutions + Indian/heritage name-match; submission-fed too. Idempotent. Carries the
-- cross-cutting enrichment/linkcheck/lifecycle columns up front.

CREATE TABLE IF NOT EXISTS education_raw (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT        NOT NULL,
    source_url  TEXT,
    source_id   TEXT,
    payload     JSONB       NOT NULL,
    scraped_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed   BOOLEAN     NOT NULL DEFAULT false,
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_education_raw_unprocessed ON education_raw (processed) WHERE NOT processed;
CREATE UNIQUE INDEX IF NOT EXISTS uq_education_raw_source ON education_raw (source_name, source_id);

CREATE TABLE IF NOT EXISTS education (
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
    edu_type         TEXT,                       -- tutoring, language_school, heritage, coaching, school
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
CREATE INDEX IF NOT EXISTS idx_education_geo ON education (lat, lng) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_education_city ON education (city, state) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_education_name_trgm ON education USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_education_tags ON education USING gin (tags);

CREATE TABLE IF NOT EXISTS education_versions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    education_id  BIGINT      NOT NULL REFERENCES education(id) ON DELETE CASCADE,
    version       INT         NOT NULL,
    data          JSONB       NOT NULL,
    change_reason TEXT,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_education_versions ON education_versions (education_id, version);
