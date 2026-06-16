-- First-party (server-side) pageview counts for public HTML pages — works even when a visitor
-- blocks Google Analytics. Daily aggregate (no per-hit rows, no PII): path normalized to its first
-- two segments. Powers the "Site pageviews" panel on the admin Traffic page.
CREATE TABLE IF NOT EXISTS pageviews (
    path  TEXT NOT NULL,
    day   DATE NOT NULL DEFAULT current_date,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (path, day)
);
CREATE INDEX IF NOT EXISTS idx_pageviews_day ON pageviews (day);
