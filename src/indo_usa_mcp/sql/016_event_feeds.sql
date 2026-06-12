-- Auto-discovered iCalendar feeds: one row per org website scanned for a calendar link.
-- The event scraper ingests `found` feeds alongside EVENT_ICAL_FEEDS. Idempotent.

CREATE TABLE IF NOT EXISTS event_feed_sources (
    site_url     TEXT        PRIMARY KEY,   -- the org website we scanned
    ics_url      TEXT,                      -- discovered .ics feed (null if none found)
    found        BOOLEAN     NOT NULL DEFAULT false,
    active       BOOLEAN     NOT NULL DEFAULT true,
    last_scanned TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feed_found ON event_feed_sources (found) WHERE found AND active;
