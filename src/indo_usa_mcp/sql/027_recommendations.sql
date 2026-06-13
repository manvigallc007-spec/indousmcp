-- Demand-driven recommendations: the agent turns unanswered searches (miss-log) into
-- structured, reviewable suggestions ("grow X in city Y", "consider a new category Z").
-- Admin approves/dismisses; approved+actionable ones can trigger a scrape. Idempotent.

CREATE TABLE IF NOT EXISTS recommendations (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    signature   TEXT        NOT NULL UNIQUE,   -- dedupe key (kind|vertical|state|city|query)
    kind        TEXT        NOT NULL,          -- 'coverage' | 'new_topic'
    vertical    TEXT,                          -- mapped vertical (null for new_topic)
    city        TEXT,
    state       TEXT,
    query       TEXT,
    n_misses    INT         NOT NULL DEFAULT 0,
    suggestion  TEXT        NOT NULL,
    action      TEXT,                           -- e.g. 'scrape:dallas:restaurants' when actionable
    status      TEXT        NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'dismissed', 'done')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_recs_pending ON recommendations (status, n_misses DESC)
    WHERE status = 'pending';
