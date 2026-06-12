-- Phase 2 vertical: Indian-American community events (festivals, garba, concerts, puja).
-- Submission-based (not in OSM). Past events are KEPT (date-filtered), not deleted. Idempotent.

-- Raw landing zone (for future iCal/calendar ingestion; unused by manual submission).
CREATE TABLE IF NOT EXISTS event_raw (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT        NOT NULL,
    source_url  TEXT,
    source_id   TEXT,
    payload     JSONB       NOT NULL,
    scraped_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed   BOOLEAN     NOT NULL DEFAULT false,
    processed_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_event_raw_source ON event_raw (source_name, source_id);

CREATE TABLE IF NOT EXISTS events (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    natural_key      TEXT        NOT NULL UNIQUE,
    name             TEXT        NOT NULL,        -- event title
    description      TEXT,
    tags             TEXT[]      NOT NULL DEFAULT '{}',
    category         TEXT,                        -- festival, garba, concert, puja, workshop
    organizer        TEXT,
    venue_name       TEXT,
    start_at         TIMESTAMPTZ,
    end_at           TIMESTAMPTZ,
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
    region_tag       TEXT,
    festival_specials TEXT,
    -- Agent-ingested events await admin approval unless auto-approved by confidence.
    status           TEXT        NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'approved', 'rejected')),
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
CREATE INDEX IF NOT EXISTS idx_event_when ON events (start_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_event_pending ON events (status) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_event_city ON events (city, state) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_event_name_trgm ON events USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_event_tags ON events USING gin (tags);

CREATE TABLE IF NOT EXISTS event_versions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id      BIGINT      NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    version       INT         NOT NULL,
    data          JSONB       NOT NULL,
    change_reason TEXT,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_event_versions ON event_versions (event_id, version);
