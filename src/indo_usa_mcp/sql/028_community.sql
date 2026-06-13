-- Vertical: Indian community organizations & cultural associations (regional samaj/sangam,
-- cultural centers, Indo-American associations). Their websites also feed the events calendar
-- via the existing iCal feed-discovery. Idempotent. Includes the cross-cutting enrichment/
-- linkcheck/lifecycle columns up front (the column-loop migrations 017/024/025/026 used a
-- fixed table list, so a brand-new table must carry them itself).

CREATE TABLE IF NOT EXISTS community_raw (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT        NOT NULL,
    source_url  TEXT,
    source_id   TEXT,
    payload     JSONB       NOT NULL,
    scraped_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed   BOOLEAN     NOT NULL DEFAULT false,
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_community_raw_unprocessed ON community_raw (processed) WHERE NOT processed;
CREATE UNIQUE INDEX IF NOT EXISTS uq_community_raw_source ON community_raw (source_name, source_id);

CREATE TABLE IF NOT EXISTS community (
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
    org_type         TEXT,                       -- association, cultural_center, student_org, community
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
CREATE INDEX IF NOT EXISTS idx_community_geo ON community (lat, lng) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_community_city ON community (city, state) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_community_name_trgm ON community USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_community_tags ON community USING gin (tags);

CREATE TABLE IF NOT EXISTS community_versions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    community_id  BIGINT      NOT NULL REFERENCES community(id) ON DELETE CASCADE,
    version       INT         NOT NULL,
    data          JSONB       NOT NULL,
    change_reason TEXT,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_community_versions ON community_versions (community_id, version);
