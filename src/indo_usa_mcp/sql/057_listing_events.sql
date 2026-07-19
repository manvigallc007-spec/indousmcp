-- Real per-listing owner analytics: human page views + action taps (call / website / directions),
-- as daily aggregate counts (same shape as `impressions`). Written by a client-side beacon so bots and
-- prefetch don't inflate it. Powers the owner dashboard's views/clicks/calls beyond impressions-only.
CREATE TABLE IF NOT EXISTS listing_events (
    vertical    TEXT   NOT NULL,
    record_id   BIGINT NOT NULL,
    kind        TEXT   NOT NULL,               -- view | call | website | directions
    day         DATE   NOT NULL DEFAULT current_date,
    count       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (vertical, record_id, kind, day)
);
CREATE INDEX IF NOT EXISTS idx_listing_events_lookup ON listing_events (vertical, record_id, day);
