-- Event-driven notification outbox. Event hooks (an answer to your question, a reply to your review,
-- a new offer on a place you saved, a new event in a city you follow) enqueue a row here instead of
-- sending inline, so they add zero request latency. NotificationAgent drains unsent rows and delivers
-- via web push (if notify_web) and/or email (if notify_email). `dedupe_key` makes each event idempotent
-- so a periodic scan never sends the same nudge twice.
CREATE TABLE IF NOT EXISTS notifications (
    id         BIGSERIAL PRIMARY KEY,
    email      TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL DEFAULT '',
    url        TEXT NOT NULL DEFAULT '/',
    kind       TEXT NOT NULL,
    dedupe_key TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_notifications_unsent ON notifications (created_at) WHERE sent_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_email ON notifications (email, created_at DESC);
