-- Opt-in subscribers for the weekly Telegram digest (festival countdown + this week's events + new
-- listings in their city). Opt-in via /subscribe, opt-out via /stop -- mirrors the email outreach
-- opt-in/suppression discipline. Idempotent.
CREATE TABLE IF NOT EXISTS telegram_subscribers (
    chat_id     BIGINT PRIMARY KEY,
    city        TEXT,
    state       TEXT,
    lang        TEXT        NOT NULL DEFAULT 'en',
    active      BOOLEAN     NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS telegram_subscribers_active_idx ON telegram_subscribers (active);
