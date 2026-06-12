-- Per-listing impressions: how often each record is surfaced to AI agents.
-- Daily buckets give per-record totals + trends. Idempotent.

CREATE TABLE IF NOT EXISTS impressions (
    vertical   TEXT  NOT NULL,
    record_id  BIGINT NOT NULL,
    day        DATE  NOT NULL DEFAULT current_date,
    count      INT   NOT NULL DEFAULT 0,
    PRIMARY KEY (vertical, record_id, day)
);
CREATE INDEX IF NOT EXISTS idx_impressions_record ON impressions (vertical, record_id);
